"""
rag/retriever.py
----------------
Runs the query embedding, calls the pgvector RPC, groups results by candidate.
"""

from supabase import Client

from ..config import settings
from .embeddings import embed_query


def retrieve_chunks(
    sb: Client,
    user_id: str,
    query: str,
    top_k: int | None = None,
    threshold: float | None = None,
    chunk_type: str | None = None,
    stage: str | None = None,
) -> list[dict]:
    """Embed the query and run pgvector similarity search (scoped to user_id)."""
    query_vec = embed_query(query)
    response = sb.rpc(
        "match_candidate_chunks",
        {
            "query_embedding":   query_vec,
            "match_user_id":     user_id,
            "match_threshold":   threshold if threshold is not None else settings.rag_threshold,
            "match_count":       top_k     if top_k     is not None else settings.rag_top_k,
            "filter_chunk_type": chunk_type,
            "filter_stage":      stage,
        },
    ).execute()
    return response.data or []


def group_by_candidate(chunks: list[dict]) -> list[dict]:
    """Group chunks by candidate_id; sort by max_similarity desc."""
    grouped: dict[str, dict] = {}
    for ch in chunks:
        cid = ch["candidate_id"]
        if cid not in grouped:
            grouped[cid] = {
                "candidate_id":   cid,
                "max_similarity": ch["similarity"],
                "chunks":         [],
            }
        grouped[cid]["chunks"].append(ch)
        if ch["similarity"] > grouped[cid]["max_similarity"]:
            grouped[cid]["max_similarity"] = ch["similarity"]
    return sorted(grouped.values(), key=lambda g: g["max_similarity"], reverse=True)


def hydrate_candidates(
    sb: Client,
    user_id: str,
    grouped: list[dict],
) -> list[dict]:
    """Fetch candidate metadata for the grouped IDs. Scoped to user_id."""
    if not grouped:
        return []
    ids = [g["candidate_id"] for g in grouped]
    rows = (
        sb.table("candidates")
        .select(
            "id, first_name, surname, residential_area, ai_summary, "
            "computer_skills, stage, availability, required_salary"
        )
        .eq("user_id", user_id)
        .in_("id", ids)
        .execute()
        .data
        or []
    )
    by_id = {r["id"]: r for r in rows}
    result = []
    for g in grouped:
        meta = by_id.get(g["candidate_id"])
        if meta:
            result.append({**g, "candidate": meta})
    return result