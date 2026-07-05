"""
Load module — inserts transformed data into PostgreSQL with batch writes.
Owner: Arsany Osama
"""

import pandas as pd
from sqlalchemy import create_engine, text
from etl.logging_config import get_logger

log = get_logger('etl.load')

BATCH_SIZE = 500


def get_engine(db_url: str):
    return create_engine(db_url, pool_size=5, max_overflow=10, pool_pre_ping=True)


def load_patients(df: pd.DataFrame, engine) -> int:
    # Make blood_type optional — add null default if absent
    df = df.copy()
    if 'blood_type' not in df.columns:
        df['blood_type'] = None

    cols = ['patient_id', 'full_name', 'age', 'gender', 'blood_type',
            'admission_date', 'ward', 'diabetes', 'hypertension', 'smoking', 'bmi']
    df_load = df[cols].copy()
    df_load['diabetes'] = df_load['diabetes'].astype(bool)
    df_load['hypertension'] = df_load['hypertension'].astype(bool)
    df_load['smoking'] = df_load['smoking'].astype(bool)

    inserted = 0
    with engine.begin() as conn:
        for i in range(0, len(df_load), BATCH_SIZE):
            batch = df_load.iloc[i:i + BATCH_SIZE]
            conn.execute(text("""
                INSERT INTO patients
                    (patient_id, full_name, age, gender, blood_type,
                     admission_date, ward, diabetes, hypertension, smoking, bmi)
                VALUES
                    (:patient_id, :full_name, :age, :gender, :blood_type,
                     :admission_date, :ward, :diabetes, :hypertension, :smoking, :bmi)
                ON CONFLICT (patient_id) DO NOTHING
            """), batch.to_dict(orient='records'))
            inserted += len(batch)
            log.debug(f"Patients batch {i // BATCH_SIZE + 1} inserted")
    log.info(f"✅ Loaded {inserted} patient records")
    return inserted


def load_vitals(df: pd.DataFrame, engine) -> int:
    cols = ['patient_id', 'timestamp', 'heart_rate', 'bp_systolic', 'bp_diastolic',
            'temperature', 'oxygen_saturation', 'respiratory_rate']
    df_load = df[cols].copy()
    df_load['timestamp'] = df_load['timestamp'].astype(str)

    inserted = 0
    with engine.begin() as conn:
        for i in range(0, len(df_load), BATCH_SIZE):
            batch = df_load.iloc[i:i + BATCH_SIZE]
            conn.execute(text("""
                INSERT INTO vital_signs
                    (patient_id,timestamp,heart_rate,bp_systolic,bp_diastolic,
                     temperature,oxygen_saturation,respiratory_rate)
                VALUES
                    (:patient_id,:timestamp,:heart_rate,:bp_systolic,:bp_diastolic,
                     :temperature,:oxygen_saturation,:respiratory_rate)
            """), batch.to_dict(orient='records'))
            inserted += len(batch)

    log.info(f"✅ Loaded {inserted:,} vital readings")
    return inserted


def log_etl_run(engine, pipeline: str, status: str,
                records_read: int, records_loaded: int,
                duration_ms: int, error: str | None = None):
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO etl_audit_log
                (pipeline_name, status, records_read, records_loaded, duration_ms, error_message)
            VALUES
                (:pipeline, :status, :r_read, :r_loaded, :dur_ms, :error)
        """), {
            'pipeline': pipeline, 'status': status,
            'r_read': records_read, 'r_loaded': records_loaded,
            'dur_ms': duration_ms, 'error': error
        })
