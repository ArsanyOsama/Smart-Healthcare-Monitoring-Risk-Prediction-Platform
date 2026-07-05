# Streamlit Cloud Deployment
*Owner: Ahmed Mostafa*

## Prerequisites
- [ ] GitHub repo is public or connected to Streamlit Cloud
- [ ] Supabase project created and database seeded (run ETL targeting SUPABASE_DB_URL)

## Steps
1. Go to **share.streamlit.io** → sign in with GitHub
2. Click **New app**
3. Select: Repository = `ArsanyOsama/Smart-Healthcare-Monitoring-Risk-Prediction-Platform`  
   Branch = `main`  
   Main file = `dashboard/app.py`
4. Click **Advanced settings** → **Secrets** → paste:
   ```toml
   [supabase]
   db_url = "your-supabase-connection-string"