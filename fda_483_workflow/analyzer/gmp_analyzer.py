"""
Claude-powered GMP observation analyzer.
Single API call per inspection analyzes all observations and produces a summary.
"""
import json
import logging
from typing import Any

import anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from .gmp_references import build_reference_context

logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

_GMP_CONTEXT = build_reference_context()

_SYSTEM_PROMPT = f"""You are a pharmaceutical GMP regulatory expert with deep knowledge of:
- FDA GMP: 21 CFR Parts 210 and 211
- EU GMP: EudraLex Volume 4 (Chapters 1–9 and Annexes)
- PIC/S: PE 009 GMP Guide
- ICH Q guidelines (Q7, Q8, Q9, Q10, Q11, Q12, Q13, Q14)
- WHO GMP guidelines (TRS 986, 992, 996, 1019, 1025, 1033, 1039, 1044)

Available regulatory references:
{_GMP_CONTEXT}

Always respond with valid JSON only — no prose, no markdown fences."""

_USER_TEMPLATE = """Analyze all observations from this FDA pharmaceutical inspection and return a single JSON response.

FIRM: {firm_name}
INSPECTION DATE: {inspection_date}
TOTAL OBSERVATIONS: {num_observations}

OBSERVATIONS:
{observations_text}

Return a JSON object with this exact schema:
{{
  "observations": [
    {{
      "observation_number": <integer>,
      "gmp_category": "string — e.g. Documentation, CAPA, Equipment, Contamination Control",
      "risk_level": "Critical | Major | Minor",
      "risk_justification": "string",
      "gmp_mappings": [
        {{
          "framework": "FDA_GMP | EU_GMP | PICS | ICH | WHO",
          "reference_code": "exact code",
          "reference_title": "title",
          "relevance_explanation": "string"
        }}
      ],
      "summary": "2-3 sentence plain-English summary",
      "remediation": "recommended corrective actions"
    }}
  ],
  "summary": {{
    "executive_summary": "3-5 sentences covering overall inspection findings",
    "key_themes": ["list of 3-6 recurring GMP deficiency themes"],
    "overall_risk_level": "Critical | Major | Minor",
    "top_gmp_gaps": [
      {{
        "framework": "framework name",
        "reference": "code",
        "gap_description": "string"
      }}
    ],
    "recommendations": "top 3-5 systemic corrective actions"
  }}
}}"""


def analyze_inspection(
    observations: list[dict],
    firm_name: str,
    inspection_date: str,
) -> dict[str, Any]:
    """
    Single API call: analyze all observations and produce an executive summary.
    """
    obs_text = "\n\n".join(
        f"OBSERVATION {o['number']}:\n{o['text']}" for o in observations
    )

    user_msg = _USER_TEMPLATE.format(
        firm_name=firm_name,
        inspection_date=inspection_date,
        num_observations=len(observations),
        observations_text=obs_text[:30000],  # cap to stay within token limits
    )

    for attempt in range(3):
        try:
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=8192,
                system=[
                    {
                        "type": "text",
                        "text": _SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_msg}],
                extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
            )

            text_content = next(
                (block.text for block in response.content if block.type == "text"),
                None,
            )
            if not text_content:
                logger.warning(f"No text response for {firm_name}, attempt {attempt + 1}")
                continue

            cleaned = text_content.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```", 2)[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
                cleaned = cleaned.rsplit("```", 1)[0].strip()

            result = json.loads(cleaned)
            result["model_used"] = CLAUDE_MODEL
            return result

        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error for {firm_name} attempt {attempt + 1}: {e}")
        except Exception as e:
            logger.error(f"API error for {firm_name} attempt {attempt + 1}: {e}")

    # All attempts failed — return a minimal fallback
    logger.error(f"All attempts failed for {firm_name}, returning fallback")
    return _fallback_result(observations, firm_name)


def _fallback_result(observations: list[dict], firm_name: str) -> dict:
    return {
        "observations": [
            {
                "observation_number": o["number"],
                "gmp_category": "Unknown",
                "risk_level": "Unknown",
                "risk_justification": "Analysis failed — manual review required.",
                "gmp_mappings": [],
                "summary": o["text"][:300],
                "remediation": "Manual review required.",
            }
            for o in observations
        ],
        "summary": {
            "executive_summary": f"Automated analysis failed for {firm_name}. Manual review required.",
            "key_themes": [],
            "overall_risk_level": "Unknown",
            "top_gmp_gaps": [],
            "recommendations": "Manual review required.",
        },
        "model_used": CLAUDE_MODEL,
    }
