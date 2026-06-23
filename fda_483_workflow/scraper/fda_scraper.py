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

            # ---- Use exact field IDs discovered from page inspection ----

            # 1. Search for CGMP in the fulltext search box
            try:
                page.fill("#edit-search-api-fulltext", "CGMP Finished Pharmaceuticals Adulterated", timeout=3000)
                logger.info("Filled fulltext search with CGMP filter")
            except Exception as e:
                logger.warning(f"Could not fill fulltext search: {e}")

            # 2. Select the year in the date dropdown
            start_year = start_date.split("/")[-1] if "/" in start_date else "2025"
            for year_sel in ["#edit-field-letter-issue-datetime", "#field_letter_issue_datetime_2"]:
                try:
                    opts = page.query_selector_all(f"{year_sel} option")
                    opt_values = [o.get_attribute("value") for o in opts]
                    logger.info(f"Date dropdown options ({year_sel}): {opt_values}")
                    if start_year in opt_values:
                        page.select_option(year_sel, value=start_year, timeout=3000)
                        logger.info(f"Selected year {start_year} in {year_sel}")
                except Exception as e:
                    logger.warning(f"Date dropdown {year_sel}: {e}")

            # 3. Use the DataTable column filter for Subject (id='lcds-datatable-filter--letter')
            try:
                opts = page.query_selector_all("#lcds-datatable-filter--letter option")
                opt_texts = [o.inner_text().strip() for o in opts]
                logger.info(f"Letter filter options: {opt_texts}")
                # Find the CGMP option
                cgmp_val = None
                for o in opts:
                    if "CGMP" in o.inner_text() and "Finished" in o.inner_text():
                        cgmp_val = o.get_attribute("value")
                        break
                if cgmp_val:
                    page.select_option("#lcds-datatable-filter--letter", value=cgmp_val, timeout=3000)
                    logger.info(f"Selected CGMP subject filter: value={cgmp_val}")
            except Exception as e:
                logger.warning(f"Letter filter: {e}")

            # 4. Click the filter Apply button — specifically the one near the warning letters form
            #    Avoid the email subscription submit button
            clicked_apply = False
            apply_selectors = [
                "#edit-submit-warning-letters",
                "form.views-exposed-form input[type='submit']",
                "input[id*='submit'][id*='warning']",
                ".views-exposed-form input[type='submit']",
            ]
            for sel in apply_selectors:
                try:
                    page.click(sel, timeout=3000)
                    logger.info(f"Clicked filter apply: {sel}")
                    clicked_apply = True
                    page.wait_for_timeout(4000)
                    break
                except Exception:
                    continue

            if not clicked_apply:
                # Use JavaScript to trigger DataTable filtering directly
                try:
                    page.evaluate("""
                        var table = document.querySelector('table');
                        if (table && $.fn && $.fn.DataTable) {
                            $(table).DataTable().search('CGMP Finished Pharmaceuticals').draw();
                        }
                    """)
                    logger.info("Triggered DataTable search via JavaScript")
                    page.wait_for_timeout(3000)
                except Exception as e:
                    logger.warning(f"JS DataTable search failed: {e}")

            _save_debug(page, "wl_filtered")

            # 5. Try Export Excel — use multiple selectors and wait longer
            export_selectors = [
                "button.dt-button:has-text('Excel')",
                "a.dt-button:has-text('Excel')",
                ".dt-buttons button:has-text('Excel')",
                ".dt-buttons a:has-text('Excel')",
                "button:has-text('Export Excel')",
                "a:has-text('Export Excel')",
                ".buttons-excel",
            ]
            exported = False
            for sel in export_selectors:
                try:
                    btn = page.query_selector(sel)
                    if btn:
                        logger.info(f"Found Excel export button: {sel}")
                        with page.expect_download(timeout=60000) as download_info:
                            btn.click()
                        download = download_info.value
                        excel_path = os.path.join(download_path, "fda_warning_letters.xlsx")
                        download.save_as(excel_path)
                        logger.info(f"Downloaded Excel: {excel_path}")
                        records = _parse_excel(excel_path, start_date, end_date)
                        exported = True
                        break
                except Exception as e:
                    logger.warning(f"Export attempt failed ({sel}): {e}")
                    continue

            if not exported:
                logger.info("Excel export not available — scraping table pages directly")
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
