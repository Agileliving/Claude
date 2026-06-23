"""
Scrapes the FDA inspection observations database (Form 483s) filtered to
pharmaceutical product types. Uses Playwright (real browser) to bypass
FDA's bot detection on their search interface.
"""
import logging
import os
import shutil
from datetime import date, datetime
from typing import Generator

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

from config import REQUEST_DELAY_SECONDS

logger = logging.getLogger(__name__)

# FDA inspection observations search — newer interface
FDA_SEARCH_URL = "https://www.fda.gov/inspections-compliance-enforcement/inspection-observations"
# Fallback: accessdata direct search
FDA_ACCESSDATA_URL = "https://www.accessdata.fda.gov/scripts/inspsearch/"

PHARMA_KEYWORDS = ["DRUG", "PHARMA", "API", "BIOLOGIC", "FINISHED DOSAGE", "CDER", "CBER"]


def _parse_date(date_str: str) -> date | None:
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def _is_pharma(record: dict) -> bool:
    product = (record.get("product_type") or "").upper()
    center = (record.get("center") or "").upper()
    return any(kw in product or kw in center for kw in PHARMA_KEYWORDS)


def _get_browser(p):
    """Return a browser instance using system Chrome if available."""
    chrome_paths = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    ]
    chrome_exe = next((path for path in chrome_paths if os.path.exists(path)), None)
    if chrome_exe:
        logger.info(f"Using system browser: {chrome_exe}")
        return p.chromium.launch(headless=True, executable_path=chrome_exe)
    return p.chromium.launch(headless=True)


def _save_debug_html(page, label: str = "fda"):
    path = f"/tmp/{label}_debug.html"
    with open(path, "w") as f:
        f.write(page.content())
    logger.info(f"Page HTML saved to {path}")
    return path


def _log_form_fields(page):
    inputs = page.query_selector_all("input, select")
    logger.info(f"Found {len(inputs)} form fields:")
    for inp in inputs:
        logger.info(
            f"  name='{inp.get_attribute('name') or ''}' "
            f"id='{inp.get_attribute('id') or ''}' "
            f"type='{inp.get_attribute('type') or ''}'"
        )


def _try_fill(page, selectors: list[str], value: str) -> bool:
    for sel in selectors:
        try:
            page.fill(sel, value, timeout=2000)
            logger.info(f"Filled '{value}' using selector: {sel}")
            return True
        except Exception:
            continue
    return False


def _try_click(page, selectors: list[str]) -> bool:
    for sel in selectors:
        try:
            page.click(sel, timeout=2000)
            logger.info(f"Clicked: {sel}")
            return True
        except Exception:
            continue
    return False


def _parse_html_table(html: str) -> list[dict]:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")

    table = (
        soup.find("table", {"id": "inspectionResultsTable"})
        or soup.find("table", class_="inspectionResults")
        or next((t for t in soup.find_all("table") if len(t.find_all("tr")) > 2), None)
    )
    if not table:
        return []

    rows = table.find_all("tr")[1:]
    records = []
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 6:
            continue

        def text(i):
            return cells[i].get_text(strip=True) if i < len(cells) else ""

        pdf_link = row.find("a", href=lambda h: h and ".pdf" in h.lower())
        pdf_url = None
        if pdf_link:
            href = pdf_link["href"]
            pdf_url = href if href.startswith("http") else "https://www.accessdata.fda.gov" + href

        records.append({
            "fda_inspection_id": text(0) or None,
            "firm_name": text(1),
            "city": text(2),
            "state": text(3),
            "zip_code": text(4),
            "country": text(5),
            "inspection_end_date": _parse_date(text(6)),
            "product_type": text(7),
            "center": text(8) if len(cells) > 8 else None,
            "pdf_url": pdf_url,
        })
    return records


def _scrape_with_browser(start_date: str, end_date: str) -> list[dict]:
    records = []

    with sync_playwright() as p:
        browser = _get_browser(p)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()

        # Try the accessdata search interface first
        for url in [FDA_ACCESSDATA_URL, FDA_SEARCH_URL]:
            try:
                logger.info(f"Trying: {url}")
                page.goto(url, timeout=60000, wait_until="networkidle")
                page.wait_for_timeout(3000)
                _save_debug_html(page, label=url.split("/")[2].replace(".", "_"))
                _log_form_fields(page)

                filled_from = _try_fill(page, [
                    "#inspDateFrom", "input[name='inspDateFrom']",
                    "input[name='dateFrom']", "input[name='startDate']",
                    "input[name='start_date']", "input[name='from']",
                ], start_date)

                filled_to = _try_fill(page, [
                    "#inspDateTo", "input[name='inspDateTo']",
                    "input[name='dateTo']", "input[name='endDate']",
                    "input[name='end_date']", "input[name='to']",
                ], end_date)

                if filled_from and filled_to:
                    _try_click(page, [
                        "input[type='submit']", "button[type='submit']",
                        "#searchBtn", "input[value='Search']",
                        "button:has-text('Search')", "input[value='GO']",
                    ])
                    page.wait_for_timeout(4000)
                    logger.info("Form submitted — parsing results")
                    break
                else:
                    logger.info(f"No matching date fields at {url}, trying next URL")

            except PWTimeout:
                logger.warning(f"Timeout loading {url}")
                continue

        # Collect results across pages
        page_num = 1
        while True:
            html = page.content()
            page_records = _parse_html_table(html)
            pharma = [r for r in page_records if _is_pharma(r)]
            records.extend(pharma)
            logger.info(f"Page {page_num}: {len(pharma)} pharma records (of {len(page_records)} total)")

            try:
                next_btn = page.query_selector("a:has-text('Next')")
                if not next_btn:
                    break
                next_btn.click()
                page.wait_for_timeout(2000)
                page_num += 1
            except Exception:
                break

        browser.close()

    return records


def scrape_inspections(start_date: str, end_date: str) -> Generator[dict, None, None]:
    """
    Generator yielding all pharmaceutical Form 483 inspection records
    between start_date and end_date (MM/DD/YYYY format).
    """
    logger.info(f"Scraping FDA 483s from {start_date} to {end_date}")
    records = _scrape_with_browser(start_date, end_date)
    logger.info(f"Scrape complete. Total pharmaceutical inspections found: {len(records)}")
    for record in records:
        yield record
