"""
Publishes weekly GMP reports and individual inspection analyses to Notion.

Setup:
1. Create a Notion integration at https://www.notion.so/my-integrations
2. Copy the Internal Integration Token → set NOTION_TOKEN in .env
3. Create two Notion databases (or one parent page) and share them with your integration:
   - A "Weekly Reports" database  → set NOTION_REPORTS_DB_ID in .env
   - An "Inspections" database    → set NOTION_INSPECTIONS_DB_ID in .env
4. Copy each database's ID from its URL:
   notion.so/<workspace>/<DATABASE_ID>?v=...
"""
import logging
import os
from datetime import date, datetime

from notion_client import Client

logger = logging.getLogger(__name__)

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_REPORTS_DB_ID = os.getenv("NOTION_REPORTS_DB_ID")
NOTION_INSPECTIONS_DB_ID = os.getenv("NOTION_INSPECTIONS_DB_ID")


def _client() -> Client:
    if not NOTION_TOKEN:
        raise ValueError("NOTION_TOKEN not set in environment.")
    return Client(auth=NOTION_TOKEN)


def _risk_color(risk: str) -> str:
    return {"Critical": "red", "Major": "orange", "Minor": "yellow"}.get(risk or "", "default")


def _md_to_blocks(markdown: str) -> list[dict]:
    """
    Convert a Markdown string into Notion block objects (simplified).
    Handles headings, bullets, bold, and paragraphs.
    """
    blocks = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("### "):
            blocks.append(_heading(stripped[4:], level=3))
        elif stripped.startswith("## "):
            blocks.append(_heading(stripped[3:], level=2))
        elif stripped.startswith("# "):
            blocks.append(_heading(stripped[2:], level=1))
        elif stripped.startswith("- ") or stripped.startswith("* "):
            blocks.append(_bullet(stripped[2:]))
        elif stripped.startswith("|"):
            # Skip table rows — Notion doesn't support Markdown tables natively
            continue
        else:
            blocks.append(_paragraph(stripped))
    return blocks


def _heading(text: str, level: int) -> dict:
    key = f"heading_{level}"
    return {
        "object": "block",
        "type": key,
        key: {"rich_text": [{"type": "text", "text": {"content": text[:2000]}}]},
    }


def _paragraph(text: str) -> dict:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": [{"type": "text", "text": {"content": text[:2000]}}]},
    }


def _bullet(text: str) -> dict:
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": text[:2000]}}]},
    }


def publish_weekly_report(
    week_start: date,
    week_end: date,
    markdown: str,
    total_inspections: int,
    total_observations: int,
    risk_summary: dict,  # {"Critical": n, "Major": n, "Minor": n}
) -> str:
    """
    Create (or update) a page in the Notion Weekly Reports database.
    Returns the Notion page URL.
    """
    notion = _client()
    if not NOTION_REPORTS_DB_ID:
        raise ValueError("NOTION_REPORTS_DB_ID not set in environment.")

    title = f"FDA 483 GMP Report — {week_start} to {week_end}"

    # Check if a page already exists for this week
    existing = notion.databases.query(
        database_id=NOTION_REPORTS_DB_ID,
        filter={
            "property": "Week Start",
            "date": {"equals": str(week_start)},
        },
    )

    blocks = _md_to_blocks(markdown)
    # Notion API limits children to 100 blocks per request
    first_batch = blocks[:100]

    properties = {
        "Name": {"title": [{"text": {"content": title}}]},
        "Week Start": {"date": {"start": str(week_start)}},
        "Week End": {"date": {"start": str(week_end)}},
        "Total Inspections": {"number": total_inspections},
        "Total Observations": {"number": total_observations},
        "Critical": {"number": risk_summary.get("Critical", 0)},
        "Major": {"number": risk_summary.get("Major", 0)},
        "Minor": {"number": risk_summary.get("Minor", 0)},
        "Generated At": {"date": {"start": datetime.utcnow().isoformat()}},
    }

    if existing["results"]:
        page_id = existing["results"][0]["id"]
        notion.pages.update(page_id=page_id, properties=properties)
        # Clear existing blocks and re-add
        existing_blocks = notion.blocks.children.list(block_id=page_id)
        for block in existing_blocks.get("results", []):
            notion.blocks.delete(block_id=block["id"])
        if first_batch:
            notion.blocks.children.append(block_id=page_id, children=first_batch)
        page_url = existing["results"][0]["url"]
    else:
        response = notion.pages.create(
            parent={"database_id": NOTION_REPORTS_DB_ID},
            properties=properties,
            children=first_batch,
        )
        page_id = response["id"]
        page_url = response["url"]

    # Append remaining blocks in batches of 100
    for i in range(100, len(blocks), 100):
        notion.blocks.children.append(
            block_id=page_id,
            children=blocks[i:i + 100],
        )

    logger.info(f"Published weekly report to Notion: {page_url}")
    return page_url


def publish_inspection(
    firm_name: str,
    city: str,
    state: str,
    country: str,
    inspection_date: date,
    num_observations: int,
    risk_level: str,
    executive_summary: str,
    key_themes: list[str],
    top_gmp_gaps: list[dict],
    recommendations: str,
) -> str:
    """
    Create (or update) a page in the Notion Inspections database for one inspection.
    Returns the Notion page URL.
    """
    notion = _client()
    if not NOTION_INSPECTIONS_DB_ID:
        raise ValueError("NOTION_INSPECTIONS_DB_ID not set in environment.")

    title = f"{firm_name} — {inspection_date}"

    # Check for existing page
    existing = notion.databases.query(
        database_id=NOTION_INSPECTIONS_DB_ID,
        filter={"property": "Name", "title": {"equals": title}},
    )

    properties = {
        "Name": {"title": [{"text": {"content": title}}]},
        "Firm": {"rich_text": [{"text": {"content": firm_name or ""}}]},
        "City": {"rich_text": [{"text": {"content": city or ""}}]},
        "State": {"rich_text": [{"text": {"content": state or ""}}]},
        "Country": {"rich_text": [{"text": {"content": country or ""}}]},
        "Inspection Date": {"date": {"start": str(inspection_date)}},
        "Observations": {"number": num_observations},
        "Risk Level": {
            "select": {"name": risk_level or "Unknown", "color": _risk_color(risk_level)}
        },
        "Key Themes": {
            "multi_select": [{"name": t[:100]} for t in (key_themes or [])[:10]]
        },
    }

    # Build page content blocks
    blocks = [
        _heading("Executive Summary", level=2),
        _paragraph(executive_summary or ""),
        _heading("Top GMP Gaps", level=2),
    ]
    for gap in (top_gmp_gaps or []):
        blocks.append(_bullet(
            f"[{gap.get('framework', '')}] {gap.get('reference', '')} — {gap.get('gap_description', '')}"
        ))
    blocks.append(_heading("Recommendations", level=2))
    blocks.append(_paragraph(recommendations or ""))

    if existing["results"]:
        page_id = existing["results"][0]["id"]
        notion.pages.update(page_id=page_id, properties=properties)
        for block in notion.blocks.children.list(block_id=page_id).get("results", []):
            notion.blocks.delete(block_id=block["id"])
        notion.blocks.children.append(block_id=page_id, children=blocks)
        page_url = existing["results"][0]["url"]
    else:
        response = notion.pages.create(
            parent={"database_id": NOTION_INSPECTIONS_DB_ID},
            properties=properties,
            children=blocks,
        )
        page_url = response["url"]

    logger.info(f"Published inspection to Notion: {page_url}")
    return page_url
