"""
Scrapes FDA Form 483s from the FDA FOIA Electronic Reading Room.
483s are published at: https://www.fda.gov/inspections-compliance-enforcement/inspection-observations
and the FOIA reading room organized by year/district.
Uses Playwright (real browser) to navigate JavaScript-rendered pages.
"""
import logging
import os
from datetime import date, datetime
from typing import Generator

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

logger = logging.getLogger(__name__)

# FDA 483 FOIA reading room — organized by year
FDA_483_FOIA_URL = "https://www.fda.gov/regulatory-information/freedom-of-information/foia-electronic-reading-room"
# FDA inspection observations landing page
FDA_OBS_URL = "https://www.fda.gov/inspections-compliance-enforcement/inspection-observations"
# FDA ORA data dashboard
FDA_DASHBOARD_URL = "https://datadashboard.fda.gov/ora/cd/inspections.htm"

PHARMA_KEYWORDS = ["DRUG", "PHARMA", "API", "BIOLOGIC", "CDER", "CBER", "PHARMACEUTICAL"]


def _parse_date(date_str: str) -> date | None:
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def _is_pharma(text: str) -> bool:
    text_upper = text.upper()
    return any(kw in text_upper for kw in PHARMA_KEYWORDS)


def _get_browser(p):
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


def _save_debug(page, name: str):
    path = f"/tmp/fda_{name}_debug.html"
    with open(path, "w") as f:
        f.write(page.content())
    logger.info(f"Saved debug HTML: {path}")


def _collect_483_links_from_foia(page, year: int) -> list[dict]:
    """
    Navigate the FDA FOIA reading room and collect 483 PDF links for a given year.
    Returns list of {firm_name, pdf_url, year} dicts.
    """
    logger.info(f"Looking for Form 483s for year {year} in FOIA reading room...")
    records = []

    try:
        page.goto(FDA_483_FOIA_URL, timeout=60000, wait_until="networkidle")
        page.wait_for_timeout(3000)
        _save_debug(page, "foia_main")

        # Find links containing "483" and the year
        links = page.query_selector_all("a")
        year_links = []
        for link in links:
            href = link.get_attribute("href") or ""
            text = link.inner_text().strip()
            if str(year) in text or str(year) in href:
                if "483" in text or "483" in href or "observation" in text.lower():
                    year_links.append({"text": text, "href": href})
                    logger.info(f"Found year link: {text} -> {href}")

        # Follow each year link and collect PDF links
        for year_link in year_links[:5]:  # limit to avoid excessive crawling
            href = year_link["href"]
            if not href:
                continue
            full_url = href if href.startswith("http") else f"https://www.fda.gov{href}"
            try:
                page.goto(full_url, timeout=30000, wait_until="networkidle")
                page.wait_for_timeout(2000)
                _save_debug(page, f"foia_{year}")

                # Collect PDF links on this page
                pdf_links = page.query_selector_all("a[href*='.pdf'], a[href*='.PDF']")
                for pdf in pdf_links:
                    href = pdf.get_attribute("href") or ""
                    text = pdf.inner_text().strip()
                    pdf_url = href if href.startswith("http") else f"https://www.fda.gov{href}"
                    records.append({
                        "fda_inspection_id": None,
                        "firm_name": text or "Unknown",
                        "city": None,
                        "state": None,
                        "zip_code": None,
                        "country": "US",
                        "inspection_end_date": None,
                        "product_type": "Drug",
                        "center": "CDER",
                        "pdf_url": pdf_url,
                    })
                logger.info(f"Found {len(pdf_links)} PDFs at {full_url}")
            except Exception as e:
                logger.warning(f"Failed to load {full_url}: {e}")
                continue

    except Exception as e:
        logger.error(f"FOIA reading room scrape failed: {e}")

    return records


def _collect_from_obs_page(page, start_date: date, end_date: date) -> list[dict]:
    """
    Try the FDA inspection observations page for links to 483s.
    """
    records = []
    try:
        logger.info(f"Trying FDA observations page: {FDA_OBS_URL}")
        page.goto(FDA_OBS_URL, timeout=60000, wait_until="networkidle")
        page.wait_for_timeout(3000)
        _save_debug(page, "obs_page")

        # Collect all PDF and detail links
        links = page.query_selector_all("a[href*='.pdf'], a[href*='483'], a[href*='observation']")
        logger.info(f"Found {len(links)} relevant links on observations page")

        for link in links:
            href = link.get_attribute("href") or ""
            text = link.inner_text().strip()
            if not href:
                continue
            full_url = href if href.startswith("http") else f"https://www.fda.gov{href}"
            if ".pdf" in href.lower():
                records.append({
                    "fda_inspection_id": None,
                    "firm_name": text or "Unknown",
                    "city": None,
                    "state": None,
                    "zip_code": None,
                    "country": "US",
                    "inspection_end_date": None,
                    "product_type": "Drug",
                    "center": "CDER",
                    "pdf_url": full_url,
                })
    except Exception as e:
        logger.error(f"Observations page scrape failed: {e}")

    return records


def _scrape_with_browser(start_date: str, end_date: str) -> list[dict]:
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    years = list(range(start.year, end.year + 1)) if start and end else [2025]

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

        # Try FOIA reading room first
        for year in years:
            found = _collect_483_links_from_foia(page, year)
            records.extend(found)
            logger.info(f"Year {year}: collected {len(found)} records from FOIA")

        # If no results, try the observations page
        if not records:
            logger.info("No results from FOIA — trying observations page")
            found = _collect_from_obs_page(page, start, end)
            records.extend(found)

        # Save final page for debugging
        _save_debug(page, "final")
        browser.close()

    logger.info(f"Total records collected: {len(records)}")
    return records


def scrape_inspections(start_date: str, end_date: str) -> Generator[dict, None, None]:
    """
    Generator yielding pharmaceutical Form 483 inspection records.
    Date format: MM/DD/YYYY
    """
    logger.info(f"Scraping FDA 483s from {start_date} to {end_date}")
    records = _scrape_with_browser(start_date, end_date)
    logger.info(f"Scrape complete. Total found: {len(records)}")
    for record in records:
        yield record
