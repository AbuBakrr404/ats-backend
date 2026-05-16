"""
routers/rag.py
--------------
Endpoints:
  POST /rag/embed/{candidate_id}   — (re)build embeddings for one candidate
  POST /rag/embed/all              — backfill all candidates for this user
  POST /rag/query                  — natural-language search over candidates
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from supabase import Client

from ..deps import verify_jwt, get_supabase
from ..rag.service import embed_candidate, answer_query

router = APIRouter()


class QueryRequest(BaseModel):
    query:      str   = Field(..., min_length=2, max_length=500)
    top_k:      int | None = None
    threshold:  float | None = None
    chunk_type: str | None = None
    stage:      str | None = None


# ---- POST /rag/embed/all ----

@router.post("/embed/all")
def embed_all(
    user_id: str = Depends(verify_jwt),
    sb: Client = Depends(get_supabase),
):
    """Backfill: embed every candidate belonging to this user."""
    rows = (
        sb.table("candidates")
        .select("id")
        .eq("user_id", user_id)
        .execute()
        .data
        or []
    )
    succeeded, failed = 0, 0
    for r in rows:
        try:
            embed_candidate(sb, user_id, r["id"])
            succeeded += 1
        except Exception:
            failed += 1
    return {
        "total":     len(rows),
        "succeeded": succeeded,
        "failed":    failed,
    }


# ---- POST /rag/embed/{candidate_id} ----

@router.post("/embed/{candidate_id}")
def embed_one(
    candidate_id: str,
    user_id: str = Depends(verify_jwt),
    sb: Client = Depends(get_supabase),
):
    """(Re)build embeddings for a single candidate."""
    try:
        result = embed_candidate(sb, user_id, candidate_id)
    except Exception as e:
        raise HTTPException(500, f"Embedding failed: {e}")

    if result["status"] == "not_found":
        raise HTTPException(404, "Candidate not found")
    return result


# ---- POST /rag/query ----

@router.post("/query")
def query_rag(
    body: QueryRequest,
    user_id: str = Depends(verify_jwt),
    sb: Client = Depends(get_supabase),
):
    """Natural-language search over the recruiter's candidates."""
    try:
        return answer_query(
            sb=sb,
            user_id=user_id,
            query=body.query,
            top_k=body.top_k,
            threshold=body.threshold,
            chunk_type=body.chunk_type,
            stage=body.stage,
        )
    except Exception as e:
        raise HTTPException(500, f"RAG query failed: {e}")