"""
governance/audit_log.py
Reads and reports the ETL audit log from the database.
Owner: Adel Assem Mohamed

Run: python governance/audit_log.py
"""

import os
import sys
import json
import logging
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()
log = logging.getLogger('governance.audit')
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(message)s')


def get_audit_summary(engine, limit: int = 50) -> pd.DataFrame:
    """Return the most recent ETL run records."""
    q = text("""
        SELECT
            pipeline_name,
            status,
            records_read,
            records_loaded,
            records_failed,
            ROUND(duration_ms / 1000.0, 2) AS duration_sec,
            run_at,
            error_message
        FROM etl_audit_log
        ORDER BY run_at DESC
        LIMIT :lim
    """)
    with engine.connect() as conn:
        return pd.read_sql(q, conn, params={'lim': limit})


def get_success_rate(engine) -> float:
    """Calculate overall ETL success rate."""
    q = text("""
        SELECT
            COUNT(*) FILTER (WHERE status = 'SUCCESS') AS successes,
            COUNT(*)                                    AS total
        FROM etl_audit_log
    """)
    with engine.connect() as conn:
        row = conn.execute(q).fetchone()
    if not row or row[1] == 0:
        return 0.0
    return row[0] / row[1]


def print_audit_report(engine):
    df = get_audit_summary(engine)
    rate = get_success_rate(engine)

    print("=" * 65)
    print(f"ETL AUDIT LOG — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Overall Success Rate: {rate:.1%}")
    print("=" * 65)

    if df.empty:
        print("No ETL runs recorded yet. Run: python etl/pipeline.py")
        return

    for _, row in df.iterrows():
        icon = "✅" if row['status'] == 'SUCCESS' else "❌"
        print(
            f"{icon} [{str(row['run_at'])[:19]}] {row['pipeline_name']:30} | "
            f"Read:{row['records_read']:>6}  Loaded:{row['records_loaded']:>6}  "
            f"Failed:{row['records_failed']:>4}  Time:{row['duration_sec']:>7}s"
        )
        if pd.notnull(row['error_message']) and row['error_message']:
            print(f"     ⚠️  Error: {row['error_message'][:100]}")

    print("=" * 65)


# Replace the __main__ block at the bottom:
if __name__ == '__main__':
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        log.critical("DATABASE_URL not set in .env")
        sys.exit(1)
    engine = create_engine(db_url)
    print_audit_report(engine)
