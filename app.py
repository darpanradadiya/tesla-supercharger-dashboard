# app.py

import streamlit as st
import pandas as pd
import numpy as np
import math
import plotly.express as px
import plotly.graph_objects as go
import pydeck as pdk
import folium
from streamlit_folium import st_folium

# ─── Config & Branding ────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Tesla Supercharger Dashboard",
    layout="wide",
    page_icon="🔌"
)
PRIMARY_RED = "#CC0000"
DARK_BG     = "#171A20"

# ─── Load & merge enhanced data ───────────────────────────────────────────────
@st.cache_data
def load_data():
    sess = pd.read_parquet("sessions_enhanced.parquet")
    sess["start_time"] = pd.to_datetime(sess["start_time"])
    stats = pd.read_parquet("stations_enhanced.parquet")
    df = sess.merge(stats, on="station_id", suffixes=("_sess","_stat"))
    df = df.drop(columns=["region_sess"]).rename(columns={"region_stat":"region"})
    return df

# Cache base Folium map for expansion analysis
def make_base_map(stats):
    m = folium.Map(location=[stats.lat.mean(), stats.lon.mean()], zoom_start=4)
    for _, r in stats.iterrows():
        folium.CircleMarker(
            location=[r.lat, r.lon],
            radius=4,
            color="blue",
            fill=True,
            fill_opacity=0.7
        ).add_to(m)
    return m
# Cache decorator to avoid re-creation
get_base_map = st.cache_data(make_base_map)

# Load data
df = load_data()

# ─── Sidebar Filters ──────────────────────────────────────────────────────────
st.sidebar.header("Filters")
min_date, max_date = st.sidebar.date_input(
    "Date range",
    value=(df.start_time.min().date(), df.start_time.max().date())
)
charger_sel = st.sidebar.multiselect(
    "Charger Type",
    options=sorted(df.charger_type.unique()),
    default=sorted(df.charger_type.unique())
)
region_sel = st.sidebar.multiselect(
    "Region",
    options=sorted(df.region.unique()),
    default=sorted(df.region.unique())
)
# Apply filters
df = df.loc[
    (df.start_time.dt.date >= min_date) &
    (df.start_time.dt.date <= max_date) &
    df.charger_type.isin(charger_sel) &
    df.region.isin(region_sel)
]

# ─── KPI Cards ────────────────────────────────────────────────────────────────
st.markdown("## 🔌 Tesla Supercharger Network Dashboard")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Sessions", f"{df.session_id.nunique():,}")
c2.metric("Avg. Wait (min)", f"{df.wait_time.mean():.1f}")
c3.metric("Total Revenue", f"${df.revenue.sum():,}")
c4.metric("Avg. NPS", f"{df.satisfaction_nps.mean():.1f}")

# ─── Tabs Setup ───────────────────────────────────────────────────────────────
tabs = st.tabs([
    "👋 Welcome",
    "1️⃣ Utilization Map",
    "2️⃣ Wait Times",
    "3️⃣ Busiest Stations",
    "4️⃣ Revenue vs Cost",
    "♾️ Queue & Capacity",
])

# ─── Tab 0: Welcome ───────────────────────────────────────────────────────────
with tabs[0]:
    st.header("Welcome!")
    st.write(
        "Use the sidebar filters to narrow by date range, charger type, and region, "
        "then explore tabs for utilization, wait times, station performance, profitability, and expansion planning."
    )

# ─── Tab 1: Utilization Map ───────────────────────────────────────────────────
with tabs[1]:
    st.header("Network Utilization Map")
    style = st.selectbox("Map Style", ["Plotly Scatter Map", "Density Map"])
    util = (
        df.groupby(["station_id","station_name","lat","lon"])  \
          .agg(sessions=("session_id","count"), avg_wait=("wait_time","mean"))  \
          .reset_index()
    )
    if style == "Plotly Scatter Map":
        util["size"]  = util.sessions / util.sessions.max() * 50
        util["color"] = (util.avg_wait - util.avg_wait.min()) / (util.avg_wait.max() - util.avg_wait.min())
        fig = px.scatter_map(
            util,
            lat="lat", lon="lon",
            size="size", color="color",
            hover_name="station_name",
            hover_data=["sessions","avg_wait"],
            color_continuous_scale="Reds",
            size_max=50,
            zoom=4,
            center={"lat": util.lat.mean(), "lon": util.lon.mean()}
        )
        fig.update_layout(margin=dict(l=0,r=0,t=30,b=0))
        st.plotly_chart(fig, use_container_width=True)
    else:
        fig = px.density_map(
            util,
            lat="lat", lon="lon", z="sessions",
            radius=25,
            zoom=4,
            center={"lat": util.lat.mean(), "lon": util.lon.mean()},
            color_continuous_scale="Reds"
        )
        fig.update_layout(margin=dict(l=0,r=0,t=30,b=0))
        st.plotly_chart(fig, use_container_width=True)

# ─── Tab 2: Wait Times ─────────────────────────────────────────────────────────
with tabs[2]:
    st.header("Average Wait Time Over Time")
    ts = df.set_index("start_time").resample("D").agg({
        "wait_time":"mean",
        "session_id":"count",
        "local_event":"max"
    }).rename(columns={"session_id":"sessions","local_event":"event_occurred"}).reset_index()
    ts["event_occurred"] = ts.event_occurred.fillna(False).astype(bool)
    ts["roll7"] = ts.wait_time.rolling(7, center=True).mean()
    mu, sigma = ts.wait_time.mean(), ts.wait_time.std()
    ts["anomaly"] = ts.wait_time > (mu + 2*sigma)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=ts.start_time, y=ts.wait_time, mode="lines",
                              line=dict(color="rgba(204,0,0,0.2)"), name="Daily Avg Wait"))
    fig.add_trace(go.Scatter(x=ts.start_time, y=ts.roll7, mode="lines",
                              line=dict(color=PRIMARY_RED, width=3), name="7D Rolling Avg"))
    fig.add_trace(go.Scatter(x=ts.loc[ts.anomaly, "start_time"], y=ts.loc[ts.anomaly, "wait_time"],
                              mode="markers", marker=dict(color="black", size=6), name="Anomaly (>2σ)"))
    for d in ts.loc[ts.event_occurred, "start_time"]:
        fig.add_vline(x=d, line_dash="dot", line_color="gray", opacity=0.3)
    fig.update_layout(title="Daily Avg Wait with Rolling Avg, Anomalies & Events",
                      xaxis_title="Date", yaxis_title="Wait (mins)",
                      xaxis=dict(rangeslider=dict(visible=True)),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    st.plotly_chart(fig, use_container_width=True)
    with st.expander("Download CSV"):
        st.download_button("Download", ts.to_csv(index=False), "wait_times.csv", "text/csv")

# ─── Tab 3: Busiest Stations ───────────────────────────────────────────────────
with tabs[3]:
    st.header("Top 10 Busiest Stations")
    top10 = df.station_name.value_counts().nlargest(10)
    top10 = top10.rename_axis("station_name").reset_index(name="sessions")
    fig = px.bar(top10, x="sessions", y="station_name", orientation="h",
                 color_discrete_sequence=[PRIMARY_RED], labels={"sessions":"Sessions","station_name":"Station"},
                 title="Sessions by Station")
    st.plotly_chart(fig, use_container_width=True)
    with st.expander("Download CSV"):
        st.download_button("Download", top10.to_csv(index=False), "top10_stations.csv", "text/csv")

# ─── Tab 4: Revenue vs Cost ────────────────────────────────────────────────────
with tabs[4]:
    st.header("Revenue vs. Cost per Station")
    revcost = df.groupby("station_name").agg({"revenue":"sum","cost":"sum"}).reset_index()
    fig = px.bar(revcost, x="station_name", y=["revenue","cost"], barmode="group",
                 color_discrete_map={"revenue":PRIMARY_RED, "cost":DARK_BG},
                 labels={"value":"USD","station_name":"Station","variable":"Metric"},
                 title="Total Revenue vs Total Cost")
    st.plotly_chart(fig, use_container_width=True)
    with st.expander("Download CSV"):
        st.download_button("Download", revcost.to_csv(index=False), "revenue_vs_cost.csv", "text/csv")

# ─── Tab 5: Queue & Capacity ───────────────────────────────────────────────────
with tabs[5]:
    st.header("Queue & Capacity Analysis (Novice View)")
    medians = df.groupby("station_name").queue_length.median().sort_values(ascending=False)
    top10_q = medians.head(10).index.tolist()
    df["is_top10_q"] = df.station_name.isin(top10_q)
    df["is_top10_i"] = df.station_name.isin(top10_q)
    fig_q = px.box(
        df, x="queue_length", y="station_name", orientation="h",
        category_orders={"station_name": medians.index.tolist()},
        color="is_top10_q", color_discrete_map={True:PRIMARY_RED, False:"#CCCCCC"},
        labels={"queue_length":"Queue Length","station_name":"Station"},
        title="Queue Length Distribution")
    fig_q.add_vline(x=3, line_dash="dash", line_color="darkred", annotation_text=">3 queued", annotation_position="top right")
    st.plotly_chart(fig_q, use_container_width=True)
    fig_i = px.box(
        df, x="idle_time", y="station_name", orientation="h",
        category_orders={"station_name": medians.index.tolist()},
        color="is_top10_i", color_discrete_map={True:DARK_BG, False:"#EEEEEE"},
        labels={"idle_time":"Idle Ports","station_name":"Station"},
        title="Idle Ports Distribution")
    fig_i.add_vline(x=1, line_dash="dash", line_color="gray", annotation_text="<1 idle", annotation_position="top right")
    st.plotly_chart(fig_i, use_container_width=True)
    df.drop(columns=["is_top10_q","is_top10_i"], inplace=True)
    with st.expander("Download CSV"):
        st.download_button("Download", df[["station_name","queue_length","idle_time"]].to_csv(index=False), "queue_capacity.csv", "text/csv")
