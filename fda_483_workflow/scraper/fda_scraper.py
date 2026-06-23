"""
Scrapes FDA Warning Letters filtered to CGMP/Pharmaceutical violations.
Source: https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/
        compliance-actions-and-activities/warning-letters

Warning Letters explicitly cite 21 CFR violations and GMP deficiencies,
making them ideal for cross-framework GMP analysis.
Uses Playwright with system Chrome to navigate the search interface.
"""
import logging
import os
import time
from datetime import date, datetime
from typing import Generator

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

FDA_WARNING_LETTERS_URL = (
    "https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations"
    "/compliance-actions-and-activities/warning-letters"
)

# Subject filter for pharmaceutical GMP warning letters
PHARMA_SUBJECTS = [
    "CGMP/Finished Pharmaceuticals/Adulterated",
    "CGMP/Active Pharmaceutical Ingredients/Adulterated",
    "CGMP/Biological Products",
]


def _parse_date(date_str: str) -> date | None:
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%m-%d-%Y"):
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


def _parse_warning_letter_list(html: str) -> list[dict]:
    """Parse the warning letters search results table."""
    soup = BeautifulSoup(html, "html.parser")
    records = []

    # FDA warning letters are typically in a table or list
    table = soup.find("table")
    if table:
        rows = table.find_all("tr")[1:]  # skip header
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 3:
                continue

            def text(i):
                return cells[i].get_text(strip=True) if i < len(cells) else ""

            link = row.find("a", href=True)
            href = link["href"] if link else ""
            full_url = href if href.startswith("http") else f"https://www.fda.gov{href}"

            records.append({
                "fda_inspection_id": text(0) or None,
                "firm_name": text(1) or (link.get_text(strip=True) if link else "Unknown"),
                "city": None,
                "state": None,
                "zip_code": None,
                "country": text(2) if len(cells) > 2 else "US",
                "inspection_end_date": _parse_date(text(3)) if len(cells) > 3 else None,
                "product_type": "Drug/Pharmaceutical (Warning Letter)",
                "center": "CDER",
                "pdf_url": None,
                "warning_letter_url": full_url,
            })
        logger.info(f"Parsed {len(records)} records from table")
        return records

    # Fallback: look for links in list items
    links = soup.select("ul li a, .views-row a, .field-content a")
    for link in links:
        href = link.get("href", "")
        if not href:
            continue
        full_url = href if href.startswith("http") else f"https://www.fda.gov{href}"
        records.append({
            "fda_inspection_id": None,
            "firm_name": link.get_text(strip=True) or "Unknown",
            "city": None,
            "state": None,
            "zip_code": None,
            "country": "US",
            "inspection_end_date": None,
            "product_type": "Drug/Pharmaceutical (Warning Letter)",
            "center": "CDER",
            "pdf_url": None,
            "warning_letter_url": full_url,
        })

    logger.info(f"Parsed {len(records)} records from link list")
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

        try:
            logger.info(f"Loading FDA Warning Letters page...")
            page.goto(FDA_WARNING_LETTERS_URL, timeout=90000, wait_until="domcontentloaded")
            page.wait_for_timeout(5000)
            _save_debug(page, "warning_letters_main")

            # Log all form fields to understand the search interface
            inputs = page.query_selector_all("input, select")
            logger.info(f"Found {len(inputs)} form fields:")
            for inp in inputs:
                name = inp.get_attribute("name") or ""
                id_ = inp.get_attribute("id") or ""
                type_ = inp.get_attribute("type") or ""
                tag = inp.evaluate("el => el.tagName")
                logger.info(f"  {tag}: name='{name}' id='{id_}' type='{type_}'")

            # Try to fill in date range
            filled = False
            for from_sel in ["input[name*='date_from']", "input[name*='start']",
                              "input[name*='from']", "#edit-field-issue-datetime-value",
                              "input[placeholder*='From']", "input[placeholder*='Start']"]:
                try:
                    page.fill(from_sel, start_date, timeout=2000)
                    logger.info(f"Filled start date: {from_sel}")
                    filled = True
                    break
                except Exception:
                    continue

            for to_sel in ["input[name*='date_to']", "input[name*='end']",
                           "input[name*='to']", "#edit-field-issue-datetime-value-1",
                           "input[placeholder*='To']", "input[placeholder*='End']"]:
                try:
                    page.fill(to_sel, end_date, timeout=2000)
                    logger.info(f"Filled end date: {to_sel}")
                    break
                except Exception:
                    continue

            # Try to select CGMP subject filter
            for sel_selector in ["select[name*='subject']", "select[name*='field']",
                                  "#edit-field-subject-tid", "select[id*='subject']"]:
                try:
                    page.select_option(sel_selector,
                                       label="CGMP/Finished Pharmaceuticals/Adulterated",
                                       timeout=2000)
                    logger.info(f"Selected CGMP subject filter: {sel_selector}")
                    break
                except Exception:
                    continue

            # Submit search
            for submit_sel in ["input[type='submit']", "button[type='submit']",
                                "#edit-submit-warning-letters", "button:has-text('Search')",
                                "input[value='Apply']", "input[value='Search']"]:
                try:
                    page.click(submit_sel, timeout=2000)
                    logger.info(f"Clicked submit: {submit_sel}")
                    page.wait_for_timeout(4000)
                    break
                except Exception:
                    continue

            _save_debug(page, "warning_letters_results")

            # Collect results across pages
            page_num = 1
            while True:
                html = page.content()
                page_records = _parse_warning_letter_list(html)
                records.extend(page_records)
                logger.info(f"Page {page_num}: {len(page_records)} warning letters")

                # Next page
                try:
                    next_btn = page.query_selector("a:has-text('Next'), li.next a, .pager-next a")
                    if not next_btn:
                        break
                    next_btn.click()
                    page.wait_for_timeout(3000)
                    page_num += 1
                except Exception:
                    break

        except PWTimeout as e:
            logger.error(f"Page timed out: {e}")
        except Exception as e:
            logger.error(f"Scrape failed: {e}")

        _save_debug(page, "final")
        browser.close()

    return records


def scrape_inspections(start_date: str, end_date: str) -> Generator[dict, None, None]:
    """
    Generator yielding FDA Warning Letter records for pharmaceutical CGMP violations.
    Date format: MM/DD/YYYY
    """
    logger.info(f"Scraping FDA Warning Letters from {start_date} to {end_date}")
    records = _scrape_with_browser(start_date, end_date)
    logger.info(f"Scrape complete. Total found: {len(records)}")
    for record in records:
        yield record
