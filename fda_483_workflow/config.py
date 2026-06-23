import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
PDF_DIR = DATA_DIR / "pdfs"
REPORTS_DIR = DATA_DIR / "reports"

for d in [DATA_DIR, PDF_DIR, REPORTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
CLAUDE_MODEL = "claude-opus-4-8"

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR}/fda483.db")

FDA_BASE_URL = "https://www.fda.gov"
FDA_483_URL = "https://www.fda.gov/inspections-compliance-enforcement/inspection-observations"
FDA_FOIA_URL = "https://www.fda.gov/regulatory-information/freedom-of-information/electronic-reading-room"

# Pharmaceutical-specific product codes (FDA industry codes)
PHARMA_PRODUCT_CODES = [
    "56A", "56B", "56C", "56D", "56E", "56F", "56G", "56H", "56I", "56J", "56K",
    "54",  # Human drug
    "03",  # Biologic
    "73",  # Veterinary drug
]

# Date range for historical backfill
BACKFILL_START_DATE = "01/01/2025"
BACKFILL_END_DATE = None  # None = today

# Weekly schedule (day of week)
WEEKLY_SCHEDULE_DAY = "monday"
WEEKLY_SCHEDULE_TIME = "06:00"

REQUEST_DELAY_SECONDS = 1.5
REQUEST_TIMEOUT_SECONDS = 30
MAX_RETRIES = 3
