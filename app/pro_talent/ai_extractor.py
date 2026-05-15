"""
ai_extractor.py
---------------
Sends raw CV text to Claude and gets back structured candidate data as JSON,
shaped to match the Pro Talent / Pro Appointments master template.
"""

import json
import os
from anthropic import Anthropic

# Schema matches the Pro Talent template fields exactly.
# Some fields are NOT typically on a CV — for those we tell Claude to use a
# specific marker so the recruiter knows the info was not on the CV.
EXTRACTION_SCHEMA = {
    "first_name": "Candidate's first name only",
    "surname": "Candidate's surname / last name only",
    "identity_number": "South African ID number if explicitly stated, otherwise '(info absent on CV)'",
    "equity": (
        "Employment Equity classification (African, Coloured, Indian, White) — "
        "only if explicitly stated, otherwise '(info absent on CV)'"
    ),
    "residential_area": "Suburb and city of residence (e.g. 'Umhlanga, Durban'), or '(info absent on CV)' if not stated",
    "language": "Languages spoken, comma-separated (e.g. 'English, isiZulu'), or '(info absent on CV)' if not stated",
    "transport": (
        "Whether the candidate has own transport. Use 'Own transport' if mentioned, "
        "'Public transport' if mentioned, else '(info absent on CV)'"
    ),
    "drivers_licence": (
        "Driver's licence type if mentioned (e.g. 'Code 8', 'Yes - Code B', 'No'), "
        "else '(info absent on CV)'"
    ),
    "current_salary": "Current salary if explicitly stated on CV, else '(info absent on CV)'",
    "required_salary": "Required/expected salary if stated, else '(info absent on CV)'",
    "availability": "Notice period or availability (e.g. '1 month notice', 'Immediate'), else '(info absent on CV)'",
    "achievements": (
        "Array of professional achievements, awards, and certifications mentioned in the CV. "
        "Each as a string. Empty array [] if none found."
    ),
    "computer_skills": (
        "Array of computer skills, software, and technical proficiencies (e.g. 'MS Excel - Advanced', "
        "'Pastel Accounting', 'SAP'). Empty array [] if none found."
    ),
    "education": (
        "Array of qualifications. Each item must be an object with these EXACT keys: "
        "{ \"institution\": \"...\", \"date\": \"YYYY or MMM YYYY\", \"qualification\": \"full qualification name\" }. "
        "Order from most recent to oldest. Provide up to 2 entries (the template has 2 slots). "
        "If a sub-field is missing, use '(info absent on CV)' for that field."
    ),
    "employment_history": (
        "Array of jobs in REVERSE chronological order (most recent first). Each item must be an object: "
        "{ \"company\": \"...\", \"period\": \"MMM YYYY - MMM YYYY (or 'Present')\", "
        "\"position\": \"job title\", \"duties\": [\"duty 1\", \"duty 2\", ...], "
        "\"reason_for_leaving\": \"...\" }. "
        "For 'reason_for_leaving' use '(info absent on CV)' unless explicitly stated on the CV. "
        "Provide up to 3 entries (the template has 3 slots). "
        "If any sub-field is missing, use '(info absent on CV)' for that field."
    ),
    "references": (
        "Array of professional references listed on the CV. Each item must be an object: "
        "{ \"name\": \"reference's full name\", "
        "\"company\": \"reference's company/organisation\", "
        "\"phone\": \"reference's phone number\" }. "
        "Provide up to 2 entries (the template has 2 slots). "
        "If a sub-field is missing for a reference that IS listed, use '(info absent on CV)' for that sub-field. "
        "If the CV has no references at all, return an empty array []."
    ),
}


SYSTEM_PROMPT = """You are an expert recruitment assistant working for Pro Talent / Pro Appointments, \
a South African specialist permanent recruitment agency. Your job is to read a candidate's CV and \
extract structured information that will populate the Pro Talent client-facing candidate profile template.

Rules:
1. Return ONLY a valid JSON object - no preamble, no markdown code fences, no explanation.
2. CRITICAL: If a field is not present in the CV, use the EXACT string '(info absent on CV)' for text fields, \
or [] for list fields. Do NOT invent, guess, or infer information that isn't clearly stated in the CV.
3. For dates, use 'MMM YYYY' format (e.g. 'Jan 2023') or just 'YYYY' if only year is given. Use 'Present' for current roles.
4. For 'duties', extract ALL bullet points from each job; rephrase any first-person language to be neutral/professional.
5. For 'employment_history', list MOST RECENT FIRST. The first entry should be the candidate's current/most recent role.
6. Be accurate. Do not invent information. When in doubt, use '(info absent on CV)'.
7. South African context: salaries may be quoted as 'R45,000 pm' or 'R540K pa' - preserve the original format.
8. The 'equity' field refers to South African Employment Equity classification - only fill this if explicitly stated; otherwise '(info absent on CV)'."""


def build_extraction_prompt(cv_text: str) -> str:
    schema_description = "\n".join(
        f'  "{field}": <{description}>'
        for field, description in EXTRACTION_SCHEMA.items()
    )

    return f"""Extract the following fields from this CV and return them as a JSON object:

{{
{schema_description}
}}

CV TEXT:
\"\"\"
{cv_text}
\"\"\"

Return ONLY the JSON object, nothing else. Remember: if a field is not in the CV, use '(info absent on CV)'."""


def extract_candidate_info(
    cv_text: str,
    api_key: str | None = None,
    model: str = "claude-haiku-4-5",
) -> dict:
    """Send CV text to Claude and get structured candidate data back."""
    client = Anthropic(api_key=api_key or os.getenv("ANTHROPIC_API_KEY"))

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": build_extraction_prompt(cv_text)}
        ],
    )

    raw_text = response.content[0].text.strip()

    if raw_text.startswith("```"):
        raw_text = raw_text.split("```")[1]
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
        raw_text = raw_text.strip()

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Claude did not return valid JSON. Got:\n{raw_text[:500]}"
        ) from e


if __name__ == "__main__":
    import sys
    from cv_parser import extract_cv_text

    if len(sys.argv) > 1:
        text = extract_cv_text(sys.argv[1])
        data = extract_candidate_info(text)
        print(json.dumps(data, indent=2))
