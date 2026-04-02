"""
Application Tracker - Logs all applications to a CSV file and provides stats.
"""

import csv
import os
from datetime import datetime
from pathlib import Path
from utils.logger import get_logger


class ApplicationTracker:
    """Tracks job applications in a CSV file with status and metadata."""

    CSV_HEADERS = [
        "timestamp",
        "platform",
        "company",
        "job_title",
        "job_url",
        "location",
        "status",       # applied, skipped, failed, duplicate
        "error_message",
        "resume_used",
        "cover_letter_generated",
    ]

    def __init__(self, data_dir: str = "data"):
        self.logger = get_logger()
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.csv_path = self.data_dir / "applications.csv"
        self._ensure_csv()

        # In-memory set of applied job URLs for dedup
        self._applied_urls = set()
        self._load_existing()

    def _ensure_csv(self):
        """Create CSV file with headers if it doesn't exist."""
        if not self.csv_path.exists():
            with open(self.csv_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=self.CSV_HEADERS)
                writer.writeheader()

    def _load_existing(self):
        """Load already-applied URLs from existing CSV."""
        if not self.csv_path.exists():
            return
        try:
            with open(self.csv_path, "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("status") == "applied":
                        self._applied_urls.add(row.get("job_url", ""))
        except Exception as e:
            self.logger.warning(f"Could not load existing applications: {e}")

    def is_already_applied(self, job_url: str) -> bool:
        """Check if we've already applied to this job."""
        return job_url in self._applied_urls

    def log_application(
        self,
        platform: str,
        company: str,
        job_title: str,
        job_url: str,
        location: str = "",
        status: str = "applied",
        error_message: str = "",
        resume_used: str = "",
        cover_letter_generated: bool = False,
    ):
        """Log a job application attempt to the CSV."""
        record = {
            "timestamp": datetime.now().isoformat(),
            "platform": platform,
            "company": company,
            "job_title": job_title,
            "job_url": job_url,
            "location": location,
            "status": status,
            "error_message": error_message,
            "resume_used": resume_used,
            "cover_letter_generated": str(cover_letter_generated),
        }

        with open(self.csv_path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self.CSV_HEADERS)
            writer.writerow(record)

        if status == "applied":
            self._applied_urls.add(job_url)

        status_emoji = {
            "applied": "[green]APPLIED[/green]",
            "skipped": "[yellow]SKIPPED[/yellow]",
            "failed": "[red]FAILED[/red]",
            "duplicate": "[dim]DUPLICATE[/dim]",
        }
        log_status = status_emoji.get(status, status)
        self.logger.info(f"{log_status} | {company} - {job_title}")

    def get_stats(self) -> dict:
        """Get application statistics from the CSV."""
        stats = {"applied": 0, "skipped": 0, "failed": 0, "duplicate": 0, "total": 0}
        if not self.csv_path.exists():
            return stats

        with open(self.csv_path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                stats["total"] += 1
                status = row.get("status", "")
                if status in stats:
                    stats[status] += 1

        return stats

    def print_summary(self):
        """Print a summary of the current run."""
        stats = self.get_stats()
        self.logger.info(
            f"\n{'='*50}\n"
            f"APPLICATION SUMMARY\n"
            f"{'='*50}\n"
            f"Total Processed: {stats['total']}\n"
            f"Applied:         {stats['applied']}\n"
            f"Skipped:         {stats['skipped']}\n"
            f"Failed:          {stats['failed']}\n"
            f"Duplicates:      {stats['duplicate']}\n"
            f"{'='*50}"
        )
