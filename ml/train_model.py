"""
ml/train_model.py
Trains XGBoost risk classifier and saves in the format dashboard expects.
Run: python ml/train_model.py
"""
from xgboost import XGBClassifier
from sklearn.utils.class_weight import compute_class_weight
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import StratifiedKFold, cross_validate
from sqlalchemy import create_engine
from dotenv import load_dotenv
from datetime import datetime
import pandas as pd
import numpy as np
import logging
import pickle
import json
from ml.feature_engineering import build_features, FEATURE_COLS
import os
import sys

# 1. BULLETPROOF PATH FIX (Must be the absolute first executable lines)
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, '..'))
sys.path.insert(0, project_root)

# 2. INTERNAL IMPORTS

# 3. EXTERNAL IMPORTS


load_dotenv()
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger('ml.train')


def generate_risk_labels(df: pd.DataFrame) -> pd.Series:
    """Clinical scoring heuristic → 4-class risk level."""
    score = (
        0.35 * (df['age'] / 100) +
        0.20 * df['diabetes'] +
        0.20 * df['hypertension'] +
        0.15 * df['smoking'] +
        0.10 * (df['bmi'].clip(15, 45) / 40) +
        np.where(df['avg_spo2'] < 90, 0.25, np.where(df['avg_spo2'] < 94, 0.12, 0)) +
        np.where(df['avg_hr'] > 120, 0.15, np.where(df['avg_hr'] < 50, 0.12, 0)) +
        np.where(df['avg_bp_sys'] > 170, 0.12, np.where(df['avg_bp_sys'] < 90, 0.15, 0)) +
        np.where(df['shock_index'] > 0.9, 0.15, 0)
    )
    noise = np.random.normal(0, 0.04, len(df))
    score = np.clip(score + noise, 0, 1)
    levels = pd.cut(score, bins=[0, 0.25, 0.5, 0.70, 1.0],
                    labels=['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'])
    return pd.Series(levels, index=df.index)


def train_and_save(db_url: str, model_path: str = 'ml/models/risk_model.pkl'):
    engine = create_engine(db_url)
    log.info("Building feature matrix from database...")
    df = build_features(engine)

    if len(df) < 100:
        log.error(f"Only {len(df)} patients — run ETL pipeline first.")
        sys.exit(1)

    X_df = df[FEATURE_COLS].copy()
    for col in ['diabetes', 'hypertension', 'smoking']:
        X_df[col] = X_df[col].astype(int)

    y_raw = generate_risk_labels(df)
    valid = y_raw.notna()
    X_df = X_df[valid]
    y_raw = y_raw[valid]

    # Encode target
    le = LabelEncoder()
    y = le.fit_transform(y_raw)

    log.info(
        f"Training: {len(X_df)} samples | Classes: {le.classes_.tolist()}")

    # Class weights integration
    classes = np.unique(y)
    weights = compute_class_weight('balanced', classes=classes, y=y)

    # Bypass Pylance iterability errors by explicitly forcing standard lists
    classes_list = np.array(classes).tolist()
    weights_list = np.array(weights).tolist()
    y_list = np.array(y).tolist()

    class_weights_dict = {int(c): float(w)
                          for c, w in zip(classes_list, weights_list)}
    sample_weights = np.array([class_weights_dict[int(i)] for i in y_list])

    # XGBClassifier configuration
    model = XGBClassifier(
        n_estimators=500,
        max_depth=4,
        learning_rate=0.03,
        subsample=0.9,
        colsample_bytree=0.9,
        gamma=0.2,
        reg_lambda=1.5,
        min_child_weight=5,
        objective='multi:softprob',
        num_class=len(classes),
        eval_metric='mlogloss',
        random_state=42
    )

    log.info("Running 5-fold cross-validation...")
    kf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_results = cross_validate(model, X_df, y, cv=kf,
                                scoring=[
                                    'recall_weighted', 'precision_weighted', 'f1_weighted', 'accuracy'],
                                fit_params={'sample_weight': sample_weights})

    metrics = {
        'test_recall':    float(cv_results['test_recall_weighted'].mean()),
        'test_precision': float(cv_results['test_precision_weighted'].mean()),
        'test_f1':        float(cv_results['test_f1_weighted'].mean()),
        'test_accuracy':  float(cv_results['test_accuracy'].mean()),
    }

    log.info(
        f"📊 Recall: {metrics['test_recall']:.2%} | Precision: {metrics['test_precision']:.2%} | F1: {metrics['test_f1']:.2%}")

    # Final fit
    model.fit(X_df, y, sample_weight=sample_weights)

    # Feature importance natively from XGBoost
    importance_raw = model.feature_importances_
    importance = dict(sorted(
        zip(FEATURE_COLS, importance_raw.tolist()),
        key=lambda x: x[1], reverse=True
    )[:12])

    # Save Unified Payload
    os.makedirs('ml/models', exist_ok=True)
    trained_at = datetime.now().isoformat()

    payload = {
        'model':              model,
        'label_encoder':      le,
        'feature_cols':       FEATURE_COLS,
        'metrics':            metrics,
        'feature_importance': importance,
        'trained_at':         trained_at,
        'version':            f"v2.0.{datetime.now().strftime('%Y%m%d')}",
    }

    with open(model_path, 'wb') as f:
        pickle.dump(payload, f)

    # Dashboard-facing metrics JSON
    with open('ml/models/metrics.json', 'w') as f:
        json.dump({
            'test_recall':        metrics['test_recall'],
            'test_precision':     metrics['test_precision'],
            'test_f1':            metrics['test_f1'],
            'test_accuracy':      metrics['test_accuracy'],
            'feature_importance': importance,
            'trained_at':         payload['trained_at'],
        }, f, indent=2)

    log.info(f"✅ Model saved → {model_path}")
    log.info(f"✅ Metrics saved → ml/models/metrics.json")
    return model, metrics


if __name__ == '__main__':
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        log.critical("DATABASE_URL not set in .env")
        sys.exit(1)
    train_and_save(db_url)
