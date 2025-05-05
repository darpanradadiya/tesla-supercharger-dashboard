# synthetic_data.py

import pandas as pd
import numpy as np
from faker import Faker
import math

fake = Faker()
np.random.seed(42)

# ─── Utility: Haversine distance ───────────────────────────────────────────────
def haversine(lat1, lon1, lat2, lon2):
    R = 6371  # Earth radius in km
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    Δφ = math.radians(lat2 - lat1)
    Δλ = math.radians(lon2 - lon1)
    a = math.sin(Δφ/2)**2 + math.cos(φ1)*math.cos(φ2)*math.sin(Δλ/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

# ─── 1) Generate station master list ──────────────────────────────────────────
regions = ["North", "South", "East", "West", "Central"]
charger_types = ["V2", "V3"]
stations = []

for sid in range(1, 51):
    stations.append({
        "station_id": sid,
        "station_name": f"SC_{sid:02d}",
        "lat": float(fake.latitude()),
        "lon": float(fake.longitude()),
        "region": np.random.choice(regions),
        "charger_type": np.random.choice(charger_types),
        "num_ports": np.random.randint(4, 21)
    })

stations_df = pd.DataFrame(stations)

# Compute nearest‐neighbor distance & expansion benefit
nearest = []
for _, a in stations_df.iterrows():
    others = stations_df[stations_df.station_id != a.station_id]
    dist = others.apply(lambda r: haversine(a.lat, a.lon, r.lat, r.lon), axis=1).min()
    nearest.append(dist)

stations_df["nearest_dist_km"] = nearest
stations_df["expansion_benefit"] = stations_df["nearest_dist_km"].apply(
    lambda d: np.random.uniform(0.1, 0.3) if d > 30 else 0.0
)

# Write stations
stations_df.to_parquet("stations_enhanced.parquet", index=False)
print("→ stations_enhanced.parquet written (50 stations)")

# ─── 2) Generate enriched sessions ─────────────────────────────────────────────
date_range = pd.date_range("2022-01-01", "2024-12-31", freq="h")
sessions = []

for ts in np.random.choice(date_range, size=25000):
    stn = stations_df.sample(1).iloc[0]
    wait = max(0, np.random.normal(5, 3))
    duration = max(0.5, np.random.normal(30, 10))
    energy = np.random.uniform(10, 75)
    revenue = energy * np.random.uniform(0.25, 0.35)
    cost = energy * np.random.uniform(0.05, 0.10)
    satisfaction = np.clip(np.random.normal(30, 15), -100, 100)
    # capacity & queue
    occ = np.random.uniform(0.5, 1.5) * stn.num_ports
    avg_occ = min(occ, stn.num_ports)
    queue_len = int(max(0, occ - stn.num_ports))
    idle_time = int(max(0, stn.num_ports - occ))

    sessions.append({
        "session_id": fake.uuid4(),
        "station_id": stn.station_id,
        "start_time": ts,
        "end_time": ts + pd.Timedelta(minutes=duration),
        "wait_time": wait,
        "energy_kwh": energy,
        "revenue": revenue,
        "cost": cost,
        "satisfaction_nps": satisfaction,
        "traffic_volume": np.random.randint(100, 1000),
        "temperature_C": np.random.uniform(-10, 35),
        "precip_mm": np.random.exponential(1),
        "local_event": np.random.choice([True, False], p=[0.05, 0.95]),
        "num_ports": stn.num_ports,
        "avg_occupied": avg_occ,
        "queue_length": queue_len,
        "idle_time": idle_time,
        "expansion_benefit": stn.expansion_benefit,
        "region": stn.region
    })

sessions_df = pd.DataFrame(sessions)
sessions_df.to_parquet("sessions_enhanced.parquet", index=False)
print("→ sessions_enhanced.parquet written (25,000 sessions)")
