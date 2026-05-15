"""
routers/cv.py
-------------
Endpoints:
  POST /cv/parse           — parse an uploaded CV (already in Supabase Storage)
  GET  /cv/{id}/profile    — download the filled Pro Talent .docx profile
"""

import io
import json
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from supabase import Client

from ..deps import verify_jwt, get_supabase
from ..pro_talent.cv_parser import extract_cv_text
from ..pro_talent.ai_extractor import extract_candidate_info
from ..pro_talent.template_filler import fill_template, make_safe_filename
from ..services.summary import generate_recruiter_summary
from ..config import settings

router = APIRouter()

TEMPLATE_PATH = Path(__file__).parent.parent / "pro_talent" / "templates" / "pro_talent_template.docx"


# ---- Request / Response models ----

class ParseRequest(BaseModel):
    storage_path: str       # e.g. "{user_id}/{uuid}.pdf"
    original_name: str      # e.g. "Sipho_Mthembu_CV.pdf"


# ---- POST /cv/parse ----

@router.post("/parse")
def parse_cv(
    body: ParseRequest,
    user_id: str = Depends(verify_jwt),
    sb: Client = Depends(get_supabase),
):
    """
    1. Download the CV from Supabase Storage
    2. Extract text (pdf/docx)
    3. Run Claude extraction (your existing ai_extractor)
    4. Run Claude recruiter summary (new)
    5. Insert candidate row
    6. Return the new candidate record
    """

    # Guard: storage path must be inside the user's own folder
    if not body.storage_path.startswith(f"{user_id}/"):
        raise HTTPException(403, "Storage path does not belong to user")

    # 1. Download file from Supabase Storage
    try:
        file_bytes = sb.storage.from_("cvs").download(body.storage_path)
    except Exception as e:
        raise HTTPException(404, f"File not found in storage: {e}")

    # 2. Write to temp file (cv_parser expects a file path, not bytes)
    suffix = Path(body.original_name).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        cv_text = extract_cv_text(tmp_path)
    except ValueError as e:
        raise HTTPException(400, str(e))

    if len(cv_text) < 50:
        raise HTTPException(422, "Could not extract meaningful text from the file")

    # 3. Run Claude extraction (your existing module — unchanged)
    try:
        data = extract_candidate_info(cv_text, api_key=settings.anthropic_api_key)
    except Exception as e:
        raise HTTPException(502, f"AI extraction failed: {e}")

    # 4. Run recruiter summary (new — optional, fails gracefully)
    try:
        summary = generate_recruiter_summary(data)
    except Exception:
        summary = {"summary": None, "strengths": [], "weaknesses": []}

    # 5. Insert candidate row into Supabase
    row = {
        "user_id":            user_id,
        "storage_path":       body.storage_path,
        "original_name":      body.original_name,
        # Personal details
        "first_name":         data.get("first_name"),
        "surname":            data.get("surname"),
        "identity_number":    data.get("identity_number"),
        "equity":             data.get("equity"),
        "residential_area":   data.get("residential_area"),
        "language":           data.get("language"),
        "transport":          data.get("transport"),
        "drivers_licence":    data.get("drivers_licence"),
        "current_salary":     data.get("current_salary"),
        "required_salary":    data.get("required_salary"),
        "availability":       data.get("availability"),
        # Arrays / nested
        "achievements":       data.get("achievements", []),
        "computer_skills":    data.get("computer_skills", []),
        "education":          data.get("education", []),
        "employment_history": data.get("employment_history", []),
        "references_data":    data.get("references", []),  # DB column is references_data
        # AI recruiter brief
        "ai_summary":        summary.get("summary"),
        "ai_strengths":      summary.get("strengths", []),
        "ai_weaknesses":     summary.get("weaknesses", []),
    }

    try:
        result = sb.table("candidates").insert(row).execute()
        return result.data[0]
    except Exception as e:
        raise HTTPException(500, f"Failed to save candidate: {e}")


# ---- GET /cv/{candidate_id}/profile ----

@router.get("/{candidate_id}/profile")
def download_profile(
    candidate_id: str,
    user_id: str = Depends(verify_jwt),
    sb: Client = Depends(get_supabase),
):
    """
    Generate (or serve cached) the filled Pro Talent .docx profile.
    Uses your existing template_filler module — unchanged.
    """

    # Fetch candidate
    try:
        result = (
            sb.table("candidates")
            .select("*")
            .eq("id", candidate_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        )
        cand = result.data
    except Exception:
        raise HTTPException(404, "Candidate not found")

    if not cand:
        raise HTTPException(404, "Candidate not found")

    # Try serving from cache first
    if cand.get("profile_storage_path"):
        try:
            cached_bytes = sb.storage.from_("profiles").download(
                cand["profile_storage_path"]
            )
            safe = make_safe_filename(
                f"{cand.get('first_name', '')} {cand.get('surname', '')}"
            )
            return StreamingResponse(
                io.BytesIO(cached_bytes),
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                headers={
                    "Content-Disposition": f'attachment; filename="{safe}_profile.docx"'
                },
            )
        except Exception:
            pass  # Cache miss — regenerate below

    # Rebuild the dict shape template_filler expects
    # (it expects 'references' key, but our DB column is 'references_data')
    candidate_data = {**cand, "references": cand.get("references_data", [])}

    # Fill the template
    if not TEMPLATE_PATH.exists():
        raise HTTPException(500, "Pro Talent template file not found on server")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
        out_path = Path(tmp.name)

    fill_template(TEMPLATE_PATH, candidate_data, out_path)
    filled_bytes = out_path.read_bytes()

    # Cache in Supabase Storage
    storage_path = f"{user_id}/{candidate_id}.docx"
    try:
        sb.storage.from_("profiles").upload(
            storage_path,
            filled_bytes,
            file_options={
                "content-type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "upsert": "true",
            },
        )
        # Update candidate row with cache path
        sb.table("candidates").update(
            {"profile_storage_path": storage_path}
        ).eq("id", candidate_id).execute()
    except Exception:
        pass  # Caching failed — not critical, we still serve the file

    safe = make_safe_filename(
        f"{cand.get('first_name', '')} {cand.get('surname', '')}"
    )
    return StreamingResponse(
        io.BytesIO(filled_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f'attachment; filename="{safe}_profile.docx"'
        },
    )
