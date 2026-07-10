"""
tests/test_etl.py
ETL pipeline unit tests — runs without a database connection.
Owner: Adel Assem Mohamed
Run: pytest tests/test_etl.py -v
"""
import pytest
import sys
import os
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

try:
    from etl.extract import extract_patients, extract_vitals
    from etl.transform import transform_patients, transform_vitals
    ETL_OK = True
except ImportError as e:
    ETL_OK = False
    IMPORT_ERR = str(e)

pytestmark = pytest.mark.skipif(
    not ETL_OK,
    reason=f"etl package not importable — check etl/__init__.py exists"
)


class TestExtract:
    def test_extract_patients_exact_count(self):
        df = extract_patients(n=100)
        assert len(df) == 100

    def test_extract_patients_required_columns(self):
        df = extract_patients(n=10)
        for col in ['patient_id', 'full_name', 'age', 'gender',
                    'ward', 'diabetes', 'hypertension', 'bmi']:
            assert col in df.columns, f"Missing column: {col}"

    def test_extract_patients_id_format(self):
        df = extract_patients(n=50)
        assert df['patient_id'].str.startswith('PAT').all(), \
            "All patient IDs should start with 'PAT'"

    def test_extract_patients_age_range(self):
        df = extract_patients(n=300)
        assert df['age'].between(0, 120).all(), \
            f"Age out of range: min={df['age'].min()}, max={df['age'].max()}"

    def test_extract_patients_gender_values(self):
        df = extract_patients(n=200)
        assert set(df['gender'].unique()).issubset({'M', 'F'}), \
            f"Unexpected gender values: {df['gender'].unique()}"

    def test_extract_patients_no_duplicate_ids(self):
        df = extract_patients(n=500)
        assert df['patient_id'].nunique() == len(
            df), "Duplicate patient IDs found"

    def test_extract_vitals_total_rows(self):
        patients = extract_patients(n=20)
        vitals = extract_vitals(patients, readings=24)
        assert len(vitals) == 20 * 24, \
            f"Expected {20*24} rows, got {len(vitals)}"

    def test_extract_vitals_all_patients_covered(self):
        patients = extract_patients(n=15)
        vitals = extract_vitals(patients, readings=10)
        assert set(vitals['patient_id'].unique()) == set(
            patients['patient_id'].unique())

    def test_extract_vitals_spo2_valid(self):
        patients = extract_patients(n=50)
        vitals = extract_vitals(patients, readings=5)
        assert vitals['oxygen_saturation'].between(50, 100).all()

    def test_extract_vitals_hr_valid(self):
        patients = extract_patients(n=50)
        vitals = extract_vitals(patients, readings=5)
        assert vitals['heart_rate'].between(20, 300).all()

    def test_extract_vitals_timestamps_increasing(self):
        patients = extract_patients(n=5)
        vitals = extract_vitals(patients, readings=10)
        for pid, grp in vitals.groupby('patient_id'):
            ts = pd.to_datetime(grp['timestamp'])
            assert ts.is_monotonic_increasing or len(ts) == 1, \
                f"Timestamps not increasing for {pid}"


class TestTransform:
    def test_transform_patients_drops_null_ids(self):
        df = extract_patients(n=50)
        df.loc[0, 'patient_id'] = None
        df.loc[1, 'full_name'] = None
        df['patient_id'] = df['patient_id'].astype(object)
        df['full_name'] = df['full_name'].astype(object)
        clean, issues = transform_patients(df)
        assert clean['patient_id'].notna().all()

    def test_transform_patients_gender_normalized(self):
        df = extract_patients(n=100)
        df.loc[0, 'gender'] = 'male'
        df.loc[1, 'gender'] = 'f'
        df.loc[2, 'gender'] = '99'
        clean, _ = transform_patients(df)
        assert set(clean['gender'].unique()).issubset({'M', 'F'})

    def test_transform_patients_age_coercion(self):
        df = extract_patients(n=20)
        # Force column type to object so it safely accepts string text strings
        df['age'] = df['age'].astype(object)
        df.loc[0, 'age'] = 'invalid'
        clean, _ = transform_patients(df)
        assert pd.to_numeric(clean['age'], errors='coerce').notna().all()

    def test_transform_vitals_clips_outliers(self):
        patients = extract_patients(n=10)
        vitals = extract_vitals(patients, readings=5)
        vitals.loc[0, 'heart_rate'] = 999
        vitals.loc[1, 'oxygen_saturation'] = -10
        vitals.loc[2, 'bp_systolic'] = 400
        clean, issues = transform_vitals(vitals)
        assert clean['heart_rate'].max() <= 300
        assert clean['oxygen_saturation'].min() >= 0
        assert clean['bp_systolic'].max() <= 280
        assert issues.get('clipped_outliers', 0) >= 3

    def test_transform_vitals_adds_map_column(self):
        patients = extract_patients(n=10)
        vitals = extract_vitals(patients, readings=5)
        clean, _ = transform_vitals(vitals)
        assert 'mean_arterial_pressure' in clean.columns
        # MAP must be between diastolic and systolic by definition
        assert (clean['mean_arterial_pressure'] >=
                clean['bp_diastolic'] - 1).all()
        assert (clean['mean_arterial_pressure']
                <= clean['bp_systolic'] + 1).all()

    def test_transform_vitals_sorted_by_patient_time(self):
        patients = extract_patients(n=5)
        vitals = extract_vitals(patients, readings=20)
        clean, _ = transform_vitals(vitals)
        for pid, grp in clean.groupby('patient_id'):
            assert pd.to_datetime(grp['timestamp']).is_monotonic_increasing
