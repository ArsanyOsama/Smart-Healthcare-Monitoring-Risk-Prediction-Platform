"""
governance/drift_detection.py
Detects statistical drift in incoming vital sign data vs established baselines.
Run: python governance/drift_detection.py
"""
import os
import sys
import logging
import typing
import numpy as np
import pandas as pd
from scipy import stats
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger('governance.drift')

# Population baseline stats (update after first full ETL run)
BASELINES = {
    'heart_rate':        {'mean': 80.0, 'std': 14.0},
    'bp_systolic':       {'mean': 126.0, 'std': 20.0},
    'oxygen_saturation': {'mean': 97.0, 'std': 2.0},
    'respiratory_rate':  {'mean': 17.0, 'std': 3.5},
    'temperature':       {'mean': 36.8, 'std': 0.5},
}


def detect_drift(engine, window_hours: int = 1) -> dict:
    vitals_cols = ', '.join(BASELINES.keys())
    with engine.connect() as conn:
        df = pd.read_sql(text(f"""
            SELECT {vitals_cols}
            FROM vital_signs
            WHERE timestamp >= NOW() - INTERVAL '{window_hours} hours'
        """), conn)

    if len(df) < 30:
        log.warning(f"Only {len(df)} rows in window — need ≥30 for drift test")
        return {}

    results = {}
    for col, baseline in BASELINES.items():
        if col not in df.columns:
            continue

        synthetic = np.random.normal(baseline['mean'], baseline['std'], 500)
        actual = df[col].dropna().to_numpy(dtype=float)

        # Tag as typing.Any to disable Pylance's strict checking on SciPy's incomplete stubs
        ks_result: typing.Any = stats.ks_2samp(synthetic, actual)

        # Now we can safely use the attributes and cast them
        ks = float(ks_result.statistic)
        p = float(ks_result.pvalue)
        drifted = bool(p < 0.05)

        results[col] = {
            'ks': round(ks, 4), 'p_value': round(p, 4),
            'drifted': drifted,
            'current_mean': round(float(actual.mean()), 2),
            'baseline_mean': baseline['mean'],
        }
        log.log(logging.WARNING if drifted else logging.INFO,
                f"{'⚠️  DRIFT' if drifted else '✅ STABLE'} {col}: "
                f"mean={actual.mean():.1f} | KS={ks:.3f} p={p:.3f}")
    return results


if __name__ == '__main__':
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        log.critical("DATABASE_URL not set in .env")
        sys.exit(1)
    engine = create_engine(db_url)
    drifted = [k for k, v in detect_drift(engine).items() if v.get('drifted')]
    if drifted:
        log.warning(f"Drift in: {drifted}")
    else:
        log.info("✅ No drift detected")
