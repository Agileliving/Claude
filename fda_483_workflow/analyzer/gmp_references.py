"""
GMP regulatory reference database covering:
  - FDA GMP: 21 CFR Parts 210 and 211
  - EU GMP: EudraLex Volume 4 (Chapters 1-9 + Annexes)
  - PIC/S: PE 009 Guide to GMP
  - ICH: Q7, Q8, Q9, Q10, Q11, Q12
  - WHO: TRS 986, TRS 1019 (GMP guidelines)
"""

GMP_FRAMEWORKS = {
    "FDA_GMP": {
        "name": "FDA GMP (21 CFR Parts 210/211)",
        "references": [
            # 21 CFR Part 210
            {"code": "21 CFR 210.1", "title": "Status of current good manufacturing practice regulations", "category": "General"},
            {"code": "21 CFR 210.3", "title": "Definitions", "category": "General"},
            # 21 CFR Part 211 - Subpart A
            {"code": "21 CFR 211.1", "title": "Scope", "category": "General"},
            {"code": "21 CFR 211.22", "title": "Responsibilities of quality control unit", "category": "Quality Systems"},
            {"code": "21 CFR 211.25", "title": "Personnel qualifications", "category": "Personnel"},
            {"code": "21 CFR 211.28", "title": "Personnel responsibilities", "category": "Personnel"},
            {"code": "21 CFR 211.34", "title": "Consultants", "category": "Personnel"},
            # Subpart C - Buildings and Facilities
            {"code": "21 CFR 211.42", "title": "Design and construction features", "category": "Facilities"},
            {"code": "21 CFR 211.44", "title": "Lighting", "category": "Facilities"},
            {"code": "21 CFR 211.46", "title": "Ventilation, air filtration, air heating and cooling", "category": "Facilities"},
            {"code": "21 CFR 211.48", "title": "Plumbing", "category": "Facilities"},
            {"code": "21 CFR 211.50", "title": "Sewage and refuse", "category": "Facilities"},
            {"code": "21 CFR 211.52", "title": "Washing and toilet facilities", "category": "Facilities"},
            {"code": "21 CFR 211.56", "title": "Sanitation", "category": "Facilities"},
            {"code": "21 CFR 211.58", "title": "Maintenance", "category": "Facilities"},
            # Subpart D - Equipment
            {"code": "21 CFR 211.63", "title": "Equipment design, size, and location", "category": "Equipment"},
            {"code": "21 CFR 211.65", "title": "Equipment construction", "category": "Equipment"},
            {"code": "21 CFR 211.67", "title": "Equipment cleaning and maintenance", "category": "Equipment"},
            {"code": "21 CFR 211.68", "title": "Automatic, mechanical, and electronic equipment", "category": "Equipment/Computerised Systems"},
            {"code": "21 CFR 211.72", "title": "Filters", "category": "Equipment"},
            # Subpart E - Control of Components
            {"code": "21 CFR 211.80", "title": "General requirements for control of components", "category": "Materials"},
            {"code": "21 CFR 211.82", "title": "Receipt and storage of untested components", "category": "Materials"},
            {"code": "21 CFR 211.84", "title": "Testing and approval or rejection of components", "category": "Materials/QC"},
            {"code": "21 CFR 211.86", "title": "Use of approved components", "category": "Materials"},
            {"code": "21 CFR 211.87", "title": "Retesting of approved components", "category": "Materials/QC"},
            {"code": "21 CFR 211.89", "title": "Rejected components", "category": "Materials"},
            {"code": "21 CFR 211.94", "title": "Drug product containers and closures", "category": "Materials/Packaging"},
            # Subpart F - Production and Process Controls
            {"code": "21 CFR 211.100", "title": "Written procedures; deviations", "category": "Documentation"},
            {"code": "21 CFR 211.101", "title": "Charge-in of components", "category": "Production"},
            {"code": "21 CFR 211.103", "title": "Calculation of yield", "category": "Production"},
            {"code": "21 CFR 211.105", "title": "Equipment identification", "category": "Equipment"},
            {"code": "21 CFR 211.110", "title": "Sampling and testing of in-process materials", "category": "QC/Production"},
            {"code": "21 CFR 211.111", "title": "Time limitations on production", "category": "Production"},
            {"code": "21 CFR 211.113", "title": "Control of microbiological contamination", "category": "Contamination Control"},
            {"code": "21 CFR 211.115", "title": "Reprocessing", "category": "Production"},
            # Subpart G - Packaging and Labeling Controls
            {"code": "21 CFR 211.122", "title": "Materials examination and usage criteria", "category": "Packaging/Labelling"},
            {"code": "21 CFR 211.125", "title": "Labeling issuance", "category": "Packaging/Labelling"},
            {"code": "21 CFR 211.130", "title": "Packaging and labeling operations", "category": "Packaging/Labelling"},
            {"code": "21 CFR 211.132", "title": "Tamper-evident packaging requirements", "category": "Packaging/Labelling"},
            {"code": "21 CFR 211.137", "title": "Expiration dating", "category": "Packaging/Labelling"},
            # Subpart H - Holding and Distribution
            {"code": "21 CFR 211.142", "title": "Warehousing procedures", "category": "Distribution"},
            {"code": "21 CFR 211.150", "title": "Distribution procedures", "category": "Distribution"},
            # Subpart I - Laboratory Controls
            {"code": "21 CFR 211.160", "title": "General requirements for laboratory controls", "category": "QC/Laboratory"},
            {"code": "21 CFR 211.165", "title": "Testing and release for distribution", "category": "QC/Laboratory"},
            {"code": "21 CFR 211.166", "title": "Stability testing", "category": "QC/Stability"},
            {"code": "21 CFR 211.167", "title": "Special testing requirements", "category": "QC/Laboratory"},
            {"code": "21 CFR 211.170", "title": "Reserve samples", "category": "QC/Laboratory"},
            {"code": "21 CFR 211.173", "title": "Laboratory animals", "category": "QC/Laboratory"},
            {"code": "21 CFR 211.176", "title": "Penicillin contamination", "category": "Contamination Control"},
            # Subpart J - Records and Reports
            {"code": "21 CFR 211.180", "title": "General requirements for records and reports", "category": "Documentation"},
            {"code": "21 CFR 211.182", "title": "Equipment cleaning and use log", "category": "Documentation/Equipment"},
            {"code": "21 CFR 211.184", "title": "Component, drug product container, closure, and labeling records", "category": "Documentation"},
            {"code": "21 CFR 211.186", "title": "Master production and control records", "category": "Documentation"},
            {"code": "21 CFR 211.188", "title": "Batch production and control records", "category": "Documentation"},
            {"code": "21 CFR 211.192", "title": "Production record review", "category": "Documentation/QC"},
            {"code": "21 CFR 211.194", "title": "Laboratory records", "category": "Documentation/QC"},
            {"code": "21 CFR 211.196", "title": "Distribution records", "category": "Documentation/Distribution"},
            {"code": "21 CFR 211.198", "title": "Complaint files", "category": "Complaints/CAPA"},
            # Subpart K - Returned and Salvaged Drug Products
            {"code": "21 CFR 211.204", "title": "Returned drug products", "category": "Complaints/CAPA"},
            {"code": "21 CFR 211.208", "title": "Drug product salvaging", "category": "Quality Systems"},
        ]
    },

    "EU_GMP": {
        "name": "EU GMP (EudraLex Volume 4)",
        "references": [
            # Part I - Basic Requirements
            {"code": "EU GMP Chapter 1", "title": "Pharmaceutical Quality System", "category": "Quality Systems"},
            {"code": "EU GMP Chapter 2", "title": "Personnel", "category": "Personnel"},
            {"code": "EU GMP Chapter 3", "title": "Premises and Equipment", "category": "Facilities/Equipment"},
            {"code": "EU GMP Chapter 4", "title": "Documentation", "category": "Documentation"},
            {"code": "EU GMP Chapter 5", "title": "Production", "category": "Production"},
            {"code": "EU GMP Chapter 6", "title": "Quality Control", "category": "QC/Laboratory"},
            {"code": "EU GMP Chapter 7", "title": "Outsourced Activities", "category": "Quality Systems/Suppliers"},
            {"code": "EU GMP Chapter 8", "title": "Complaints, Quality Defects and Product Recalls", "category": "Complaints/CAPA"},
            {"code": "EU GMP Chapter 9", "title": "Self-Inspection", "category": "Quality Systems"},
            # Part I sub-sections (EMA Annex-referenced)
            {"code": "EU GMP 1.1", "title": "Quality Management System (PQS)", "category": "Quality Systems"},
            {"code": "EU GMP 1.4", "title": "Product Quality Review", "category": "Quality Systems"},
            {"code": "EU GMP 2.1-2.2", "title": "Key Personnel (QP, Head of Production, Head of QC)", "category": "Personnel"},
            {"code": "EU GMP 3.6-3.9", "title": "Equipment qualification and calibration", "category": "Equipment"},
            {"code": "EU GMP 4.29-4.30", "title": "Change control and deviations", "category": "Documentation/CAPA"},
            {"code": "EU GMP 5.63-5.68", "title": "Computerised systems in production", "category": "Computerised Systems"},
            {"code": "EU GMP 6.15-6.17", "title": "Out of specification (OOS) investigations", "category": "QC/Laboratory"},
            # Annexes
            {"code": "EU GMP Annex 1", "title": "Manufacture of Sterile Medicinal Products", "category": "Sterile Manufacturing"},
            {"code": "EU GMP Annex 2", "title": "Manufacture of Biological Active Substances and Medicinal Products", "category": "Biological Products"},
            {"code": "EU GMP Annex 3", "title": "Manufacture of Radiopharmaceuticals", "category": "Radiopharmaceuticals"},
            {"code": "EU GMP Annex 4", "title": "Manufacture of Veterinary Medicinal Products", "category": "Veterinary"},
            {"code": "EU GMP Annex 6", "title": "Manufacture of Medicinal Gases", "category": "Gases"},
            {"code": "EU GMP Annex 7", "title": "Manufacture of Herbal Medicinal Products", "category": "Herbal"},
            {"code": "EU GMP Annex 8", "title": "Sampling of Starting and Packaging Materials", "category": "Materials/QC"},
            {"code": "EU GMP Annex 9", "title": "Manufacture of Liquids, Creams and Ointments", "category": "Production"},
            {"code": "EU GMP Annex 10", "title": "Manufacture of Pressurised Metered Dose Aerosol Products", "category": "Production"},
            {"code": "EU GMP Annex 11", "title": "Computerised Systems", "category": "Computerised Systems"},
            {"code": "EU GMP Annex 12", "title": "Use of Ionising Radiation in the Manufacture of Medicinal Products", "category": "Irradiation"},
            {"code": "EU GMP Annex 13", "title": "Manufacture of Investigational Medicinal Products", "category": "Clinical Trials"},
            {"code": "EU GMP Annex 14", "title": "Manufacture of Medicinal Products Derived from Human Blood or Plasma", "category": "Blood Products"},
            {"code": "EU GMP Annex 15", "title": "Qualification and Validation", "category": "Validation"},
            {"code": "EU GMP Annex 16", "title": "Certification by a Qualified Person", "category": "Quality Systems"},
            {"code": "EU GMP Annex 17", "title": "Real Time Release Testing", "category": "QC/Production"},
            {"code": "EU GMP Annex 19", "title": "Reference and Retention Samples", "category": "QC/Laboratory"},
            {"code": "EU GMP Annex 20", "title": "Quality Risk Management", "category": "Quality Systems/Risk"},
            {"code": "EU GMP Annex 21", "title": "Import of Medicinal Products", "category": "Distribution"},
        ]
    },

    "PICS": {
        "name": "PIC/S GMP Guide (PE 009)",
        "references": [
            {"code": "PIC/S PE 009 Part I Ch.1", "title": "Quality Management", "category": "Quality Systems"},
            {"code": "PIC/S PE 009 Part I Ch.2", "title": "Personnel", "category": "Personnel"},
            {"code": "PIC/S PE 009 Part I Ch.3", "title": "Premises and Equipment", "category": "Facilities/Equipment"},
            {"code": "PIC/S PE 009 Part I Ch.4", "title": "Documentation", "category": "Documentation"},
            {"code": "PIC/S PE 009 Part I Ch.5", "title": "Production", "category": "Production"},
            {"code": "PIC/S PE 009 Part I Ch.6", "title": "Quality Control", "category": "QC/Laboratory"},
            {"code": "PIC/S PE 009 Part I Ch.7", "title": "Contract Manufacture and Analysis", "category": "Quality Systems/Suppliers"},
            {"code": "PIC/S PE 009 Part I Ch.8", "title": "Complaints and Product Recall", "category": "Complaints/CAPA"},
            {"code": "PIC/S PE 009 Part I Ch.9", "title": "Self Inspection", "category": "Quality Systems"},
            {"code": "PIC/S PE 009 Part II", "title": "Basic Requirements for Active Substances (APIs)", "category": "API Manufacturing"},
            {"code": "PIC/S PE 009 Annex 1", "title": "Manufacture of Sterile Medicinal Products", "category": "Sterile Manufacturing"},
            {"code": "PIC/S PE 009 Annex 11", "title": "Computerised Systems", "category": "Computerised Systems"},
            {"code": "PIC/S PE 009 Annex 15", "title": "Qualification and Validation", "category": "Validation"},
            {"code": "PIC/S PE 009 Annex 20", "title": "Quality Risk Management", "category": "Quality Systems/Risk"},
            {"code": "PIC/S PI 006", "title": "Recommendations on Validation Master Plan (VMP)", "category": "Validation"},
            {"code": "PIC/S PI 011", "title": "Sterile Manufacture Interpretation", "category": "Sterile Manufacturing"},
            {"code": "PIC/S PI 041", "title": "Data Integrity and Management of Records", "category": "Data Integrity"},
            {"code": "PIC/S PI 043", "title": "GMP for Medicinal Products for Human Use (Revised)", "category": "Quality Systems"},
        ]
    },

    "ICH": {
        "name": "ICH Q Guidelines",
        "references": [
            {"code": "ICH Q1A(R2)", "title": "Stability Testing of New Drug Substances and Products", "category": "QC/Stability"},
            {"code": "ICH Q1B", "title": "Photostability Testing of New Drug Substances and Products", "category": "QC/Stability"},
            {"code": "ICH Q1C", "title": "Stability Testing for New Dosage Forms", "category": "QC/Stability"},
            {"code": "ICH Q1D", "title": "Bracketing and Matrixing Designs for Stability Testing", "category": "QC/Stability"},
            {"code": "ICH Q1E", "title": "Evaluation for Stability Data", "category": "QC/Stability"},
            {"code": "ICH Q2(R2)", "title": "Validation of Analytical Procedures", "category": "QC/Laboratory"},
            {"code": "ICH Q3A(R2)", "title": "Impurities in New Drug Substances", "category": "QC/Impurities"},
            {"code": "ICH Q3B(R2)", "title": "Impurities in New Drug Products", "category": "QC/Impurities"},
            {"code": "ICH Q3C(R8)", "title": "Impurities: Guideline for Residual Solvents", "category": "QC/Impurities"},
            {"code": "ICH Q3D(R2)", "title": "Guideline for Elemental Impurities", "category": "QC/Impurities"},
            {"code": "ICH Q4B", "title": "Evaluation and Recommendation of Pharmacopoeial Texts", "category": "QC/Laboratory"},
            {"code": "ICH Q5A(R2)", "title": "Viral Safety Evaluation of Biotechnology Products", "category": "Biological Products"},
            {"code": "ICH Q5C", "title": "Stability Testing of Biotechnological/Biological Products", "category": "QC/Stability"},
            {"code": "ICH Q5D", "title": "Derivation and Characterisation of Cell Substrates", "category": "Biological Products"},
            {"code": "ICH Q6A", "title": "Specifications: Test Procedures and Acceptance Criteria (Chemical)", "category": "QC/Specifications"},
            {"code": "ICH Q6B", "title": "Specifications: Test Procedures and Acceptance Criteria (Biological)", "category": "QC/Specifications"},
            {"code": "ICH Q7", "title": "Good Manufacturing Practice for Active Pharmaceutical Ingredients", "category": "API Manufacturing"},
            {"code": "ICH Q8(R2)", "title": "Pharmaceutical Development", "category": "Quality Systems/Development"},
            {"code": "ICH Q9(R1)", "title": "Quality Risk Management", "category": "Quality Systems/Risk"},
            {"code": "ICH Q10", "title": "Pharmaceutical Quality System", "category": "Quality Systems"},
            {"code": "ICH Q11", "title": "Development and Manufacture of Drug Substances", "category": "API Manufacturing"},
            {"code": "ICH Q12", "title": "Technical and Regulatory Considerations for Pharmaceutical Product Lifecycle Management", "category": "Quality Systems"},
            {"code": "ICH Q13", "title": "Continuous Manufacturing of Drug Substances and Drug Products", "category": "Production"},
            {"code": "ICH Q14", "title": "Analytical Procedure Development", "category": "QC/Laboratory"},
        ]
    },

    "WHO": {
        "name": "WHO GMP Guidelines",
        "references": [
            {"code": "WHO TRS 986 Annex 2", "title": "WHO GMP for Pharmaceutical Products: Main Principles", "category": "Quality Systems"},
            {"code": "WHO TRS 986 Annex 3", "title": "WHO GMP for Pharmaceutical Products Containing Hazardous Substances", "category": "Contamination Control"},
            {"code": "WHO TRS 992 Annex 3", "title": "WHO GMP for Biological Products", "category": "Biological Products"},
            {"code": "WHO TRS 996 Annex 2", "title": "WHO GMP for Sterile Products", "category": "Sterile Manufacturing"},
            {"code": "WHO TRS 1019 Annex 2", "title": "WHO GMP for Active Pharmaceutical Ingredients", "category": "API Manufacturing"},
            {"code": "WHO TRS 1019 Annex 3", "title": "WHO GMP Supplementary Guidelines for Manufacture of Investigational Pharmaceutical Products", "category": "Clinical Trials"},
            {"code": "WHO TRS 1019 Annex 4", "title": "WHO Guidance on Good Data and Record Management Practices", "category": "Data Integrity"},
            {"code": "WHO TRS 1019 Annex 7", "title": "WHO Guidelines for Sampling of Pharmaceutical Products and Related Materials", "category": "Materials/QC"},
            {"code": "WHO TRS 1025 Annex 3", "title": "WHO GMP for Starting Materials", "category": "Materials"},
            {"code": "WHO TRS 1025 Annex 9", "title": "Model Guidance for Storage and Transport of Time and Temperature Sensitive Pharmaceutical Products", "category": "Distribution"},
            {"code": "WHO TRS 1033 Annex 4", "title": "WHO GMP Supplementary Guidance — Parametric Release", "category": "QC/Production"},
            {"code": "WHO TRS 1039 Annex 1", "title": "WHO Guidance on Computerised Systems", "category": "Computerised Systems"},
            {"code": "WHO TRS 1044 Annex 2", "title": "WHO Good Manufacturing Practices for Blood Establishments", "category": "Blood Products"},
            {"code": "WHO TRS 1044 Annex 4", "title": "WHO GMP for Radiopharmaceuticals", "category": "Radiopharmaceuticals"},
            {"code": "WHO TRS 1044 Annex 6", "title": "WHO Guidance on Qualification of Pharmaceutical Manufacturing Equipment", "category": "Equipment/Validation"},
        ]
    }
}


# Category-based cross-reference lookup: maps a category keyword to refs across all frameworks
def get_references_by_category(category_keyword: str) -> dict[str, list[dict]]:
    """Return matching references from all frameworks for a given category keyword."""
    results = {}
    kw = category_keyword.lower()
    for fw_key, fw_data in GMP_FRAMEWORKS.items():
        matches = [
            ref for ref in fw_data["references"]
            if kw in ref["category"].lower() or kw in ref["title"].lower()
        ]
        if matches:
            results[fw_key] = matches
    return results


def get_framework_summary() -> str:
    """Return a compact summary of all frameworks and their reference counts."""
    lines = []
    for fw_key, fw_data in GMP_FRAMEWORKS.items():
        lines.append(f"- {fw_data['name']}: {len(fw_data['references'])} references")
    return "\n".join(lines)


def build_reference_context() -> str:
    """Build a condensed GMP reference list for inclusion in Claude prompts."""
    sections = []
    for fw_key, fw_data in GMP_FRAMEWORKS.items():
        refs = fw_data["references"]
        ref_list = "\n".join(f"  • {r['code']}: {r['title']} [{r['category']}]" for r in refs)
        sections.append(f"### {fw_data['name']}\n{ref_list}")
    return "\n\n".join(sections)
