# Generate mock data for any module (run this standalone)
# File: data/generate_mock.py

import pandas as pd
import numpy as np
import os
os.makedirs('data/sample', exist_ok=True)

# Mock patients
patients = pd.DataFrame({
    'patient_id': [f'PAT{str(i).zfill(4)}' for i in range(1, 21)],
    'age': np.random.randint(25, 85, 20),
    'gender': np.random.choice(['M', 'F'], 20),
    'ward': np.random.choice(['ICU', 'Cardiology', 'General', 'Emergency'], 20),
    'diabetes': np.random.choice([True, False], 20, p=[0.3, 0.7]),
    'hypertension': np.random.choice([True, False], 20, p=[0.4, 0.6]),
    'smoking': np.random.choice([True, False], 20, p=[0.25, 0.75]),
    'bmi': np.round(np.random.normal(27, 5, 20), 1)
})
patients.to_csv('data/sample/patients.csv', index=False)

# Mock risk scores
risk = pd.DataFrame({
    'patient_id': patients['patient_id'],
    'risk_score': np.random.uniform(0.1, 0.9, 20),
    'risk_level': np.random.choice(['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'], 20, p=[0.4, 0.3, 0.2, 0.1])
})
risk.to_csv('data/sample/risk_scores.csv', index=False)
print("✅ Mock data generated at data/sample/")
