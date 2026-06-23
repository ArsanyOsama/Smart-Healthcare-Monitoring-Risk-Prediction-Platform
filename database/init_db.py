"""
Initialize the healthcare database.
Run once: python database/init_db.py
Owner: Arsany Osama
"""

import os
import sys
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from dotenv import load_dotenv
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s — %(message)s')
log = logging.getLogger(__name__)

load_dotenv()

DB_CONFIG = {
    'host':     os.getenv('DB_HOST', 'localhost'),
    'port':     int(os.getenv('DB_PORT', 5432)),
    'dbname':   os.getenv('DB_NAME', 'healthcare_db'),
    'user':     os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'password')
}


def create_database_if_not_exists():
    """Create the database if it doesn't already exist."""
    conn = psycopg2.connect(
        host=DB_CONFIG['host'], port=DB_CONFIG['port'],
        user=DB_CONFIG['user'], password=DB_CONFIG['password'],
        dbname='postgres'  # connect to default DB first
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()

    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s",
                (DB_CONFIG['dbname'],))
    if not cur.fetchone():
        cur.execute(f"CREATE DATABASE {DB_CONFIG['dbname']}")
        log.info(f"✅ Created database: {DB_CONFIG['dbname']}")
    else:
        log.info(f"ℹ️  Database already exists: {DB_CONFIG['dbname']}")

    cur.close()
    conn.close()


def run_sql_file(filepath: str):
    """Execute a SQL file against the database."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    with open(filepath, 'r') as f:
        sql = f.read()
    try:
        cur.execute(sql)
        conn.commit()
        log.info(f"✅ Executed: {filepath}")
    except Exception as e:
        conn.rollback()
        log.error(f"❌ Failed {filepath}: {e}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == '__main__':
    log.info("🏥 Initializing Healthcare Database...")
    try:
        create_database_if_not_exists()
        run_sql_file('database/schema_operational.sql')
        run_sql_file('database/schema_analytical.sql')
        log.info("🎉 Database initialization complete!")
    except Exception as e:
        log.critical(f"Database init failed: {e}")
        sys.exit(1)
