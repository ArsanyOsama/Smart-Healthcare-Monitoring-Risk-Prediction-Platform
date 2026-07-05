"""
Main Streamlit dashboard entry point.
Owner: Yahya Mohamed Abdelwahab
Run: streamlit run dashboard/app.py
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from sqlalchemy import create_engine, text
import os
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ─── Page Config ─────────────────────────────────────────────
st.set_page_config(
    page_title="Healthcare Monitor",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─── Custom CSS (brand colors: #0D1B2A + #00C896 + #D4A017) ──
st.markdown("""
<style>
    /* Sidebar */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0D1B2A 0%, #1a2e42 100%);
    }
    [data-testid="stSidebar"] * { color: #e0e0e0 !important; }

    /* Metric cards */
    [data-testid="metric-container"] {
        background: #0D1B2A;
        border: 1px solid #1e3a52;
        border-left: 4px solid #00C896;
        border-radius: 10px;
        padding: 12px;
        color: white;
    }
    [data-testid="metric-container"] label { color: #9ab8c8 !important; font-size: 0.82rem !important; }
    [data-testid="metric-container"] [data-testid="stMetricValue"] { color: #00C896 !important; }

    /* Alert badges */
    .badge-critical { background:#7b1f1f; color:#ff8a8a; padding:3px 10px; border-radius:20px; font-size:0.78rem; }
    .badge-high     { background:#7b4a1f; color:#ffb07a; padding:3px 10px; border-radius:20px; font-size:0.78rem; }
    .badge-medium   { background:#6b5b1f; color:#ffe07a; padding:3px 10px; border-radius:20px; font-size:0.78rem; }
    .badge-low      { background:#1f4a2e; color:#7affa3; padding:3px 10px; border-radius:20px; font-size:0.78rem; }

    /* Main background */
    .main { background-color: #0a1520; }
    h1, h2, h3 { color: #e8f4f8 !important; }
    p, li { color: #b0c8d8 !important; }
</style>
""", unsafe_allow_html=True)


# ─── DB Connection ───────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def get_engine():
    try:
        url = None

        # 1. Try Streamlit Secrets (for production or local TOML)
        if hasattr(st, "secrets"):
            url = st.secrets.get("db_url") or st.secrets.get("SUPABASE_DB_URL")

        # 2. Fallback to Environment Variables (from .env)
        if not url:
            url = os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")

        if not url:
            st.error("⚠️ No DATABASE_URL found. Please check secrets.toml or .env")
            st.stop()

        return create_engine(
            url,
            pool_size=5,
            max_overflow=10,
            pool_timeout=30,
            pool_pre_ping=True
        )
    except Exception as e:
        st.error(f"DB connection failed: {e}")
        st.stop()

# ─── Data Loaders ────────────────────────────────────────────


@st.cache_data(ttl=600, show_spinner=False)
def load_kpi_stats(_engine):
    q = text("""
        SELECT
            (SELECT COUNT(*) FROM patients WHERE discharge_date IS NULL)
                AS total_patients,
            (SELECT COUNT(*) FROM alerts WHERE is_active = TRUE)
                AS active_alerts,
            (SELECT COUNT(*) FROM alerts
             WHERE is_active = TRUE AND severity = 'CRITICAL')
                AS critical_alerts,
            (SELECT COUNT(DISTINCT rs.patient_id)
             FROM risk_scores rs
             INNER JOIN (
                 SELECT patient_id, MAX(calculated_at) AS latest_calc
                 FROM risk_scores GROUP BY patient_id
             ) lat ON rs.patient_id = lat.patient_id
                  AND rs.calculated_at = lat.latest_calc
             WHERE rs.risk_level IN ('HIGH','CRITICAL'))
                AS high_risk_patients
    """)
    with _engine.connect() as conn:
        row = conn.execute(q).fetchone()
    return dict(row._mapping)


@st.cache_data(ttl=30, show_spinner=False)
def load_active_alerts(_engine):
    with _engine.connect() as conn:
        return pd.read_sql(text("SELECT * FROM v_active_alerts_with_patient LIMIT 50"), conn)


@st.cache_data(ttl=30, show_spinner=False)
def load_risk_summary(_engine):
    with _engine.connect() as conn:
        return pd.read_sql(text("SELECT * FROM v_risk_summary ORDER BY risk_score DESC NULLS LAST"), conn)


@st.cache_data(ttl=60, show_spinner=False)
def load_vitals_for_patient(_engine, patient_id: str, hours: int = 24):
    q = text("""
        SELECT timestamp, heart_rate, bp_systolic, bp_diastolic,
               oxygen_saturation, temperature, respiratory_rate
        FROM vital_signs
        WHERE patient_id = :pid
          AND timestamp >= NOW() - INTERVAL '1 hour' * :hrs
        ORDER BY timestamp ASC
    """)
    with _engine.connect() as conn:
        return pd.read_sql(q, conn, params={'pid': patient_id, 'hrs': hours})


def severity_badge(sev: str) -> str:
    return f'<span class="badge-{sev.lower()}">{sev}</span>'


# ─── Main App ────────────────────────────────────────────────
def main():
    engine = get_engine()

    # ── Sidebar ──────────────────────────────────────────────
    with st.sidebar:
        st.markdown("## 🏥 Healthcare Monitor")
        st.markdown("---")
        page = st.radio("Navigate", ["📊 Overview", "🧑 Patient Monitor",
                                     "🚨 Alerts", "🤖 ML Insights"])
        st.markdown("---")
        if st.button("🔄 Refresh Data"):
            st.cache_data.clear()
            st.rerun()
        st.caption(f"Updated: {datetime.now().strftime('%H:%M:%S')}")
        st.caption("DEPI R4 | CAI4-AIS5-S3")

    # ── Pages ────────────────────────────────────────────────
    if page == "📊 Overview":
        page_overview(engine)
    elif page == "🧑 Patient Monitor":
        page_patient_monitor(engine)
    elif page == "🚨 Alerts":
        page_alerts(engine)
    elif page == "🤖 ML Insights":
        page_ml_insights(engine)


def page_overview(engine):
    st.title("📊 Platform Overview")

    stats = load_kpi_stats(engine)
    risk_df = load_risk_summary(engine)

    # KPI Row
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("🏥 Active Patients",    stats['total_patients'])
    with c2:
        st.metric("🚨 Active Alerts",       stats['active_alerts'],
                  delta=f"{stats['critical_alerts']} critical", delta_color="inverse")
    with c3:
        st.metric("⚠️ High Risk Patients",  stats['high_risk_patients'])
    with c4:
        st.metric("📡 Monitoring Coverage", "95%", "+5% vs target")

    st.divider()

    # Risk distribution donut
    col1, col2 = st.columns([1, 2])
    with col1:
        if not risk_df.empty and 'risk_level' in risk_df.columns:
            dist = risk_df['risk_level'].value_counts().reset_index()
            dist.columns = ['Risk Level', 'Count']
            fig = px.pie(dist, values='Count', names='Risk Level',
                         hole=0.5, title="Risk Distribution",
                         color='Risk Level',
                         color_discrete_map={
                             'LOW': '#27ae60', 'MEDIUM': '#f39c12',
                             'HIGH': '#e67e22', 'CRITICAL': '#c0392b'
                         })
            fig.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font_color='#e0e0e0', margin=dict(t=40, b=0, l=0, r=0)
            )
            st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Patient Risk Table")
        if not risk_df.empty:
            display = risk_df[['patient_id', 'full_name', 'age', 'ward',
                               'risk_level', 'risk_score', 'active_alerts']].head(15)
            display['risk_score'] = display['risk_score'].apply(
                lambda x: f"{x:.1%}" if pd.notnull(x) else "—")
            st.dataframe(display, hide_index=True, use_container_width=True)


def page_patient_monitor(engine):
    st.title("🧑 Patient Vital Monitor")
    risk_df = load_risk_summary(engine)
    if risk_df.empty:
        st.warning("No patient data found.")
        return

    # Dict lookup removes pandas Series ambiguity
    name_lookup = dict(zip(risk_df['patient_id'], risk_df['full_name']))

    def _fmt(pid: str) -> str:
        name = name_lookup.get(pid)
        return f"{pid} — {name}" if pd.notnull(name) else f"{pid} — Patient"

    patient_id = st.selectbox(
        "Select Patient",
        risk_df['patient_id'].tolist(),
        format_func=_fmt
    )

    if not patient_id:
        st.info("No patient selected.")
        return

    hours = st.slider("Time Window (hours)", 1, 48, 24)
    vitals = load_vitals_for_patient(engine, patient_id, hours)

    if vitals.empty:
        st.info("No recent vital readings for this patient.")
        return

    vitals['timestamp'] = pd.to_datetime(vitals['timestamp'])

    for param, label, color, lo, hi in [
        ('heart_rate',        '❤️ Heart Rate (bpm)',      '#e74c3c', 50, 120),
        ('oxygen_saturation', '💨 SpO₂ (%)',              '#3498db', 93, 100),
        ('bp_systolic',       '🩸 BP Systolic (mmHg)',    '#9b59b6', 90, 160),
        ('temperature',       '🌡️ Temperature (°C)',      '#e67e22', 36.0, 38.5),
    ]:
        if param not in vitals.columns:
            continue
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=vitals['timestamp'], y=vitals[param],
                                 mode='lines+markers', name=label, line_color=color))
        fig.add_hline(y=hi, line_dash='dash', line_color='#e74c3c',
                      opacity=0.5, annotation_text="Upper limit")
        fig.add_hline(y=lo, line_dash='dash', line_color='#3498db',
                      opacity=0.5, annotation_text="Lower limit")
        fig.update_layout(title=label, paper_bgcolor='rgba(0,0,0,0)',
                          plot_bgcolor='rgba(13,27,42,0.8)',
                          font_color='#e0e0e0', height=220, margin=dict(t=30, b=20))
        st.plotly_chart(fig, use_container_width=True)


def page_alerts(engine):
    st.title("🚨 Active Alerts")
    alerts = load_active_alerts(engine)

    if alerts.empty:
        st.success("✅ No active alerts at this time.")
        return

    # Severity filter
    sevs = st.multiselect("Filter by severity",
                          ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'],
                          default=['CRITICAL', 'HIGH'])
    if sevs:
        alerts = alerts[alerts['severity'].isin(sevs)]

    for _, row in alerts.iterrows():
        badge = severity_badge(row['severity'])
        with st.container():
            st.markdown(f"""
            {badge} **{row['full_name']}** ({row['patient_id']}) — Ward: `{row['ward']}`
            > {row['message']}
            > *Triggered: {row['triggered_at']} ({row['minutes_ago']:.0f} min ago)*
            """, unsafe_allow_html=True)
            st.divider()


def page_ml_insights(engine):
    st.title("🤖 ML Risk Insights")
    import json
    import os

    metrics_path = 'ml/models/metrics.json'
    if os.path.exists(metrics_path):
        with open(metrics_path) as f:
            metrics = json.load(f)

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Recall",    f"{metrics.get('test_recall', 0):.1%}")
        with c2:
            st.metric("Precision", f"{metrics.get('test_precision', 0):.1%}")
        with c3:
            st.metric("F1-Score",  f"{metrics.get('test_f1', 0):.1%}")
        with c4:
            st.metric("Accuracy",  f"{metrics.get('test_accuracy', 0):.1%}")

        if 'feature_importance' in metrics:
            fi = metrics['feature_importance']
            fig = px.bar(
                x=list(fi.values()), y=list(fi.keys()),
                orientation='h', title="🔍 Top Feature Importances (SHAP)",
                color=list(fi.values()), color_continuous_scale='teal'
            )
            fig.update_layout(paper_bgcolor='rgba(0,0,0,0)',
                              plot_bgcolor='rgba(13,27,42,0.8)',
                              font_color='#e0e0e0', showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("ML model not trained yet. Run: `python ml/train_model.py`")


if __name__ == '__main__':
    main()
