"""
Threshold-based alert engine.
Checks incoming vitals and writes alerts to PostgreSQL.
Owner: Noureldeen Mohamed
"""

from sqlalchemy import text
from datetime import datetime
import logging

log = logging.getLogger('streaming.alert_engine')

THRESHOLDS = {
    'heart_rate':        {'critical_low': 40,   'low': 50,  'high': 120,  'critical_high': 150},
    'bp_systolic':       {'critical_low': 80,   'low': 90,  'high': 160,  'critical_high': 185},
    'bp_diastolic':      {'critical_low': 50,   'low': 60,  'high': 100,  'critical_high': 125},
    'oxygen_saturation': {'critical_low': 90,   'low': 93},
    'temperature':       {'critical_low': 35.0, 'low': 36.0, 'high': 38.5, 'critical_high': 40.0},
    'respiratory_rate':  {'critical_low': 8,    'low': 10,  'high': 25,   'critical_high': 30},
}


class AlertEngine:
    def __init__(self, db_engine):
        self.engine = db_engine
        self._alert_cooldown = {}  # patient_id+param → last_alert_time, to avoid spam

    def check_vitals(self, reading: dict) -> int:
        """Return number of alerts triggered."""
        triggered = 0
        patient_id = reading.get('patient_id')

        for param, thresholds in THRESHOLDS.items():
            value = reading.get(param)
            if value is None:
                continue

            alert = self._evaluate(patient_id, param, float(value), thresholds)
            if alert and self._should_alert(patient_id, param):
                self._insert_alert(alert)
                triggered += 1
                self._alert_cooldown[f"{patient_id}:{param}"] = datetime.now()

        return triggered

    def _evaluate(self, patient_id, param, value, thresholds) -> dict | None:
        if 'critical_low' in thresholds and value <= thresholds['critical_low']:
            sev, thresh = 'CRITICAL', thresholds['critical_low']
            atype = 'LOW_THRESHOLD'
        elif 'critical_high' in thresholds and value >= thresholds['critical_high']:
            sev, thresh = 'CRITICAL', thresholds['critical_high']
            atype = 'HIGH_THRESHOLD'
        elif 'low' in thresholds and value <= thresholds['low']:
            sev, thresh = 'HIGH', thresholds['low']
            atype = 'LOW_THRESHOLD'
        elif 'high' in thresholds and value >= thresholds['high']:
            sev, thresh = 'HIGH', thresholds['high']
            atype = 'HIGH_THRESHOLD'
        else:
            return None

        label = param.replace('_', ' ').title()
        return {
            'patient_id':       patient_id,
            'alert_type':       atype,
            'severity':         sev,
            'vital_parameter':  param,
            'observed_value':   value,
            'threshold_value':  thresh,
            'message':          f"[{sev}] {label} = {value} (threshold: {thresh})",
            'is_active':        True,
        }

    def _should_alert(self, patient_id, param, cooldown_minutes=5) -> bool:
        """Prevent duplicate alerts within cooldown window."""
        key = f"{patient_id}:{param}"
        last = self._alert_cooldown.get(key)
        if not last:
            return True
        return (datetime.now() - last).total_seconds() > cooldown_minutes * 60

    def _insert_alert(self, alert: dict):
        try:
            with self.engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO alerts
                        (patient_id,alert_type,severity,vital_parameter,
                         observed_value,threshold_value,message,is_active)
                    VALUES
                        (:patient_id,:alert_type,:severity,:vital_parameter,
                         :observed_value,:threshold_value,:message,:is_active)
                """), alert)
            log.warning(f"🚨 [{alert['severity']}] {alert['message']}")
        except Exception as e:
            log.error(f"Alert insert failed: {e}")
