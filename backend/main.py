from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional
import os
import json
import ee

# Initialize FastAPI app
app = FastAPI(title="FloodWatch AI", version="1.0.0")

# CORS middleware - allow all origins
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

# Create outputs directory if not exists
os.makedirs(outputs_dir, exist_ok=True)

# Initialize Earth Engine with Service Account
def init_gee():
    try:
        # Try service account first (for deployment)
        service_account_key = os.environ.get('GEE_SERVICE_ACCOUNT_KEY')
        if service_account_key:
            import json as json_lib
            key_data = json_lib.loads(service_account_key)
            credentials = ee.ServiceAccountCredentials(
                key_data['client_email'],
                key_data=key_data
            )
            ee.Initialize(credentials, project='flood-analysis-478517')
            print("✓ GEE initialized with service account!")
        else:
            # Local development fallback
            ee.Initialize(project='flood-analysis-478517')
            print("✓ GEE initialized with local credentials!")
    except Exception as e:
        print(f"⚠ GEE initialization failed: {e}")

init_gee()

# Import analyzer after GEE init
from flood_analysis import FloodAnalyzer
analyzer = FloodAnalyzer()

# Request model
class AnalyzeRequest(BaseModel):
    location: str
    before_start_date: str
    before_end_date: str
    after_start_date: str
    after_end_date: str
    lat: Optional[float] = None
    lon: Optional[float] = None

# API Routes
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
            lon=request.lon
        )
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
    return {"status": "ok", "message": "FloodWatch AI is running"}

# Serve frontend static files
@app.get("/styles.css")
async def styles():
    return FileResponse(os.path.join(frontend_dir, 'styles.css'))

@app.get("/script.js")
async def script():
    return FileResponse(os.path.join(frontend_dir, 'script.js'))

@app.get("/")
async def index():
    return FileResponse(os.path.join(frontend_dir, 'index.html'))