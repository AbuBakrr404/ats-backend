"""
main.py
-------
Pro Talent ATS — FastAPI backend.

This server handles only the heavy lifting:
  - CV parsing + AI extraction
  - Profile generation (.docx)
  - Candidate-job matching

All CRUD (candidates list, jobs, notes, pipeline) is handled
directly by the React frontend via Supabase JS.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routers import health, cv, matching

app = FastAPI(
    title="Pro Talent ATS API",
    description="AI-powered recruitment system for Pro Talent / Pro Appointments",
    version="1.0.0",
)

# CORS — allow the React frontend to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(health.router)
app.include_router(cv.router, prefix="/cv", tags=["cv"])
app.include_router(matching.router, prefix="/jobs", tags=["matching"])
