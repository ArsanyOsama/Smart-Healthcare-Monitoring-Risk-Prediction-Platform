"""
streaming/consumer.py
Polls the vital_signs table for new readings and computes batch statistics.
Simulates a Kafka consumer without requiring Kafka infrastructure.
Owner: Noureldeen Mohamed

Run: python streaming/consumer.py
Stop: Ctrl+C
"""

import os
import sys
import time
import logging
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

load_dotenv()
log = logging.getLogger('streaming.consumer')
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(message)s')

POLL_INTERVAL = int(os.getenv('STREAM_INTERVAL_SECONDS', 30))
LOOKBACK_BUFFER = POLL_INTERVAL + 5   # small overlap to never miss rows


def consume_new_vitals(engine, since: datetime) -> pd.DataFrame:
    """
    Poll vital_signs for rows inserted after `since`.
    In a real Kafka setup this would be consumer.poll().
    """
    q = text("""
        SELECT
            v.reading_id, v.patient_id, v.timestamp,
            v.heart_rate, v.bp_systolic, v.bp_diastolic,
            v.temperature, v.oxygen_saturation, v.respiratory_rate,
            p.ward, p.age
        FROM vital_signs v
        JOIN patients p ON v.patient_id = p.patient_id
        WHERE v.created_at >= :since
        ORDER BY v.created_at ASC
    """)
    with engine.connect() as conn:
        return pd.read_sql(q, conn, params={'since': since.isoformat()})


def compute_batch_stats(df: pd.DataFrame) -> dict:
    """Summarise an incoming batch — would trigger ML re-scoring in production."""
    if df.empty:
        return {'count': 0}

    return {
        'count':            len(df),
        'unique_patients':  df['patient_id'].nunique(),
        'avg_hr':           round(df['heart_rate'].mean(), 1),
        'avg_spo2':         round(df['oxygen_saturation'].mean(), 1),
        'low_spo2_count':   int((df['oxygen_saturation'] < 93).sum()),
        'high_hr_count':    int((df['heart_rate'] > 120).sum()),
        'processed_at':     datetime.now().isoformat(),
    }


def run_consumer(engine, poll_interval: int = POLL_INTERVAL):
    log.info(f"🟢 Consumer started | Polling every {poll_interval}s")
    last_poll = datetime.now() - timedelta(seconds=poll_interval)

    while True:
        try:
            now = datetime.now()
            batch = consume_new_vitals(engine, last_poll)
            stats = compute_batch_stats(batch)

            if stats['count'] > 0:
                log.info(
                    f"📥 Batch received | Readings: {stats['count']} | "
                    f"Patients: {stats['unique_patients']} | "
                    f"Avg HR: {stats['avg_hr']} | "
                    f"Low SpO2 events: {stats['low_spo2_count']}"
                )
                if stats['low_spo2_count'] > 0:
                    log.warning(
                        f"⚠️  {stats['low_spo2_count']} patients with SpO2 < 93% this batch")
            else:
                log.debug("No new readings in this poll window.")

            last_poll = now
            time.sleep(poll_interval)

        except KeyboardInterrupt:
            log.info("🛑 Consumer stopped by user (Ctrl+C).")
            break
        except Exception as e:
            log.error(f"Consumer error: {e} — retrying in {poll_interval}s")
            time.sleep(poll_interval)


if __name__ == '__main__':
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        log.critical("DATABASE_URL not set in .env")
        sys.exit(1)
    engine = create_engine(db_url, pool_pre_ping=True)
    run_consumer(engine)
