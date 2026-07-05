# ==============================
# 1. IMPORTS
# ==============================
import pandas as pd
import numpy as np

from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.impute import SimpleImputer
from sklearn.utils.class_weight import compute_class_weight

from xgboost import XGBClassifier

import matplotlib.pyplot as plt
import joblib

# ==============================
# 2. LOAD DATA
# ==============================
patients = pd.read_csv("data/sample/patients.csv")
risk = pd.read_csv("data/sample/risk_scores.csv")

df = patients.merge(risk, on="patient_id")

# ==============================
# 3. CLEAN TARGET
# ==============================
valid_classes = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
df = df[df["risk_level"].isin(valid_classes)]

print("Available classes:", df["risk_level"].unique())

# ==============================
# 4. FEATURE ENGINEERING
# ==============================
df["risk_factor_count"] = df[["diabetes", "hypertension", "smoking"]].sum(axis=1)
df["age_bmi"] = df["age"] * df["bmi"]

# ==============================
# 5. FEATURES & TARGET
# ==============================
X = df.drop(columns=["patient_id", "risk_level", "risk_score"])
y = df["risk_level"]

# Encode target
le = LabelEncoder()
y = le.fit_transform(y)

# ==============================
# 6. ENCODING
# ==============================
X = pd.get_dummies(X, drop_first=True)
feature_names = X.columns

# ==============================
# 7. SPLIT
# ==============================
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)


# ==============================
# 8. CLASS WEIGHTS (بديل SMOTE 🔥)
# ==============================
classes = np.unique(y_train)
weights = compute_class_weight(
    class_weight='balanced',
    classes=classes,
    y=y_train
)

class_weights_dict = {i: w for i, w in zip(classes, weights)}

sample_weights = np.array([class_weights_dict[i] for i in y_train])

# ==============================
# 9. MODEL (محسن جدًا)
# ==============================
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
    num_class=len(np.unique(y)),
    eval_metric='mlogloss',
    random_state=42
)

# ==============================
# 10. CROSS VALIDATION 🔥
# ==============================
kf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

cv_scores = cross_val_score(
    model,
    X_train,
    y_train,
    cv=kf,
    scoring='f1_weighted'
)

print("\n📊 Cross Validation F1 Scores:", cv_scores)
print("📊 Mean CV Score:", cv_scores.mean())

# ==============================
# 11. TRAIN
# ==============================
model.fit(X_train, y_train, sample_weight=sample_weights)

# ==============================
# 12. PREDICT
# ==============================
y_pred = model.predict(X_test)

# ==============================
# 13. EVALUATION
# ==============================
class_names = le.classes_

print("\n📊 Classification Report:\n")
print(classification_report(y_test, y_pred, target_names=class_names))

print("\n📊 Confusion Matrix:\n")
print(confusion_matrix(y_test, y_pred))

# ==============================
# 14. FEATURE IMPORTANCE
# ==============================
importance = model.feature_importances_
feat_imp = pd.Series(importance, index=feature_names).sort_values(ascending=False)

print("\n🔥 Top 10 Features:\n")
print(feat_imp.head(10))

plt.figure()
feat_imp.head(10).plot(kind='barh')
plt.title("Top Features")
plt.gca().invert_yaxis()
plt.show()

# ==============================
# 15. SAVE
# ==============================
joblib.dump(model, "risk_model_advanced.pkl")
joblib.dump(le, "label_encoder.pkl")