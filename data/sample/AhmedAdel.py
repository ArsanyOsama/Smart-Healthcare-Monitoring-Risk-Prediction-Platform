# File: data/generate_mock.py

import pandas as pd
import numpy as np
import os

os.makedirs('data/sample', exist_ok=True)

# حجم الداتا
N = 50000  # تقدر تزودها (100K - 1M)

# ---------------------------
# Generate Patients Data
# ---------------------------
patients = pd.DataFrame({
    'patient_id': [f'PAT{str(i).zfill(6)}' for i in range(1, N+1)],
    'age': np.random.randint(25, 85, N),
    'gender': np.random.choice(['M', 'F'], N),
    'ward': np.random.choice(['ICU', 'Cardiology', 'General', 'Emergency'], N),
    'diabetes': np.random.choice([1, 0], N, p=[0.3, 0.7]),
    'hypertension': np.random.choice([1, 0], N, p=[0.4, 0.6]),
    'smoking': np.random.choice([1, 0], N, p=[0.25, 0.75]),
    'bmi': np.round(np.random.normal(27, 5, N), 1)
})

# تنظيف بسيط للـ BMI (عشان realism)
patients['bmi'] = patients['bmi'].clip(15, 45)

# ---------------------------
# Generate Risk Score (Realistic)
# ---------------------------
risk_score = (
    0.35 * (patients['age'] / 100) +           # السن
    0.20 * patients['diabetes'] +              # سكر
    0.20 * patients['hypertension'] +          # ضغط
    0.15 * patients['smoking'] +               # تدخين
    0.10 * (patients['bmi'] / 40)              # BMI
)

# إضافة noise بسيط عشان مايبقاش perfect
noise = np.random.normal(0, 0.05, N)
risk_score = risk_score + noise

# Clip بين 0 و 1
risk_score = np.clip(risk_score, 0, 1)

# ---------------------------
# Class Imbalance (Realistic Distribution)
# ---------------------------
risk_level = pd.cut(
    risk_score,
    bins=[0, 0.25, 0.5, 0.7, 1],
    labels=['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']
)

# ---------------------------
# Save Data
# ---------------------------
patients.to_csv('data/sample/patients.csv', index=False)

risk = pd.DataFrame({
    'patient_id': patients['patient_id'],
    'risk_score': np.round(risk_score, 3),
    'risk_level': risk_level
})

risk.to_csv('data/sample/risk_scores.csv', index=False)

# ---------------------------
# Print Summary
# ---------------------------
print("✅ Data Generated Successfully!")
print(f"Total Rows: {N}")
print("\nRisk Level Distribution:")
print(risk['risk_level'].value_counts(normalize=True))