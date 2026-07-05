"""
governance/data_quality.py
Runs automated data quality checks against the operational database.
Owner: Adel Assem Mohamed
Run: python governance/data_quality.py
"""
import os
import sys
import logging
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger('governance.quality')

CHECKS = [
    {"name": "No null patient IDs in vitals",
     "query": "SELECT COUNT(*) FROM vital_signs WHERE patient_id IS NULL",
     "expected": 0, "severity": "CRITICAL"},
    {"name": "SpO2 in valid range (0-100)",
     "query": "SELECT COUNT(*) FROM vital_signs WHERE oxygen_saturation NOT BETWEEN 0 AND 100",
     "expected": 0, "severity": "HIGH"},
    {"name": "Heart rate in valid range (20-300)",
     "query": "SELECT COUNT(*) FROM vital_signs WHERE heart_rate NOT BETWEEN 20 AND 300",
     "expected": 0, "severity": "HIGH"},
    {"name": "No duplicate patient IDs",
     "query": "SELECT COUNT(*) - COUNT(DISTINCT patient_id) FROM patients",
     "expected": 0, "severity": "CRITICAL"},
    {"name": "All vitals linked to existing patients",
     "query": "SELECT COUNT(*) FROM vital_signs v LEFT JOIN patients p ON v.patient_id=p.patient_id WHERE p.patient_id IS NULL",
     "expected": 0, "severity": "CRITICAL"},
    {"name": "Patients table not empty",
     "query": "SELECT COUNT(*) FROM patients",
     "expected_min": 1, "severity": "CRITICAL"},
    {"name": "Vitals table not empty",
     "query": "SELECT COUNT(*) FROM vital_signs",
     "expected_min": 1, "severity": "CRITICAL"},
    {"name": "No future timestamps",
     "query": "SELECT COUNT(*) FROM vital_signs WHERE timestamp > NOW() + INTERVAL '1 minute'",
     "expected": 0, "severity": "HIGH"},
    {"name": "Risk scores present",
     "query": "SELECT COUNT(*) FROM risk_scores",
     "expected_min": 1, "severity": "MEDIUM"},
    {"name": "ETL audit log has SUCCESS entries",
     "query": "SELECT COUNT(*) FROM etl_audit_log WHERE status='SUCCESS'",
     "expected_min": 1, "severity": "MEDIUM"},
]


def run_checks(engine) -> dict:
    passed = failed = 0
    results = []
    with engine.connect() as conn:
        for check in CHECKS:
            try:
                val = conn.execute(text(check['query'])).scalar()
                exp = check.get('expected')
                exp_min = check.get('expected_min')
                ok = (val == exp) if exp is not None else (val >= exp_min)
                status = "✅ PASS" if ok else f"❌ FAIL (got {val})"
                if ok:
                    passed += 1
                else:
                    failed += 1
                log.log(logging.INFO if ok else logging.WARNING,
                        f"{status} [{check['severity']}] {check['name']}")
                results.append({**check, 'actual': val, 'passed': ok})
            except Exception as e:
                failed += 1
                log.error(f"❌ ERROR {check['name']}: {e}")

    log.info(
        f"\n{'='*50}\nQA: {passed}/{passed+failed} passed ({passed/(passed+failed):.0%})\n{'='*50}")
    return {'passed': passed, 'failed': failed, 'results': results}


# Replace the __main__ block at the bottom:
if __name__ == '__main__':
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        log.critical("DATABASE_URL not set in .env")
        sys.exit(1)
    engine = create_engine(db_url)
    run_checks(engine)
