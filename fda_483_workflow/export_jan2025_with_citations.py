"""
Export all inspections (2025-01-01 to 2026-06-30) to Excel with original
FDA citation text and linked FDA cGMP references (21 CFR Part 210/211).
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

    start = date(2025, 1, 1)
    end   = date(2026, 6, 30)

    with get_session() as session:
        inspections = (
            session.query(Inspection)
            .filter(
                Inspection.inspection_end_date >= start,
                Inspection.inspection_end_date <= end,
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

            citations = []
            for obs in obs_list:
                if obs.observation_text and obs.observation_text.strip():
                    citations.append(
                        f"[Finding {obs.observation_number}]\n{obs.observation_text.strip()}"
                    )

            fda_refs = _build_fda_refs(obs_list)

            rows.append({
                "firm_name":       insp.firm_name or "",
                "country":         insp.country or "",
                "inspection_date": insp.inspection_end_date,
                "num_findings":    insp.num_observations or 0,
                "fda_citations":   "\n\n".join(citations) or "(no citation text stored)",
                "fda_cgmp_refs":   fda_refs,
            })

    print(f"Found {len(rows)} analyzed inspections (Jan 2025 – Jun 2026)")
    if not rows:
        print("No data — check that the backfill ran for January 2025.")
        return

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "FDA Citations 2025-2026"

    # ── Title ─────────────────────────────────────────────────────────────────
    ws.merge_cells("A1:F1")
    t = ws.cell(row=1, column=1,
        value=f"FDA CGMP Warning Letters — Jan 2025 to Jun 2026  ({len(rows)} inspections)")
    t.font = Font(bold=True, size=14, color="1F4E79")
    t.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 30

    # ── Headers ───────────────────────────────────────────────────────────────
    headers = [
        "Firm Name",
        "Country",
        "Inspection Date",
        "# Findings",
        "FDA CITATIONS\n(Original text from Warning Letter)",
        "FDA cGMP REFERENCES\n(21 CFR 210/211 — mapped per finding)",
    ]
    for col, h in enumerate(headers, 1):
        _cell(ws, 2, col, h, font=HEADER_FONT, fill=HEADER_FILL, wrap=True)
    ws.row_dimensions[2].height = 40

    # ── Data ──────────────────────────────────────────────────────────────────
    for row_idx, r in enumerate(rows, 3):
        alt = ALT_FILL if row_idx % 2 == 0 else None

        values = [
            r["firm_name"],
            r["country"],
            str(r["inspection_date"]) if r["inspection_date"] else "",
            r["num_findings"],
            r["fda_citations"],
            r["fda_cgmp_refs"],
        ]

        for col, val in enumerate(values, 1):
            if col == 5:
                fill = CITE_FILL
            elif col == 6:
                fill = REF_FILL
            else:
                fill = alt

            c = _cell(ws, row_idx, col, val, fill=fill, wrap=(col >= 5))
            if col == 5:
                c.font = Font(size=9)
            elif col == 6:
                c.font = Font(size=9, bold=False, color="1A4D1A")

        citation_lines = r["fda_citations"].count("\n") + 1
        ws.row_dimensions[row_idx].height = min(400, max(80, citation_lines * 13))

    # ── Column widths ─────────────────────────────────────────────────────────
    widths = [28, 12, 14, 8, 72, 50]
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
    out = Path(__file__).parent / "data" / "reports" / "FDA_CGMP_2025_2026_citations.xlsx"
    wb.save(out)
    print(f"\nSaved: {out}")
    import subprocess
    subprocess.run(["open", str(out)])


if __name__ == "__main__":
    main()
