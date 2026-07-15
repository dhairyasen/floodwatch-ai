# FloodWatch AI 🌊

An automated flood detection and monitoring system for Indian cities, built on satellite imagery analysis. FloodWatch AI compares water coverage between two time periods to detect new flooding, classify severity, and alert subscribers via automated email reports.

**Live deployment:** [floodwatch-ai.onrender.com](https://floodwatch-ai.onrender.com)

---

## How It Works

FloodWatch AI does **not** use machine learning models. It uses a deterministic, threshold-based remote sensing approach:

1. **Satellite Data** — Pulls Sentinel-2 Level-2A surface reflectance imagery (`COPERNICUS/S2_SR_HARMONIZED`, 10m resolution) via Google Earth Engine, filtered by cloud cover (< 80%).
2. **Water Indices** — Computes NDWI (Normalized Difference Water Index, using Green/NIR bands) and MNDWI (Modified NDWI, using Green/SWIR bands) for a "before" and "after" period.
3. **Water Classification** — A pixel is classified as water if NDWI > 0 **or** MNDWI > 0 (dual-index threshold, no trained classifier involved).
4. **Permanent Water Filtering** — A triple-layer filter removes pre-existing water bodies so only *new* flooding is counted:
   - JRC Global Surface Water dataset (permanent water bodies)
   - Elevation-based ocean/sea exclusion
   - Baseline "before" water exclusion
5. **Severity Classification** — New flooded area (km²) is bucketed into NONE / LOW / MEDIUM / HIGH / CRITICAL, each with recommended emergency-response actions.

### Validated Results
| Location | New Flooded Area | Severity |
|---|---|---|
| Mumbai | 10.82 km² | — |
| Chennai (July 2024) | 18.20 km² | MEDIUM |

---

## Architecture

```
FloodWatch AI/
├── backend/
│   ├── main.py            # FastAPI app — routes, GEE init, startup/shutdown
│   ├── flood_analysis.py  # Core NDWI/MNDWI analysis engine (FloodAnalyzer)
│   ├── config.py          # City coordinates, thresholds, GEE constants
│   ├── alarm_system.py    # Severity classification + alarm persistence + subscribers
│   ├── email_reporter.py  # Weekly HTML email report builder + Gmail SMTP sender
│   ├── scheduler.py       # APScheduler background jobs (weekly report cron)
│   └── server_legacy.py   # Legacy standalone http.server (pre-FastAPI version)
├── frontend/
│   ├── index.html
│   ├── styles.css
│   └── script.js           # Autocomplete (Nominatim), analysis flow, alarm UI, subscriptions
├── outputs/                # Generated charts, maps, JSON (served via /outputs)
└── requirements.txt
```

## Tech Stack

- **Backend:** FastAPI, Google Earth Engine (`earthengine-api`, `geemap`)
- **Data processing:** pandas, numpy, matplotlib, seaborn
- **Mapping:** folium (interactive flood maps)
- **Scheduling:** APScheduler (`BackgroundScheduler`, cron trigger)
- **Email:** `smtplib` over Gmail SMTP SSL (port 465)
- **Frontend:** Vanilla HTML/CSS/JS with Nominatim (OpenStreetMap) location autocomplete

---

## Phase 1 — Core Analysis

- `POST /analyze` — Runs before/after flood analysis for a location and date range, returns water coverage stats, new flooded area, % change, and generated chart/map assets.
- `GET /outputs/{filename}` — Serves generated PNG charts and the interactive Folium HTML map.
- `GET /health` — Health check, includes scheduler status.

## Phase 2 — Alarms, Subscriptions & Reporting

Every `/analyze` call automatically evaluates an alarm based on the new flooded area:

| Severity | Threshold (new flooded area) |
|---|---|
| NONE | 0 – 1.0 km² |
| LOW | 1.0 – 10.0 km² |
| MEDIUM | 10.0 – 50.0 km² |
| HIGH | 50.0 – 100.0 km² |
| CRITICAL | 100+ km² |

**Alarm endpoints:**
- `GET /alarms/latest` — Most recent alarm record
- `GET /alarms/history?limit=20` — Recent alarm history

**Subscriber endpoints:**
- `POST /subscribe` — Subscribe an email to weekly reports (optionally scoped to specific cities)
- `POST /unsubscribe` — Remove a subscriber
- `GET /subscribers` — Admin listing of active subscribers

**Reporting:**
- `POST /report/send` — Manually trigger the weekly HTML email report
- `GET /report/preview` — Preview the current week's report in-browser
- `GET /scheduler/status` — Check background job status
- Automated job runs **every Monday at 08:00 IST** via APScheduler `CronTrigger`

---

## Setup

### Environment Variables
| Variable | Purpose |
|---|---|
| `GEE_SERVICE_ACCOUNT_KEY` | JSON service account credentials for Google Earth Engine |
| `EMAIL_SENDER` | Gmail address used to send weekly reports |
| `EMAIL_PASSWORD` | Gmail **App Password** (not account password) |
| `EMAIL_RECIPIENTS` | Comma-separated fallback recipients if no subscribers exist |

GEE project ID: `flood-analysis-478517` (requires **Earth Engine Resource Writer** IAM role on the service account for tile layer access).

### Install
```bash
pip install -r requirements.txt
```

### Run
```bash
uvicorn main:app --reload
```

---

## Known Limitations

- Requires clear (low cloud cover) satellite imagery — heavy monsoon cloud cover can delay usable passes.
- Coastal/urban water bodies with unusual reflectance profiles may need threshold tuning per region.
- Alarm and subscriber data are stored as local JSON files, not a database — fine for a single-instance deployment, not built for horizontal scaling.

---

## TODO / Next Steps

> Edit this list to reflect what's actually left — it's a starting point, not a confirmed backlog.

- [x] Retire or clearly mark `server.py` as legacy (pre-FastAPI) so tooling doesn't treat it as the active entrypoint
- [x] Migrate alarm/subscriber storage from local JSON files to a proper database (implemented SQLite migration)
- [x] Add automated tests for `FloodAnalyzer`, `FloodAlarmSystem`, and the alarm-severity classification logic
- [x] Verify weekly email report renders correctly across major email clients (Gmail, Outlook)
- [x] Add input validation / error handling around `/analyze` for malformed dates or unsupported locations
- [x] Review project report chapters (verified against `REMOTE SENSING AND GIS PROJECT REPORT.pdf`) for any drift since the last documentation pass
- [x] Confirm frontend alarm history pagination (`Load More`) works correctly beyond 10 records
- [x] Add rate limiting or auth to admin endpoints (`/subscribers`, `/report/send`)

**Ground rule for any tool continuing this work:** no fabricated ML models, accuracy metrics, or methods — the system is strictly NDWI/MNDWI threshold-based on Sentinel-2 imagery, not a trained classifier.

---

*A minor project under the India Space Lab Pilot Program (Disaster Risk Zonation for Urban Flood Management), affiliated with the IIT Roorkee E&ICT Academy AI & Data Science certification.*
