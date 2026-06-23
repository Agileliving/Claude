"""
Scrapes the FDA inspection observations database (Form 483s) filtered to
pharmaceutical product types. Uses Playwright (real browser) to bypass
FDA's bot detection on their search interface.
"""
import asyncio
import logging
import time
from datetime import date, datetime
from typing import Generator

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

from config import REQUEST_DELAY_SECONDS

logger = logging.getLogger(__name__)

FDA_SEARCH_URL = (
    "https://www.accessdata.fda.gov/scripts/inspsearch/inspectionresults.cfm"
)

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


def _scrape_with_browser(start_date: str, end_date: str) -> list[dict]:
    """
    Use a real Chromium browser to search the FDA inspection database
    and collect all pharmaceutical inspection records.
    """
    records = []

    with sync_playwright() as p:
        # Use installed Chrome/Chromium if available, fall back to downloaded
        import shutil
        chrome_paths = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        ]
        chrome_exe = next((p for p in chrome_paths if shutil.which(p) or __import__('os').path.exists(p)), None)

        if chrome_exe:
            browser = p.chromium.launch(headless=True, executable_path=chrome_exe)
        else:
            browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()

        try:
            logger.info("Opening FDA inspection search page...")
            page.goto(FDA_SEARCH_URL, timeout=60000, wait_until="networkidle")
            page.wait_for_timeout(3000)

            # Save page HTML for debugging
            html_debug = page.content()
            debug_path = "/tmp/fda_page_debug.html"
            with open(debug_path, "w") as f:
                f.write(html_debug)
            logger.info(f"Page HTML saved to {debug_path}")

            # Log all input fields found on the page
            inputs = page.query_selector_all("input, select")
            logger.info(f"Found {len(inputs)} form fields on page:")
            for inp in inputs:
                name = inp.get_attribute("name") or ""
                id_ = inp.get_attribute("id") or ""
                type_ = inp.get_attribute("type") or ""
                logger.info(f"  field: name='{name}' id='{id_}' type='{type_}'")

            # Try all common FDA form field name patterns
            filled_from = False
            for sel in [
                "#inspDateFrom", "input[name='inspDateFrom']",
                "input[name='dateFrom']", "input[name='from_date']",
                "input[name='startDate']", "input[name='start_date']",
            ]:
                try:
                    page.fill(sel, start_date, timeout=2000)
                    logger.info(f"Filled start date using: {sel}")
                    filled_from = True
                    break
                except Exception:
                    continue

            filled_to = False
            for sel in [
                "#inspDateTo", "input[name='inspDateTo']",
                "input[name='dateTo']", "input[name='to_date']",
                "input[name='endDate']", "input[name='end_date']",
            ]:
                try:
                    page.fill(sel, end_date, timeout=2000)
                    logger.info(f"Filled end date using: {sel}")
                    filled_to = True
                    break
                except Exception:
                    continue

            if not filled_from or not filled_to:
                logger.warning("Could not fill date fields — check /tmp/fda_page_debug.html for form structure")

            # Submit the form
            for submit in [
                "input[type='submit']", "button[type='submit']",
                "#searchBtn", "input[value='Search']", "button:has-text('Search')",
            ]:
                try:
                    page.click(submit, timeout=2000)
                    logger.info(f"Clicked submit: {submit}")
                    break
                except Exception:
                    continue

            page.wait_for_timeout(4000)

        except PWTimeout:
            logger.warning("Timed out loading FDA search page")

        # Parse results from all pages
        page_num = 1
        while True:
            html = page.content()
            page_records = _parse_html_table(html)
            pharma = [r for r in page_records if _is_pharma(r)]
            records.extend(pharma)
            logger.info(f"Page {page_num}: {len(pharma)} pharma records")

            # Try to go to next page
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


def _parse_html_table(html: str) -> list[dict]:
    """Parse inspection records from FDA results table HTML."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")

    # Try to find the results table
    table = (
        soup.find("table", {"id": "inspectionResultsTable"})
        or soup.find("table", class_="inspectionResults")
        or next((t for t in soup.find_all("table") if t.find("td")), None)
    )

    if not table:
        return []

    rows = table.find_all("tr")[1:]  # skip header row
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
            if href.startswith("http"):
                pdf_url = href
            else:
                pdf_url = "https://www.accessdata.fda.gov" + href

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


def scrape_inspections(start_date: str, end_date: str) -> Generator[dict, None, None]:
    """
    Generator that yields all pharmaceutical inspection records
    between start_date and end_date (format: MM/DD/YYYY).
    Uses a real browser to bypass FDA bot protection.
    """
    logger.info(f"Scraping FDA 483s from {start_date} to {end_date}")
    records = _scrape_with_browser(start_date, end_date)
    logger.info(f"Scrape complete. Total pharmaceutical inspections found: {len(records)}")
    for record in records:
        yield record
