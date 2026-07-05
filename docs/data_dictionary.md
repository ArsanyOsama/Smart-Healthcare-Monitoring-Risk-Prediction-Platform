# Data Dictionary — Smart Healthcare Monitoring Platform
*Owner: Arsany Osama | CAI4-AIS5-S3 | DEPI R4*

## Operational Tables

### `patients`
| Column | Type | Nullable | Constraint | Description |
|---|---|---|---|---|
| patient_id | VARCHAR(10) | NO | PK | Format: PAT0001–PAT9999 |
| full_name | VARCHAR(100) | NO | — | Patient name (de-identified in mock) |
| age | INTEGER | NO | 0–120 | Age in years |
| gender | CHAR(1) | NO | M or F | Patient sex |
| blood_type | VARCHAR(3) | YES | — | ABO/Rh blood group |
| admission_date | DATE | NO | — | Hospital admission date |
| ward | VARCHAR(50) | YES | Enum | ICU / Cardiology / General / Emergency / Neurology |
| diabetes | BOOLEAN | NO | — | Diabetes mellitus diagnosis |
| hypertension | BOOLEAN | NO | — | Hypertension diagnosis |
| smoking | BOOLEAN | NO | — | Current/former smoker |
| bmi | DECIMAL(4,1) | YES | 10–60 | Body Mass Index |
| discharge_date | DATE | YES | ≥ admission | NULL if currently admitted |
| created_at | TIMESTAMPTZ | NO | — | Record insertion timestamp |
| updated_at | TIMESTAMPTZ | NO | — | Last update (auto via trigger) |

### `vital_signs`
| Column | Type | Nullable | Constraint | Description |
|---|---|---|---|---|
| reading_id | SERIAL | NO | PK | Auto-increment |
| patient_id | VARCHAR(10) | NO | FK→patients | Foreign key |
| timestamp | TIMESTAMPTZ | NO | — | Reading capture time |
| heart_rate | DECIMAL(5,1) | YES | 20–300 | Beats per minute |
| bp_systolic | DECIMAL(5,1) | YES | 50–280 | Systolic blood pressure (mmHg) |
| bp_diastolic | DECIMAL(5,1) | YES | 30–180 | Diastolic blood pressure (mmHg) |
| temperature | DECIMAL(4,1) | YES | 28–45 | Body temperature (°C) |
| oxygen_saturation | DECIMAL(4,1) | YES | 0–100 | SpO2 pulse oximetry (%) |
| respiratory_rate | DECIMAL(4,1) | YES | 4–80 | Breaths per minute |
| mean_arterial_pressure | DECIMAL(5,1) | YES | GENERATED | (SBP + 2×DBP) / 3 |

### `alerts`
| Column | Type | Nullable | Values | Description |
|---|---|---|---|---|
| alert_id | SERIAL | NO | PK | Auto-increment |
| patient_id | VARCHAR(10) | NO | FK→patients | — |
| alert_type | VARCHAR(50) | NO | HIGH_THRESHOLD, LOW_THRESHOLD, ANOMALY, HIGH_RISK | What triggered the alert |
| severity | VARCHAR(20) | NO | LOW, MEDIUM, HIGH, CRITICAL | Clinical urgency |
| vital_parameter | VARCHAR(60) | YES | — | Which vital sign |
| observed_value | DECIMAL(8,2) | YES | — | Value that breached threshold |
| threshold_value | DECIMAL(8,2) | YES | — | The limit that was crossed |
| message | TEXT | NO | — | Human-readable description |
| triggered_at | TIMESTAMPTZ | NO | — | When alert fired |
| is_active | BOOLEAN | NO | — | TRUE = unresolved |

### `risk_scores`
| Column | Type | Nullable | Description |
|---|---|---|---|
| score_id | SERIAL | NO | PK |
| patient_id | VARCHAR(10) | NO | FK→patients |
| calculated_at | TIMESTAMPTZ | NO | Scoring timestamp |
| risk_score | DECIMAL(6,5) | YES | Probability [0.00000–1.00000] |
| risk_level | VARCHAR(20) | YES | LOW / MEDIUM / HIGH / CRITICAL |
| model_version | VARCHAR(30) | YES | e.g. v1.0.20260624 |
| feature_importances | JSONB | YES | SHAP importance per feature |

### `etl_audit_log`
| Column | Type | Description |
|---|---|---|
| log_id | SERIAL | PK |
| pipeline_name | VARCHAR(100) | Which ETL run |
| run_at | TIMESTAMPTZ | Execution start |
| status | VARCHAR(20) | STARTED / SUCCESS / FAILED |
| records_read | INTEGER | Input rows |
| records_loaded | INTEGER | Successfully inserted rows |
| records_failed | INTEGER | Rejected rows |
| duration_ms | INTEGER | Wall-clock time in milliseconds |
| error_message | TEXT | NULL if SUCCESS |

## Analytical / DWH Tables

### `dim_patients` — slowly-changing dimension (Type 2)
Patient dimensional table with historical tracking via `valid_from/valid_to`.

### `dim_time` — time dimension
Hourly grain. Contains year, month, day, hour, shift (MORNING/AFTERNOON/NIGHT), is_weekend.

### `fact_vitals_hourly` — central fact table
Hourly aggregated vital signs (avg, min, max per vital per patient). Loaded via stored procedure `sp_load_fact_vitals_hourly()`.