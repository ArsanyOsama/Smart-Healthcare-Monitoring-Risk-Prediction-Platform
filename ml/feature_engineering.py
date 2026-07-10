"""
ml/feature_engineering.py
Builds ML feature matrix from the operational database.
Owner: Ahmed Adel Abd ElAziz
"""
import pandas as pd
import numpy as np
from sqlalchemy import text
import logging

log = logging.getLogger('ml.features')

FEATURE_COLS = [
    'age', 'gender_m', 'bmi',
    'diabetes', 'hypertension', 'smoking', 'comorbidity_count', 'age_group_encoded',
    'avg_hr', 'avg_bp_sys', 'avg_bp_dia', 'avg_spo2', 'avg_rr', 'avg_temp',
    'min_spo2', 'max_hr', 'min_bp_sys', 'std_hr', 'std_bp_sys',
    'pulse_pressure', 'shock_index', 'resp_to_hr_ratio',
    'hr_trend', 'bp_trend', 'spo2_trend', 'reading_count',
]


def build_features(engine) -> pd.DataFrame:
    patients_sql = text("""
        SELECT patient_id, age, gender, bmi::float,
               diabetes::int, hypertension::int, smoking::int
        FROM patients WHERE discharge_date IS NULL
    """)

    vitals_sql = text("""
        WITH numbered AS (
            SELECT *,
                ROW_NUMBER() OVER (PARTITION BY patient_id ORDER BY timestamp ASC)  AS rn_asc,
                ROW_NUMBER() OVER (PARTITION BY patient_id ORDER BY timestamp DESC) AS rn_desc
            FROM vital_signs
            WHERE timestamp >= NOW() - INTERVAL '24 hours'
        )
        SELECT
            patient_id,
            AVG(heart_rate)           AS avg_hr,
            AVG(bp_systolic)          AS avg_bp_sys,
            AVG(bp_diastolic)         AS avg_bp_dia,
            AVG(temperature)          AS avg_temp,
            AVG(oxygen_saturation)    AS avg_spo2,
            AVG(respiratory_rate)     AS avg_rr,
            MIN(oxygen_saturation)    AS min_spo2,
            MAX(heart_rate)           AS max_hr,
            MIN(bp_systolic)          AS min_bp_sys,
            STDDEV(heart_rate)        AS std_hr,
            STDDEV(bp_systolic)       AS std_bp_sys,
            COUNT(*)                  AS reading_count,
            AVG(heart_rate)    FILTER (WHERE rn_desc <= 6)
            - AVG(heart_rate)  FILTER (WHERE rn_asc  <= 6) AS hr_trend,
            AVG(bp_systolic)   FILTER (WHERE rn_desc <= 6)
            - AVG(bp_systolic) FILTER (WHERE rn_asc  <= 6) AS bp_trend,
            AVG(oxygen_saturation) FILTER (WHERE rn_desc <= 6)
            - AVG(oxygen_saturation) FILTER (WHERE rn_asc <= 6) AS spo2_trend
        FROM numbered
        GROUP BY patient_id
    """)

    with engine.connect() as conn:
        pat = pd.read_sql(patients_sql, conn)
        vit = pd.read_sql(vitals_sql, conn)

    df = pat.merge(vit, on='patient_id', how='left')
    df['gender_m'] = (df['gender'] == 'M').astype(int)
    df['age_group_encoded'] = pd.cut(df['age'],
                                     bins=[0, 30, 45, 60, 75, 130], labels=[0, 1, 2, 3, 4]).astype(int)
    df['comorbidity_count'] = df['diabetes'] + \
        df['hypertension'] + df['smoking']
    df['pulse_pressure'] = df['avg_bp_sys'] - df['avg_bp_dia']
    df['shock_index'] = df['avg_hr'] / df['avg_bp_sys'].replace(0, np.nan)
    df['resp_to_hr_ratio'] = df['avg_rr'] / df['avg_hr'].replace(0, np.nan)

    DEFAULTS = {
        'avg_hr': 78, 'avg_bp_sys': 125, 'avg_bp_dia': 78, 'avg_spo2': 97,
        'avg_rr': 16, 'avg_temp': 36.8, 'min_spo2': 96, 'max_hr': 90,
        'min_bp_sys': 110, 'std_hr': 8, 'std_bp_sys': 12,
        'hr_trend': 0, 'bp_trend': 0, 'spo2_trend': 0, 'reading_count': 0,
        'pulse_pressure': 47, 'shock_index': 0.63, 'resp_to_hr_ratio': 0.21,
    }
    df = df.fillna(DEFAULTS)

    # --- FIX: Force all features to float so XGBoost doesn't crash ---
    for col in FEATURE_COLS:
        df[col] = df[col].astype(float)
    # -----------------------------------------------------------------

    log.info(
        f"✅ Feature matrix: {len(df)} patients × {len(FEATURE_COLS)} features")
    return df
