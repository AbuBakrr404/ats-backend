"""
rag/chunker.py
--------------
Turns a candidate row into searchable chunks for embedding.

We produce one chunk per semantically coherent unit:
- AI summary, AI strengths, skills, achievements
- One chunk per education entry
- One chunk per employment role (with optional overflow chunk for long roles)

Sentinel '(info absent on CV)' values are skipped everywhere.
"""

from typing import Any

ABSENT = "(info absent on CV)"


def _is_present(value: Any) -> bool:
    """True if the value is meaningful (not None, empty, or the sentinel)."""
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != "" and value.strip() != ABSENT
    if isinstance(value, (list, dict)):
        return len(value) > 0
    return True


def _candidate_label(candidate: dict) -> str:
    """Stable label prefixed on every chunk so the embedding has context."""
    first = candidate.get("first_name") or ""
    last  = candidate.get("surname") or ""
    name  = f"{first} {last}".strip() or "Candidate"
    area  = candidate.get("residential_area")
    if _is_present(area):
        return f"{name} ({area})"
    return name


def build_candidate_chunks(candidate: dict) -> list[dict]:
    """
    Return a list of {chunk_type, chunk_text, chunk_index} dicts ready to embed.
    Order is stable so chunk_index is deterministic.
    """
    label  = _candidate_label(candidate)
    chunks: list[dict] = []

    # ---- AI summary ----
    if _is_present(candidate.get("ai_summary")):
        chunks.append({
            "chunk_type": "summary",
            "chunk_text": f"{label} — Summary: {candidate['ai_summary']}",
        })

    # ---- AI strengths (one chunk per strength) ----
    for strength in candidate.get("ai_strengths") or []:
        if _is_present(strength):
            chunks.append({
                "chunk_type": "strengths",
                "chunk_text": f"{label} — Strength: {strength}",
            })

    # ---- Computer skills (single chunk) ----
    skills = [s for s in (candidate.get("computer_skills") or []) if _is_present(s)]
    if skills:
        chunks.append({
            "chunk_type": "skills",
            "chunk_text": f"{label} — Skills: {', '.join(skills)}",
        })

    # ---- Achievements / certifications (single chunk) ----
    achievements = [a for a in (candidate.get("achievements") or []) if _is_present(a)]
    if achievements:
        chunks.append({
            "chunk_type": "achievements",
            "chunk_text": f"{label} — Achievements: {'; '.join(achievements)}",
        })

    # ---- Education (one chunk per qualification) ----
    for edu in candidate.get("education") or []:
        parts = []
        if _is_present(edu.get("qualification")):
            parts.append(edu["qualification"])
        if _is_present(edu.get("institution")):
            parts.append(f"at {edu['institution']}")
        if _is_present(edu.get("date")):
            parts.append(f"({edu['date']})")
        if parts:
            chunks.append({
                "chunk_type": "education",
                "chunk_text": f"{label} — Education: {' '.join(parts)}",
            })

    # ---- Employment (one chunk per role + overflow for many duties) ----
    for role in candidate.get("employment_history") or []:
        position = role.get("position") if _is_present(role.get("position")) else None
        company  = role.get("company")  if _is_present(role.get("company"))  else None
        period   = role.get("period")   if _is_present(role.get("period"))   else None
        duties   = [d for d in (role.get("duties") or []) if _is_present(d)]

        if position or company:
            header = f"{position or 'Role'} at {company or 'unknown company'}"
            if period:
                header += f" ({period})"
            body = ". ".join(duties[:6]) if duties else ""
            chunks.append({
                "chunk_type": "role",
                "chunk_text": f"{label} — {header}. {body}".strip(),
            })

            if len(duties) > 6:
                chunks.append({
                    "chunk_type": "duties",
                    "chunk_text": (
                        f"{label} — Additional duties at {company or 'previous role'}: "
                        + ". ".join(duties[6:])
                    ),
                })

    # Stable index for ordering
    for i, ch in enumerate(chunks):
        ch["chunk_index"] = i

    return chunks