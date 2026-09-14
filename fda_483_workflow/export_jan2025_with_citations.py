"""
Export January 2025 inspections to Excel with original FDA citation text
and linked FDA cGMP references (21 CFR Part 210/211).
Run from the fda_483_workflow directory:
    python3 export_jan2025_with_citations.py
"""
import sys
from datetime import date
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
from db.models import Inspection

# ── Styles ────────────────────────────────────────────────────────────────────
HEADER_FILL   = PatternFill("solid", fgColor="1F4E79")
CRITICAL_FILL = PatternFill("solid", fgColor="FF0000")
MAJOR_FILL    = PatternFill("solid", fgColor="FF6600")
MINOR_FILL    = PatternFill("solid", fgColor="FFD700")
ALT_FILL      = PatternFill("solid", fgColor="EBF3FB")
CITE_FILL     = PatternFill("solid", fgColor="FFFBF0")
REF_FILL      = PatternFill("solid", fgColor="EBF5EB")
HEADER_FONT   = Font(bold=True, color="FFFFFF", size=11)
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


def _build_fda_refs(obs_list) -> str:
    """
    Collect FDA GMP reference codes from gmp_mappings for each observation,
    filtered to FDA_GMP framework only, formatted as:
      [Finding 1] 21 CFR 211.68 — Automatic, mechanical, and electronic equipment
      [Finding 2] 21 CFR 211.192 — Production record review
    """
    lines = []
    for obs in obs_list:
        fda_refs = [
            m for m in obs.gmp_mappings
            if (m.framework or "").upper() in ("FDA_GMP", "FDA GMP")
        ]
        if fda_refs:
            for m in fda_refs:
                code  = m.reference_code or ""
                title = m.reference_title or ""
                ref   = f"{code} — {title}" if title else code
                lines.append(f"[Finding {obs.observation_number}]  {ref}")
    return "\n".join(lines) if lines else "(no FDA cGMP references mapped)"


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
            if not a:
                continue

            obs_list = sorted(insp.observations, key=lambda o: o.observation_number or 0)

            # Original FDA citation text per finding
            citations = []
            for obs in obs_list:
                if obs.observation_text and obs.observation_text.strip():
                    citations.append(
                        f"[Finding {obs.observation_number}]\n{obs.observation_text.strip()}"
                    )

            # FDA cGMP references from the AI mapping
            fda_refs = _build_fda_refs(obs_list)

            rows.append({
                "firm_name":        insp.firm_name or "",
                "country":          insp.country or "",
                "location":         ", ".join(filter(None, [insp.city, insp.state])),
                "inspection_date":  insp.inspection_end_date,
                "num_findings":     insp.num_observations or 0,
                "risk_level":       a.risk_level or "",
                "fda_citations":    "\n\n".join(citations) or "(no citation text stored)",
                "fda_cgmp_refs":    fda_refs,
                "warning_letter_url": insp.pdf_url or "",
            })

    print(f"Found {len(rows)} analyzed inspections for January 2025")
    if not rows:
        print("No data — check that the backfill ran for January 2025.")
        return

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Jan 2025 FDA Citations"

    # ── Title ─────────────────────────────────────────────────────────────────
    ws.merge_cells("A1:I1")
    t = ws.cell(row=1, column=1,
        value=f"FDA CGMP Warning Letters — January 2025  ({len(rows)} inspections)")
    t.font = Font(bold=True, size=14, color="1F4E79")
    t.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 30

    # ── Headers ───────────────────────────────────────────────────────────────
    headers = [
        "Firm Name",
        "Country",
        "Location",
        "Inspection Date",
        "# Findings",
        "Risk Level",
        "FDA CITATIONS\n(Original text from Warning Letter)",
        "FDA cGMP REFERENCES\n(21 CFR 210/211 — mapped per finding)",
        "Warning Letter URL",
    ]
    for col, h in enumerate(headers, 1):
        _cell(ws, 2, col, h, font=HEADER_FONT, fill=HEADER_FILL, wrap=True)
    ws.row_dimensions[2].height = 40

    # ── Data ──────────────────────────────────────────────────────────────────
    for row_idx, r in enumerate(rows, 3):
        alt       = ALT_FILL if row_idx % 2 == 0 else None
        risk      = r["risk_level"]
        risk_fill = RISK_FILL.get(risk, alt)

        values = [
            r["firm_name"],
            r["country"],
            r["location"],
            str(r["inspection_date"]) if r["inspection_date"] else "",
            r["num_findings"],
            risk,
            r["fda_citations"],
            r["fda_cgmp_refs"],
            r["warning_letter_url"],
        ]

        for col, val in enumerate(values, 1):
            if col == 6:
                fill = risk_fill
            elif col == 7:
                fill = CITE_FILL      # warm cream — original FDA text
            elif col == 8:
                fill = REF_FILL       # light green — regulatory references
            else:
                fill = alt

            c = _cell(ws, row_idx, col, val, fill=fill, wrap=(col >= 7))
            if col == 7:
                c.font = Font(size=9)
            elif col == 8:
                c.font = Font(size=9, bold=False, color="1A4D1A")

        citation_lines = r["fda_citations"].count("\n") + 1
        ws.row_dimensions[row_idx].height = min(400, max(80, citation_lines * 13))

    # ── Column widths ─────────────────────────────────────────────────────────
    widths = [28, 10, 16, 14, 8, 10, 72, 48, 38]
    for col, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(col)].width = w

    ws.freeze_panes = "A3"
    ws.auto_filter.ref = f"A2:{get_column_letter(len(headers))}2"

    # ── Legend ────────────────────────────────────────────────────────────────
    leg = wb.create_sheet("Legend")
    leg_rows = [
        ("Column", "Data Source", "Notes"),
        ("Firm Name → Risk Level", "FDA Website (scraped)", ""),
        ("FDA CITATIONS", "FDA Warning Letter (verbatim)", "Original text of each finding as written in the letter"),
        ("FDA cGMP REFERENCES", "AI-mapped to 21 CFR 210/211", "Identifies which cGMP regulation each finding violates"),
        ("Warning Letter URL", "FDA Website", "Direct link to the full warning letter"),
        ("", "", ""),
        ("Risk Level", "Color", "Meaning"),
        ("Critical", "Red", "Immediate risk to product quality or patient safety"),
        ("Major", "Orange", "Significant GMP deficiency requiring prompt action"),
        ("Minor", "Yellow", "Lower-risk finding, still requires correction"),
    ]
    for r_idx, row_data in enumerate(leg_rows, 1):
        for c_idx, val in enumerate(row_data, 1):
            c = leg.cell(row=r_idx, column=c_idx, value=val)
            c.border = BORDER
            c.alignment = Alignment(wrap_text=True, vertical="top")
            if r_idx in (1, 7):
                c.font = HEADER_FONT
                c.fill = HEADER_FILL
            elif r_idx == 8:
                c.fill = CRITICAL_FILL
                c.font = Font(bold=True, color="FFFFFF")
            elif r_idx == 9:
                c.fill = MAJOR_FILL
                c.font = Font(bold=True)
            elif r_idx == 10:
                c.fill = MINOR_FILL
                c.font = Font(bold=True)
    leg.column_dimensions["A"].width = 28
    leg.column_dimensions["B"].width = 28
    leg.column_dimensions["C"].width = 55

    # ── Save & open ───────────────────────────────────────────────────────────
    out = Path(__file__).parent / "data" / "reports" / "FDA_CGMP_Jan2025_citations.xlsx"
    wb.save(out)
    print(f"\nSaved: {out}")
    import subprocess
    subprocess.run(["open", str(out)])


if __name__ == "__main__":
    main()
