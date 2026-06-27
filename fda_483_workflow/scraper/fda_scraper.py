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
from datetime import date, datetime
from typing import Generator

import pandas as pd
from bs4 import BeautifulSoup
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
            # NOTE: Do NOT set the year dropdown (#field_letter_issue_datetime_2) — it causes
            # Excel to export with empty columns. Date filtering is done in Python after download.

            # 1. Use the DataTable column filter for Subject (id='lcds-datatable-filter--letter')
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

            # Always scrape the HTML table to get URLs (Excel strips hyperlinks)
            logger.info("Collecting URLs from rendered HTML table...")
            url_map = _collect_urls_from_table(page)

            # For firms not found in the table, fall back to HTTP search per company
            missing_firms = [r["firm_name"] for r in records if r["firm_name"] not in url_map]
            if missing_firms:
                logger.info(f"Looking up {len(missing_firms)} missing URLs via HTTP search...")
                for firm in missing_firms:
                    url = _find_url_via_requests(firm)
                    if url:
                        url_map[firm] = url
                        logger.info(f"HTTP fallback found URL for {firm}: {url}")

            for r in records:
                firm = r["firm_name"]
                if firm in url_map:
                    url = url_map[firm]
                    r["warning_letter_url"] = url if not url.lower().endswith(".pdf") else None
                    r["pdf_url"] = url if url.lower().endswith(".pdf") else r.get("pdf_url")
                    logger.info(f"Matched URL for {firm}: {url}")
                else:
                    logger.warning(f"No URL found for: {firm}")

            if not exported:
                logger.info("Excel export not available — scraping table pages directly")
                records = _scrape_table_pages(page, start_date, end_date)

        except PWTimeout as e:
            logger.error(f"Page timed out: {e}")
        except Exception as e:
            logger.error(f"Scrape error: {e}")

        _save_debug(page, "wl_final")
        browser.close()

    return records


def _parse_excel(excel_path: str, start_date: str, end_date: str) -> list[dict]:
    """
    Parse the downloaded Warning Letters Excel file.
    Extracts hyperlinks from the Company Name column using openpyxl directly.
    """
    import openpyxl
    logger.info(f"Parsing Excel: {excel_path}")

    try:
        wb = openpyxl.load_workbook(excel_path)
        ws = wb.active
    except Exception as e:
        logger.error(f"Failed to read Excel: {e}")
        return []

    # Read headers from first row
    headers = [str(cell.value or "").strip().lower().replace(" ", "_") for cell in ws[1]]
    logger.info(f"Excel columns: {headers}")

    # Find column indices
    def col_idx(keywords):
        for i, h in enumerate(headers):
            if any(kw in h for kw in keywords):
                return i
        return None

    firm_col   = col_idx(["company", "firm"])
    date_col   = col_idx(["issue", "letter_issue"])
    posted_col = col_idx(["posted"])
    subj_col   = col_idx(["subject"])

    logger.info(f"Columns — firm:{firm_col} date:{date_col} posted:{posted_col} subject:{subj_col}")

    start = _parse_date(start_date)
    end = _parse_date(end_date)

    seen = set()
    records = []
    for row in ws.iter_rows(min_row=2):
        subject = str(row[subj_col].value or "") if subj_col is not None else ""
        if not _is_cgmp_pharma(subject):
            continue

        issue_date  = _parse_date(str(row[date_col].value or ""))   if date_col is not None else None
        posted_date = _parse_date(str(row[posted_col].value or "")) if posted_col is not None else None
        ref_date = issue_date or posted_date

        if start and end and ref_date:
            if not (start <= ref_date <= end):
                continue

        # Extract firm name and hyperlink from Company Name cell
        firm_cell = row[firm_col] if firm_col is not None else None
        firm = str(firm_cell.value or "Unknown").strip() if firm_cell is not None else "Unknown"

        # Deduplicate by (firm, date)
        dedup_key = (firm, str(ref_date))
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        # Get the hyperlink embedded in the cell
        url = ""
        if firm_cell and firm_cell.hyperlink:
            url = firm_cell.hyperlink.target or ""
        if url and not url.startswith("http"):
            url = f"https://www.fda.gov{url}"

        logger.info(f"  Record: {firm} | {ref_date} | {subject} | URL: {url or 'none'}")

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
            "pdf_url": url if url.lower().endswith(".pdf") else None,
            "warning_letter_url": url if url and not url.lower().endswith(".pdf") else None,
        })

    logger.info(f"Parsed {len(records)} CGMP pharmaceutical records from Excel")
    return records


def _find_url_via_requests(firm_name: str) -> str | None:
    """
    Fallback: search FDA warning letters page via HTTP for a firm and return its URL.
    Uses the first significant word(s) of the firm name to search.
    """
    import requests
    from urllib.parse import urlencode

    # Use the first meaningful word of the firm name (skip short words)
    words = [w for w in firm_name.split() if len(w) > 3]
    query = words[0] if words else firm_name[:20]

    base = (
        "https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations"
        "/compliance-actions-and-activities/warning-letters"
    )
    try:
        url = f"{base}?{urlencode({'search_api_fulltext': query})}"
        resp = requests.get(url, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        })
        if not resp.ok:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        firm_lower = firm_name.lower()
        # Try to find a link whose text matches the firm name
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "/warning-letters/" in href and href.count("/") > 4:
                text = link.get_text(strip=True).lower()
                if any(w.lower() in text for w in firm_name.split()[:2] if len(w) > 3):
                    return href if href.startswith("http") else f"https://www.fda.gov{href}"
        # Return first warning letter link as last resort
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "/warning-letters/" in href and href.count("/") > 4:
                return href if href.startswith("http") else f"https://www.fda.gov{href}"
    except Exception as e:
        logger.warning(f"Requests URL lookup failed for {firm_name}: {e}")
    return None


def _collect_urls_from_table(page, max_urls: int = 500) -> dict[str, str]:
    """
    Paginate through DataTable pages and collect {company_name: url}.
    Stops after max_urls unique URLs are collected (prevents runaway pagination).
    """
    url_map = {}
    page_num = 1

    # Try to set rows-per-page to 100 to reduce page count
    for length_sel in ["select[name$='_length']", ".dt-length select", "#datatable_length"]:
        try:
            page.select_option(length_sel, value="100", timeout=2000)
            page.wait_for_timeout(1500)
            logger.info(f"Set rows-per-page to 100 via {length_sel}")
            break
        except Exception:
            continue

    while True:
        soup = BeautifulSoup(page.content(), "html.parser")
        table = soup.find("table")
        if not table:
            break

        rows = table.find_all("tr")[1:]
        page_found = 0
        for row in rows:
            for cell in row.find_all("td"):
                link = cell.find("a", href=True)
                if link and "/warning-letters/" in link["href"]:
                    firm = link.get_text(strip=True)
                    href = link["href"]
                    url = href if href.startswith("http") else f"https://www.fda.gov{href}"
                    url_map[firm] = url
                    page_found += 1
                    break

        logger.info(f"Table page {page_num}: {len(rows)} rows, {page_found} WL URLs, {len(url_map)} total")

        if len(url_map) >= max_urls:
            logger.info(f"Reached {max_urls} URL cap — stopping URL collection")
            break

        clicked = page.evaluate("""
            () => {
                var candidates = [
                    document.querySelector('.paginate_button.next:not(.disabled) a'),
                    document.querySelector('.paginate_button.next:not(.disabled)'),
                    document.querySelector('li.next:not(.disabled) a'),
                    document.querySelector('a[aria-label="Next"]:not([aria-disabled="true"])'),
                ];
                for (var el of candidates) {
                    if (el) { el.click(); return true; }
                }
                return false;
            }
        """)
        if not clicked:
            logger.info(f"No more pages after page {page_num}")
            break
        page.wait_for_timeout(2000)
        page_num += 1

    return url_map


def _scrape_table_pages(page, start_date: str = None, end_date: str = None) -> list[dict]:
    """Fallback: scrape visible table pages, filtered by date range."""
    from bs4 import BeautifulSoup
    records = []
    seen_urls = set()
    page_num = 1
    max_pages = 100  # safety cap

    start = _parse_date(start_date) if start_date else None
    end = _parse_date(end_date) if end_date else None

    # Try to set rows-per-page to 100 to reduce page count
    for length_sel in ["select[name$='_length']", ".dt-length select", "#datatable_length"]:
        try:
            page.select_option(length_sel, value="100", timeout=2000)
            page.wait_for_timeout(1500)
            logger.info(f"Set rows-per-page to 100 via {length_sel}")
            break
        except Exception:
            continue

    while page_num <= max_pages:
        soup = BeautifulSoup(page.content(), "html.parser")
        table = soup.find("table")
        if not table:
            break

        rows = table.find_all("tr")[1:]
        page_records = 0
        all_out_of_range = True  # track if entire page is outside date range

        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 4:
                continue

            subject = cells[4].get_text(strip=True) if len(cells) > 4 else ""
            ref_date = _parse_date(cells[1].get_text(strip=True))

            # Date range check — table is sorted newest-first, so once we go below
            # start_date we can stop entirely
            if start and ref_date and ref_date < start:
                logger.info(f"Page {page_num}: reached date {ref_date} < start {start}, stopping")
                return records
            if end and ref_date and ref_date > end:
                continue  # skip future rows but keep scanning
            if ref_date:
                all_out_of_range = False

            if not _is_cgmp_pharma(subject):
                continue

            link = row.find("a", href=True)
            href = link["href"] if link else ""
            full_url = href if href.startswith("http") else f"https://www.fda.gov{href}"

            # Dedup by URL to detect when we've cycled back to the beginning
            if full_url and full_url in seen_urls:
                logger.info(f"Page {page_num}: duplicate URL detected — stopping pagination")
                return records
            if full_url:
                seen_urls.add(full_url)

            records.append({
                "fda_inspection_id": None,
                "firm_name": cells[2].get_text(strip=True) if len(cells) > 2 else "Unknown",
                "city": None, "state": None, "zip_code": None, "country": "US",
                "inspection_end_date": ref_date,
                "product_type": subject,
                "center": "CDER",
                "pdf_url": None,
                "warning_letter_url": full_url,
            })
            page_records += 1

        logger.info(f"Page {page_num}: {len(rows)} rows, {page_records} CGMP matches, {len(records)} total")

        if all_out_of_range and start and end:
            logger.info(f"Page {page_num}: all rows out of date range — stopping")
            break

        clicked = page.evaluate("""
            () => {
                var candidates = [
                    document.querySelector('.paginate_button.next:not(.disabled) a'),
                    document.querySelector('.paginate_button.next:not(.disabled)'),
                    document.querySelector('li.next:not(.disabled) a'),
                    document.querySelector('a[aria-label="Next"]:not([aria-disabled="true"])'),
                ];
                for (var el of candidates) {
                    if (el) { el.click(); return true; }
                }
                return false;
            }
        """)
        if not clicked:
            logger.info(f"No more pages after page {page_num}")
            break
        page.wait_for_timeout(2000)
        page_num += 1

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
