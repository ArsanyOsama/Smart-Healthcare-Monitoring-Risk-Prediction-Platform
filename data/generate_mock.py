"""
data/generate_mock.py
Generates production-scale mock data for offline development and ML training.

Scale: 1000 patients × 48 readings = 48,000 vital rows
       Sufficient for 5-fold CV, dashboard demo, and meaningful ML metrics.

Owner: Arsany Osama
Run:   python data/generate_mock.py
"""

import pandas as pd
import numpy as np
import os
import random
from datetime import datetime, timedelta

random.seed(42)
np.random.seed(42)

os.makedirs('data/sample', exist_ok=True)

N_PATIENTS = 1000   # minimum for reliable ML — increase to 2000 for better results
N_READINGS = 48     # 24h at 30-min intervals per patient
N_ALERTS_PRE = 200    # pre-seeded alerts so dashboard shows data immediately

WARDS = ['ICU', 'Cardiology', 'General', 'Emergency', 'Neurology']
BLOOD_TYPES = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']

print(f"🏗️  Generating mock data — {N_PATIENTS} patients, "
      f"{N_PATIENTS * N_READINGS:,} vitals...")

# ═══════════════════════════════════════════════════════════════════
# PATIENTS
# ═══════════════════════════════════════════════════════════════════
records = []
for i in range(N_PATIENTS):
    age = random.randint(22, 88)
    diabetes = random.random() < min(0.50, 0.04 + age * 0.003)
    hypert = random.random() < min(0.85, 0.08 + age * 0.005)
    smoking = random.random() < 0.27
    ward = random.choice(WARDS)
    admit_d = (datetime.now() - timedelta(days=random.randint(0, 30))).date()
    discharg = (datetime.now().date() if random.random() < 0.05 else None)

    records.append({
        'patient_id':    f'PAT{str(i + 1).zfill(4)}',
        'full_name':     f'Patient {str(i + 1).zfill(4)}',
        'age':           age,
        'gender':        random.choice(['M', 'F']),
        'blood_type':    random.choice(BLOOD_TYPES),
        'admission_date': admit_d.isoformat(),
        'ward':          ward,
        'diabetes':      diabetes,
        'hypertension':  hypert,
        'smoking':       smoking,
        'bmi':           round(max(16.0, min(48.0, random.gauss(27.5, 6.0))), 1),
        'discharge_date': discharg.isoformat() if discharg else None,
    })

patients = pd.DataFrame(records)
patients.to_csv('data/sample/patients.csv', index=False)

# ═══════════════════════════════════════════════════════════════════
# VITALS (time-series)
# ═══════════════════════════════════════════════════════════════════
active = patients[patients['discharge_date'].isna()].copy()
vitals_rows = []

for _, p in active.iterrows():
    base_hr = 72 + (p['age'] - 50) * 0.18 + (5 if p['diabetes'] else 0)
    base_bps = 115 + p['age'] * 0.28 + (22 if p['hypertension'] else 0)
    base_spo2 = 98.0 - p['age'] * 0.06 - (1.5 if p['diabetes'] else 0)
    is_crit = (p['age'] > 65 and
               (p['diabetes'] or p['hypertension']) and
               p['ward'] in ['ICU', 'Emergency'])

    for i in range(N_READINGS):
        ts = datetime.now() - timedelta(minutes=30 * (N_READINGS - i))
        circ = np.sin(i / 16 * np.pi) * 4.5
        degrade = i * 0.25 if is_crit else 0

        hr = max(38, min(185, base_hr + circ + random.gauss(0, 5) + degrade))
        bps = max(70, min(225, base_bps + circ *
                  2 + random.gauss(0, 9) + degrade))
        bpd = max(40, min(130, bps * 0.63 + random.gauss(0, 5)))
        spo = max(72, min(100, base_spo2 - degrade *
                  0.08 + random.gauss(0, 1.3)))
        rr = max(8,  min(42,  16 + degrade * 0.08 + random.gauss(0, 2.0)))

        vitals_rows.append({
            'patient_id':        p['patient_id'],
            'timestamp':         ts.isoformat(),
            'heart_rate':        round(hr, 1),
            'bp_systolic':       round(bps, 1),
            'bp_diastolic':      round(bpd, 1),
            'temperature':       round(max(34.5, min(41.0, 36.7 + random.gauss(0, 0.45))), 1),
            'oxygen_saturation': round(spo, 1),
            'respiratory_rate':  round(rr, 1),
        })

vitals = pd.DataFrame(vitals_rows)
vitals.to_csv('data/sample/vitals.csv', index=False)

# ═══════════════════════════════════════════════════════════════════
# ALERTS (pre-seeded for dashboard)
# ═══════════════════════════════════════════════════════════════════
PARAMS = ['heart_rate', 'bp_systolic',
          'oxygen_saturation', 'respiratory_rate', 'temperature']
alert_pids = active['patient_id'].sample(
    min(N_ALERTS_PRE, len(active)), random_state=42).tolist()
alert_rows = []

for pid in alert_pids:
    sev = np.random.choice(['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'], p=[
                           0.40, 0.35, 0.18, 0.07])
    atype = random.choice(
        ['HIGH_THRESHOLD', 'LOW_THRESHOLD', 'ANOMALY', 'HIGH_RISK'])
    param = random.choice(PARAMS)
    obs = round(random.uniform(40, 180), 1)
    thr = round(random.uniform(80, 160), 1)
    mins = random.randint(1, 480)

    alert_rows.append({
        'patient_id':      pid,
        'alert_type':      atype,
        'severity':        sev,
        'vital_parameter': param,
        'observed_value':  obs,
        'threshold_value': thr,
        'message':         f"[{sev}] {param.replace('_',' ').title()} = {obs} (threshold {thr})",
        'triggered_at':    (datetime.now() - timedelta(minutes=mins)).isoformat(),
        'is_active':       True,
    })

alerts = pd.DataFrame(alert_rows)
alerts.to_csv('data/sample/alerts.csv', index=False)

# ═══════════════════════════════════════════════════════════════════
# RISK SCORES (pre-computed)
# ═══════════════════════════════════════════════════════════════════
risk_rows = []
for _, p in active.iterrows():
    score = round(float(np.random.beta(2, 5)), 5)
    if score < 0.25:
        level = 'LOW'
    elif score < 0.50:
        level = 'MEDIUM'
    elif score < 0.75:
        level = 'HIGH'
    else:
        level = 'CRITICAL'
    risk_rows.append({
        'patient_id':   p['patient_id'],
        'risk_score':   score,
        'risk_level':   level,
        'model_version': 'v1.0-mock',
        'calculated_at': datetime.now().isoformat(),
    })

risk_scores = pd.DataFrame(risk_rows)
risk_scores.to_csv('data/sample/risk_scores.csv', index=False)

# ═══════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════
hi_risk = (risk_scores['risk_level'].isin(['HIGH', 'CRITICAL'])).sum()
print(f"""
{'='*60}    
✅ MOCK DATA COMPLETE
{'='*60}
  data/sample/patients.csv    → {len(patients):>6,} rows
  data/sample/vitals.csv      → {len(vitals):>6,} rows
  data/sample/alerts.csv      → {len(alerts):>6,} rows
  data/sample/risk_scores.csv → {len(risk_scores):>6,} rows

  ML READINESS CHECK:
  Active patients      : {len(active):,}
  5-fold CV fold size  : {len(active)//5:,} training samples each
  High-risk patients   : {hi_risk} ({hi_risk/len(active):.1%})
  → {'✅ READY for ML training' if len(active) >= 500 else '⚠️  Increase N_PATIENTS'}
{'='*60}
""")
