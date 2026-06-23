-- ============================================================
-- SMART HEALTHCARE PLATFORM — OPERATIONAL DATABASE SCHEMA
-- Owner: Arsany Osama | Version: 1.0
-- Run: psql -U postgres -d healthcare_db -f schema_operational.sql
-- ============================================================

-- Create DB (run as superuser if needed)
-- CREATE DATABASE healthcare_db;

-- ─────────────────────────────────────────────────────────────
-- CORE TABLES
-- ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS patients (
    patient_id      VARCHAR(10)     PRIMARY KEY,
    full_name       VARCHAR(100)    NOT NULL,
    age             INTEGER         CHECK (age BETWEEN 0 AND 120) NOT NULL,
    gender          CHAR(1)         CHECK (gender IN ('M', 'F')) NOT NULL,
    blood_type      VARCHAR(3),
    admission_date  DATE            NOT NULL DEFAULT CURRENT_DATE,
    ward            VARCHAR(50)     CHECK (ward IN ('ICU','Cardiology','General','Emergency','Neurology')),
    diabetes        BOOLEAN         DEFAULT FALSE,
    hypertension    BOOLEAN         DEFAULT FALSE,
    smoking         BOOLEAN         DEFAULT FALSE,
    bmi             DECIMAL(4,1)    CHECK (bmi BETWEEN 10 AND 60),
    discharge_date  DATE,
    created_at      TIMESTAMPTZ     DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     DEFAULT NOW(),
    CONSTRAINT no_discharge_before_admission CHECK (
        discharge_date IS NULL OR discharge_date >= admission_date
    )
);

CREATE TABLE IF NOT EXISTS vital_signs (
    reading_id          SERIAL          PRIMARY KEY,
    patient_id          VARCHAR(10)     NOT NULL REFERENCES patients(patient_id) ON DELETE CASCADE,
    timestamp           TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    heart_rate          DECIMAL(5,1)    CHECK (heart_rate BETWEEN 20 AND 300),
    bp_systolic         DECIMAL(5,1)    CHECK (bp_systolic BETWEEN 50 AND 280),
    bp_diastolic        DECIMAL(5,1)    CHECK (bp_diastolic BETWEEN 30 AND 180),
    temperature         DECIMAL(4,1)    CHECK (temperature BETWEEN 28 AND 45),
    oxygen_saturation   DECIMAL(4,1)    CHECK (oxygen_saturation BETWEEN 0 AND 100),
    respiratory_rate    DECIMAL(4,1)    CHECK (respiratory_rate BETWEEN 4 AND 80),
    mean_arterial_pressure DECIMAL(5,1) GENERATED ALWAYS AS
                            ((bp_systolic + 2 * bp_diastolic) / 3) STORED,
    created_at          TIMESTAMPTZ     DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS alerts (
    alert_id        SERIAL          PRIMARY KEY,
    patient_id      VARCHAR(10)     NOT NULL REFERENCES patients(patient_id),
    alert_type      VARCHAR(50)     NOT NULL
                    CHECK (alert_type IN ('HIGH_THRESHOLD','LOW_THRESHOLD','ANOMALY','HIGH_RISK')),
    severity        VARCHAR(20)     NOT NULL
                    CHECK (severity IN ('LOW','MEDIUM','HIGH','CRITICAL')),
    vital_parameter VARCHAR(60),
    observed_value  DECIMAL(8,2),
    threshold_value DECIMAL(8,2),
    message         TEXT            NOT NULL,
    triggered_at    TIMESTAMPTZ     DEFAULT NOW(),
    resolved_at     TIMESTAMPTZ,
    acknowledged_by VARCHAR(100),
    is_active       BOOLEAN         DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS risk_scores (
    score_id            SERIAL          PRIMARY KEY,
    patient_id          VARCHAR(10)     NOT NULL REFERENCES patients(patient_id),
    calculated_at       TIMESTAMPTZ     DEFAULT NOW(),
    risk_score          DECIMAL(6,5)    CHECK (risk_score BETWEEN 0 AND 1),
    risk_level          VARCHAR(20)     CHECK (risk_level IN ('LOW','MEDIUM','HIGH','CRITICAL')),
    model_version       VARCHAR(30)     DEFAULT 'v1.0',
    feature_importances JSONB
);

CREATE TABLE IF NOT EXISTS etl_audit_log (
    log_id          SERIAL          PRIMARY KEY,
    pipeline_name   VARCHAR(100)    NOT NULL,
    run_at          TIMESTAMPTZ     DEFAULT NOW(),
    status          VARCHAR(20)     CHECK (status IN ('STARTED','SUCCESS','FAILED')),
    records_read    INTEGER         DEFAULT 0,
    records_loaded  INTEGER         DEFAULT 0,
    records_failed  INTEGER         DEFAULT 0,
    duration_ms     INTEGER,
    error_message   TEXT
);

-- ─────────────────────────────────────────────────────────────
-- INDEXES — QUERY OPTIMIZATION
-- ─────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_vitals_patient_time
    ON vital_signs (patient_id, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_vitals_timestamp
    ON vital_signs (timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_alerts_active
    ON alerts (is_active, severity, triggered_at DESC)
    WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_alerts_patient
    ON alerts (patient_id, triggered_at DESC);

CREATE INDEX IF NOT EXISTS idx_risk_latest
    ON risk_scores (patient_id, calculated_at DESC);

-- ─────────────────────────────────────────────────────────────
-- TRIGGERS — AUTO-UPDATE TIMESTAMPS
-- ─────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_patients_updated_at
    BEFORE UPDATE ON patients
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ─────────────────────────────────────────────────────────────
-- USEFUL VIEWS
-- ─────────────────────────────────────────────────────────────

CREATE OR REPLACE VIEW v_patient_latest_vitals AS
SELECT DISTINCT ON (v.patient_id)
    p.patient_id,
    p.full_name,
    p.age,
    p.ward,
    v.timestamp       AS last_reading,
    v.heart_rate,
    v.bp_systolic,
    v.bp_diastolic,
    v.oxygen_saturation,
    v.temperature,
    v.respiratory_rate,
    v.mean_arterial_pressure
FROM patients p
JOIN vital_signs v ON p.patient_id = v.patient_id
WHERE p.discharge_date IS NULL
ORDER BY v.patient_id, v.timestamp DESC;

CREATE OR REPLACE VIEW v_active_alerts_with_patient AS
SELECT
    a.alert_id,
    a.patient_id,
    p.full_name,
    p.ward,
    a.severity,
    a.alert_type,
    a.vital_parameter,
    a.observed_value,
    a.threshold_value,
    a.message,
    a.triggered_at,
    EXTRACT(EPOCH FROM (NOW() - a.triggered_at))/60 AS minutes_ago
FROM alerts a
JOIN patients p ON a.patient_id = p.patient_id
WHERE a.is_active = TRUE
ORDER BY
    CASE a.severity
        WHEN 'CRITICAL' THEN 1
        WHEN 'HIGH'     THEN 2
        WHEN 'MEDIUM'   THEN 3
        WHEN 'LOW'      THEN 4
    END, a.triggered_at DESC;

CREATE OR REPLACE VIEW v_risk_summary AS
SELECT
    p.patient_id,
    p.full_name,
    p.age,
    p.ward,
    rs.risk_level,
    rs.risk_score,
    rs.calculated_at,
    COUNT(a.alert_id) FILTER (WHERE a.is_active) AS active_alerts
FROM patients p
LEFT JOIN LATERAL (
    SELECT risk_level, risk_score, calculated_at
    FROM risk_scores
    WHERE patient_id = p.patient_id
    ORDER BY calculated_at DESC LIMIT 1
) rs ON TRUE
LEFT JOIN alerts a ON p.patient_id = a.patient_id
WHERE p.discharge_date IS NULL
GROUP BY p.patient_id, p.full_name, p.age, p.ward,
         rs.risk_level, rs.risk_score, rs.calculated_at;