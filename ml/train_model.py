"""
Train and evaluate the risk classification model.
Run: python ml/train_model.py
Owner: Ahmed Adel Abd ElAziz
"""

import logging
import pickle
from sqlalchemy import create_engine, text
import json
from ml.feature_engineering import build_features, FEATURE_COLS
import os
import sys
import json
import pickle
import logging
import numpy as np
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy import create_engine

from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold, cross_validate
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report
import shap

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

load_dotenv()
log = logging.getLogger('ml.train')
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(message)s')


def generate_risk_labels(df: pd.DataFrame) -> pd.Series:
    """
    Clinical scoring heuristic → binary labels (0=low-medium, 1=high-critical).
    Produces realistic class imbalance (~25% high risk).
    """
    score = np.zeros(len(df))

    # Demographics
    score += np.where(df['age'] > 70, 22, np.where(df['age']
                      > 60, 14, np.where(df['age'] > 50, 7, 0)))
    score += df['diabetes'].values * 16
    score += df['hypertension'].values * 13
    score += df['smoking'].values * 8
    score += np.where(df['bmi'].values > 35, 10,
                      np.where(df['bmi'].values > 30, 5, 0))

    # Vitals — SpO2 is most critical predictor
    score += np.where(df['avg_spo2'] < 90, 35, np.where(df['avg_spo2']
                      < 93, 22, np.where(df['avg_spo2'] < 95, 8, 0)))
    score += np.where(df['avg_hr'] > 130, 28, np.where(df['avg_hr']
                      > 110, 16, np.where(df['avg_hr'] < 48, 22, 0)))
    score += np.where(df['avg_bp_sys'] > 185, 28, np.where(df['avg_bp_sys']
                      > 165, 16, np.where(df['avg_bp_sys'] < 88, 28, 0)))
    score += np.where(df['avg_rr'] > 28, 22,
                      np.where(df['avg_rr'] > 22, 10, 0))
    score += np.where(df['avg_temp'] > 39.5, 20,
                      np.where(df['avg_temp'] > 38.5, 10, 0))

    # Trends (deterioration)
    score += np.where(df['hr_trend'] > 12, 12,
                      np.where(df['hr_trend'] > 6, 6, 0))
    score += np.where(df['bp_trend'] > 15, 10, 0)
    score += np.where(df['spo2_trend'] < -2, 15, 0)

    # Shock index (HR/SBP > 1 is dangerous)
    score += np.where(df['shock_index'] > 1.0, 20,
                      np.where(df['shock_index'] > 0.8, 10, 0))

    # Add noise (10% of std)
    score += np.random.normal(0, score.std() * 0.10, len(score))

    return (score >= 45).astype(int)


def train_and_save(db_url: str, model_path: str = 'ml/models/risk_model.pkl'):
    engine = create_engine(db_url)
    df = build_features(engine)

    X = df[FEATURE_COLS].copy()
    X[['diabetes', 'hypertension', 'smoking']] = X[[
        'diabetes', 'hypertension', 'smoking']].astype(int)
    y = generate_risk_labels(df)

    log.info(f"Training: {len(X)} samples | High-risk rate: {y.mean():.1%}")

    model = Pipeline([
        ('scaler', StandardScaler()),
        ('clf', RandomForestClassifier(
            n_estimators=300, max_depth=8, min_samples_leaf=3,
            class_weight='balanced', random_state=42, n_jobs=-1
        ))
    ])

    # 5-fold cross-validation
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    results = cross_validate(model, X, y, cv=cv,
                             scoring=['recall', 'precision', 'f1', 'accuracy'])
    metrics = {k: float(v.mean())
               for k, v in results.items() if k.startswith('test_')}

    log.info("📊 Cross-validation results:")
    log.info(f"   Recall    : {metrics['test_recall']:.2%}   (target ≥ 87%)")
    log.info(f"   Precision : {metrics['test_precision']:.2%}  (target ≥ 82%)")
    log.info(f"   F1-Score  : {metrics['test_f1']:.2%}   (target ≥ 80%)")
    log.info(f"   Accuracy  : {metrics['test_accuracy']:.2%}  (target ≥ 85%)")

    # Final fit on full data
    model.fit(X, y)

    # SHAP feature importance (top 10)
    explainer = shap.TreeExplainer(model.named_steps['clf'])
    X_scaled = pd.DataFrame(
        model.named_steps['scaler'].transform(X), columns=FEATURE_COLS)
    shap_vals = explainer.shap_values(X_scaled)
    importance = dict(zip(FEATURE_COLS, np.abs(
        shap_vals[1]).mean(axis=0).tolist()))
    importance = dict(
        sorted(importance.items(), key=lambda x: x[1], reverse=True)[:10])

    log.info(f"🔍 Top 3 predictors: {list(importance.keys())[:3]}")

    # Save
    os.makedirs('ml/models', exist_ok=True)
    payload = {
        'model': model, 'feature_cols': FEATURE_COLS,
        'metrics': metrics, 'feature_importance': importance,
        'trained_at': datetime.now().isoformat(),
        'version': f"v1.0.{datetime.now().strftime('%Y%m%d')}"
    }
    with open(model_path, 'wb') as f:
        pickle.dump(payload, f)

    with open('ml/models/metrics.json', 'w') as f:
        json.dump({**metrics, 'feature_importance': importance,
                   'trained_at': payload['trained_at']}, f, indent=2)

    log.info(f"✅ Model saved → {model_path}")
    return model, metrics, importance


if __name__ == '__main__':
    train_and_save(os.getenv('DATABASE_URL'))
ml/predict.py
"""
Score all active patients and persist risk scores to DB.
Run after training: python ml/predict.py
Owner: Ahmed Adel Abd ElAziz
"""


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

load_dotenv()
log = logging.getLogger('ml.predict')
logging.basicConfig(level=logging.INFO)

RISK_LEVELS = {0: ('LOW', 0.0), 1: ('HIGH', 0.7)}  # binary → label mapping


def predict_and_store(db_url: str, model_path: str = 'ml/models/risk_model.pkl'):
    with open(model_path, 'rb') as f:
        payload = pickle.load(f)

    model = payload['model']
    version = payload['version']
    feat_imp_json = json.dumps(payload['feature_importance'])

    engine = create_engine(db_url)
    df = build_features(engine)

    X = df[FEATURE_COLS].copy()
    X[['diabetes', 'hypertension', 'smoking']] = X[[
        'diabetes', 'hypertension', 'smoking']].astype(int)

    proba = model.predict_proba(X)[:, 1]  # probability of high-risk class
    predicted = (proba >= 0.5).astype(int)

    rows = []
    for i, pid in enumerate(df['patient_id']):
        score = float(proba[i])
        if score < 0.25:
            level = 'LOW'
        elif score < 0.50:
            level = 'MEDIUM'
        elif score < 0.75:
            level = 'HIGH'
        else:
            level = 'CRITICAL'

        rows.append({
            'patient_id':          pid,
            'risk_score':          round(score, 5),
            'risk_level':          level,
            'model_version':       version,
            'feature_importances': feat_imp_json,
        })

    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO risk_scores
                (patient_id, risk_score, risk_level, model_version, feature_importances)
            VALUES
                (:patient_id, :risk_score, :risk_level, :model_version, :feature_importances::jsonb)
        """), rows)

    log.info(f"✅ Scored {len(rows)} patients | "
             f"CRITICAL: {sum(1 for r in rows if r['risk_level']=='CRITICAL')} | "
             f"HIGH: {sum(1 for r in rows if r['risk_level']=='HIGH')}")


if __name__ == '__main__':
    predict_and_store(os.getenv('DATABASE_URL'))
