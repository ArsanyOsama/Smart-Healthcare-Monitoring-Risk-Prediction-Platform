"""
Transform module — validates, cleans, and enriches raw extracted data.
Owner: Arsany Osama
"""

import pandas as pd
import numpy as np
from etl.logging_config import get_logger

log = get_logger('etl.transform')

VITAL_RANGES = {
    'heart_rate':          (20, 300),
    'bp_systolic':         (50, 280),
    'bp_diastolic':        (30, 180),
    'temperature':         (28, 45),
    'oxygen_saturation':   (0, 100),
    'respiratory_rate':    (4, 80),
}

AGE_GROUP_BINS = [0, 30, 45, 60, 75, 130]
AGE_GROUP_LABELS = ['18-30', '31-45', '46-60', '61-75', '76+']


def transform_patients(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Validate and enrich patient records."""
    initial = len(df)
    issues = {}

    # Drop rows with missing required fields
    required = ['patient_id', 'full_name', 'age', 'gender']
    before = len(df)
    df = df.dropna(subset=required)
    if len(df) < before:
        issues['missing_required'] = before - len(df)

    # Type coercion
    df['age'] = pd.to_numeric(df['age'], errors='coerce')
    df['bmi'] = pd.to_numeric(df['bmi'], errors='coerce')
    df['diabetes'] = df['diabetes'].astype(bool)
    df['hypertension'] = df['hypertension'].astype(bool)
    df['smoking'] = df['smoking'].astype(bool)

    # Age bounds check
    invalid_age = (df['age'] < 0) | (df['age'] > 120)
    if invalid_age.any():
        issues['invalid_age'] = int(invalid_age.sum())
        df = df[~invalid_age]

    # Derived fields
    df['age_group'] = pd.cut(
        df['age'], bins=AGE_GROUP_BINS, labels=AGE_GROUP_LABELS)
    df['comorbidity_count'] = df[['diabetes',
                                  'hypertension', 'smoking']].astype(int).sum(axis=1)

    # Normalise gender
    df['gender'] = df['gender'].astype(str).str.upper().str.strip().str[0]
    df.loc[~df['gender'].isin(['M', 'F']), 'gender'] = 'M'

    issues['records_in'] = initial
    issues['records_out'] = len(df)
    issues['dropped'] = initial - len(df)

    log.info(f"✅ Patients transform: {initial} → {len(df)} | Issues: {issues}")
    return df, issues


def transform_vitals(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Validate vital signs, clip outliers, derive MAP."""
    initial = len(df)
    issues = {}

    df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
    df = df.dropna(subset=['patient_id', 'timestamp'])

    clipped = 0
    for col, (lo, hi) in VITAL_RANGES.items():
        if col in df.columns:
            before_clip = ((df[col] < lo) | (df[col] > hi)).sum()
            df[col] = df[col].clip(lower=lo, upper=hi)
            clipped += before_clip

    if clipped:
        issues['clipped_outliers'] = int(clipped)
        log.warning(f"⚠️  Clipped {clipped} out-of-range vital values")

    # Derive Mean Arterial Pressure
    df['mean_arterial_pressure'] = (
        (df['bp_systolic'] + 2 * df['bp_diastolic']) / 3).round(1)

    # Sort for time-series consistency
    df = df.sort_values(['patient_id', 'timestamp']).reset_index(drop=True)

    issues['records_in'] = initial
    issues['records_out'] = len(df)
    log.info(f"✅ Vitals transform: {initial:,} → {len(df):,}")
    return df, issues
