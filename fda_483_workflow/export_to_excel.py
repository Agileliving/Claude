"""
Export all analyzed inspections from the local database to Excel.
Run from the fda_483_workflow directory:
    python3 export_to_excel.py
"""
import sys
from datetime import datetime
from pathlib import Path

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
except ImportError:
    print("Installing openpyxl...")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "openpyxl"], check=True)
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

from db import init_db, get_session
from db.models import Inspection

# ── Colours ──────────────────────────────────────────────────────────────────
HEADER_FILL   = PatternFill("solid", fgColor="1F4E79")
CRITICAL_FILL = PatternFill("solid", fgColor="FF0000")
MAJOR_FILL    = PatternFill("solid", fgColor="FF6600")
MINOR_FILL    = PatternFill("solid", fgColor="FFD700")
ALT_FILL      = PatternFill("solid", fgColor="EBF3FB")
HEADER_FONT   = Font(bold=True, color="FFFFFF", size=11)
BOLD          = Font(bold=True)

THIN = Side(style="thin", color="CCCCCC")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

RISK_FILL = {"Critical": CRITICAL_FILL, "Major": MAJOR_FILL, "Minor": MINOR_FILL}


def _cell(ws, row, col, value, font=None, fill=None, wrap=False, bold=False):
    c = ws.cell(row=row, column=col, value=value)
    if font:
        c.font = font
    elif bold:
        c.font = BOLD
    if fill:
        c.fill = fill
    c.alignment = Alignment(wrap_text=wrap, vertical="top")
    c.border = BORDER
    return c


def build_summary_sheet(wb, inspections):
    ws = wb.active
    ws.title = "All Inspections"

    headers = [
        "Month", "Firm Name", "Country", "City/State",
        "Inspection Date", "# Observations", "Risk Level",
        "Executive Summary", "Key Themes", "Top GMP Gaps", "Recommendations",
    ]

    # Header row
    for col, h in enumerate(headers, 1):
        _cell(ws, 1, col, h, font=HEADER_FONT, fill=HEADER_FILL)

    ws.row_dimensions[1].height = 22

    for row_idx, insp in enumerate(inspections, 2):
        analysis = insp.analysis
        alt = ALT_FILL if row_idx % 2 == 0 else None
        risk = analysis.risk_level if analysis else ""
        risk_fill = RISK_FILL.get(risk, alt)

        date = insp.inspection_end_date
        month = date.strftime("%Y-%m") if date else ""
        location = ", ".join(filter(None, [insp.city, insp.state, insp.country]))

        themes = "; ".join(analysis.key_themes or []) if analysis else ""
        gaps = ""
        if analysis and analysis.top_gmp_gaps:
            gaps = "\n".join(
                f"[{g.get('framework','')}] {g.get('reference','')} — {g.get('gap_description','')}"
                for g in analysis.top_gmp_gaps
            )

        values = [
            month,
            insp.firm_name or "",
            insp.country or "",
            location,
            str(date) if date else "",
            insp.num_observations or 0,
            risk,
            (analysis.executive_summary or "") if analysis else "",
            themes,
            gaps,
            (analysis.recommendations or "") if analysis else "",
        ]

        for col, val in enumerate(values, 1):
            fill = risk_fill if col == 7 else alt
            _cell(ws, row_idx, col, val, fill=fill, wrap=(col >= 8))

        ws.row_dimensions[row_idx].height = max(
            60, 15 * max(1, len((analysis.executive_summary or "")) // 80)
        ) if analysis else 20

    # Column widths
    widths = [10, 32, 12, 18, 14, 8, 10, 55, 35, 45, 45]
    for col, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(col)].width = w

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}1"


def build_monthly_sheets(wb, inspections):
    from collections import defaultdict
    by_month = defaultdict(list)
    for insp in inspections:
        key = insp.inspection_end_date.strftime("%Y-%m") if insp.inspection_end_date else "Unknown"
        by_month[key].append(insp)

    for month in sorted(by_month):
        ws = wb.create_sheet(title=month)
        month_inspections = by_month[month]

        # Month summary header
        ws.merge_cells("A1:G1")
        c = ws.cell(row=1, column=1, value=f"FDA CGMP Warning Letters — {month}  ({len(month_inspections)} inspections)")
        c.font = Font(bold=True, size=13, color="1F4E79")
        c.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[1].height = 28

        # Stats row
        from collections import Counter
        risks = Counter(
            (insp.analysis.risk_level or "Unknown") for insp in month_inspections if insp.analysis
        )
        ws.cell(row=2, column=1, value=f"Critical: {risks.get('Critical',0)}  |  Major: {risks.get('Major',0)}  |  Minor: {risks.get('Minor',0)}")
        ws.cell(row=2, column=1).font = Font(bold=True, color="444444")
        ws.merge_cells("A2:G2")
        ws.row_dimensions[2].height = 18

        headers = ["Firm", "Country", "Date", "Observations", "Risk", "Key Themes", "Recommendations"]
        for col, h in enumerate(headers, 1):
            _cell(ws, 3, col, h, font=HEADER_FONT, fill=HEADER_FILL)
        ws.row_dimensions[3].height = 20

        for i, insp in enumerate(month_inspections, 4):
            analysis = insp.analysis
            risk = analysis.risk_level if analysis else ""
            alt = ALT_FILL if i % 2 == 0 else None

            themes = "; ".join(analysis.key_themes or []) if analysis else ""
            recs = (analysis.recommendations or "") if analysis else ""

            row_vals = [
                insp.firm_name or "",
                insp.country or "",
                str(insp.inspection_end_date) if insp.inspection_end_date else "",
                insp.num_observations or 0,
                risk,
                themes,
                recs,
            ]
            for col, val in enumerate(row_vals, 1):
                fill = RISK_FILL.get(risk, alt) if col == 5 else alt
                _cell(ws, i, col, val, fill=fill, wrap=(col >= 6))
            ws.row_dimensions[i].height = 45

        widths = [32, 12, 12, 10, 10, 40, 50]
        for col, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(col)].width = w

        ws.freeze_panes = "A4"


def main():
    init_db()
    with get_session() as session:
        inspections = (
            session.query(Inspection)
            .filter(Inspection.analysis != None)
            .order_by(Inspection.inspection_end_date)
            .all()
        )

        # Eagerly load relationships while session is open
        for insp in inspections:
            _ = insp.analysis
            _ = insp.observations

    print(f"Found {len(inspections)} analyzed inspections")

    if not inspections:
        print("No data yet — run the backfill first.")
        return

    wb = openpyxl.Workbook()
    build_summary_sheet(wb, inspections)
    build_monthly_sheets(wb, inspections)

    out = Path(__file__).parent / "data" / "reports" / f"FDA_CGMP_Report_{datetime.now().strftime('%Y%m%d')}.xlsx"
    wb.save(out)
    print(f"\nExcel report saved: {out}")
    print("Open it in Finder with:  open \"" + str(out) + "\"")


if __name__ == "__main__":
    main()
