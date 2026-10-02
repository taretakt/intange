"""
Fleet Twin — ELD wedge busy box.
Simulated ELD feed in SQLite -> live map + event feed + a
wireframe of the money-view stage. Busy box output: design
spec for the React product lane. Not the product.
"""
import math
import os
import random
import sqlite3
import time as _time
from datetime import datetime, timedelta
from pathlib import Path

import folium
import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit.components.v1 import html as st_html

DB = Path(os.environ.get("FLEET_DB", Path(__file__).parent / "twin.db"))

VEHICLES = [
    {"id": "V1", "name": "Halifax West", "route": "Wharf St loop", "load": "dry van", "color": "#2E86AB"},
    {"id": "V2", "name": "Bedford Run", "route": "Bedford Hwy corridor", "load": "reefer", "color": "#A23B72"},
    {"id": "V3", "name": "Dartmouth D1", "route": "Dartmouth crossing", "load": "parcels", "color": "#F4A259"},
]

# (lat, lon) starters for each vehicle's pseudo-route
ROUTES = {
    "V1": [(44.645, -63.585), (44.652, -63.590), (44.660, -63.596), (44.668, -63.602), (44.640, -63.578)],
    "V2": [(44.730, -63.680), (44.738, -63.686), (44.745, -63.692), (44.752, -63.698), (44.725, -63.674)],
    "V3": [(44.680, -63.548), (44.688, -63.554), (44.695, -63.560), (44.702, -63.566), (44.676, -63.542)],
}

EVENT_KINDS = [
    ("departure", "left yard"), ("parcel_scan", "scan at pickup"), ("stop_start", "arrived stop"),
    ("stop_end", "left stop"), ("delivery", "drop complete"), ("idling", "idle > 5 min"), ("hard_brake", "harsh event"),
]


def connect():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def _wrap_lon(dx, lon):
    return lon + dx


def seed(con):
    now = int(_time.time())
    for v in VEHICLES:
        wp = ROUTES[v["id"]]
        n = 121  # 60 min at 30 s
        lat, lon = wp[0]
        for i in range(n):
            ts = now - (n - i) * 30
            seg = (i * 3) // len(wp) % len(wp)
            tgt = wp[(seg + 1) % len(wp)]
            lat += (tgt[0] - lat) * 0.06 + random.uniform(-0.0004, 0.0004)
            lon += (tgt[1] - lon) * 0.06 + random.uniform(-0.0004, 0.0004)
            speed = 0.0 if i % 11 == 0 else random.uniform(18, 62)
            heading = random.uniform(0, 360)
            con.execute(
                "INSERT INTO positions (vehicle_id, ts, lat, lon, speed_kmh, heading) VALUES (?,?,?,?,?,?)",
                (v["id"], ts, lat, lon, round(speed, 1), round(heading, 1)),
            )
        # sprinkle events at selected timestamps
        e_ts = sorted((now - random.randint(0, 60) * 60 for _ in range(9)))
        for ts in e_ts:
            kind, detail = random.choice(EVENT_KINDS)
            row = con.execute(
                "SELECT lat, lon FROM positions WHERE vehicle_id=? AND ts<=? ORDER BY ts DESC LIMIT 1",
                (v["id"], ts),
            ).fetchone()
            if row:
                con.execute(
                    "INSERT INTO events (vehicle_id, ts, kind, detail, lat, lon) VALUES (?,?,?,?,?,?)",
                    (v["id"], ts, kind, detail, row["lat"], row["lon"]),
                )


def init_db():
    con = connect()
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS vehicles(
          id TEXT PRIMARY KEY, name TEXT, route TEXT, load_type TEXT, color TEXT);
        CREATE TABLE IF NOT EXISTS positions(
          id INTEGER PRIMARY KEY AUTOINCREMENT, vehicle_id TEXT, ts INTEGER,
          lat REAL, lon REAL, speed_kmh REAL, heading REAL);
        CREATE TABLE IF NOT EXISTS events(
          id INTEGER PRIMARY KEY AUTOINCREMENT, vehicle_id TEXT, ts INTEGER,
          kind TEXT, detail TEXT, lat REAL, lon REAL);
        """
    )
    if con.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0] == 0:
        con.executemany("INSERT INTO vehicles VALUES (?,?,?,?,?)",
                        [(v["id"], v["name"], v["route"], v["load"], v["color"]) for v in VEHICLES])
    if con.execute("SELECT COUNT(*) FROM positions").fetchone()[0] == 0:
        seed(con)
    con.commit()
    con.close()


def advance(con, minutes):
    con.execute("UPDATE positions SET ts = ts + ?", (minutes * 60,))
    con.execute("UPDATE events SET ts = ts + ?", (minutes * 60,))
    con.commit()


def reset_feed():
    con = connect()
    con.execute("DELETE FROM positions")
    con.execute("DELETE FROM events")
    seed(con)
    con.commit()
    con.close()


def latest_ts(con):
    return con.execute("SELECT MAX(ts) FROM positions").fetchone()[0]


def build_map(positions_df, events_df, vmap, center):
    m = folium.Map(location=center, zoom_start=12)
    for vid, g in positions_df.groupby("vehicle_id"):
        pts = [[r.lat, r.lon] for r in g.itertuples()]
        folium.PolyLine(pts, color=vmap[vid]["color"], weight=4).add_to(m)
        last = g.iloc[-1]
        folium.Marker(
            [last.lat, last.lon],
            popup=f"{vmap[vid]['name']} · {last.speed_kmh:.0f} km/h",
            tooltip=vmap[vid]["name"],
            icon=folium.Icon(color="blue", prefix="fa", icon="truck"),
        ).add_to(m)
    for e in events_df.itertuples():
        folium.CircleMarker(
            [e.lat, e.lon], radius=7, color="crimson", fill=True,
            popup=f"{e.kind}: {e.detail}", tooltip=e.kind,
        ).add_to(m)
    return m


def main():
    st.set_page_config(page_title="Fleet Twin — ELD busy box", layout="wide")
    st.title("Fleet Twin — ELD wedge (busy box)")
    st.caption("Simulated ELD feed → live map · SQLite · purpose: design the money-view stage")

    init_db()
    con = connect()
    vmap = {v["id"]: v for v in VEHICLES}

    with st.sidebar:
        st.subheader("Feed controls")
        veh_ids = [v["id"] for v in VEHICLES]
        picked = st.multiselect("Vehicles", veh_ids, default=veh_ids,
                                format_func=lambda x: vmap[x]["name"])
        window_min = st.slider("Window (min)", 10, 120, 40, 5)
        c1, c2 = st.columns(2)
        if c1.button("＋1 min"):
            advance(con, 1)
            st.rerun()
        if c2.button("＋10 min"):
            advance(con, 10)
            st.rerun()
        auto = st.checkbox("Auto-advance (1 min / 2 s)")
        if st.button("Reset feed"):
            reset_feed()
            st.rerun()
        rate = st.number_input("Revenue $/drive-hour (stage draft)", min_value=0.0, value=65.0, step=5.0)

    now = latest_ts(con)
    lo = now - window_min * 60
    if not picked:
        picked = veh_ids
    ph = ",".join("?" * len(picked))
    pos = pd.DataFrame(
        dict(r) for r in con.execute(
            f"SELECT * FROM positions WHERE vehicle_id IN ({ph}) AND ts BETWEEN ? AND ? ORDER BY ts",
            [*picked, lo, now],
        ).fetchall()
    )
    ev = pd.DataFrame(
        dict(r) for r in con.execute(
            f"SELECT * FROM events WHERE vehicle_id IN ({ph}) AND ts BETWEEN ? AND ? ORDER BY ts",
            [*picked, lo, now],
        ).fetchall()
    )

    tab_map, tab_events, tab_money = st.tabs(["Live map", "Event feed", "Money view (stage draft)"])

    with tab_map:
        if pos.empty:
            st.info("No positions in window for the selection.")
        else:
            center = [pos["lat"].mean(), pos["lon"].mean()]
            m = build_map(pos, ev, vmap, center)
            st_html(m.get_root().render(), height=560, scrolling=True)
            last = pos.sort_values("ts").groupby("vehicle_id").tail(1)
            st.dataframe(
                last[["vehicle_id", "lat", "lon", "speed_kmh"]]
                .rename(columns={"vehicle_id": "Vehicle", "lat": "Lat", "lon": "Lon", "speed_kmh": "Speed (km/h)"}),
                use_container_width=True, hide_index=True,
            )

    with tab_events:
        if ev.empty:
            st.info("No events in window.")
        else:
            ev2 = ev.rename(columns={"vehicle_id": "Vehicle", "ts": "Feed time", "kind": "Kind", "detail": "Detail"})
            counts = ev.groupby("vehicle_id")["kind"].count().rename("events")
            fig = px.bar(counts.reset_index(), x="vehicle_id", y="events", color="vehicle_id",
                         title="Events by vehicle (window)")
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(ev2[["Vehicle", "Feed time", "Kind", "Detail"]], use_container_width=True, hide_index=True)

    with tab_money:
        st.subheader("Stage draft — the paid money view")
        st.caption("Provisional outputs for designing the React stage. Not the product.")
        if pos.empty:
            st.info("Advance the feed to generate a window of driving data.")
        else:
            pos2 = pos.sort_values("ts")
            rows = []
            for vid, g in pos2.groupby("vehicle_id"):
                g = g.reset_index(drop=True)
                dt = g["ts"].diff().fillna(30) / 3600.0
                g = g.assign(dt_h=dt)
                dist = float((g["speed_kmh"] * g["dt_h"]).sum())
                drive_h = float((g["speed_kmh"] >= 3).sum() * 30 / 3600)
                dwell_h = float((g["speed_kmh"] < 3).sum() * 30 / 3600)
                util = drive_h / (drive_h + dwell_h) if (drive_h + dwell_h) else 0.0
                rows.append({
                    "Vehicle": vmap[vid]["name"], "km": round(dist, 1),
                    "drive h": round(drive_h, 2), "dwell h": round(dwell_h, 2),
                    "utilisation %": round(util * 100, 1),
                    "weekly $ (draft)": round(drive_h * rate, 0),
                })
            mtab = pd.DataFrame(rows)
            st.dataframe(mtab, use_container_width=True, hide_index=True)
            fig = px.bar(mtab, x="Vehicle", y="weekly $ (draft)", color="Vehicle", title="Draft weekly revenue by vehicle")
            st.plotly_chart(fig, use_container_width=True)
            st.warning(
                "Provisional: placeholder rate, simulated feed. The React stage must add: real telemetry "
                "ingest, accounts, saved layouts, historical trip playback, invoicing. This draft exists "
                "to spec that stage — it is NOT the product."
            )

    st.caption("Fleet Twin busy box — simulated data · sqlite://twin.db · graduate to React on Ross's call")


if __name__ == "__main__":
    main()