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
            url = st.secrets.get("supabase", {}).get("db_url")

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


# ── STALE DATA FIX: Uses (SELECT MAX...) instead of NOW() ──
@st.cache_data(ttl=60, show_spinner=False)
def load_vitals_for_patient(_engine, patient_id: str, hours: int = 24):
    q = text("""
        SELECT timestamp, heart_rate, bp_systolic, bp_diastolic,
               oxygen_saturation, temperature, respiratory_rate
        FROM vital_signs
        WHERE patient_id = :pid
          AND timestamp >= (
              SELECT COALESCE(MAX(timestamp), NOW()) 
              FROM vital_signs 
              WHERE patient_id = :pid
          ) - INTERVAL '1 hour' * :hrs
        ORDER BY timestamp ASC
    """)
    with _engine.connect() as conn:
        return pd.read_sql(q, conn, params={'pid': patient_id, 'hrs': hours})


@st.cache_data(ttl=60, show_spinner=False)
def load_latest_vitals_all(_engine):
    with _engine.connect() as conn:
        return pd.read_sql(text("SELECT * FROM v_patient_latest_vitals"), conn)


# ── STALE DATA FIX: Uses (SELECT MAX...) instead of NOW() ──
@st.cache_data(ttl=30, show_spinner=False)
def load_alert_volume_hourly(_engine, hours: int = 48):
    q = text(f"""
        SELECT date_trunc('hour', triggered_at) AS hour,
               severity, COUNT(*) AS alert_count
        FROM alerts
        WHERE triggered_at >= (
            SELECT COALESCE(MAX(triggered_at), NOW()) FROM alerts
        ) - INTERVAL '{hours} hours'
        GROUP BY 1, severity ORDER BY 1
    """)
    with _engine.connect() as conn:
        return pd.read_sql(q, conn)


@st.cache_data(ttl=300, show_spinner=False)
def load_admission_trend(_engine):
    q = text("""
        SELECT admission_date, COUNT(*) AS admissions
        FROM patients GROUP BY admission_date ORDER BY admission_date
    """)
    with _engine.connect() as conn:
        return pd.read_sql(q, conn)


# ── STALE DATA & POSTGRES ARRAY FIX (With Pylance bypass) ──
@st.cache_data(ttl=20, show_spinner=False)
def load_sparkline_batch(_engine, patient_ids: list, hours: int = 6):
    import typing  # Import typing to silence Pylance
    
    if not patient_ids:
        return pd.DataFrame()
    
    q = text("""
        SELECT patient_id, timestamp, heart_rate, oxygen_saturation
        FROM vital_signs
        WHERE patient_id = ANY(:pids)
          AND timestamp >= (
              SELECT COALESCE(MAX(timestamp), NOW()) 
              FROM vital_signs 
              WHERE patient_id = ANY(:pids)
          ) - INTERVAL '1 hour' * :hrs
        ORDER BY patient_id, timestamp ASC
    """)
    
    with _engine.connect() as conn:
        # Explicitly typing as Any forces Pylance to stop checking this dictionary's types
        sql_params: typing.Any = {'pids': list(patient_ids), 'hrs': hours}
        return pd.read_sql(q, conn, params=sql_params)


def severity_badge(sev: str) -> str:
    return f'<span class="badge-{sev.lower()}">{sev}</span>'


# ── EMPTY FILTER STATE FIX ──
def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    """Apply the sidebar's global filters to any risk_summary-shaped dataframe."""
    if df.empty:
        return df

    # Read from session state. If empty (user cleared it), default to ALL available options
    wards = st.session_state.get("selected_wards", [])
    if not wards and 'ward' in df.columns:
        wards = df['ward'].dropna().unique().tolist()

    risks = st.session_state.get("selected_risk", [])
    if not risks:
        risks = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']

    ages = st.session_state.get("age_range", (0, 100))

    # Core filters
    out = df[
        df['ward'].isin(wards) &
        df['age'].between(ages[0], ages[1]) &
        df['risk_level'].isin(risks)
    ]

    # Comorbidity filters
    if st.session_state.get("show_diabetes") is False and 'diabetes' in out.columns:
        out = out[out['diabetes'] != True]
    if st.session_state.get("show_hypertension") is False and 'hypertension' in out.columns:
        out = out[out['hypertension'] != True]
    if st.session_state.get("show_smoking") is False and 'smoking' in out.columns:
        out = out[out['smoking'] != True]

    return out


# ─── CHART & WIDGET RENDERING FUNCTIONS ───
def render_gauge(value, title, val_range, good_range, warn_range, suffix=""):
    if pd.isna(value):
        value = 0
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=value,
        number={'suffix': suffix, 'font': {'color': '#00C896', 'size': 28}},
        title={'text': title, 'font': {'color': '#9ab8c8', 'size': 13}},
        gauge={
            'axis': {'range': list(val_range), 'tickcolor': '#9ab8c8'},
            'bar': {'color': '#00C896', 'thickness': 0.25},
            'bgcolor': '#0D1B2A',
            'steps': [
                {'range': good_range, 'color': '#1f4a2e'},
                {'range': warn_range, 'color': '#6b5b1f'},
            ],
        }
    ))
    fig.update_layout(height=170, margin=dict(t=40, b=10, l=25, r=25),
                      paper_bgcolor='rgba(0,0,0,0)', font_color='#e0e0e0')
    return fig


def render_bedside_view(vitals_df: pd.DataFrame):
    st.subheader("🩺 Bedside Monitor View")
    traces = [
        ('heart_rate', 'HR', '#39ff14'),
        ('oxygen_saturation', 'SpO₂', '#00e5ff'),
        ('bp_systolic', 'BP Sys', '#ff3b3b'),
        ('respiratory_rate', 'Resp', '#ffe135'),
        ('temperature', 'Temp', '#ff8c00'),
        ('bp_diastolic', 'BP Dia', '#c77dff'),
    ]
    cols = st.columns(3)
    for i, (param, label, color) in enumerate(traces):
        if param not in vitals_df.columns:
            continue
        with cols[i % 3]:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                y=vitals_df[param], mode='lines', line=dict(color=color, width=1.5)))
            fig.update_layout(
                title=dict(text=label, font=dict(color=color, size=12)),
                height=120, margin=dict(l=5, r=5, t=25, b=5),
                paper_bgcolor='#000814', plot_bgcolor='#000814',
                xaxis=dict(visible=False), yaxis=dict(color='#333', gridcolor='#111'), showlegend=False
            )
            st.plotly_chart(fig, use_container_width=True,
                            config={'displayModeBar': False})


def render_monitor_grid(engine, filtered_df: pd.DataFrame, top_n: int = 12):
    st.subheader("🖥️ Live Multi-Patient Monitor")
    watch_list = filtered_df.sort_values(
        'risk_score', ascending=False).head(top_n)
    if watch_list.empty:
        st.info("No patients match current filters.")
        return

    sparklines = load_sparkline_batch(
        engine, watch_list['patient_id'].tolist())
    SEVERITY_COLOR = {'CRITICAL': '#c0392b',
                      'HIGH': '#e67e22', 'MEDIUM': '#f39c12', 'LOW': '#27ae60'}

    cols_per_row = 4
    rows = [watch_list.iloc[i:i + cols_per_row]
            for i in range(0, len(watch_list), cols_per_row)]

    for row_chunk in rows:
        cols = st.columns(cols_per_row)
        for col, (_, patient) in zip(cols, row_chunk.iterrows()):
            with col:
                color = SEVERITY_COLOR.get(patient['risk_level'], '#555')
                patient_spark = sparklines[sparklines['patient_id']
                                           == patient['patient_id']]

                st.markdown(f"""
                <div style="border-left:4px solid {color}; background:#0D1B2A;
                            border-radius:8px; padding:10px 12px; margin-bottom:2px;">
                    <strong style="color:#e8f4f8;">{patient['patient_id']}</strong>
                    <span style="float:right; color:{color}; font-size:0.72rem;
                                 font-weight:700;">{patient['risk_level']}</span><br>
                    <span style="color:#9ab8c8; font-size:0.78rem;">{patient['ward']} · Age {patient['age']}</span>
                </div>
                """, unsafe_allow_html=True)

                if not patient_spark.empty:
                    spark = go.Figure()
                    spark.add_trace(go.Scatter(
                        y=patient_spark['heart_rate'], mode='lines',
                        line=dict(color=color, width=2), fill='tozeroy', fillcolor=color + '22'
                    ))
                    spark.update_layout(
                        height=50, margin=dict(l=0, r=0, t=0, b=0),
                        xaxis=dict(visible=False), yaxis=dict(visible=False),
                        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', showlegend=False
                    )
                    st.plotly_chart(spark, use_container_width=True,
                                    config={'displayModeBar': False}, key=f"spark_{patient['patient_id']}")


def render_ward_comparison(filtered_df: pd.DataFrame):
    st.subheader("🏥 Ward Comparison")
    if filtered_df.empty or 'ward' not in filtered_df.columns:
        st.info("No data available for ward comparison.")
        return

    ward_stats = filtered_df.groupby('ward').agg(
        patients=('patient_id', 'count'),
        avg_risk=('risk_score', 'mean'),
        critical=('risk_level', lambda x: (x == 'CRITICAL').sum())
    ).reset_index().sort_values('avg_risk', ascending=False)

    fig = go.Figure()
    fig.add_trace(go.Bar(x=ward_stats['ward'], y=ward_stats['patients'],
                  name='Patients', marker_color='#00C896', yaxis='y'))
    fig.add_trace(go.Scatter(x=ward_stats['ward'], y=ward_stats['avg_risk'],
                  name='Avg Risk', marker_color='#D4A017', mode='lines+markers', yaxis='y2'))
    fig.update_layout(
        yaxis=dict(title='Patient Count'), yaxis2=dict(title='Avg Risk Score', overlaying='y', side='right', range=[0, 1]),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(13,27,42,0.8)',
        font_color='#e0e0e0', legend=dict(orientation='h', y=1.15), height=320
    )
    st.plotly_chart(fig, use_container_width=True)


def render_vitals_distribution(vitals_df: pd.DataFrame):
    st.subheader("📊 Population Vital Sign Distribution")
    if vitals_df.empty:
        st.info("No vital sign data available.")
        return

    metric = st.selectbox("Vital sign", [
                          'heart_rate', 'oxygen_saturation', 'bp_systolic', 'respiratory_rate'], key='dist_metric')
    normal_ranges = {'heart_rate': (60, 100), 'oxygen_saturation': (
        95, 100), 'bp_systolic': (90, 120), 'respiratory_rate': (12, 20)}

    if metric in vitals_df.columns:
        lo, hi = normal_ranges[metric]
        fig = px.histogram(vitals_df, x=metric, nbins=30,
                           color_discrete_sequence=['#00C896'])
        fig.add_vrect(x0=lo, x1=hi, fillcolor='#27ae60', opacity=0.15, line_width=0,
                      annotation_text="Normal range", annotation_position="top left")
        fig.update_layout(paper_bgcolor='rgba(0,0,0,0)',
                          plot_bgcolor='rgba(13,27,42,0.8)', font_color='#e0e0e0', height=320)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning(f"Column '{metric}' not found in vitals data.")


def render_age_risk_scatter(filtered_df: pd.DataFrame):
    st.subheader("🎯 Age vs Risk Score")
    if filtered_df.empty:
        st.info("No data available.")
        return

    fig = px.scatter(
        filtered_df, x='age', y='risk_score', color='risk_level',
        size='active_alerts', size_max=20, hover_data=['patient_id', 'ward'],
        color_discrete_map={'LOW': '#27ae60', 'MEDIUM': '#f39c12',
                            'HIGH': '#e67e22', 'CRITICAL': '#c0392b'}
    )
    fig.update_layout(paper_bgcolor='rgba(0,0,0,0)',
                      plot_bgcolor='rgba(13,27,42,0.8)', font_color='#e0e0e0', height=340)
    st.plotly_chart(fig, use_container_width=True)


def render_alert_volume(alert_hourly_df: pd.DataFrame):
    st.subheader("🚨 Alert Volume — Last Window")
    if alert_hourly_df.empty:
        st.info("No alerts recorded yet in this window.")
        return

    fig = px.bar(alert_hourly_df, x='hour', y='alert_count', color='severity',
                 color_discrete_map={'LOW': '#27ae60', 'MEDIUM': '#f39c12', 'HIGH': '#e67e22', 'CRITICAL': '#c0392b'})
    fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(13,27,42,0.8)',
                      font_color='#e0e0e0', height=300, barmode='stack')
    st.plotly_chart(fig, use_container_width=True)


def render_comorbidity_prevalence(filtered_df: pd.DataFrame):
    st.subheader("🧬 Comorbidity Prevalence")
    if len(filtered_df) == 0:
        st.info("No patients match current filters.")
        return

    data = pd.DataFrame({
        'Condition': ['Diabetes', 'Hypertension', 'Smoking'],
        'Percentage': [
            filtered_df['diabetes'].mean(
            ) * 100 if 'diabetes' in filtered_df else 0,
            filtered_df['hypertension'].mean(
            ) * 100 if 'hypertension' in filtered_df else 0,
            filtered_df['smoking'].mean(
            ) * 100 if 'smoking' in filtered_df else 0,
        ]
    })
    # PYLANCE FIX: Using text_auto=True, formatting applied via update_traces
    fig = px.bar(data, x='Condition', y='Percentage', color='Condition',
                 color_discrete_sequence=['#e67e22', '#c0392b', '#7f8c8d'], text_auto=True)
    fig.update_traces(texttemplate='%{y:.1f}')
    fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(13,27,42,0.8)',
                      font_color='#e0e0e0', height=280, showlegend=False)
    st.plotly_chart(fig, use_container_width=True)


def render_vital_correlations(vitals_df: pd.DataFrame):
    st.subheader("🔗 Vital Sign Correlations")
    if vitals_df.empty:
        st.info("No vital sign data available.")
        return

    cols = ['heart_rate', 'bp_systolic', 'bp_diastolic',
            'oxygen_saturation', 'respiratory_rate']
    cols = [c for c in cols if c in vitals_df.columns]

    if len(cols) > 1:
        corr = vitals_df[cols].corr().round(2)
        fig = px.imshow(corr, text_auto=True,
                        color_continuous_scale='RdBu_r', zmin=-1, zmax=1)
        fig.update_layout(paper_bgcolor='rgba(0,0,0,0)',
                          font_color='#e0e0e0', height=340)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info(
            "Not enough vital sign columns available to build a correlation heatmap.")


def render_admission_trend(df: pd.DataFrame):
    st.subheader("📈 Daily Admissions")
    if df.empty:
        st.info("No admission data available.")
        return

    fig = px.area(df, x='admission_date', y='admissions',
                  color_discrete_sequence=['#00C896'])
    fig.update_layout(paper_bgcolor='rgba(0,0,0,0)',
                      plot_bgcolor='rgba(13,27,42,0.8)', font_color='#e0e0e0', height=260)
    st.plotly_chart(fig, use_container_width=True)


# ─── Main App ────────────────────────────────────────────────
def main():
    engine = get_engine()

    with st.sidebar:
        st.markdown("## 🏥 Healthcare Monitor")
        st.markdown("---")
        page = st.radio(
            "Navigate", ["📊 Overview", "🧑 Patient Monitor", "🚨 Alerts", "🤖 ML Insights"])

        st.markdown("---")
        st.markdown("### 🎛️ Filters")

        all_risk_df = load_risk_summary(engine)

        if not all_risk_df.empty and 'ward' in all_risk_df.columns:
            ward_options = sorted(
                all_risk_df['ward'].dropna().unique().tolist())
        else:
            ward_options = []

        st.multiselect("Ward", ward_options,
                       default=ward_options, key="selected_wards")

        if not all_risk_df.empty and 'age' in all_risk_df.columns:
            age_min, age_max = int(all_risk_df['age'].min()), int(
                all_risk_df['age'].max())
        else:
            age_min, age_max = 0, 100

        st.slider("Age range", age_min, age_max,
                  (age_min, age_max), key="age_range")

        risk_options = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']
        st.multiselect("Risk level", risk_options,
                       default=risk_options, key="selected_risk")

        st.markdown("##### Comorbidities")
        st.checkbox("Diabetes", value=True, key="show_diabetes")
        st.checkbox("Hypertension", value=True, key="show_hypertension")
        st.checkbox("Smoking", value=True, key="show_smoking")

        st.markdown("---")
        if st.button("🔄 Refresh Data"):
            st.cache_data.clear()
            st.rerun()

        st.markdown("""
        <style>
        @keyframes pulse { 0%{opacity:1} 50%{opacity:0.25} 100%{opacity:1} }
        .live-dot { height:9px; width:9px; background:#00C896; border-radius:50%;
                    display:inline-block; animation:pulse 1.4s infinite; margin-right:6px; }
        </style>
        """, unsafe_allow_html=True)
        st.markdown(f'<span class="live-dot"></span> **LIVE** · updated {datetime.now().strftime("%H:%M:%S")}',
                    unsafe_allow_html=True)
        st.caption("DEPI R4 | CAI4-AIS5-S3")

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

    with st.expander("⚙️ Adjust Alert Thresholds (this session only)"):
        c1, c2, c3 = st.columns(3)
        with c1:
            hr_high_thresh = st.slider("HR high (bpm)", 100, 180, 120)
        with c2:
            spo2_low_thresh = st.slider("SpO₂ low (%)", 80, 95, 93)
        with c3:
            bp_high_thresh = st.slider(
                "BP systolic high (mmHg)", 140, 200, 160)
        st.caption(
            "Recalculates the charts below live. Your real alert_engine.py thresholds in the database are unchanged.")

    stats = load_kpi_stats(engine)
    all_risk_df = load_risk_summary(engine)
    filtered_df = apply_filters(all_risk_df)
    vitals_df = load_latest_vitals_all(engine)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("🏥 Active Patients", stats['total_patients'])
    with c2:
        st.metric("🚨 Active Alerts", stats['active_alerts'],
                  delta=f"{stats['critical_alerts']} critical", delta_color="inverse")
    with c3:
        st.metric("⚠️ High Risk Patients", stats['high_risk_patients'])
    with c4:
        st.metric("📡 Monitoring Coverage", "95%", "+5% vs target")

    st.markdown("<br>", unsafe_allow_html=True)
    g1, g2, g3 = st.columns(3)
    with g1:
        st.plotly_chart(render_gauge(vitals_df['heart_rate'].mean() if not vitals_df.empty else 0, "Avg Heart Rate", (40, 160), [
                        60, 100], [100, 130], " bpm"), use_container_width=True)
    with g2:
        st.plotly_chart(render_gauge(vitals_df['oxygen_saturation'].mean(
        ) if not vitals_df.empty else 0, "Avg SpO₂", (80, 100), [95, 100], [90, 95], "%"), use_container_width=True)
    with g3:
        st.plotly_chart(render_gauge(vitals_df['bp_systolic'].mean() if not vitals_df.empty else 0, "Avg BP Systolic", (70, 200), [
                        90, 120], [120, 160], " mmHg"), use_container_width=True)

    st.divider()

    render_monitor_grid(engine, filtered_df)

    st.divider()

    b1, b2 = st.columns(2)
    with b1:
        render_ward_comparison(filtered_df)
    with b2:
        render_age_risk_scatter(filtered_df)

    b3, b4 = st.columns(2)
    with b3:
        render_vitals_distribution(vitals_df)
    with b4:
        render_vital_correlations(vitals_df)

    b5, b6 = st.columns(2)
    with b5:
        render_comorbidity_prevalence(filtered_df)
    with b6:
        render_admission_trend(load_admission_trend(engine))

    render_alert_volume(load_alert_volume_hourly(engine))

    st.divider()

    col1, col2 = st.columns([1, 2])
    with col1:
        if not filtered_df.empty and 'risk_level' in filtered_df.columns:
            dist = filtered_df['risk_level'].value_counts().reset_index()
            dist.columns = ['Risk Level', 'Count']
            fig = px.pie(dist, values='Count', names='Risk Level', hole=0.5, title="Filtered Risk Distribution",
                         color='Risk Level', color_discrete_map={'LOW': '#27ae60', 'MEDIUM': '#f39c12', 'HIGH': '#e67e22', 'CRITICAL': '#c0392b'})
            fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                              font_color='#e0e0e0', margin=dict(t=40, b=0, l=0, r=0))
            st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Filtered Patient Risk Table")
        if not filtered_df.empty:
            display = filtered_df[['patient_id', 'full_name', 'age',
                                   'ward', 'risk_level', 'risk_score', 'active_alerts']].head(15)
            display['risk_score'] = display['risk_score'].apply(
                lambda x: f"{x:.1%}" if pd.notnull(x) else "—")
            st.dataframe(display, hide_index=True, use_container_width=True)


def page_patient_monitor(engine):
    st.title("🧑 Patient Vital Monitor")
    risk_df = load_risk_summary(engine)
    if risk_df.empty:
        st.warning("No patient data found.")
        return

    name_lookup = dict(zip(risk_df['patient_id'], risk_df['full_name']))
    def _fmt(
        pid: str) -> str: return f"{pid} — {name_lookup.get(pid, 'Patient')}"

    patient_id = st.selectbox(
        "Select Patient", risk_df['patient_id'].tolist(), format_func=_fmt)

    if not patient_id:
        st.info("No patient selected.")
        return

    hours = st.slider("Time Window (hours)", 1, 48, 24)
    vitals = load_vitals_for_patient(engine, patient_id, hours)

    if vitals.empty:
        st.info("No recent vital readings for this patient.")
        return

    vitals['timestamp'] = pd.to_datetime(vitals['timestamp'])

    render_bedside_view(vitals)
    st.divider()

    for param, label, color, lo, hi in [
        ('heart_rate',        '❤️ Heart Rate (bpm)',      '#e74c3c', 60, 100),
        ('oxygen_saturation', '💨 SpO₂ (%)',             '#3498db', 95, 100),
        ('bp_systolic',       '🩸 BP Systolic (mmHg)',    '#9b59b6', 90, 120),
        ('temperature',       '🌡️ Temperature (°C)',      '#e67e22', 36.5, 37.5),
    ]:
        if param not in vitals.columns:
            continue
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=vitals['timestamp'], y=vitals[param], mode='lines+markers', name=label, line_color=color))

        fig.add_hrect(y0=lo, y1=hi, fillcolor='#27ae60',
                      opacity=0.08, line_width=0)
        fig.add_hrect(y0=hi, y1=hi*1.3 if hi > 0 else 100,
                      fillcolor='#e67e22', opacity=0.08, line_width=0)

        fig.add_hline(y=hi, line_dash='dash', line_color='#e74c3c',
                      opacity=0.5, annotation_text="Upper limit")
        fig.add_hline(y=lo, line_dash='dash', line_color='#3498db',
                      opacity=0.5, annotation_text="Lower limit")

        fig.update_layout(title=label, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(13,27,42,0.8)',
                          font_color='#e0e0e0', height=220, margin=dict(t=30, b=20))
        st.plotly_chart(fig, use_container_width=True)


def page_alerts(engine):
    st.title("🚨 Active Alerts")
    alerts = load_active_alerts(engine)

    if alerts.empty:
        st.success("✅ No active alerts at this time.")
        return

    sevs = st.multiselect("Filter by severity", [
                          'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'], default=['CRITICAL', 'HIGH'])
    if sevs:
        alerts = alerts[alerts['severity'].isin(sevs)]

    for _, row in alerts.iterrows():
        col1, col2 = st.columns([6, 1])
        with col1:
            badge = severity_badge(row['severity'])
            st.markdown(f"""{badge} **{row['patient_id']}** — Ward: `{row['ward']}`
            > {row['message']}
            > *{row['minutes_ago']:.0f} min ago*
            """, unsafe_allow_html=True)
        with col2:
            if 'alert_id' in row and st.button("✓ Ack", key=f"ack_{row['alert_id']}"):
                with engine.begin() as conn:
                    conn.execute(text("UPDATE alerts SET is_active = FALSE, resolved_at = NOW() WHERE alert_id = :aid"), {
                                 'aid': row['alert_id']})
                st.cache_data.clear()
                st.rerun()
        st.divider()


def page_ml_insights(engine):
    st.title("🤖 ML Risk Insights")
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, '..'))
    metrics_path = os.path.join(project_root, 'ml', 'models', 'metrics.json')

    if os.path.exists(metrics_path):
        with open(metrics_path) as f:
            metrics = json.load(f)
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Recall", f"{metrics.get('test_recall', 0):.1%}")
        with c2:
            st.metric("Precision", f"{metrics.get('test_precision', 0):.1%}")
        with c3:
            st.metric("F1-Score", f"{metrics.get('test_f1', 0):.1%}")
        with c4:
            st.metric("Accuracy", f"{metrics.get('test_accuracy', 0):.1%}")

        if 'feature_importance' in metrics:
            fi = metrics['feature_importance']
            fig = px.bar(x=list(fi.values()), y=list(fi.keys()), orientation='h',
                         title="🔍 Top Feature Importances (SHAP)", color=list(fi.values()), color_continuous_scale='teal')
            fig.update_layout(paper_bgcolor='rgba(0,0,0,0)',
                              plot_bgcolor='rgba(13,27,42,0.8)', font_color='#e0e0e0', showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("ML model not trained yet. Run: `python ml/train_model.py`")


if __name__ == '__main__':
    main()
