"""
tests/test_ml.py
ML model unit tests — verifies feature engineering and model integrity.
Owner: Adel Assem Mohamed
Run: pytest tests/test_ml.py -v
"""
import pytest
import sys
import os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

try:
    from ml.feature_engineering import FEATURE_COLS
    ML_OK = True
except ImportError:
    ML_OK = False

pytestmark = pytest.mark.skipif(
    not ML_OK,
    reason="ml package not importable — check ml/__init__.py exists"
)


def _fake_features(n: int = 300) -> pd.DataFrame:
    """Build a synthetic feature matrix that matches FEATURE_COLS exactly."""
    np.random.seed(42)
    return pd.DataFrame({
        'age':               np.random.randint(20, 90, n),
        'gender_m':          np.random.randint(0, 2, n),
        'bmi':               np.round(np.random.normal(27, 5, n).clip(15, 50), 1),
        'diabetes':          np.random.randint(0, 2, n),
        'hypertension':      np.random.randint(0, 2, n),
        'smoking':           np.random.randint(0, 2, n),
        'comorbidity_count': np.random.randint(0, 4, n),
        'age_group_encoded': np.random.randint(0, 5, n),
        'avg_hr':            np.random.normal(80, 12, n),
        'avg_bp_sys':        np.random.normal(125, 18, n),
        'avg_bp_dia':        np.random.normal(78, 10, n),
        'avg_spo2':          np.random.normal(97, 2, n),
        'avg_rr':            np.random.normal(17, 3, n),
        'avg_temp':          np.random.normal(36.8, 0.5, n),
        'min_spo2':          np.random.normal(95, 3, n),
        'max_hr':            np.random.normal(95, 15, n),
        'min_bp_sys':        np.random.normal(110, 20, n),
        'std_hr':            np.random.normal(10, 3, n).clip(0),
        'std_bp_sys':        np.random.normal(15, 5, n).clip(0),
        'pulse_pressure':    np.random.normal(47, 10, n),
        'shock_index':       np.random.normal(0.65, 0.15, n).clip(0.1, 2.0),
        'resp_to_hr_ratio':  np.random.normal(0.21, 0.05, n).clip(0.05, 0.8),
        'hr_trend':          np.random.normal(0, 5, n),
        'bp_trend':          np.random.normal(0, 8, n),
        'spo2_trend':        np.random.normal(0, 1.5, n),
        'reading_count':     np.random.randint(1, 50, n),
    })


class TestFeatureCols:
    def test_feature_cols_is_list(self):
        assert isinstance(FEATURE_COLS, list) and len(FEATURE_COLS) > 0

    def test_feature_cols_no_duplicates(self):
        assert len(FEATURE_COLS) == len(
            set(FEATURE_COLS)), "Duplicate feature names"

    def test_fake_df_has_all_features(self):
        df = _fake_features(50)
        missing = [c for c in FEATURE_COLS if c not in df.columns]
        assert not missing, f"Features missing from fake df: {missing}"

    def test_no_nulls_in_fake_features(self):
        df = _fake_features(100)
        nulls = df[FEATURE_COLS].isnull().sum()
        assert nulls.sum() == 0, f"Null values found: {nulls[nulls>0]}"


class TestSavedModel:
    MODEL_PATH = 'ml/models/risk_model.pkl'
    METRICS_PATH = 'ml/models/metrics.json'

    def test_model_file_exists(self):
        if not os.path.exists(self.MODEL_PATH):
            pytest.skip(
                "Model not trained yet — run: python ml/train_model.py")
        assert os.path.getsize(self.MODEL_PATH) > 5_000, "Model file too small"

    def test_metrics_json_keys(self):
        if not os.path.exists(self.METRICS_PATH):
            pytest.skip("metrics.json missing — run: python ml/train_model.py")
        import json
        with open(self.METRICS_PATH) as f:
            m = json.load(f)
        for key in ['test_recall', 'test_precision', 'test_f1', 'test_accuracy']:
            assert key in m, f"Missing metric key: {key}"

    def test_model_recall_above_floor(self):
        if not os.path.exists(self.METRICS_PATH):
            pytest.skip("metrics.json missing")
        import json
        with open(self.METRICS_PATH) as f:
            m = json.load(f)
        assert m['test_recall'] >= 0.70, \
            f"Recall {m['test_recall']:.2%} below acceptable floor 70%"

    def test_model_predict_shape(self):
        if not os.path.exists(self.MODEL_PATH):
            pytest.skip("Model not trained yet")
        import pickle
        with open(self.MODEL_PATH, 'rb') as f:
            payload = pickle.load(f)
        model = payload['model']
        df = _fake_features(20)
        X = df[FEATURE_COLS]
        proba = model.predict_proba(X)
        assert proba.shape == (20, 4), f"Expected (20,4), got {proba.shape}"
        assert (proba >= 0).all() and (
            proba <= 1).all(), "Probabilities out of [0,1]"

    def test_model_predict_four_risk_levels(self):
        if not os.path.exists(self.MODEL_PATH):
            pytest.skip("Model not trained yet")
        import pickle
        with open(self.MODEL_PATH, 'rb') as f:
            payload = pickle.load(f)
        model = payload['model']
        df = _fake_features(500)
        X = df[FEATURE_COLS]
        proba = model.predict_proba(X)[:, 1]
        levels = []
        for p in proba:
            if p < 0.25:
                levels.append('LOW')
            elif p < 0.50:
                levels.append('MEDIUM')
            elif p < 0.75:
                levels.append('HIGH')
            else:
                levels.append('CRITICAL')
        unique = set(levels)
        assert len(unique) >= 2, \
            f"Model only predicts {unique} — likely degenerate (check training data size)"
