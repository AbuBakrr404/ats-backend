"""
services/matching.py
--------------------
On-demand candidate-job matching using Claude.
Called from the matching router when a recruiter clicks "Find candidates" on a job.
"""

import json
from anthropic import Anthropic
from ..config import settings

_client = Anthropic(api_key=settings.anthropic_api_key)

MATCHING_SYSTEM = """You score how well a candidate matches a job for Pro Talent / Pro Appointments.

Return ONLY valid JSON — no preamble, no markdown fences:
{ "score": <integer 0-100>, "reasoning": "2-3 sentence explanation" }

Scoring guide:
  90-100  perfect or near-perfect fit
  70-89   strong fit, minor gaps
  50-69   partial fit, notable gaps
  30-49   weak fit, major gaps
  0-29    very poor fit

Rules:
- Weight required skills > years/seniority in employment history > general experience > nice-to-haves.
- Salary expectations vs offered range is relevant if both are available.
- Location and availability matter — note mismatches.
- Ignore '(info absent on CV)' values — treat as unknown, neither positive nor negative.
- 'equity' and 'identity_number' are NEVER part of the match score — South African law prohibits this.
- Be concise and evidence-based in reasoning."""


def build_matching_prompt(job: dict, candidate: dict) -> str:
    return f"""<job>
title: {job.get('title')}
company: {job.get('company', 'Not specified')}
location: {job.get('location', 'Not specified')}
required_skills: {job.get('required_skills', [])}
description: {job.get('description')}
</job>

<candidate>
name: {candidate.get('first_name', '')} {candidate.get('surname', '')}
location: {candidate.get('residential_area', '(info absent on CV)')}
availability: {candidate.get('availability', '(info absent on CV)')}
current_salary: {candidate.get('current_salary', '(info absent on CV)')}
required_salary: {candidate.get('required_salary', '(info absent on CV)')}
computer_skills: {json.dumps(candidate.get('computer_skills', []))}
achievements: {json.dumps(candidate.get('achievements', []))}
employment_history: {json.dumps(candidate.get('employment_history', []))}
ai_summary: {candidate.get('ai_summary', '')}
</candidate>

Score this candidate for this job."""


def score_candidate(job: dict, candidate: dict) -> dict:
    """
    Score a single candidate against a job.
    Returns dict with keys: score (int), reasoning (str).
    """
    response = _client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        system=MATCHING_SYSTEM,
        messages=[
            {"role": "user", "content": build_matching_prompt(job, candidate)}
        ],
    )

    text = response.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip().rstrip("`").strip()

    result = json.loads(text)
    # Clamp score to valid range
    result["score"] = max(0, min(100, int(result["score"])))
    return result
