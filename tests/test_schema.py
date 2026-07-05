"""tests/test_schema.py — Schema integrity tests. Owner: Adel Assem"""
import pytest
import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()


@pytest.fixture(scope='module')
def engine():
    url = os.getenv('DATABASE_URL')
    if not url:
        pytest.skip("DATABASE_URL not set — skipping DB tests")
    return create_engine(url)


def test_tables_exist(engine):
    with engine.connect() as conn:
        existing = conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname='public'"
        )).scalars().all()
    for t in ['patients', 'vital_signs', 'alerts', 'risk_scores', 'etl_audit_log']:
        assert t in existing, f"Table '{t}' missing"


def test_views_exist(engine):
    with engine.connect() as conn:
        existing = conn.execute(text(
            "SELECT viewname FROM pg_views WHERE schemaname='public'"
        )).scalars().all()
    for v in ['v_patient_latest_vitals', 'v_active_alerts_with_patient', 'v_risk_summary']:
        assert v in existing, f"View '{v}' missing"


def test_patients_not_empty(engine):
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM patients")).scalar()
    assert count > 0, "patients table is empty — run ETL first"


def test_vitals_referential_integrity(engine):
    with engine.connect() as conn:
        orphans = conn.execute(text("""
            SELECT COUNT(*) FROM vital_signs v
            LEFT JOIN patients p ON v.patient_id=p.patient_id
            WHERE p.patient_id IS NULL
        """)).scalar()
    assert orphans == 0, f"{orphans} vitals have no matching patient"


def test_spo2_range(engine):
    with engine.connect() as conn:
        bad = conn.execute(text(
            "SELECT COUNT(*) FROM vital_signs WHERE oxygen_saturation NOT BETWEEN 0 AND 100"
        )).scalar()
    assert bad == 0, f"{bad} SpO2 readings outside valid range"


def test_risk_scores_exist(engine):
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM risk_scores")).scalar()
    assert count > 0, "risk_scores empty — run ml/predict.py"
