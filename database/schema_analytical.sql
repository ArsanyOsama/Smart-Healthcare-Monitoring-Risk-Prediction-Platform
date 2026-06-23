-- ============================================================
-- ANALYTICAL / DATA WAREHOUSE LAYER (Star Schema)
-- Owner: Arsany Osama
-- ============================================================

CREATE TABLE IF NOT EXISTS dim_patients (
    patient_key         SERIAL          PRIMARY KEY,
    patient_id          VARCHAR(10)     UNIQUE NOT NULL,
    full_name           VARCHAR(100),
    age_group           VARCHAR(20)
                        CHECK (age_group IN ('18-30','31-45','46-60','61-75','76+')),
    gender              CHAR(1),
    ward                VARCHAR(50),
    comorbidity_count   INTEGER         DEFAULT 0,
    valid_from          TIMESTAMPTZ     DEFAULT NOW(),
    valid_to            TIMESTAMPTZ,
    is_current          BOOLEAN         DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS dim_time (
    time_key        SERIAL          PRIMARY KEY,
    full_hour       TIMESTAMPTZ     UNIQUE NOT NULL,
    year            INTEGER,
    month           INTEGER,
    day             INTEGER,
    hour            INTEGER,
    day_of_week     INTEGER,
    is_weekend      BOOLEAN,
    shift           VARCHAR(20)
                    CHECK (shift IN ('MORNING','AFTERNOON','NIGHT'))
);

CREATE TABLE IF NOT EXISTS fact_vitals_hourly (
    fact_id             SERIAL          PRIMARY KEY,
    patient_key         INTEGER         REFERENCES dim_patients(patient_key),
    time_key            INTEGER         REFERENCES dim_time(time_key),
    avg_heart_rate      DECIMAL(5,1),
    avg_bp_systolic     DECIMAL(5,1),
    avg_bp_diastolic    DECIMAL(5,1),
    avg_temperature     DECIMAL(4,1),
    avg_oxygen_sat      DECIMAL(4,1),
    avg_resp_rate       DECIMAL(4,1),
    min_oxygen_sat      DECIMAL(4,1),
    max_heart_rate      DECIMAL(5,1),
    reading_count       INTEGER         DEFAULT 0,
    alert_count         INTEGER         DEFAULT 0,
    UNIQUE (patient_key, time_key)
);

-- ETL from operational to analytical
CREATE OR REPLACE PROCEDURE sp_load_fact_vitals_hourly()
LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO dim_time (full_hour, year, month, day, hour, day_of_week, is_weekend, shift)
    SELECT DISTINCT
        DATE_TRUNC('hour', timestamp) AS full_hour,
        EXTRACT(YEAR FROM timestamp)::INT,
        EXTRACT(MONTH FROM timestamp)::INT,
        EXTRACT(DAY FROM timestamp)::INT,
        EXTRACT(HOUR FROM timestamp)::INT,
        EXTRACT(DOW FROM timestamp)::INT,
        EXTRACT(DOW FROM timestamp) IN (0, 6),
        CASE
            WHEN EXTRACT(HOUR FROM timestamp) BETWEEN 7 AND 14 THEN 'MORNING'
            WHEN EXTRACT(HOUR FROM timestamp) BETWEEN 15 AND 22 THEN 'AFTERNOON'
            ELSE 'NIGHT'
        END
    FROM vital_signs
    ON CONFLICT (full_hour) DO NOTHING;

    INSERT INTO fact_vitals_hourly (
        patient_key, time_key,
        avg_heart_rate, avg_bp_systolic, avg_bp_diastolic,
        avg_temperature, avg_oxygen_sat, avg_resp_rate,
        min_oxygen_sat, max_heart_rate, reading_count
    )
    SELECT
        dp.patient_key,
        dt.time_key,
        AVG(v.heart_rate),
        AVG(v.bp_systolic),
        AVG(v.bp_diastolic),
        AVG(v.temperature),
        AVG(v.oxygen_saturation),
        AVG(v.respiratory_rate),
        MIN(v.oxygen_saturation),
        MAX(v.heart_rate),
        COUNT(*)
    FROM vital_signs v
    JOIN dim_patients dp ON v.patient_id = dp.patient_id AND dp.is_current = TRUE
    JOIN dim_time dt ON DATE_TRUNC('hour', v.timestamp) = dt.full_hour
    GROUP BY dp.patient_key, dt.time_key
    ON CONFLICT (patient_key, time_key) DO UPDATE
        SET avg_heart_rate  = EXCLUDED.avg_heart_rate,
            reading_count   = EXCLUDED.reading_count;

    RAISE NOTICE 'DWH load complete at %', NOW();
END;
$$;