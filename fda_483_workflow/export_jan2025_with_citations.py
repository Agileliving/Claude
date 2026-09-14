"""
Export January 2025 inspections to Excel with original FDA citation text.
Run from the fda_483_workflow directory:
    python3 export_jan2025_with_citations.py
"""
import sys
from datetime import date, datetime
from pathlib import Path

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "openpyxl"], check=True)
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

from db import init_db, get_session
from db.models import Inspection, Observation

# ── Styles ────────────────────────────────────────────────────────────────────
HEADER_FILL   = PatternFill("solid", fgColor="1F4E79")
CRITICAL_FILL = PatternFill("solid", fgColor="FF0000")
MAJOR_FILL    = PatternFill("solid", fgColor="FF6600")
MINOR_FILL    = PatternFill("solid", fgColor="FFD700")
ALT_FILL      = PatternFill("solid", fgColor="EBF3FB")
CITE_FILL     = PatternFill("solid", fgColor="F2F2F2")
HEADER_FONT   = Font(bold=True, color="FFFFFF", size=11)
BOLD          = Font(bold=True)
THIN          = Side(style="thin", color="CCCCCC")
BORDER        = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
RISK_FILL     = {"Critical": CRITICAL_FILL, "Major": MAJOR_FILL, "Minor": MINOR_FILL}


def _cell(ws, row, col, value, font=None, fill=None, wrap=False):
    c = ws.cell(row=row, column=col, value=value)
    if font:
        c.font = font
    if fill:
        c.fill = fill
    c.alignment = Alignment(wrap_text=wrap, vertical="top")
    c.border = BORDER
    return c


def main():
    init_db()

    jan_start = date(2025, 1, 1)
    jan_end   = date(2025, 1, 31)

    with get_session() as session:
        inspections = (
            session.query(Inspection)
            .filter(
                Inspection.inspection_end_date >= jan_start,
                Inspection.inspection_end_date <= jan_end,
            )
            .order_by(Inspection.inspection_end_date)
            .all()
        )

        rows = []
        for insp in inspections:
            a = insp.analysis

            # Collect all observations with their original text
            obs_list = sorted(insp.observations, key=lambda o: o.observation_number or 0)
            citations = []
            for obs in obs_list:
                if obs.observation_text and obs.observation_text.strip():
                    citations.append(
                        f"[Finding {obs.observation_number}]\n{obs.observation_text.strip()}"
                    )

            rows.append({
                "firm_name":         insp.firm_name or "",
                "country":           insp.country or "",
                "city":              insp.city or "",
                "state":             insp.state or "",
                "inspection_date":   insp.inspection_end_date,
                "num_observations":  insp.num_observations or 0,
                "risk_level":        (a.risk_level or "") if a else "",
                "executive_summary": (a.executive_summary or "") if a else "",
                "key_themes":        (a.key_themes or []) if a else [],
                "recommendations":   (a.recommendations or "") if a else "",
                "fda_citations":     "\n\n".join(citations) if citations else "(no citation text stored)",
                "warning_letter_url": insp.pdf_url or "",
            })

    print(f"Found {len(rows)} inspections for January 2025")
    if not rows:
        print("No data — check that the backfill ran for January 2025.")
        return

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Jan 2025 — FDA Citations"

    # ── Title row ─────────────────────────────────────────────────────────────
    ws.merge_cells("A1:L1")
    title_cell = ws.cell(row=1, column=1,
        value=f"FDA CGMP Warning Letters — January 2025  ({len(rows)} inspections)")
    title_cell.font = Font(bold=True, size=14, color="1F4E79")
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 30

    # ── Column headers ─────────────────────────────────────────────────────────
    headers = [
        "Firm Name", "Country", "Location", "Inspection Date",
        "# Findings", "Risk Level",
        "AI Executive Summary",        # Claude-generated
        "Key Themes (AI)",             # Claude-generated
        "Recommendations (AI)",        # Claude-generated
        "FDA CITATIONS\n(Original Text from Warning Letter)",  # Raw FDA text
        "Warning Letter URL",
    ]
    for col, h in enumerate(headers, 1):
        _cell(ws, 2, col, h, font=HEADER_FONT, fill=HEADER_FILL, wrap=True)
    ws.row_dimensions[2].height = 36

    # ── Data rows ──────────────────────────────────────────────────────────────
    for row_idx, r in enumerate(rows, 3):
        alt  = ALT_FILL if row_idx % 2 == 0 else None
        risk = r["risk_level"]
        risk_fill = RISK_FILL.get(risk, alt)

        location = ", ".join(filter(None, [r["city"], r["state"], r["country"]]))
        themes   = "; ".join(r["key_themes"])

        values = [
            r["firm_name"],
            r["country"],
            location,
            str(r["inspection_date"]) if r["inspection_date"] else "",
            r["num_observations"],
            risk,
            r["executive_summary"],
            themes,
            r["recommendations"],
            r["fda_citations"],          # ← original FDA text
            r["warning_letter_url"],
        ]

        for col, val in enumerate(values, 1):
            if col == 6:
                fill = risk_fill
            elif col == 10:
                fill = CITE_FILL        # light grey for citation column
            else:
                fill = alt
            wrap = col >= 7
            c = _cell(ws, row_idx, col, val, fill=fill, wrap=wrap)
            # Make citation column text slightly smaller for readability
            if col == 10:
                c.font = Font(size=9)

        # Row height based on citation length
        citation_len = len(r["fda_citations"])
        ws.row_dimensions[row_idx].height = min(400, max(60, citation_len // 8))

    # ── Column widths ──────────────────────────────────────────────────────────
    widths = [28, 10, 18, 13, 8, 10, 45, 30, 40, 70, 35]
    for col, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(col)].width = w

    ws.freeze_panes = "A3"
    ws.auto_filter.ref = f"A2:{get_column_letter(len(headers))}2"

    # ── Legend sheet ───────────────────────────────────────────────────────────
    leg = wb.create_sheet("Legend")
    leg_data = [
        ("Column", "Source", "Description"),
        ("Firm Name – Risk Level", "FDA Website", "Scraped directly from FDA Warning Letters page"),
        ("AI Executive Summary", "Claude AI (Haiku)", "AI-generated summary of all findings"),
        ("Key Themes (AI)", "Claude AI (Haiku)", "AI-identified recurring GMP deficiency themes"),
        ("Recommendations (AI)", "Claude AI (Haiku)", "AI-suggested corrective actions"),
        ("FDA CITATIONS", "FDA Warning Letter", "Original verbatim text of each finding from the letter"),
        ("", "", ""),
        ("Risk Level", "Color", ""),
        ("Critical", "Red", "Immediate risk to product quality or patient safety"),
        ("Major", "Orange", "Significant GMP deficiency requiring prompt action"),
        ("Minor", "Yellow", "Lower-risk finding, still requires correction"),
    ]
    for r_idx, row_data in enumerate(leg_data, 1):
        for c_idx, val in enumerate(row_data, 1):
            c = leg.cell(row=r_idx, column=c_idx, value=val)
            if r_idx == 1 or (r_idx == 8):
                c.font = HEADER_FONT
                c.fill = HEADER_FILL
            if r_idx == 9:
                c.fill = CRITICAL_FILL
                c.font = Font(bold=True, color="FFFFFF")
            if r_idx == 10:
                c.fill = MAJOR_FILL
                c.font = Font(bold=True)
            if r_idx == 11:
                c.fill = MINOR_FILL
                c.font = Font(bold=True)
    leg.column_dimensions["A"].width = 25
    leg.column_dimensions["B"].width = 20
    leg.column_dimensions["C"].width = 55

    # ── Save ───────────────────────────────────────────────────────────────────
    out = Path(__file__).parent / "data" / "reports" / "FDA_CGMP_Jan2025_with_citations.xlsx"
    wb.save(out)
    print(f"\nSaved: {out}")

    import subprocess
    subprocess.run(["open", str(out)])
    print("Opening file...")


if __name__ == "__main__":
    main()
