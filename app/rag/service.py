"""
rag/service.py
--------------
High-level orchestration. Routers call into these two functions.
"""

from supabase import Client

from ..config import settings
from .chunker    import build_candidate_chunks
from .embeddings import embed_documents
from .retriever  import retrieve_chunks, group_by_candidate, hydrate_candidates
from .generator  import generate_rag_response


def embed_candidate(sb: Client, user_id: str, candidate_id: str) -> dict:
    """Idempotently (re)build embeddings for a single candidate."""
    row = (
        sb.table("candidates")
        .select("*")
        .eq("id", candidate_id)
        .eq("user_id", user_id)
        .single()
        .execute()
        .data
    )
    if not row:
        return {"status": "not_found", "chunks": 0}

    chunks = build_candidate_chunks(row)
    if not chunks:
        return {"status": "no_content", "chunks": 0}

    vectors = embed_documents([c["chunk_text"] for c in chunks])

    # Replace existing rows (delete + insert keeps it idempotent)
    sb.table("candidate_embeddings").delete().eq("candidate_id", candidate_id).execute()
    payload = [
        {
            "candidate_id": candidate_id,
            "user_id":      user_id,
            "chunk_type":   c["chunk_type"],
            "chunk_text":   c["chunk_text"],
            "chunk_index":  c["chunk_index"],
            "embedding":    vec,
        }
        for c, vec in zip(chunks, vectors)
    ]
    sb.table("candidate_embeddings").insert(payload).execute()
    return {"status": "ok", "chunks": len(payload)}


def answer_query(
    sb: Client,
    user_id: str,
    query: str,
    top_k: int | None = None,
    threshold: float | None = None,
    chunk_type: str | None = None,
    stage: str | None = None,
) -> dict:
    """Full RAG pipeline: embed query → vector search → hydrate → Claude."""
    chunks    = retrieve_chunks(sb, user_id, query, top_k, threshold, chunk_type, stage)
    grouped   = group_by_candidate(chunks)
    hydrated  = hydrate_candidates(sb, user_id, grouped)
    response  = generate_rag_response(
        query=query,
        candidates=hydrated[: settings.rag_max_candidates_in_context],
    )
    return {
        "query":                  query,
        "retrieved_chunk_count":  len(chunks),
        "candidates_considered":  len(hydrated),
        **response,
    }