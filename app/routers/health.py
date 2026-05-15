"""
routers/health.py
-----------------
Simple health check endpoint for monitoring and deployment verification.
"""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check():
    return {"status": "ok", "service": "pro-talent-ats"}
