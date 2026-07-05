# Streaming & Alert System API
*Owner: Noureldeen Mohamed | CAI4-AIS5-S3*

## Overview
The streaming layer simulates a Kafka producer/consumer pair using pure Python
threading + PostgreSQL. No Kafka installation required for MVP.

## Producer: `streaming/producer.py`
Generates batches of vital readings every N seconds and writes to `vital_signs`.

**Run:** `python streaming/producer.py [--interval N] [--dry-run]`

| Argument | Default | Description |
|---|---|---|
| `--interval` | 30 | Seconds between batches |
| `--dry-run` | false | Log output only, no DB writes |

**Output:** Rows inserted to `vital_signs` table.

## Consumer: `streaming/consumer.py`
Polls `vital_signs` for new rows and computes batch statistics.

**Run:** `python streaming/consumer.py`

**Output:** Log messages with batch stats. Would trigger ML re-scoring in production.

## Alert Engine: `streaming/alert_engine.py`

**Class:** `AlertEngine(db_engine)`  
**Method:** `check_vitals(reading: dict) → int` — returns number of alerts triggered

### Alert Thresholds

| Parameter | Critical Low | Low | High | Critical High |
|---|---|---|---|---|
| heart_rate | 40 | 50 | 120 | 150 |
| bp_systolic | 80 | 90 | 160 | 185 |
| bp_diastolic | 50 | 60 | 100 | 125 |
| oxygen_saturation | 90 | 93 | — | — |
| temperature | 35.0 | 36.0 | 38.5 | 40.0 |
| respiratory_rate | 8 | 10 | 25 | 30 |

**Cooldown:** 5 minutes per patient per parameter (prevents alert storms).

### Alert Severity Rules
- Value beyond `critical_*` → `CRITICAL`
- Value beyond `low/high` → `HIGH`
- Values within bounds → no alert