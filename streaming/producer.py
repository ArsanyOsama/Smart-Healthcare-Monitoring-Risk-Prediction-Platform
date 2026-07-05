"""
Simulates a real-time patient data stream using Python threading.
Mimics Kafka producer behaviour — no Kafka installation required for MVP.
Owner: Noureldeen Mohamed

Run: python streaming/producer.py
"""

from streaming.alert_engine import AlertEngine
import threading
import queue
import time
import random
import os
import sys
import numpy as np
import argparse
import logging
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

load_dotenv()
log = logging.getLogger('streaming.producer')
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(message)s')


def get_active_patient_ids(engine) -> list[str]:
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT patient_id FROM patients WHERE discharge_date IS NULL LIMIT 50")
        )
        return [row[0] for row in result]


def generate_reading(patient_id: str, t: int = 0) -> dict:
    """Simulate a single vital reading with mild random walk."""
    return {
        'patient_id':       patient_id,
        'timestamp':        datetime.now().isoformat(),
        'heart_rate':       round(max(40, min(180, random.gauss(78, 12) + np.sin(t/20)*4)), 1),
        'bp_systolic':      round(max(75, min(220, random.gauss(125, 18))), 1),
        'bp_diastolic':     round(max(45, min(130, random.gauss(78, 10))), 1),
        'temperature':      round(max(35.0, min(40.5, random.gauss(36.8, 0.4))), 1),
        'oxygen_saturation': round(max(75, min(100, random.gauss(97, 1.5))), 1),
        'respiratory_rate': round(max(8, min(38, random.gauss(16, 2.5))), 1),
    }


def stream_vitals(engine, interval: float = 30.0, dry_run: bool = False):
    alert_engine = AlertEngine(engine)
    patient_ids = get_active_patient_ids(engine)
    log.info(f"🟢 Streaming {len(patient_ids)} patients every {interval}s")
    t = 0

    while True:
        readings = [generate_reading(pid, t) for pid in patient_ids]
        t += 1

        if dry_run:
            log.info(f"[DRY RUN] Would stream {len(readings)} readings")
            for r in readings[:3]:
                log.info(f"  Sample: {r}")
            break

        # Batch insert vitals
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO vital_signs
                    (patient_id,timestamp,heart_rate,bp_systolic,bp_diastolic,
                     temperature,oxygen_saturation,respiratory_rate)
                VALUES
                    (:patient_id,:timestamp,:heart_rate,:bp_systolic,:bp_diastolic,
                     :temperature,:oxygen_saturation,:respiratory_rate)
            """), readings)

        # Check alerts
        total_alerts = sum(alert_engine.check_vitals(r) for r in readings)
        log.info(
            f"✅ Streamed {len(readings)} readings | Alerts triggered: {total_alerts}")

        time.sleep(interval)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--interval', type=float, default=30.0)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    engine = create_engine(os.getenv('DATABASE_URL'))
    stream_vitals(engine, args.interval, args.dry_run)
