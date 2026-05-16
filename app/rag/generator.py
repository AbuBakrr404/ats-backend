"""
rag/generator.py
----------------
Calls Claude with retrieved candidate chunks + recruiter query.
Returns a structured JSON answer with ranked candidate recommendations.
"""

import json
from anthropic import Anthropic

from ..config import settings

_client = Anthropic(api_key=settings.anthropic_api_key)

RAG_SYSTEM = """You are the AI assistant inside Pro Talent / Pro Appointments — a South African \
specialist permanent recruitment agency. Recruiters ask you natural-language questions about \
candidates in their database, and you answer using ONLY the retrieved context provided.

Return ONLY valid JSON — no preamble, no markdown fences:
{
  "answer": "Plain-English answer to the recruiter's question. 2-4 sentences.",
  "candidates": [
    {
      "candidate_id": "uuid",
      "name": "First Surname",
      "match_reason": "Specific evidence from the context explaining why this candidate matches",
      "confidence": <float 0.0-1.0>,
      "sources": ["chunk_type values used, e.g. 'role', 'skills', 'strengths'"]
    }
  ],
  "reasoning": "1-2 sentence explanation of how you ranked the candidates"
}

Rules:
- Use ONLY information present in the <candidates> block. Never invent skills, employers, or qualifications.
- If the retrieved context is empty or doesn't match the query, set candidates to [] and explain in 'answer'.
- Rank by how well the candidate matches the query, not by similarity score alone.
- 'equity' classification and ID numbers are NEVER part of ranking — POPIA / Employment Equity Act.
- Be concise. Each match_reason should cite specific evidence (a role, skill, or strength)."""


def build_context_block(candidates: list[dict]) -> str:
    """Format the grouped candidates into the <candidates> XML block for Claude."""
    blocks = []
    for c in candidates:
        meta = c["candidate"]
        name = f"{meta.get('first_name', '')} {meta.get('surname', '')}".strip()
        chunks_text = "\n".join(
            f"  [{ch['chunk_type']} sim={ch['similarity']:.2f}] {ch['chunk_text']}"
            for ch in c["chunks"]
        )
        blocks.append(
            f'<candidate id="{meta["id"]}" name="{name}" stage="{meta.get("stage", "")}">\n'
            f"{chunks_text}\n"
            f"</candidate>"
        )
    return "<candidates>\n" + "\n\n".join(blocks) + "\n</candidates>"


def generate_rag_response(query: str, candidates: list[dict]) -> dict:
    """Send context + query to Claude, return parsed JSON dict."""
    if not candidates:
        return {
            "answer":     "No candidates in your database matched this query.",
            "candidates": [],
            "reasoning":  "Vector search returned no chunks above the similarity threshold.",
        }

    user_message = (
        f"{build_context_block(candidates)}\n\n"
        f"Recruiter query: {query}\n\n"
        "Return your JSON response now."
    )

    # Retry up to 3 times on transient Anthropic 5xx errors
    import time
    import anthropic
    response = None
    for attempt in range(3):
        try:
            response = _client.messages.create(
                model=settings.rag_chat_model,
                max_tokens=1500,
                system=RAG_SYSTEM,
                messages=[{"role": "user", "content": user_message}],
            )
            break
        except (anthropic.InternalServerError, anthropic.APITimeoutError):
            if attempt < 2:
                time.sleep(1 + attempt)   # 1s, then 2s backoff
                continue
            return {
                "answer":     "The AI service is temporarily unavailable. Please try again in a moment.",
                "candidates": [],
                "reasoning":  "Anthropic API returned a transient error after 3 retries.",
            }

    if response is None:
        return {
            "answer":     "The AI service is temporarily unavailable.",
            "candidates": [],
            "reasoning":  "No response received.",
        }

    text = response.content[0].text.strip()
    # Strip markdown fences if Claude wraps the JSON
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip().rstrip("`").strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {
            "answer":     text,
            "candidates": [],
            "reasoning":  "Model returned non-JSON output.",
        }