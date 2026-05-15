"""
services/summary.py
-------------------
Generates a recruiter-facing candidate brief using Claude.
This is a NEW feature not in the original Streamlit app.

Takes the structured data from ai_extractor and produces:
- A 2-3 sentence professional summary
- 3-5 evidence-based strengths
- 1-3 constructive weaknesses (gaps to probe in interview)
"""

import json
import os
from anthropic import Anthropic
from ..config import settings

_client = Anthropic(api_key=settings.anthropic_api_key)

SUMMARY_SYSTEM = """You write concise recruiter-facing candidate notes for Pro Talent / Pro Appointments, \
a South African specialist permanent recruitment agency. You receive structured CV data and produce a brief \
that helps recruiters quickly assess the candidate.

Return ONLY valid JSON — no preamble, no markdown fences:
{
  "summary": "2-3 sentence professional framing of the candidate for an internal recruiter view",
  "strengths": ["strength 1", "strength 2", "strength 3"],
  "weaknesses": ["gap 1", "gap 2"]
}

Rules:
- Every strength must be supported by something explicit in the data.
- Provide 3-5 strengths.
- Weaknesses are constructive gaps a recruiter should probe in interview, not negative judgements. Provide 1-3.
- Ignore any fields with value '(info absent on CV)' — do not treat them as data or as weaknesses.
- South African context: salary in ZAR is fine to reference; equity classification is sensitive — do not comment on it.
- Keep the summary factual and useful. No fluff."""


def generate_recruiter_summary(candidate_data: dict) -> dict:
    """
    Call Claude to produce a recruiter-facing summary.
    Returns dict with keys: summary, strengths, weaknesses.
    Raises on API or parse error — caller should handle gracefully.
    """
    response = _client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=800,
        system=SUMMARY_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": (
                    f"<candidate>\n{json.dumps(candidate_data, indent=2)}\n</candidate>\n\n"
                    "Produce the recruiter brief."
                ),
            }
        ],
    )

    text = response.content[0].text.strip()

    # Strip markdown fences if Claude adds them
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip().rstrip("`").strip()

    return json.loads(text)
