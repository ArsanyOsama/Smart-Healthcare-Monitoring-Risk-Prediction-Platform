"""
Automated data quality checks for the operational database.
Owner: Adel Assem Mohamed
Run: python governance/data_quality.py
"""

import os
import logging
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()
log = logging.getLogger('governance.quality')
logging.basicConfig(level=logging.INFO)


QUALITY_CHECKS = [
    {
        "name": "No null patient IDs in vitals",
        "query": "SELECT COUNT(*) FROM vital_signs WHERE patient_id IS NULL",
        "expected": 0,
        "severity": "CRITICAL"
    },
    {
        "name": "SpO2 in valid range (0-100)",
        "query": "SELECT COUNT(*) FROM vital_signs WHERE oxygen_saturation NOT BETWEEN 0 AND 100",
        "expected": 0,
        "severity": "HIGH"
    },
    {
        "name": "Heart rate in valid range (20-300)",
        "query": "SELECT COUNT(*) FROM vital_signs WHERE heart_rate NOT BETWEEN 20 AND 300",
        "expected": 0,
        "severity": "HIGH"
    },
    {
        "name": "No duplicate patient IDs",
        "query": "SELECT COUNT(*) - COUNT(DISTINCT patient_id) FROM patients",
        "expected": 0,
        "severity": "CRITICAL"
    },
    {
        "name": "All vitals linked to existing patients",
        "query": """SELECT COUNT(*) FROM vital_signs v
                    LEFT JOIN patients p ON v.patient_id = p.patient_id
                    WHERE p.patient_id IS NULL""",
        "expected": 0,
        "severity": "CRITICAL"
    },
    {
        "name": "Patients have at least 1 vital reading",
        "query": """SELECT COUNT(*) FROM patients p
                    WHERE p.discharge_date IS NULL
                    AND NOT EXISTS (SELECT 1 FROM vital_signs v WHERE v.patient_id = p.patient_id)""",
        "expected_max": 5,  # Allow up to 5 patients with no readings
        "severity": "MEDIUM"
    },
    {
        "name": "No future timestamps in vitals",
        "query": "SELECT COUNT(*) FROM vital_signs WHERE timestamp > NOW() + INTERVAL '1 minute'",
        "expected": 0,
        "severity": "HIGH"
    },
]


def run_quality_checks(engine) -> dict:
    results = []
    passed = failed = 0

    with engine.connect() as conn:
        for check in QUALITY_CHECKS:
            try:
                count = conn.execute(text(check['query'])).scalar()
                expected = check.get('expected', None)
                expected_max = check.get('expected_max', None)

                if expected is not None:
                    ok = (count == expected)
                elif expected_max is not None:
                    ok = (count <= expected_max)
                else:
                    ok = True

                status = "✅ PASS" if ok else f"❌ FAIL"
                if ok:
                    passed += 1
                else:
                    failed += 1

                log.log(logging.INFO if ok else logging.WARNING,
                        f"{status} [{check['severity']}] {check['name']} — count={count}")

                results.append({**check, 'actual': count,
                               'passed': ok, 'status': status})

            except Exception as e:
                log.error(f"Check failed with error: {check['name']}: {e}")
                results.append(
                    {**check, 'actual': None, 'passed': False, 'status': f"❌ ERROR: {e}"})
                failed += 1

    summary = {
        'run_at': datetime.now().isoformat(),
        'total': passed + failed,
        'passed': passed,
        'failed': failed,
        'pass_rate': passed / (passed + failed) if (passed + failed) > 0 else 0,
        'results': results
    }

    log.info(f"\n{'='*50}")
    log.info(
        f"QA SUMMARY: {passed}/{passed+failed} checks passed ({summary['pass_rate']:.0%})")
    log.info(f"{'='*50}")
    return summary


if __name__ == '__main__':
    engine = create_engine(os.getenv('DATABASE_URL'))
    summary = run_quality_checks(engine)
    if summary['failed'] > 0:
        log.warning(
            f"⚠️  {summary['failed']} checks failed — review data quality")
    else:
        log.info("🎉 All data quality checks passed!")
