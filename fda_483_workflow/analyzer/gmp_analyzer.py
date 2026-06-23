"""
Claude-powered GMP observation analyzer.
Uses claude-opus-4-8 with adaptive thinking to analyze each Form 483 observation
and map it to EU GMP, FDA GMP, PIC/S, ICH, and WHO regulatory references.
"""
import json
import logging
from typing import Any

import anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from .gmp_references import build_reference_context, GMP_FRAMEWORKS

logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

_GMP_CONTEXT = build_reference_context()

_OBSERVATION_SYSTEM_PROMPT = f"""You are a pharmaceutical GMP regulatory expert with deep knowledge of:
- FDA GMP: 21 CFR Parts 210 and 211
- EU GMP: EudraLex Volume 4 (Chapters 1–9 and Annexes)
- PIC/S: PE 009 GMP Guide
- ICH Q guidelines (Q7, Q8, Q9, Q10, Q11, Q12, Q13, Q14)
- WHO GMP guidelines (TRS 986, 992, 996, 1019, 1025, 1033, 1039, 1044)

You will analyze FDA Form 483 inspectional observations from pharmaceutical facilities and:
1. Identify the GMP deficiency category (e.g., Documentation, CAPA, Contamination Control)
2. Map each observation to the most relevant regulatory references across ALL five frameworks
3. Explain why each reference applies
4. Assess the risk level (Critical / Major / Minor) using ICH Q9 / EU GMP Annex 1 criteria
5. Provide actionable remediation recommendations

Available regulatory references:
{_GMP_CONTEXT}

Always respond in valid JSON matching the specified schema exactly."""

_OBSERVATION_USER_TEMPLATE = """Analyze the following FDA Form 483 observation from a pharmaceutical inspection:

FIRM: {firm_name}
INSPECTION DATE: {inspection_date}
OBSERVATION {obs_number}:
{observation_text}

Respond with a JSON object matching this exact schema:
{{
  "gmp_category": "string — primary GMP category (e.g., 'Documentation', 'Equipment', 'Contamination Control')",
  "risk_level": "Critical | Major | Minor",
  "risk_justification": "string — why this risk level was assigned",
  "gmp_mappings": [
    {{
      "framework": "FDA_GMP | EU_GMP | PICS | ICH | WHO",
      "reference_code": "exact code from the reference list above",
      "reference_title": "title of the reference",
      "relevance_explanation": "string — how this observation violates or relates to this requirement"
    }}
  ],
  "summary": "string — 2-3 sentence plain-English summary of the deficiency",
  "remediation": "string — recommended corrective actions"
}}"""

_INSPECTION_SUMMARY_SYSTEM = """You are a pharmaceutical GMP regulatory expert. You will synthesize multiple
Form 483 observation analyses into an executive-level inspection summary.
Respond only with valid JSON."""

_INSPECTION_SUMMARY_USER = """Based on the following analyzed observations from a single FDA inspection,
provide an executive summary.

FIRM: {firm_name}
DATE: {inspection_date}
TOTAL OBSERVATIONS: {num_observations}

ANALYZED OBSERVATIONS:
{observations_json}

Respond with a JSON object:
{{
  "executive_summary": "string — 3-5 sentences covering the overall inspection findings",
  "key_themes": ["list of 3-6 recurring GMP deficiency themes"],
  "overall_risk_level": "Critical | Major | Minor",
  "top_gmp_gaps": [
    {{
      "framework": "framework name",
      "reference": "code",
      "gap_description": "string"
    }}
  ],
  "recommendations": "string — top 3-5 systemic corrective actions for this facility"
}}"""


def analyze_observation(
    observation_text: str,
    observation_number: int,
    firm_name: str,
    inspection_date: str,
) -> dict[str, Any]:
    """
    Use Claude to analyze a single Form 483 observation and map it to GMP references.
    Returns a structured dict with category, risk level, and cross-framework mappings.
    """
    user_msg = _OBSERVATION_USER_TEMPLATE.format(
        firm_name=firm_name,
        inspection_date=inspection_date,
        obs_number=observation_number,
        observation_text=observation_text.strip(),
    )

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        thinking={"type": "adaptive"},
        system=_OBSERVATION_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )

    # Extract text content (thinking blocks are separate)
    text_content = next(
        (block.text for block in response.content if block.type == "text"),
        None,
    )

    if not text_content:
        logger.warning(f"No text response for observation {observation_number}")
        return _fallback_observation(observation_number, observation_text)

    # Strip markdown code fences if present
    cleaned = text_content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 2)[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.rsplit("```", 1)[0].strip()

    try:
        result = json.loads(cleaned)
        result["observation_number"] = observation_number
        return result
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON for observation {observation_number}: {e}")
        return _fallback_observation(observation_number, observation_text)


def analyze_inspection(
    observations: list[dict],
    firm_name: str,
    inspection_date: str,
) -> dict[str, Any]:
    """
    Analyze all observations for an inspection and produce an executive summary.
    First analyzes each observation individually, then synthesizes across them.
    """
    analyzed_observations = []

    for obs in observations:
        logger.info(f"Analyzing observation {obs['number']} for {firm_name}")
        result = analyze_observation(
            observation_text=obs["text"],
            observation_number=obs["number"],
            firm_name=firm_name,
            inspection_date=inspection_date,
        )
        analyzed_observations.append(result)

    # Now synthesize into an inspection-level summary
    summary = _synthesize_inspection_summary(
        analyzed_observations=analyzed_observations,
        firm_name=firm_name,
        inspection_date=inspection_date,
        num_observations=len(observations),
    )

    return {
        "observations": analyzed_observations,
        "summary": summary,
        "model_used": CLAUDE_MODEL,
    }


def _synthesize_inspection_summary(
    analyzed_observations: list[dict],
    firm_name: str,
    inspection_date: str,
    num_observations: int,
) -> dict[str, Any]:
    """Synthesize observation-level analyses into an inspection-level executive summary."""
    obs_json = json.dumps(analyzed_observations, indent=2)

    user_msg = _INSPECTION_SUMMARY_USER.format(
        firm_name=firm_name,
        inspection_date=str(inspection_date),
        num_observations=num_observations,
        observations_json=obs_json[:12000],  # cap to avoid token overflow
    )

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2048,
        thinking={"type": "adaptive"},
        system=_INSPECTION_SUMMARY_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )

    text_content = next(
        (block.text for block in response.content if block.type == "text"),
        "{}",
    )

    cleaned = text_content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 2)[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.rsplit("```", 1)[0].strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        logger.error("Failed to parse inspection summary JSON")
        return {
            "executive_summary": "Analysis summary unavailable.",
            "key_themes": [],
            "overall_risk_level": "Unknown",
            "top_gmp_gaps": [],
            "recommendations": "",
        }


def _fallback_observation(number: int, text: str) -> dict:
    return {
        "observation_number": number,
        "gmp_category": "Unknown",
        "risk_level": "Unknown",
        "risk_justification": "Analysis failed — manual review required.",
        "gmp_mappings": [],
        "summary": text[:300],
        "remediation": "Manual review required.",
    }
