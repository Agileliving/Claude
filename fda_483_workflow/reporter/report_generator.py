"""
Generates weekly Markdown reports from analyzed Form 483 data.
"""
import logging
from collections import Counter
from datetime import date, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from config import REPORTS_DIR
from db import get_session, WeeklyReport, Inspection, Observation, GMPMapping, InspectionAnalysis

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_jinja_env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), trim_blocks=True)


def _count_risk(inspections_data: list[dict], level: str) -> int:
    return sum(1 for i in inspections_data if (i.get("risk_level") or "").lower() == level.lower())


def _top_refs(framework: str, gmp_mappings: list[dict], n: int = 5) -> list[dict]:
    fw_refs = [m for m in gmp_mappings if m["framework"] == framework]
    counts = Counter(m["reference_code"] for m in fw_refs)
    top = counts.most_common(n)
    ref_titles = {m["reference_code"]: m["reference_title"] for m in fw_refs}
    return [{"code": code, "count": cnt, "title": ref_titles.get(code, "")} for code, cnt in top]


def generate_weekly_report(week_start: date, week_end: date) -> str:
    """
    Pull all analyzed inspections for the week from the DB,
    render the Markdown report, save it, and return the file path.
    """
    with get_session() as session:
        db_inspections = (
            session.query(Inspection)
            .filter(
                Inspection.inspection_end_date >= week_start,
                Inspection.inspection_end_date <= week_end,
            )
            .all()
        )

        inspections_data = []
        all_mappings = []

        for insp in db_inspections:
            analysis = insp.analysis
            if not analysis:
                continue

            top_gmp_gaps = analysis.top_gmp_gaps or []
            inspections_data.append({
                "firm_name": insp.firm_name,
                "city": insp.city,
                "state": insp.state,
                "country": insp.country,
                "inspection_date": insp.inspection_end_date,
                "num_observations": insp.num_observations or 0,
                "risk_level": analysis.risk_level,
                "executive_summary": analysis.executive_summary or "",
                "key_themes": analysis.key_themes or [],
                "top_gmp_gaps": top_gmp_gaps,
                "recommendations": analysis.recommendations or "",
            })

            # Collect all GMP mappings for stats
            for obs in insp.observations:
                for mapping in obs.gmp_mappings:
                    all_mappings.append({
                        "framework": mapping.framework,
                        "reference_code": mapping.reference_code,
                        "reference_title": mapping.reference_title,
                    })

        # Aggregate theme counts
        theme_counter: Counter = Counter()
        theme_inspections: Counter = Counter()
        for insp_d in inspections_data:
            for theme in insp_d["key_themes"]:
                theme_counter[theme] += 1
                theme_inspections[theme] += 1

        top_themes = [
            {"name": theme, "count": cnt, "inspections": theme_inspections[theme]}
            for theme, cnt in theme_counter.most_common(10)
        ]

        framework_counts = Counter(m["framework"] for m in all_mappings)
        total_observations = sum(i["num_observations"] for i in inspections_data)

        template = _jinja_env.get_template("weekly_report.md.j2")
        rendered = template.render(
            report_week_start=week_start.strftime("%Y-%m-%d"),
            report_week_end=week_end.strftime("%Y-%m-%d"),
            generated_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
            total_inspections=len(inspections_data),
            total_observations=total_observations,
            critical_count=_count_risk(inspections_data, "Critical"),
            major_count=_count_risk(inspections_data, "Major"),
            minor_count=_count_risk(inspections_data, "Minor"),
            top_themes=top_themes,
            framework_counts=dict(framework_counts),
            inspections=inspections_data,
            fda_top_refs=_top_refs("FDA_GMP", all_mappings),
            eu_top_refs=_top_refs("EU_GMP", all_mappings),
            ich_top_refs=_top_refs("ICH", all_mappings),
            pics_top_refs=_top_refs("PICS", all_mappings),
            who_top_refs=_top_refs("WHO", all_mappings),
        )

        # Save report to file
        report_filename = f"report_{week_start}_{week_end}.md"
        report_path = REPORTS_DIR / report_filename
        report_path.write_text(rendered, encoding="utf-8")
        logger.info(f"Report saved: {report_path}")

        # Persist report metadata to DB
        existing = session.query(WeeklyReport).filter(
            WeeklyReport.report_week_start == week_start,
            WeeklyReport.report_week_end == week_end,
        ).first()

        if existing:
            existing.report_markdown = rendered
            existing.report_path = str(report_path)
            existing.total_inspections = len(inspections_data)
            existing.total_observations = total_observations
            existing.generated_at = datetime.utcnow()
        else:
            session.add(WeeklyReport(
                report_week_start=week_start,
                report_week_end=week_end,
                total_inspections=len(inspections_data),
                total_observations=total_observations,
                report_markdown=rendered,
                report_path=str(report_path),
            ))

    # Publish to Notion if configured
    _publish_to_notion(
        week_start=week_start,
        week_end=week_end,
        markdown=rendered,
        inspections_data=inspections_data,
        total_observations=total_observations,
    )

    return str(report_path)


def _publish_to_notion(
    week_start: date,
    week_end: date,
    markdown: str,
    inspections_data: list[dict],
    total_observations: int,
) -> None:
    """Publish the weekly report and each inspection to Notion (if credentials set)."""
    import os
    if not os.getenv("NOTION_TOKEN"):
        return

    from .notion_publisher import publish_weekly_report, publish_inspection

    risk_summary = {
        "Critical": _count_risk(inspections_data, "Critical"),
        "Major": _count_risk(inspections_data, "Major"),
        "Minor": _count_risk(inspections_data, "Minor"),
    }

    try:
        url = publish_weekly_report(
            week_start=week_start,
            week_end=week_end,
            markdown=markdown,
            total_inspections=len(inspections_data),
            total_observations=total_observations,
            risk_summary=risk_summary,
        )
        logger.info(f"Weekly report on Notion: {url}")
    except Exception as e:
        logger.warning(f"Notion weekly report publish failed: {e}")

    for insp in inspections_data:
        try:
            publish_inspection(
                firm_name=insp["firm_name"],
                city=insp.get("city", ""),
                state=insp.get("state", ""),
                country=insp.get("country", ""),
                inspection_date=insp["inspection_date"],
                num_observations=insp["num_observations"],
                risk_level=insp["risk_level"],
                executive_summary=insp["executive_summary"],
                key_themes=insp["key_themes"],
                top_gmp_gaps=insp["top_gmp_gaps"],
                recommendations=insp["recommendations"],
            )
        except Exception as e:
            logger.warning(f"Notion inspection publish failed for {insp['firm_name']}: {e}")
