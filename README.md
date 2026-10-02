# Fleet Twin — ELD busy box

A simulated ELD feed turned into a live operations view: field-vehicle map, event feed, and a **stage draft of the paid money view** (utilization · drive/dwell hours · revenue-at-rate).

This is a busy box — a working prototype built to spec the design of a real product. Simulated data, single-user, no persistence of business logic. It is **not** the product.

## What it demos

| Piece | What it shows |
|---|---|
| Live map (Folium) | vehicle trails, live positions, speed, event markers |
| Event feed | departures, scans, stops, deliveries, idling, harsh events — per-vehicle counts |
| Money view (draft) | distance, drive vs dwell hours, utilization %, weekly revenue at a configurable $/drive-hour rate |

The money-view tab is the point: it exists to answer *"what does the paid layer look like?"* before the React build.

## Run

```bash
uv sync
uv run streamlit run app.py
```

Requires Python ≥ 3.11. Data is seeded into `twin.db` on first run (SQLite, 3 simulated vehicles on Halifax-area pseudo-routes).

Feed controls (sidebar): advance time +1/+10 min, auto-advance, reset feed, pick vehicles, window size, revenue rate.

## Layout

```
app.py        Streamlit app: map / events / money-view tabs
tests/        smoke test (app imports, db seeds, money-view math)
twin.db       created at runtime — not committed
```

## Data model

- `vehicles` — id, name, route, load type, color
- `positions` — vehicle_id, ts, lat, lon, speed_kmh, heading
- `events` — vehicle_id, ts, kind, detail, lat, lon

## Why it exists

Build the busy box → extract the real requirements → build the React stage. The draft money view assumes a flat $/drive-hour placeholder; the real product needs: telemetry ingest, accounts, saved layouts, trip playback, invoicing. Scope for that work lives per the project plan, not in this repo.

## Test

```bash
uv run pytest
```

---

Built as a public artifact — simulated telemetry only, no fleet data, no production keys.