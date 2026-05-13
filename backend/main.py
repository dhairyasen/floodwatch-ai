from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from pydantic import BaseModel, EmailStr
from typing import Optional, List
import os
import json
import ee

# Initialize FastAPI app
app = FastAPI(title="FloodWatch AI", version="2.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Paths
backend_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(backend_dir)
outputs_dir = os.path.join(project_dir, 'outputs')
frontend_dir = os.path.join(project_dir, 'frontend')

os.makedirs(outputs_dir, exist_ok=True)


# ---------------------------------------------------------------------- #
# GEE Init
# ---------------------------------------------------------------------- #
def init_gee():
    try:
        service_account_key = os.environ.get('GEE_SERVICE_ACCOUNT_KEY')
        if service_account_key:
            if isinstance(service_account_key, str):
                key_data = json.loads(service_account_key)
            else:
                key_data = service_account_key
            key_json_str = json.dumps(key_data)
            credentials = ee.ServiceAccountCredentials(
                key_data['client_email'],
                key_data=key_json_str
            )
            ee.Initialize(credentials, project='flood-analysis-478517')
            print("✓ GEE initialized with service account!")
        else:
            ee.Initialize(project='flood-analysis-478517')
            print("✓ GEE initialized with local credentials!")
    except Exception as e:
        print(f"⚠ GEE initialization failed: {e}")


init_gee()

# Import modules after GEE init
from flood_analysis import FloodAnalyzer
from alarm_system import FloodAlarmSystem
from email_reporter import WeeklyReporter
from scheduler import start_scheduler, stop_scheduler, get_scheduler_status

analyzer = FloodAnalyzer()
alarm_system = FloodAlarmSystem()
reporter = WeeklyReporter()


# ---------------------------------------------------------------------- #
# Startup / Shutdown
# ---------------------------------------------------------------------- #
@app.on_event("startup")
async def startup_event():
    start_scheduler()
    print("✓ Background scheduler started")


@app.on_event("shutdown")
async def shutdown_event():
    stop_scheduler()


# ---------------------------------------------------------------------- #
# Request models
# ---------------------------------------------------------------------- #
class AnalyzeRequest(BaseModel):
    location: str
    before_start_date: str
    before_end_date: str
    after_start_date: str
    after_end_date: str
    lat: Optional[float] = None
    lon: Optional[float] = None


class SubscribeRequest(BaseModel):
    email: str
    name: Optional[str] = ''
    cities: Optional[List[str]] = []


class UnsubscribeRequest(BaseModel):
    email: str


# ---------------------------------------------------------------------- #
# Phase 1 Routes
# ---------------------------------------------------------------------- #
@app.post("/analyze")
async def analyze(request: AnalyzeRequest):
    try:
        results = analyzer.analyze(
            request.location,
            request.before_start_date,
            request.before_end_date,
            request.after_start_date,
            request.after_end_date,
            lat=request.lat,
            lon=request.lon,
        )

        # Phase 2 — auto-evaluate alarm after every analysis
        alarm = alarm_system.evaluate(results)
        results['alarm'] = alarm

        return JSONResponse(content=results)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/outputs/{filename:path}")
async def serve_output(filename: str):
    filepath = os.path.join(outputs_dir, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(filepath)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "2.0.0",
        "message": "FloodWatch AI is running",
        "scheduler": get_scheduler_status(),
    }


# ---------------------------------------------------------------------- #
# Phase 2 — Alarm Routes
# ---------------------------------------------------------------------- #
@app.get("/alarms/latest")
async def latest_alarm():
    """Return the most recent alarm record."""
    alarm = alarm_system.get_latest_alarm()
    if not alarm:
        return JSONResponse(content={"message": "No alarms recorded yet"})
    return JSONResponse(content=alarm)


@app.get("/alarms/history")
async def alarm_history(limit: int = 20):
    """Return the last N alarm records."""
    return JSONResponse(content=alarm_system.get_alarm_history(limit=limit))


# ---------------------------------------------------------------------- #
# Phase 2 — Subscriber Routes
# ---------------------------------------------------------------------- #
@app.post("/subscribe")
async def subscribe(req: SubscribeRequest):
    result = alarm_system.subscribe(req.email, req.name, req.cities)
    return JSONResponse(content=result)


@app.post("/unsubscribe")
async def unsubscribe(req: UnsubscribeRequest):
    result = alarm_system.unsubscribe(req.email)
    return JSONResponse(content=result)


@app.get("/subscribers")
async def list_subscribers():
    """Admin endpoint — list all active subscribers."""
    return JSONResponse(content=alarm_system.get_subscribers())


# ---------------------------------------------------------------------- #
# Phase 2 — Email Report Routes
# ---------------------------------------------------------------------- #
@app.post("/report/send")
async def send_report():
    """Trigger the weekly report email immediately (admin / testing)."""
    try:
        result = reporter.send_weekly_report()
        return JSONResponse(content=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/report/preview", response_class=HTMLResponse)
async def report_preview():
    """Return the current week's report as HTML (for browser preview)."""
    html = reporter.get_report_preview()
    return HTMLResponse(content=html)


@app.get("/scheduler/status")
async def scheduler_status():
    return JSONResponse(content=get_scheduler_status())


# ---------------------------------------------------------------------- #
# Static file serving
# ---------------------------------------------------------------------- #
@app.get("/styles.css")
async def styles():
    return FileResponse(os.path.join(frontend_dir, 'styles.css'))


@app.get("/script.js")
async def script():
    return FileResponse(os.path.join(frontend_dir, 'script.js'))


@app.get("/")
async def index():
    return FileResponse(os.path.join(frontend_dir, 'index.html'))