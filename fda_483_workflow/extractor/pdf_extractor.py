"""
Extracts text and structured observations from FDA Form 483 PDFs.
Form 483s list numbered observations; this module parses them out.
"""
import logging
import re
from pathlib import Path
from typing import NamedTuple

import pdfplumber

logger = logging.getLogger(__name__)


class Observation(NamedTuple):
    number: int
    text: str


class ExtractionResult(NamedTuple):
    raw_text: str
    observations: list[Observation]
    num_observations: int
    extraction_error: str | None


# Patterns that signal the start of a numbered observation
_OBS_PATTERN = re.compile(
    r"(?:^|\n)\s*(?:Observation\s+)?(\d{1,2})[.):\s]",
    re.MULTILINE | re.IGNORECASE,
)

_FORM_483_HEADER = re.compile(
    r"form\s*483|inspectional\s+observation|notice\s+of\s+inspectional",
    re.IGNORECASE,
)


def extract_text(pdf_path: str | Path) -> str:
    """Extract raw text from all pages of a PDF."""
    full_text = []
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page in pdf.pages:
                text = page.extract_text(x_tolerance=3, y_tolerance=3)
                if text:
                    full_text.append(text)
    except Exception as e:
        logger.error(f"Failed to extract text from {pdf_path}: {e}")
        raise

    return "\n".join(full_text)


def parse_observations(raw_text: str) -> list[Observation]:
    """
    Split extracted text into individual numbered observations.
    Returns a list of Observation(number, text) tuples.
    """
    # Find all observation-start positions
    matches = list(_OBS_PATTERN.finditer(raw_text))
    if not matches:
        return []

    observations = []
    for i, match in enumerate(matches):
        obs_num = int(match.group(1))
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw_text)
        obs_text = raw_text[start:end].strip()

        # Skip very short fragments (likely false positives)
        if len(obs_text) < 20:
            continue

        # Clean up excessive whitespace
        obs_text = re.sub(r"\n{3,}", "\n\n", obs_text)
        obs_text = re.sub(r"[ \t]{2,}", " ", obs_text)

        observations.append(Observation(number=obs_num, text=obs_text))

    return observations


def extract_form_483(pdf_path: str | Path) -> ExtractionResult:
    """
    Full extraction pipeline for a single Form 483 PDF.
    Returns raw text, parsed observations, and any error message.
    """
    try:
        raw_text = extract_text(pdf_path)
    except Exception as e:
        return ExtractionResult(
            raw_text="",
            observations=[],
            num_observations=0,
            extraction_error=str(e),
        )

    if not _FORM_483_HEADER.search(raw_text[:2000]):
        logger.warning(f"Document may not be a Form 483: {pdf_path}")

    observations = parse_observations(raw_text)

    return ExtractionResult(
        raw_text=raw_text,
        observations=observations,
        num_observations=len(observations),
        extraction_error=None,
    )
