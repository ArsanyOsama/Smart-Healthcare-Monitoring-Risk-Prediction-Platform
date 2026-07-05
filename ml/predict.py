"""
ml/predict.py
Loads saved model and scores all active patients, persists to risk_scores table.
Owner: Ahmed Adel Abd ElAziz
Run: python ml/predict.py
"""
from ml.feature_engineering import build_features, FEATURE_COLS
import os
import sys
import pickle
import logging
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

load_dotenv()
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger('ml.predict')

MODEL_PATH = os.getenv('MODEL_PATH', 'ml/models/risk_model.pkl')


def predict_and_store(db_url: str, model_path: str = MODEL_PATH):
    if not os.path.exists(model_path):
        log.critical(
            f"Model not found at {model_path}. Run ml/train_model.py first.")
        sys.exit(1)

    with open(model_path, 'rb') as f:
        payload = pickle.load(f)

    model = payload['model']
    le = payload['label_encoder']
    version = payload.get('version', 'v2.0')
    feat_imp = json.dumps(payload.get('feature_importance', {}))

    engine = create_engine(db_url, pool_pre_ping=True)
    df = build_features(engine)

    X = df[FEATURE_COLS].copy()
    for col in ['diabetes', 'hypertension', 'smoking']:
        X[col] = X[col].astype(int)

    proba = model.predict_proba(X)
    predicted = model.predict(X)
    labels = le.inverse_transform(predicted)

    # Map class label → numeric score (probability of HIGH or CRITICAL)
    high_idx = list(le.classes_).index('HIGH') if 'HIGH' in le.classes_ else -1
    critical_idx = list(le.classes_).index(
        'CRITICAL') if 'CRITICAL' in le.classes_ else -1

    rows = []
    for i, pid in enumerate(df['patient_id']):
        label = str(labels[i])
        if high_idx >= 0 and critical_idx >= 0:
            risk_score = float(proba[i, high_idx] + proba[i, critical_idx])
        else:
            risk_score = float(proba[i].max())

        rows.append({
            'patient_id':          pid,
            'risk_score':          round(min(risk_score, 0.99999), 5),
            'risk_level':          label,
            'model_version':       version,
            'feature_importances': feat_imp,
        })

    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO risk_scores
                (patient_id, risk_score, risk_level, model_version, feature_importances)
            VALUES
                (:patient_id, :risk_score, :risk_level, :model_version,
                 :feature_importances::jsonb)
        """), rows)

    critical = sum(1 for r in rows if r['risk_level'] == 'CRITICAL')
    high = sum(1 for r in rows if r['risk_level'] == 'HIGH')
    log.info(
        f"✅ Scored {len(rows)} patients | CRITICAL: {critical} | HIGH: {high}")


if __name__ == '__main__':
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        log.critical("DATABASE_URL not set")
        sys.exit(1)
    predict_and_store(db_url)
