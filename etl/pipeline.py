"""
Main ETL orchestrator.
Run: python etl/pipeline.py
Owner: Arsany Osama
"""

import os
import sys
# This MUST be the very first thing before any other imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import time
from dotenv import load_dotenv
from etl.extract import extract_patients, extract_vitals
from etl.transform import transform_patients, transform_vitals
from etl.load import get_engine, load_patients, load_vitals, log_etl_run
from etl.logging_config import get_logger

load_dotenv()
log = get_logger('etl.pipeline')

N_PATIENTS = int(os.getenv('N_PATIENTS', 100))
READINGS = int(os.getenv('READINGS_PER_PATIENT', 48))


def run_pipeline():
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        log.critical("❌ DATABASE_URL not set in .env")
        sys.exit(1)

    engine = get_engine(db_url)
    start = time.time()

    log.info("=" * 60)
    log.info("🏥 SMART HEALTHCARE ETL PIPELINE — STARTING")
    log.info("=" * 60)

    try:
        # ── EXTRACT ──────────────────────────────────────────────
        log.info("[1/3] EXTRACT phase")
        raw_patients = extract_patients(N_PATIENTS)
        raw_vitals = extract_vitals(raw_patients, READINGS)

        records_read = len(raw_patients) + len(raw_vitals)

        # ── TRANSFORM ────────────────────────────────────────────
        log.info("[2/3] TRANSFORM phase")
        clean_patients, p_issues = transform_patients(raw_patients)
        clean_vitals,   v_issues = transform_vitals(raw_vitals)

        # ── LOAD ─────────────────────────────────────────────────
        log.info("[3/3] LOAD phase")
        n_patients_loaded = load_patients(clean_patients, engine)
        n_vitals_loaded = load_vitals(clean_vitals, engine)
        records_loaded = n_patients_loaded + n_vitals_loaded

        duration_ms = int((time.time() - start) * 1000)
        log_etl_run(engine, 'main_pipeline', 'SUCCESS',
                    records_read, records_loaded, duration_ms)

        log.info("=" * 60)
        log.info(f"✅ ETL COMPLETE in {duration_ms}ms")
        log.info(f"   Patients loaded : {n_patients_loaded}")
        log.info(f"   Vitals loaded   : {n_vitals_loaded:,}")
        log.info("=" * 60)

    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        log_etl_run(engine, 'main_pipeline', 'FAILED',
                    0, 0, duration_ms, str(e))
        log.critical(f"❌ ETL FAILED: {e}")
        raise


if __name__ == '__main__':
    run_pipeline()
