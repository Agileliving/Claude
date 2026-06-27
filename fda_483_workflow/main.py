"""
FDA Form 483 GMP Intelligence Pipeline
Entry point for running the weekly pull, backfill, or single-date analysis.
"""
import argparse
import logging
import schedule
import time

from config import WEEKLY_SCHEDULE_DAY, WEEKLY_SCHEDULE_TIME
from db import init_db
from scheduler import run_weekly_pull, run_backfill

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="FDA Form 483 GMP Intelligence Pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Weekly pull (manual trigger)
    subparsers.add_parser("pull", help="Run a weekly pull for the past 7 days")

    # Historical backfill
    backfill_parser = subparsers.add_parser("backfill", help="Run historical backfill")
    backfill_parser.add_argument("--start", default=None, help="Start date MM/DD/YYYY (default: 01/01/2025)")
    backfill_parser.add_argument("--end", default=None, help="End date MM/DD/YYYY (default: yesterday)")

    # Daemon mode: schedule weekly pulls
    subparsers.add_parser("daemon", help="Run as a weekly scheduled daemon")

    args = parser.parse_args()

    # Initialize database
    init_db()
    logger.info("Database initialized.")

    if args.command == "pull":
        logger.info("Running manual weekly pull...")
        run_weekly_pull()

    elif args.command == "backfill":
        logger.info(f"Running backfill: {args.start or '01/01/2025'} to {args.end or 'yesterday'}")
        run_backfill(start_date_str=args.start, end_date_str=args.end)

    elif args.command == "daemon":
        logger.info(f"Starting daemon — weekly pull every {WEEKLY_SCHEDULE_DAY} at {WEEKLY_SCHEDULE_TIME}")
        getattr(schedule.every(), WEEKLY_SCHEDULE_DAY).at(WEEKLY_SCHEDULE_TIME).do(run_weekly_pull)
        while True:
            schedule.run_pending()
            time.sleep(60)


if __name__ == "__main__":
    main()
