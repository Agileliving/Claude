"""
Weekly scheduler: pulls new FDA 483s, analyzes them, and generates a report.
Can also run a historical backfill for 2025–2026.
"""
import logging
from datetime import date, timedelta

from config import BACKFILL_START_DATE, WEEKLY_SCHEDULE_DAY, WEEKLY_SCHEDULE_TIME
from db import init_db, get_session, Inspection, Observation, GMPMapping, InspectionAnalysis
from scraper import scrape_inspections, batch_download
from extractor import extract_form_483
from analyzer import analyze_inspection
from reporter import generate_weekly_report

logger = logging.getLogger(__name__)


def _date_to_fda_str(d: date) -> str:
    return d.strftime("%m/%d/%Y")


def _persist_inspection(session, record: dict, analysis_result: dict, extraction) -> None:
    """Upsert inspection + observations + mappings + analysis into the DB."""
    existing = session.query(Inspection).filter_by(
        fda_inspection_id=record["fda_inspection_id"]
    ).first()

    if existing:
        insp = existing
    else:
        insp = Inspection(fda_inspection_id=record["fda_inspection_id"])
        session.add(insp)

    insp.firm_name = record.get("firm_name")
    insp.city = record.get("city")
    insp.state = record.get("state")
    insp.country = record.get("country")
    insp.zip_code = record.get("zip_code")
    insp.inspection_end_date = record.get("inspection_end_date")
    insp.product_type = record.get("product_type")
    insp.center = record.get("center")
    insp.pdf_url = record.get("pdf_url")
    insp.pdf_local_path = record.get("pdf_local_path")
    insp.pdf_downloaded = record.get("pdf_downloaded", False)
    insp.raw_text = extraction.raw_text
    insp.num_observations = extraction.num_observations
    session.flush()

    # Clear and re-insert observations
    for obs_data in analysis_result.get("observations", []):
        obs = Observation(
            inspection_id=insp.id,
            observation_number=obs_data.get("observation_number"),
            observation_text=next(
                (o.text for o in extraction.observations if o.number == obs_data.get("observation_number")),
                ""
            ),
            gmp_category=obs_data.get("gmp_category"),
        )
        session.add(obs)
        session.flush()

        for mapping in obs_data.get("gmp_mappings", []):
            session.add(GMPMapping(
                observation_id=obs.id,
                framework=mapping.get("framework"),
                reference_code=mapping.get("reference_code"),
                reference_title=mapping.get("reference_title"),
                relevance_explanation=mapping.get("relevance_explanation"),
            ))

    # Upsert analysis
    summary = analysis_result.get("summary", {})
    if insp.analysis:
        ai = insp.analysis
    else:
        ai = InspectionAnalysis(inspection_id=insp.id)
        session.add(ai)

    ai.executive_summary = summary.get("executive_summary")
    ai.key_themes = summary.get("key_themes", [])
    ai.risk_level = summary.get("overall_risk_level")
    ai.top_gmp_gaps = summary.get("top_gmp_gaps", [])
    ai.recommendations = summary.get("recommendations")
    ai.model_used = analysis_result.get("model_used")


def process_date_range(start_date: date, end_date: date) -> None:
    """
    Scrape, download, extract, analyze, and store all pharmaceutical
    Form 483s issued between start_date and end_date.
    """
    logger.info(f"Processing FDA 483s from {start_date} to {end_date}")

    records = list(scrape_inspections(
        start_date=_date_to_fda_str(start_date),
        end_date=_date_to_fda_str(end_date),
    ))
    logger.info(f"Found {len(records)} pharmaceutical inspections")

    if not records:
        logger.info("No records found for this period.")
        return

    # Download PDFs
    records = batch_download(records)

    for record in records:
        fda_id = record.get("fda_inspection_id", "unknown")

        # Skip if already processed
        with get_session() as session:
            existing = session.query(Inspection).filter_by(fda_inspection_id=fda_id).first()
            if existing and existing.analysis:
                logger.info(f"Already processed: {fda_id} — skipping")
                continue

        # Extract text from PDF
        if not record.get("pdf_local_path"):
            logger.warning(f"No PDF for {fda_id} — skipping extraction")
            continue

        extraction = extract_form_483(record["pdf_local_path"])
        if extraction.extraction_error:
            logger.error(f"Extraction failed for {fda_id}: {extraction.extraction_error}")
            continue

        if not extraction.observations:
            logger.warning(f"No observations found in {fda_id}")
            continue

        # Analyze with Claude
        logger.info(f"Analyzing {len(extraction.observations)} observations for {fda_id}")
        obs_list = [{"number": o.number, "text": o.text} for o in extraction.observations]
        analysis_result = analyze_inspection(
            observations=obs_list,
            firm_name=record.get("firm_name", "Unknown"),
            inspection_date=str(record.get("inspection_end_date", "")),
        )

        # Persist to DB
        with get_session() as session:
            _persist_inspection(session, record, analysis_result, extraction)

        logger.info(f"Stored analysis for {fda_id}")

    logger.info(f"Processing complete for {start_date} to {end_date}")


def run_weekly_pull() -> None:
    """Pull and analyze the past 7 days of FDA 483s, then generate a report."""
    today = date.today()
    week_end = today - timedelta(days=1)
    week_start = week_end - timedelta(days=6)

    process_date_range(week_start, week_end)
    report_path = generate_weekly_report(week_start, week_end)
    logger.info(f"Weekly report generated: {report_path}")


def run_backfill(start_date_str: str = None, end_date_str: str = None) -> None:
    """
    Backfill all pharmaceutical 483s for a date range.
    Processes in monthly chunks to avoid rate limits.
    Defaults to 2025-01-01 through yesterday.
    """
    from datetime import datetime

    start = datetime.strptime(start_date_str or BACKFILL_START_DATE, "%m/%d/%Y").date()
    end = datetime.strptime(end_date_str, "%m/%d/%Y").date() if end_date_str else date.today() - timedelta(days=1)

    logger.info(f"Starting backfill from {start} to {end}")

    current = start
    while current <= end:
        # Process month by month
        if current.month == 12:
            chunk_end = date(current.year + 1, 1, 1) - timedelta(days=1)
        else:
            chunk_end = date(current.year, current.month + 1, 1) - timedelta(days=1)

        chunk_end = min(chunk_end, end)
        process_date_range(current, chunk_end)

        # Generate monthly report
        generate_weekly_report(current, chunk_end)

        # Move to next month
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)

    logger.info("Backfill complete.")
