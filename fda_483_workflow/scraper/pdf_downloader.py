"""
Downloads Form 483 PDFs from FDA servers with retry logic and deduplication.
"""
import hashlib
import logging
import time
from pathlib import Path

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from config import PDF_DIR, REQUEST_DELAY_SECONDS, REQUEST_TIMEOUT_SECONDS, MAX_RETRIES

logger = logging.getLogger(__name__)


def _pdf_filename(url: str, fda_id: str = None) -> str:
    suffix = fda_id.replace("/", "_").replace(" ", "_") if fda_id else hashlib.md5(url.encode()).hexdigest()
    return f"483_{suffix}.pdf"


@retry(stop=stop_after_attempt(MAX_RETRIES), wait=wait_exponential(multiplier=2, min=2, max=60))
def download_pdf(url: str, fda_id: str = None) -> Path | None:
    """
    Download a single PDF. Returns local path or None if unavailable.
    Skips download if file already exists.
    """
    filename = _pdf_filename(url, fda_id)
    local_path = PDF_DIR / filename

    if local_path.exists() and local_path.stat().st_size > 1024:
        logger.debug(f"Already downloaded: {filename}")
        return local_path

    try:
        resp = requests.get(
            url,
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers={"User-Agent": "Mozilla/5.0 (compatible; FDA483Researcher/1.0)"},
            stream=True,
        )
        resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")
        if "pdf" not in content_type.lower() and not url.lower().endswith(".pdf"):
            logger.warning(f"Unexpected content type '{content_type}' for {url}")

        with open(local_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        logger.info(f"Downloaded: {filename} ({local_path.stat().st_size // 1024} KB)")
        return local_path

    except requests.HTTPError as e:
        if e.response.status_code == 404:
            logger.warning(f"PDF not found (404): {url}")
            return None
        raise


def batch_download(records: list[dict], delay: float = REQUEST_DELAY_SECONDS) -> list[dict]:
    """
    Download PDFs for a list of inspection records.
    Updates each record with 'pdf_local_path' and 'pdf_downloaded'.
    """
    updated = []
    for i, record in enumerate(records, 1):
        url = record.get("pdf_url")
        if not url:
            record["pdf_downloaded"] = False
            record["pdf_local_path"] = None
            updated.append(record)
            continue

        path = download_pdf(url, fda_id=record.get("fda_inspection_id"))
        record["pdf_local_path"] = str(path) if path else None
        record["pdf_downloaded"] = path is not None
        updated.append(record)

        if i % 10 == 0:
            logger.info(f"Downloaded {i}/{len(records)} PDFs")

        time.sleep(delay)

    return updated
