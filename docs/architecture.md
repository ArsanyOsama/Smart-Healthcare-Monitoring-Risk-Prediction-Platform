# System Architecture — Smart Healthcare Monitoring Platform
*CAI4-AIS5-S3 | DEPI R4*

## High-Level Architecture
[Synthetic Data Generator] ──→ [ETL Pipeline] ──→ [PostgreSQL] [Streaming Simulator] ─────────────────────────→ │ ├──→ [ML Risk Classifier] ├──→ [Alert Engine] └──→ [Streamlit Dashboard] │ [Docker / Supabase]


## Components

| Component | Technology | Owner |
|---|---|---|
| Database | PostgreSQL 15 — operational + DWH layers | Arsany |
| ETL Pipeline | Python (pandas, SQLAlchemy, Faker) | Arsany |
| Streaming | Python threading + PostgreSQL polling | Noureldeen |
| Alert Engine | Threshold-based rules + cooldown logic | Noureldeen |
| ML Risk Model | XGBoost multiclass classifier | Ahmed Adel |
| Dashboard | Streamlit + Plotly | Adel Assem |
| Deployment | Docker Compose + Supabase + Streamlit Cloud | Ahmed Mostafa |
| Governance | Data quality checks, drift detection, audit log | Adel Assem |

## Data Flow
1. `etl/pipeline.py` → generates/transforms/loads 1000 patients + 48K vitals into PostgreSQL
2. `streaming/producer.py` → adds new readings every 30 seconds
3. `streaming/alert_engine.py` → checks each reading against clinical thresholds → inserts alerts
4. `ml/train_model.py` → trains XGBoost on patient features + vital aggregates
5. `ml/predict.py` → scores all active patients → inserts into risk_scores
6. `dashboard/app.py` → reads from views and displays live data

## Database Schema
- **Operational layer**: `patients`, `vital_signs`, `alerts`, `risk_scores`, `etl_audit_log`
- **Analytical layer**: `dim_patients`, `dim_time`, `fact_vitals_hourly`
- **Views**: `v_patient_latest_vitals`, `v_active_alerts_with_patient`, `v_risk_summary`