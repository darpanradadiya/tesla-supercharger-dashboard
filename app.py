# app.py

import streamlit as st
import pandas as pd
import plotly.express as px
import pydeck as pdk

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
    # 1) sessions_enhanced.parquet has a 'region' column
    sess = pd.read_parquet("sessions_enhanced.parquet")
    sess["start_time"] = pd.to_datetime(sess["start_time"])
    # 2) stations_enhanced.parquet also has 'region'
    stats = pd.read_parquet("stations_enhanced.parquet")
    # Merge with suffixes so we can pick the station-region
    df = sess.merge(
        stats,
        on="station_id",
        suffixes=("_sess", "_stat")
    )
    # Drop the session-level region, keep station-level region
    df = df.drop(columns=["region_sess"])
    df = df.rename(columns={"region_stat": "region"})
    return df

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
total_sessions = df.session_id.nunique()
avg_wait       = df.wait_time.mean()
total_revenue  = df.revenue.sum()
avg_nps        = df.satisfaction_nps.mean()
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Sessions", f"{total_sessions:,}")
c2.metric("Avg. Wait (min)", f"{avg_wait:.1f}")
c3.metric("Total Revenue", f"${total_revenue:,.0f}")
c4.metric("Avg. NPS", f"{avg_nps:.1f}")

# ─── Tabs ─────────────────────────────────────────────────────────────────────
tabs = st.tabs([
    "👋 Welcome",
    "1️⃣ Utilization Map",
    "2️⃣ Wait Times",
    "3️⃣ Busiest Stations",
    "4️⃣ Revenue vs Cost",
    "5️⃣ Customer Satisfaction",
    "♾️ Queue & Capacity",
    "🚀 Expansion Analysis"
])

# Tab 0: Welcome
with tabs[0]:
    st.header("Welcome!")
    st.write(
        "Use the sidebar to filter by date range, charger type, and region, "
        "then explore each tab for insights on utilization, wait times, station performance, profitability, and expansion planning."
    )

# Tab 1: Utilization Map
with tabs[1]:
    st.header("Network Utilization Map")
    style = st.selectbox(
        "Map Style",
        ["Plotly Scatter Mapbox", "Density Heatmap"]
    )

    util = (
        df.groupby(["station_id","station_name","lat","lon"])
          .agg(sessions=("session_id","count"), avg_wait=("wait_time","mean"))
          .reset_index()
    )

    if style == "Plotly Scatter Mapbox":
        util["size"]  = util.sessions / util.sessions.max() * 50
        util["color"] = (
            util.avg_wait - util.avg_wait.min()
        ) / (
            util.avg_wait.max() - util.avg_wait.min()
        )
        fig = px.scatter_mapbox(
            util,
            lat="lat",
            lon="lon",
            size="size",
            color="color",
            hover_name="station_name",
            hover_data=["sessions","avg_wait"],
            color_continuous_scale="Reds",
            size_max=50
        )
        fig.update_layout(
            mapbox_style="open-street-map",
            margin={"l":0,"r":0,"t":30,"b":0}
        )
        st.plotly_chart(fig, use_container_width=True)

    else:  # Density Heatmap
        fig = px.density_mapbox(
            util,
            lat="lat",
            lon="lon",
            z="sessions",
            radius=25,
            center={"lat":util.lat.mean(),"lon":util.lon.mean()},
            zoom=4,
            mapbox_style="open-street-map",
            color_continuous_scale="Reds"
        )
        st.plotly_chart(fig, use_container_width=True)

# Tab 2: Wait Times
with tabs[2]:
    st.header("Average Wait Time Over Time")
    ts = df.set_index("start_time").resample("D").wait_time.mean().reset_index()
    fig = px.line(
        ts,
        x="start_time",
        y="wait_time",
        title="Daily Avg. Wait Time (mins)",
        color_discrete_sequence=[PRIMARY_RED],
        labels={"start_time":"Date","wait_time":"Wait (mins)"}
    )
    st.plotly_chart(fig, use_container_width=True)
    with st.expander("Download CSV"):
        st.download_button("Download", ts.to_csv(index=False), "wait_times.csv", "text/csv")

# Tab 3: Busiest Stations
with tabs[3]:
    st.header("Top 10 Busiest Stations")
    top10 = (
        df.station_name
          .value_counts()
          .nlargest(10)
          .rename_axis("station_name")
          .reset_index(name="sessions")
    )
    fig = px.bar(
        top10,
        x="sessions",
        y="station_name",
        orientation="h",
        title="Sessions by Station",
        color_discrete_sequence=[PRIMARY_RED],
        labels={"sessions":"Sessions","station_name":"Station"}
    )
    st.plotly_chart(fig, use_container_width=True)
    with st.expander("Download CSV"):
        st.download_button("Download", top10.to_csv(index=False), "top10_stations.csv", "text/csv")

# Tab 4: Revenue vs Cost
with tabs[4]:
    st.header("Revenue vs. Cost per Station")
    revcost = (
        df.groupby("station_name")
          .agg({"revenue":"sum","cost":"sum"})
          .reset_index()
    )
    fig = px.bar(
        revcost,
        x="station_name",
        y=["revenue","cost"],
        barmode="group",
        title="Total Revenue vs Total Cost",
        color_discrete_map={"revenue":PRIMARY_RED,"cost":DARK_BG},
        labels={"value":"USD","station_name":"Station","variable":"Metric"}
    )
    st.plotly_chart(fig, use_container_width=True)
    with st.expander("Download CSV"):
        st.download_button("Download", revcost.to_csv(index=False), "revenue_vs_cost.csv", "text/csv")

# Tab 5: Customer Satisfaction
with tabs[5]:
    st.header("Customer Satisfaction (NPS) by Region")
    nps = df.groupby("region").satisfaction_nps.mean().reset_index()
    fig = px.bar(
        nps,
        x="region",
        y="satisfaction_nps",
        color_discrete_sequence=[PRIMARY_RED],
        labels={"region":"Region","satisfaction_nps":"NPS"}
    )
    st.plotly_chart(fig, use_container_width=True)
    with st.expander("Download CSV"):
        st.download_button("Download", nps.to_csv(index=False), "nps_by_region.csv", "text/csv")

# Tab 6: Queue & Capacity
with tabs[6]:
    st.header("Queue & Capacity Analysis")
    fig_q = px.box(
        df,
        x="station_name",
        y="queue_length",
        color_discrete_sequence=[PRIMARY_RED],
        labels={"station_name":"Station","queue_length":"Queue Length"}
    )
    fig_q.update_layout(xaxis={"categoryorder":"total descending"})
    st.plotly_chart(fig_q, use_container_width=True)

    fig_i = px.box(
        df,
        x="station_name",
        y="idle_time",
        color_discrete_sequence=[DARK_BG],
        labels={"station_name":"Station","idle_time":"Idle Ports"}
    )
    fig_i.update_layout(xaxis={"categoryorder":"total descending"})
    st.plotly_chart(fig_i, use_container_width=True)

    with st.expander("Download CSV"):
        st.download_button(
            "Download",
            df[["station_name","queue_length","idle_time"]].to_csv(index=False),
            "queue_capacity.csv",
            "text/csv"
        )

# Tab 7: Expansion Analysis
with tabs[7]:
    st.header("Expansion Analysis")
    stats = pd.read_parquet("stations_enhanced.parquet")
    exp = stats.sort_values("expansion_benefit", ascending=False)[
        ["station_name","nearest_dist_km","expansion_benefit"]
    ].head(10)
    st.subheader("Top 10 Stations by Expansion Benefit")
    st.dataframe(exp, use_container_width=True)

    with st.expander("Download CSV"):
        st.download_button(
            "Download",
            stats.to_csv(index=False),
            "stations_expansion.csv",
            "text/csv"
        )

    icon_layer_exp = pdk.Layer(
        "IconLayer",
        data=stats,
        pickable=True,
        icon_atlas="https://raw.githubusercontent.com/visgl/deck.gl-data/master/website/icon-atlas.png",
        icon_mapping={"marker": {"x": 0, "y": 0, "width": 128, "height": 128, "anchorY": 128}},
        get_icon='"marker"',
        get_size="expansion_benefit * 100",
        size_scale=1,
        get_position=["lon","lat"],
        get_color="[0, expansion_benefit*255, 0]"
    )
    view_state_exp = pdk.ViewState(
        latitude=stats.lat.mean(),
        longitude=stats.lon.mean(),
        zoom=4
    )
    st.pydeck_chart(
        pdk.Deck(layers=[icon_layer_exp], initial_view_state=view_state_exp),
        use_container_width=True
    )
