"""
Extract module — generates synthetic patient data.
Simulates a hospital data feed using Faker + NumPy.
Owner: Arsany Osama
"""

import pandas as pd
import numpy as np
from faker import Faker
import random
from datetime import datetime, timedelta
from etl.logging_config import get_logger

log = get_logger('etl.extract')
fake = Faker(['en_US'])
random.seed(42)
np.random.seed(42)

WARDS = ['ICU', 'Cardiology', 'General', 'Emergency', 'Neurology']
BLOOD_TYPES = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']


def extract_patients(n: int = 100) -> pd.DataFrame:
    """Generate synthetic patient records that mimic real hospital data."""
    log.info(f"Generating {n} synthetic patient records...")
    records = []

    for i in range(n):
        age = random.randint(22, 88)
        # Age-correlated comorbidity probabilities (more realistic)
        p_hyper = min(0.85, 0.08 + age * 0.005)
        p_diab = min(0.50, 0.04 + age * 0.003)

        records.append({
            'patient_id':       f'PAT{str(i + 1).zfill(4)}',
            'full_name':        fake.name(),
            'age':              age,
            'gender':           random.choice(['M', 'F']),
            'blood_type':       random.choice(BLOOD_TYPES),
            'admission_date':   fake.date_between(start_date='-30d', end_date='today').isoformat(),
            'ward':             random.choice(WARDS),
            'diabetes':         random.random() < p_diab,
            'hypertension':     random.random() < p_hyper,
            'smoking':          random.random() < 0.27,
            'bmi':              round(max(16.0, min(48.0, random.gauss(27.5, 6.0))), 1),
        })

    df = pd.DataFrame(records)
    log.info(f"✅ Extracted {len(df)} patients | "
             f"Diabetic: {df['diabetes'].sum()} | Hypertensive: {df['hypertension'].sum()}")
    return df


def extract_vitals(patients_df: pd.DataFrame, readings: int = 48) -> pd.DataFrame:
    """
    Generate time-series vital signs for all patients.
    48 readings = 24 hours at 30-minute intervals.
    Includes circadian rhythm, clinical deterioration patterns.
    """
    log.info(
        f"Generating {readings} vital readings per patient ({len(patients_df)} patients)...")
    records = []

    for _, p in patients_df.iterrows():
        # Personalised baselines
        base_hr = 72 + (p['age'] - 50) * 0.18 + (5 if p['diabetes'] else 0)
        base_bp_s = 115 + p['age'] * 0.28 + (22 if p['hypertension'] else 0)
        base_spo2 = 98.0 - p['age'] * 0.06 - (1.5 if p['diabetes'] else 0)

        # Patients over 65 with comorbidities may deteriorate
        is_deteriorating = (p['age'] > 65 and
                            (p['diabetes'] or p['hypertension']) and
                            p['ward'] in ['ICU', 'Emergency'])

        for i in range(readings):
            ts = datetime.now() - timedelta(minutes=30 * (readings - i))
            circadian = np.sin(i / 16 * np.pi) * 4.5     # natural variation
            degrade = i * 0.25 if is_deteriorating else 0

            hr = max(38, min(185, base_hr + circadian +
                     random.gauss(0, 5) + degrade))
            bps = max(70, min(225, base_bp_s + circadian *
                      2 + random.gauss(0, 9) + degrade))
            bpd = max(40, min(130, bps * 0.63 + random.gauss(0, 5)))
            spo = max(72, min(100, base_spo2 - degrade *
                      0.08 + random.gauss(0, 1.3)))
            rr = max(8,  min(42,  16 + degrade * 0.08 + random.gauss(0, 2.0)))

            records.append({
                'patient_id':       p['patient_id'],
                'timestamp':        ts.isoformat(),
                'heart_rate':       round(hr, 1),
                'bp_systolic':      round(bps, 1),
                'bp_diastolic':     round(bpd, 1),
                'temperature':      round(max(34.5, min(41.0, 36.7 + random.gauss(0, 0.45))), 1),
                'oxygen_saturation': round(spo, 1),
                'respiratory_rate': round(rr, 1),
            })

    df = pd.DataFrame(records)
    log.info(f"✅ Extracted {len(df):,} vital readings")
    return df
