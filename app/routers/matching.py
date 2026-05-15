"""
routers/matching.py
-------------------
Endpoint:
  POST /jobs/{job_id}/match — score all candidates against a job
"""

from fastapi import APIRouter, Depends, HTTPException
from supabase import Client

from ..deps import verify_jwt, get_supabase
from ..services.matching import score_candidate

router = APIRouter()


@router.post("/{job_id}/match")
def match_candidates(
    job_id: str,
    user_id: str = Depends(verify_jwt),
    sb: Client = Depends(get_supabase),
):
    """
    On-demand matching: score all candidates (with skill overlap) against
    a job and return ranked results. Results are cached in match_results.
    """

    # Fetch the job
    try:
        job = (
            sb.table("jobs")
            .select("*")
            .eq("id", job_id)
            .eq("user_id", user_id)
            .single()
            .execute()
            .data
        )
    except Exception:
        raise HTTPException(404, "Job not found")

    if not job:
        raise HTTPException(404, "Job not found")

    # Fetch candidates (cap at 50 to control Claude spend)
    candidates = (
        sb.table("candidates")
        .select("*")
        .eq("user_id", user_id)
        .limit(50)
        .execute()
        .data
    )

    if not candidates:
        return {"job_id": job_id, "results": [], "message": "No candidates to match"}

    results = []
    for cand in candidates:
        try:
            match = score_candidate(job, cand)
            score = match["score"]
            reasoning = match.get("reasoning", "")
        except Exception:
            # Skip one bad candidate, don't fail the whole batch
            continue

        results.append({
            "candidate_id": cand["id"],
            "candidate_name": f"{cand.get('first_name', '')} {cand.get('surname', '')}".strip(),
            "score": score,
            "reasoning": reasoning,
        })

        # Upsert into match_results cache
        try:
            sb.table("match_results").upsert(
                {
                    "user_id": user_id,
                    "job_id": job_id,
                    "candidate_id": cand["id"],
                    "score": score,
                    "reasoning": reasoning,
                },
                on_conflict="job_id,candidate_id",
            ).execute()
        except Exception:
            pass  # Cache write failed — not critical

    # Sort by score descending
    results.sort(key=lambda r: r["score"], reverse=True)

    return {"job_id": job_id, "results": results}
