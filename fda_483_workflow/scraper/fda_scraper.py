"""
Scrapes the FDA inspection observations database (Form 483s) filtered to
pharmaceutical product types. Handles both weekly pulls and historical backfill.
"""
import time
import logging
from datetime import date, datetime
from typing import Generator
import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

from config import (
    FDA_483_URL, REQUEST_DELAY_SECONDS, REQUEST_TIMEOUT_SECONDS,
    MAX_RETRIES, PHARMA_PRODUCT_CODES
)

logger = logging.getLogger(__name__)

# FDA inspection observations search API endpoint
FDA_SEARCH_API = "https://www.accessdata.fda.gov/scripts/inspsearch/inspectionresults.cfm"

PHARMA_CENTER_FILTERS = ["CDER", "CBER", "CVM"]


@retry(stop=stop_after_attempt(MAX_RETRIES), wait=wait_exponential(multiplier=2, min=2, max=30))
def _get(url: str, params: dict = None, session: requests.Session = None) -> requests.Response:
    s = session or requests.Session()
    resp = s.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS, headers={
        "User-Agent": "Mozilla/5.0 (compatible; FDA483Researcher/1.0)"
    })
    resp.raise_for_status()
    return resp


def _parse_inspection_row(row) -> dict | None:
    """Parse a single table row from the FDA inspection search results."""
    cells = row.find_all("td")
    if len(cells) < 8:
        return None

    def text(cell):
        return cell.get_text(strip=True)

    pdf_link = row.find("a", href=lambda h: h and ".pdf" in h.lower())

    return {
        "fda_inspection_id": text(cells[0]) or None,
        "firm_name": text(cells[1]),
        "city": text(cells[2]),
        "state": text(cells[3]),
        "zip_code": text(cells[4]),
        "country": text(cells[5]),
        "inspection_end_date": _parse_date(text(cells[6])),
        "product_type": text(cells[7]),
        "center": text(cells[8]) if len(cells) > 8 else None,
        "pdf_url": ("https://www.accessdata.fda.gov" + pdf_link["href"]) if pdf_link else None,
    }


def _parse_date(date_str: str) -> date | None:
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def _is_pharma(record: dict) -> bool:
    """Filter to pharmaceutical inspections only."""
    product = (record.get("product_type") or "").upper()
    center = (record.get("center") or "").upper()
    pharma_keywords = ["DRUG", "PHARMA", "API", "BIOLOGIC", "FINISHED DOSAGE"]
    return (
        any(kw in product for kw in pharma_keywords)
        or center in PHARMA_CENTER_FILTERS
    )


def fetch_inspections_page(
    start_date: str,
    end_date: str,
    page: int = 1,
    page_size: int = 100,
    session: requests.Session = None,
) -> tuple[list[dict], bool]:
    """
    Fetch one page of inspection results from the FDA search.
    Returns (records, has_more_pages).
    """
    params = {
        "action": "Search",
        "inspDateFrom": start_date,
        "inspDateTo": end_date,
        "pageNum": page,
        "rowsPerPage": page_size,
        "output": "display",
    }

    try:
        resp = _get(FDA_SEARCH_API, params=params, session=session)
    except Exception as e:
        logger.error(f"Failed to fetch page {page}: {e}")
        return [], False

    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table", {"id": "inspectionResultsTable"}) or soup.find("table", class_="inspectionResults")

    if not table:
        # Fallback: find any data table
        tables = soup.find_all("table")
        table = next((t for t in tables if t.find("td")), None)

    if not table:
        return [], False

    rows = table.find_all("tr")[1:]  # skip header
    records = []
    for row in rows:
        record = _parse_inspection_row(row)
        if record and _is_pharma(record):
            records.append(record)

    # Check for next-page link
    next_link = soup.find("a", string=lambda s: s and "next" in s.lower())
    has_more = next_link is not None

    return records, has_more


def scrape_inspections(
    start_date: str,
    end_date: str,
) -> Generator[dict, None, None]:
    """
    Generator that yields all pharmaceutical inspection records
    between start_date and end_date (format: MM/DD/YYYY).
    """
    session = requests.Session()
    page = 1
    total = 0

    logger.info(f"Scraping FDA 483s from {start_date} to {end_date}")

    while True:
        records, has_more = fetch_inspections_page(start_date, end_date, page=page, session=session)
        for record in records:
            total += 1
            yield record

        logger.info(f"Page {page}: {len(records)} pharma records (total so far: {total})")

        if not has_more:
            break

        page += 1
        time.sleep(REQUEST_DELAY_SECONDS)

    logger.info(f"Scrape complete. Total pharmaceutical inspections found: {total}")
