"""
Scrapes FDA Warning Letters filtered to CGMP/Pharmaceutical violations.
Source: https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/
        compliance-actions-and-activities/warning-letters

Strategy:
1. Load the Warning Letters DataTable
2. Filter by Subject "CGMP/Finished Pharmaceuticals/Adulterated" and date range
3. Export Excel (downloads all filtered results at once)
4. Parse Excel into inspection records
"""
import logging
import os
import time
import glob
from datetime import date, datetime
from typing import Generator

import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

logger = logging.getLogger(__name__)

FDA_WARNING_LETTERS_URL = (
    "https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations"
    "/compliance-actions-and-activities/warning-letters"
)

CGMP_SUBJECTS = [
    "CGMP/Finished Pharmaceuticals/Adulterated",
    "CGMP/Active Pharmaceutical Ingredients/Adulterated",
    "CGMP/Biological Products",
    "CGMP/Finished Pharmaceuticals",
]


def _parse_date(val) -> date | None:
    if isinstance(val, date):
        return val
    if isinstance(val, datetime):
        return val.date()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(str(val).strip(), fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def _is_cgmp_pharma(subject: str) -> bool:
    s = (subject or "").upper()
    return "CGMP" in s and any(kw in s for kw in ["PHARMA", "DRUG", "API", "BIOLOG", "FINISHED"])


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


def _scrape_with_browser(start_date: str, end_date: str) -> list[dict]:
    records = []
    download_path = os.path.expanduser("~/Downloads")

    with sync_playwright() as p:
        browser = _get_browser(p)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            accept_downloads=True,
        )
        page = context.new_page()

        try:
            logger.info("Loading FDA Warning Letters page...")
            page.goto(FDA_WARNING_LETTERS_URL, timeout=90000, wait_until="domcontentloaded")
            page.wait_for_timeout(6000)
            _save_debug(page, "wl_loaded")

            # Log all inputs to understand filter structure
            inputs = page.query_selector_all("input, select")
            logger.info(f"Found {len(inputs)} form fields on page:")
            for inp in inputs:
                tag = inp.evaluate("el => el.tagName")
                logger.info(
                    f"  {tag}: name='{inp.get_attribute('name') or ''}' "
                    f"id='{inp.get_attribute('id') or ''}' "
                    f"type='{inp.get_attribute('type') or ''}' "
                    f"placeholder='{inp.get_attribute('placeholder') or ''}'"
                )

            # ---- Apply date filter ----
            # Try to fill "Posted Date From" filter
            for sel in [
                "input[name*='date_from']", "input[name*='start']",
                "input[placeholder*='From']", "input[placeholder*='Start']",
                "input[placeholder*='from']", "#edit-field-issue-datetime-value",
            ]:
                try:
                    page.fill(sel, start_date, timeout=2000)
                    logger.info(f"Filled start date with: {sel}")
                    break
                except Exception:
                    continue

            for sel in [
                "input[name*='date_to']", "input[name*='end']",
                "input[placeholder*='To']", "input[placeholder*='End']",
                "input[placeholder*='to']", "#edit-field-issue-datetime-value-1",
            ]:
                try:
                    page.fill(sel, end_date, timeout=2000)
                    logger.info(f"Filled end date with: {sel}")
                    break
                except Exception:
                    continue

            # ---- Apply subject column filter (DataTables column search) ----
            # DataTables column search inputs are usually below the header row
            subject_filled = False
            for sel in [
                "tfoot input", "thead input",
                "input[placeholder*='Subject']", "input[placeholder*='subject']",
            ]:
                try:
                    elems = page.query_selector_all(sel)
                    for elem in elems:
                        placeholder = (elem.get_attribute("placeholder") or "").lower()
                        if "subject" in placeholder or len(elems) == 1:
                            elem.fill("CGMP/Finished Pharmaceuticals", timeout=2000)
                            elem.press("Enter")
                            logger.info(f"Filled subject column filter: {sel}")
                            subject_filled = True
                            break
                    if subject_filled:
                        break
                except Exception:
                    continue

            # Submit any filter form
            for sel in ["input[type='submit']", "button[type='submit']",
                        "#edit-submit-warning-letters", "input[value='Apply']"]:
                try:
                    page.click(sel, timeout=2000)
                    logger.info(f"Clicked apply/submit: {sel}")
                    page.wait_for_timeout(3000)
                    break
                except Exception:
                    continue

            _save_debug(page, "wl_filtered")

            # ---- Click Export Excel ----
            try:
                with page.expect_download(timeout=30000) as download_info:
                    page.click("button:has-text('Export Excel'), a:has-text('Export Excel'), "
                               "input[value*='Export'], button:has-text('Export')", timeout=5000)
                download = download_info.value
                excel_path = os.path.join(download_path, "fda_warning_letters.xlsx")
                download.save_as(excel_path)
                logger.info(f"Downloaded Excel: {excel_path}")
                records = _parse_excel(excel_path, start_date, end_date)

            except Exception as e:
                logger.warning(f"Excel export failed ({e}) — falling back to page scraping")
                records = _scrape_table_pages(page)

        except PWTimeout as e:
            logger.error(f"Page timed out: {e}")
        except Exception as e:
            logger.error(f"Scrape error: {e}")

        _save_debug(page, "wl_final")
        browser.close()

    return records


def _parse_excel(excel_path: str, start_date: str, end_date: str) -> list[dict]:
    """Parse the downloaded Warning Letters Excel file into inspection records."""
    logger.info(f"Parsing Excel: {excel_path}")
    try:
        df = pd.read_excel(excel_path)
        logger.info(f"Excel columns: {list(df.columns)}")
        logger.info(f"Total rows in Excel: {len(df)}")
    except Exception as e:
        logger.error(f"Failed to read Excel: {e}")
        return []

    # Normalise column names
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    logger.info(f"Normalised columns: {list(df.columns)}")

    # Map column names flexibly
    col_map = {}
    for col in df.columns:
        if "company" in col or "firm" in col:
            col_map["firm_name"] = col
        elif "posted" in col:
            col_map["posted_date"] = col
        elif "issue" in col and "date" in col:
            col_map["issue_date"] = col
        elif "subject" in col:
            col_map["subject"] = col
        elif "office" in col or "issuing" in col:
            col_map["office"] = col
        elif "url" in col or "link" in col or "letter" in col:
            col_map["url"] = col

    logger.info(f"Column mapping: {col_map}")

    start = _parse_date(start_date)
    end = _parse_date(end_date)

    records = []
    for _, row in df.iterrows():
        subject = str(row.get(col_map.get("subject", ""), "") or "")
        if not _is_cgmp_pharma(subject):
            continue

        issue_date = _parse_date(row.get(col_map.get("issue_date", ""), ""))
        posted_date = _parse_date(row.get(col_map.get("posted_date", ""), ""))
        ref_date = issue_date or posted_date

        if start and end and ref_date:
            if not (start <= ref_date <= end):
                continue

        firm = str(row.get(col_map.get("firm_name", ""), "") or "Unknown").strip()
        url = str(row.get(col_map.get("url", ""), "") or "").strip()
        if url and not url.startswith("http"):
            url = f"https://www.fda.gov{url}"

        records.append({
            "fda_inspection_id": None,
            "firm_name": firm,
            "city": None,
            "state": None,
            "zip_code": None,
            "country": "US",
            "inspection_end_date": ref_date,
            "product_type": subject,
            "center": "CDER",
            "pdf_url": url if url.endswith(".pdf") else None,
            "warning_letter_url": url if not url.endswith(".pdf") else None,
        })

    logger.info(f"Parsed {len(records)} CGMP pharmaceutical records from Excel")
    return records


def _scrape_table_pages(page) -> list[dict]:
    """Fallback: scrape the visible table page by page."""
    from bs4 import BeautifulSoup
    records = []
    page_num = 1

    while True:
        soup = BeautifulSoup(page.content(), "html.parser")
        table = soup.find("table")
        if not table:
            break

        rows = table.find_all("tr")[1:]
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 4:
                continue
            subject = cells[4].get_text(strip=True) if len(cells) > 4 else ""
            if not _is_cgmp_pharma(subject):
                continue
            link = row.find("a", href=True)
            href = link["href"] if link else ""
            full_url = href if href.startswith("http") else f"https://www.fda.gov{href}"
            records.append({
                "fda_inspection_id": None,
                "firm_name": cells[2].get_text(strip=True) if len(cells) > 2 else "Unknown",
                "city": None, "state": None, "zip_code": None, "country": "US",
                "inspection_end_date": _parse_date(cells[1].get_text(strip=True)),
                "product_type": subject,
                "center": "CDER",
                "pdf_url": None,
                "warning_letter_url": full_url,
            })

        logger.info(f"Page {page_num}: {len(rows)} rows scraped")

        try:
            next_btn = page.query_selector("a:has-text('Next'), .paginate_button.next:not(.disabled)")
            if not next_btn:
                break
            next_btn.click()
            page.wait_for_timeout(2000)
            page_num += 1
        except Exception:
            break

    return records


def scrape_inspections(start_date: str, end_date: str) -> Generator[dict, None, None]:
    """
    Generator yielding FDA CGMP Warning Letter records.
    Date format: MM/DD/YYYY
    """
    logger.info(f"Scraping FDA CGMP Warning Letters from {start_date} to {end_date}")
    records = _scrape_with_browser(start_date, end_date)
    logger.info(f"Scrape complete. Total found: {len(records)}")
    for record in records:
        yield record
