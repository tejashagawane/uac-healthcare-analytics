import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from statsmodels.tsa.arima.model import ARIMA

# =========================
# PAGE CONFIG
# =========================
st.set_page_config(page_title="UAC Analytics Dashboard", layout="wide")

# =========================
# CUSTOM UI (DARK THEME)
# =========================
st.markdown("""
<style>
.main {
    background-color: #0E1117;
}
h1, h2, h3 {
    color: white;
}
[data-testid="metric-container"] {
    background-color: #1E1E1E;
    border-radius: 10px;
    padding: 15px;
    text-align: center;
    box-shadow: 2px 2px 10px rgba(0,0,0,0.5);
}
</style>
""", unsafe_allow_html=True)

st.title("📊 UAC Healthcare Capacity Dashboard")

# =========================
# LOAD DATA
# =========================
@st.cache_data
def load_data():
    df = pd.read_csv("HHS_Unaccompanied_Alien_Children_Program.csv")

    df.rename(columns={
        'Children apprehended and placed in CBP custody*': 'CBP_Intake',
        'Children in CBP custody': 'CBP_Custody',
        'Children transferred out of CBP custody': 'Transfers_to_HHS',
        'Children in HHS Care': 'HHS_Care',
        'Children discharged from HHS Care': 'HHS_Discharged'
    }, inplace=True)

    cols = ['CBP_Intake','CBP_Custody','Transfers_to_HHS','HHS_Care','HHS_Discharged']
    for col in cols:
        df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', ''), errors='coerce')

    df['Date'] = pd.to_datetime(df['Date'])

    df = df.groupby('Date').sum().reset_index()
    df = df.sort_values('Date')
    df.set_index('Date', inplace=True)

    df = df.asfreq('D')
    df.fillna(method='ffill', inplace=True)

    # Metrics
    df['Total_Load'] = df['CBP_Custody'] + df['HHS_Care']
    df['Net_Intake'] = df['Transfers_to_HHS'] - df['HHS_Discharged']
    df['Cumulative_Load'] = df['Total_Load'].cumsum()
    df['7_day_avg'] = df['Total_Load'].rolling(7).mean()
    df['14_day_avg'] = df['Total_Load'].rolling(14).mean()
    df['Backlog'] = df['Net_Intake'].clip(lower=0).rolling(7).sum()

    # Stress
    df['Stress'] = df['Total_Load'] > df['7_day_avg']

    # Anomaly
    df['Z'] = (df['Total_Load'] - df['Total_Load'].mean()) / df['Total_Load'].std()
    df['Anomaly'] = df['Z'].apply(lambda x: 1 if abs(x) > 2 else 0)

    return df

df = load_data()

# =========================
# SIDEBAR
# =========================
st.sidebar.header("📅 Filters")

start = st.sidebar.date_input("Start Date", df.index.min())
end = st.sidebar.date_input("End Date", df.index.max())

df = df.loc[start:end]

# Export CSV
st.sidebar.subheader("📤 Export Data")
csv = df.to_csv().encode('utf-8')

st.sidebar.download_button(
    label="Download Processed Data",
    data=csv,
    file_name='uac_analysis.csv',
    mime='text/csv'
)

# =========================
# KPI SECTION
# =========================
st.subheader("📌 Key Metrics")

col1, col2, col3, col4, col5 = st.columns(5)

total_load = int(df['Total_Load'].iloc[-1])
net_intake = df['Net_Intake'].mean()
volatility = df['Total_Load'].std()
backlog = df['Backlog'].mean()
efficiency = df['HHS_Discharged'].sum()/df['Transfers_to_HHS'].sum()

def status_color(value, good):
    return "🟢" if good else "🔴"

col1.metric("Total Load", total_load)

col2.metric("Net Intake", round(net_intake,2),
            delta=status_color(net_intake, net_intake < 0))

col3.metric("Volatility", round(volatility,2),
            delta=status_color(volatility, volatility < 2000))

col4.metric("Backlog", round(backlog,2),
            delta=status_color(backlog, backlog < 10))

col5.metric("Efficiency", round(efficiency,2),
            delta=status_color(efficiency, efficiency >= 1))

# =========================
# CHARTS
# =========================
st.subheader("📈 Total System Load")

fig1 = go.Figure()
fig1.add_trace(go.Scatter(x=df.index, y=df['Total_Load'], name="Total Load"))
fig1.add_trace(go.Scatter(x=df.index, y=df['7_day_avg'], name="7 Day Avg"))
fig1.add_trace(go.Scatter(x=df.index, y=df['14_day_avg'], name="14 Day Avg"))
st.plotly_chart(fig1, use_container_width=True)

st.subheader("📊 Cumulative Load")
st.line_chart(df['Cumulative_Load'])

st.subheader("⚖️ Inflow vs Outflow")
st.line_chart(df[['Transfers_to_HHS', 'HHS_Discharged']])

st.subheader("🏥 CBP vs HHS Load")
st.line_chart(df[['CBP_Custody', 'HHS_Care']])

st.subheader("📊 Net Intake Pressure")
st.bar_chart(df['Net_Intake'])

# =========================
# STRESS
# =========================
st.subheader("🚨 Stress Analysis")
stress_days = df[df['Stress']].shape[0]
st.write(f"Total Stress Days: {stress_days}")

# =========================
# ANOMALY
# =========================
st.subheader("🚨 Anomaly Detection")
anomalies = df[df['Anomaly'] == 1]

if not anomalies.empty:
    st.dataframe(anomalies[['Total_Load']])
else:
    st.success("No anomalies detected")

# =========================
# FORECAST
# =========================
st.subheader("🔮 30-Day Forecast")

model = ARIMA(df['Total_Load'], order=(5,1,0)).fit()
forecast = model.forecast(steps=30)

fig2 = go.Figure()
fig2.add_trace(go.Scatter(x=df.index, y=df['Total_Load'], name="Actual"))
fig2.add_trace(go.Scatter(
    x=pd.date_range(df.index[-1], periods=30, freq='D'),
    y=forecast,
    name="Forecast"
))
st.plotly_chart(fig2, use_container_width=True)

# =========================
# INSIGHTS
# =========================
st.subheader("🧠 Key Insights")

if net_intake > 0:
    st.warning("⚠️ System is under pressure (intake > discharge)")
else:
    st.success("✅ System is stable")

if volatility > 2000:
    st.warning("⚠️ High volatility detected")

if stress_days > 50:
    st.warning("⚠️ Frequent stress periods observed")

# =========================
# SUMMARY EXPORT
# =========================
st.subheader("📄 Download Summary")

summary = f"""
UAC Healthcare System Summary

Total Load: {total_load}
Net Intake: {round(net_intake,2)}
Volatility: {round(volatility,2)}
Backlog: {round(backlog,2)}
Efficiency: {round(efficiency,2)}
"""

st.download_button("Download Summary Report", summary, "summary.txt")

# =========================
# METRIC DEFINITIONS
# =========================
st.markdown("## 📘 Metric Definitions")

with st.expander("Click to expand"):
    st.markdown("""
    - **Total Load**: CBP + HHS children  
    - **Net Intake**: Transfers − Discharges  
    - **Volatility**: System fluctuation  
    - **Backlog**: Accumulated pressure  
    - **Efficiency**: Discharge effectiveness  
    """)

# =========================
# FOOTER
# =========================
st.markdown("---")
st.markdown("💡 Built for UAC Healthcare Analytics | Final Submission")