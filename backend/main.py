from fastapi import FastAPI, HTTPException, Depends, Security, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel, EmailStr
from typing import Optional, List
import os
import json
import ee
from datetime import datetime

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
# API Key Authentication
# ---------------------------------------------------------------------- #
API_KEY_NAME = "X-Admin-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY")
if not ADMIN_API_KEY:
    ADMIN_API_KEY = "floodwatch_admin_secret"
    print(f"[WARNING] ADMIN_API_KEY environment variable not set. Falling back to default: '{ADMIN_API_KEY}'")

async def get_api_key(header_key: Optional[str] = Security(api_key_header)):
    if not header_key or header_key != ADMIN_API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Could not authenticate. Invalid or missing X-Admin-API-Key header."
        )
    return header_key


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
            print("[OK] GEE initialized with service account!")
        else:
            ee.Initialize(project='flood-analysis-478517')
            print("[OK] GEE initialized with local credentials!")
    except Exception as e:
        print(f"[ERROR] GEE initialization failed: {e}")


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
    print("[OK] Background scheduler started")


@app.on_event("shutdown")
async def shutdown_event():
    stop_scheduler()


# ---------------------------------------------------------------------- #
# Request models & Validation
# ---------------------------------------------------------------------- #
class AnalyzeRequest(BaseModel):
    location: str
    before_start_date: str
    before_end_date: str
    after_start_date: str
    after_end_date: str
    lat: Optional[float] = None
    lon: Optional[float] = None


def validate_analyze_request(req: AnalyzeRequest):
    def parse_date(d_str, field_name):
        for fmt in ('%d-%m-%Y', '%Y-%m-%d'):
            try:
                return datetime.strptime(d_str, fmt)
            except ValueError:
                pass
        raise HTTPException(
            status_code=422,
            detail=f"Invalid date format for '{field_name}': '{d_str}'. Must be in DD-MM-YYYY or YYYY-MM-DD format."
        )

    b_start = parse_date(req.before_start_date, "before_start_date")
    b_end = parse_date(req.before_end_date, "before_end_date")
    a_start = parse_date(req.after_start_date, "after_start_date")
    a_end = parse_date(req.after_end_date, "after_end_date")

    if b_start > b_end:
        raise HTTPException(status_code=422, detail="Before start date must be before or equal to before end date.")
    if a_start > a_end:
        raise HTTPException(status_code=422, detail="After start date must be before or equal to after end date.")
    if b_end >= a_start:
        raise HTTPException(status_code=422, detail="Baseline period (before) must end before the current period (after) starts.")

    # Validate coordinates if provided
    if req.lat is not None:
        if req.lat < -90 or req.lat > 90:
            raise HTTPException(status_code=422, detail="Latitude must be between -90 and 90.")
    if req.lon is not None:
        if req.lon < -180 or req.lon > 180:
            raise HTTPException(status_code=422, detail="Longitude must be between -180 and 180.")

    # Validate location name
    if not req.location.strip():
        raise HTTPException(status_code=422, detail="Location name cannot be empty.")

    # If coordinates are not provided, make sure we can resolve the location
    if req.lat is None or req.lon is None:
        location_lower = req.location.lower().strip()
        from config import CITY_COORDINATES
        if location_lower not in CITY_COORDINATES:
            try:
                parts = req.location.split(',')
                if len(parts) != 2:
                    raise ValueError()
                float(parts[0].strip())
                float(parts[1].strip())
            except ValueError:
                raise HTTPException(
                    status_code=422,
                    detail=f"Location '{req.location}' is not a recognized city. Please select from autocomplete or enter as 'latitude, longitude'."
                )


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
    validate_analyze_request(request)
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
async def subscribe(req: SubscribeRequest, background_tasks: BackgroundTasks):
    result = alarm_system.subscribe(req.email, req.name, req.cities)
    if result.get('status') in ('subscribed', 'updated'):
        background_tasks.add_task(reporter.send_welcome_email, req.email, req.name, req.cities)
        background_tasks.add_task(reporter.send_personalized_report_to_email, req.email, req.name, req.cities)
    result["email_status"] = {"status": "queued"}
    return JSONResponse(content=result)


@app.get("/debug-email")
async def debug_email(email: str):
    """Helper endpoint to test and diagnose email sending failures."""
    welcome_res = reporter.send_welcome_email(email, "Debug User", ["Mumbai"])
    report_res = reporter.send_personalized_report_to_email(email, "Debug User", ["Mumbai"])
    return JSONResponse(content={
        "sender_configured": bool(reporter.sender_email),
        "sender_email": reporter.sender_email,
        "welcome_status": welcome_res,
        "report_status": report_res
    })


@app.post("/unsubscribe")
async def unsubscribe(req: UnsubscribeRequest):
    result = alarm_system.unsubscribe(req.email)
    return JSONResponse(content=result)


@app.get("/subscribers")
async def list_subscribers(api_key: str = Depends(get_api_key)):
    """Admin endpoint — list all active subscribers."""
    return JSONResponse(content=alarm_system.get_subscribers())


# ---------------------------------------------------------------------- #
# Phase 2 — Email Report Routes
# ---------------------------------------------------------------------- #
@app.post("/report/send")
async def send_report(api_key: str = Depends(get_api_key)):
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



# Static file serving

@app.get("/styles.css")
async def styles():
    return FileResponse(os.path.join(frontend_dir, 'styles.css'))


@app.get("/script.js")
async def script():
    return FileResponse(os.path.join(frontend_dir, 'script.js'))


@app.get("/")
async def index():
    return FileResponse(os.path.join(frontend_dir, 'index.html'))