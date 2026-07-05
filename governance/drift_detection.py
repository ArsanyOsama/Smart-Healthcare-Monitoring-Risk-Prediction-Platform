"""
Statistical drift detection — monitors if incoming data distribution
shifts from the baseline (training data).
Owner: Adel Assem Mohamed
"""

import os
import json
import logging
import numpy as np
import pandas as pd
from scipy import stats
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger('governance.drift')
VITALS = ['heart_rate', 'bp_systolic',
          'oxygen_saturation', 'respiratory_rate', 'temperature']

BASELINE = {  # Population norms — update after first ETL run
    'heart_rate':        {'mean': 78.0, 'std': 12.0},
    'bp_systolic':       {'mean': 125.0, 'std': 18.0},
    'oxygen_saturation': {'mean': 97.0, 'std': 1.5},
    'respiratory_rate':  {'mean': 16.5, 'std': 2.5},
    'temperature':       {'mean': 36.8, 'std': 0.45},
}


def detect_drift(engine, window_hours: int = 1) -> dict:
    """KS-test between baseline distributions and latest window."""
    results = {}
    with engine.connect() as conn:
        df = pd.read_sql(text(f"""
            SELECT {', '.join(VITALS)}
            FROM vital_signs
            WHERE timestamp >= NOW() - INTERVAL '{window_hours} hours'
        """), conn)

    if len(df) < 30:
        log.warning(f"Not enough data for drift detection ({len(df)} rows)")
        return {}

    for col in VITALS:
        if col not in df.columns or col not in BASELINE:
            continue
        baseline = BASELINE[col]
        # Simulate baseline distribution
        synthetic_baseline = np.random.normal(
            baseline['mean'], baseline['std'], 500)
        actual = df[col].dropna().values

        ks_stat, p_value = stats.ks_2samp(synthetic_baseline, actual)
        drifted = p_value < 0.05

        results[col] = {
            'ks_statistic': round(ks_stat, 4),
            'p_value':      round(p_value, 4),
            'drifted':      drifted,
            'current_mean': round(actual.mean(), 2),
            'current_std':  round(actual.std(), 2),
            'baseline_mean': baseline['mean'],
        }
        status = "⚠️ DRIFT" if drifted else "✅ STABLE"
        log.info(
            f"{status} {col}: current_mean={actual.mean():.1f} | KS={ks_stat:.3f} p={p_value:.3f}")

    return results


if __name__ == '__main__':
    engine = create_engine(os.getenv('DATABASE_URL'))
    drift_results = detect_drift(engine)
    drifted = [k for k, v in drift_results.items() if v['drifted']]
    if drifted:
        log.warning(f"⚠️  Drift detected in: {drifted}")
    else:
        log.info("✅ No significant data drift detected")
