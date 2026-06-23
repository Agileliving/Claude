"""
Scrapes FDA Form 483 PDFs using the FDA's site search (search.gov).
Searches for "form 483 pharmaceutical [year]" and collects PDF links.
Uses Playwright (real browser) with your system Chrome.
"""
import logging
import os
import time
from datetime import date, datetime
from typing import Generator
from urllib.parse import urlencode

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

logger = logging.getLogger(__name__)

# FDA uses search.gov — this is the reliable search endpoint
FDA_SEARCH_BASE = "https://search.usa.gov/search"
FDA_AFFILIATE = "fda"

PHARMA_KEYWORDS = ["DRUG", "PHARMA", "API", "BIOLOGIC", "CDER", "CBER", "PHARMACEUTICAL", "483"]


def _parse_date(date_str: str) -> date | None:
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except (ValueError, TypeError):
            continue
    return None


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


def _search_for_483s(page, year: int, query_term: str = "form 483 pharmaceutical") -> list[dict]:
    """Search FDA site for 483 PDFs for a given year."""
    records = []
    search_query = f"{query_term} {year}"
    params = urlencode({"affiliate": FDA_AFFILIATE, "query": search_query})
    search_url = f"{FDA_SEARCH_BASE}?{params}"

    logger.info(f"Searching FDA for: {search_query}")
    logger.info(f"URL: {search_url}")

    try:
        page.goto(search_url, timeout=90000, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        _save_debug(page, f"search_{year}")

        # Collect PDF links from search results
        pdf_links = page.query_selector_all("a[href*='.pdf'], a[href*='.PDF']")
        logger.info(f"Found {len(pdf_links)} PDF links in search results for {year}")

        for link in pdf_links:
            href = link.get_attribute("href") or ""
            text = link.inner_text().strip()
            if not href:
                continue
            full_url = href if href.startswith("http") else f"https://www.fda.gov{href}"
            records.append({
                "fda_inspection_id": None,
                "firm_name": text or f"FDA 483 - {year}",
                "city": None,
                "state": None,
                "zip_code": None,
                "country": "US",
                "inspection_end_date": date(year, 1, 1),  # approximate
                "product_type": "Drug/Pharmaceutical",
                "center": "CDER",
                "pdf_url": full_url,
            })

        # Also collect links to pages that may contain 483s
        result_links = page.query_selector_all(".result-title a, .search-result-title a, h3 a, h2 a")
        for link in result_links:
            href = link.get_attribute("href") or ""
            text = link.inner_text().strip()
            if "483" in href or "483" in text or "observation" in text.lower():
                logger.info(f"Found 483 result page: {text} -> {href}")

    except PWTimeout:
        logger.warning(f"Search timed out for year {year}")
    except Exception as e:
        logger.error(f"Search failed for year {year}: {e}")

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

        for year in years:
            found = _search_for_483s(page, year)
            records.extend(found)
            logger.info(f"Year {year}: {len(found)} 483 records found")
            time.sleep(2)

        _save_debug(page, "final")
        browser.close()

    logger.info(f"Total records collected: {len(records)}")
    return records


def scrape_inspections(start_date: str, end_date: str) -> Generator[dict, None, None]:
    """
    Generator yielding pharmaceutical Form 483 records.
    Date format: MM/DD/YYYY
    """
    logger.info(f"Scraping FDA 483s from {start_date} to {end_date}")
    records = _scrape_with_browser(start_date, end_date)
    logger.info(f"Scrape complete. Total found: {len(records)}")
    for record in records:
        yield record
