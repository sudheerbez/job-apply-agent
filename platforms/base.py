"""
Base platform class - common interface for all job platforms.
"""

import re
from abc import ABC, abstractmethod
from utils.browser_manager import BrowserManager
from utils.ai_helper import AIHelper
from utils.tracker import ApplicationTracker
from utils.logger import get_logger


class BasePlatform(ABC):
    """Abstract base class for job platform automation."""

    PLATFORM_NAME = "base"

    def __init__(
        self,
        browser: BrowserManager,
        config: dict,
        tracker: ApplicationTracker,
        ai_helper: AIHelper,
    ):
        self.browser = browser
        self.config = config
        self.tracker = tracker
        self.ai = ai_helper
        self.logger = get_logger()
        self.search_config = config.get("search", {})
        self.profile = config.get("profile", {})
        self.max_applications = self.search_config.get("max_applications_per_run", 50)
        self._applied_count = 0

    @abstractmethod
    async def login(self):
        """Log in to the platform."""
        pass

    @abstractmethod
    async def search_jobs(self, keyword: str, location: str) -> list:
        """
        Search for jobs and return a list of job dicts.
        Each dict should have: title, company, location, url, description (optional)
        """
        pass

    @abstractmethod
    async def apply_to_job(self, job: dict) -> bool:
        """
        Apply to a single job. Returns True if successful.
        """
        pass

    async def run(self):
        """Main execution: login, search, and apply."""
        self.logger.info(f"Starting {self.PLATFORM_NAME} automation...")

        try:
            await self.login()
        except Exception as e:
            self.logger.error(f"Login failed for {self.PLATFORM_NAME}: {e}")
            await self.browser.screenshot(f"{self.PLATFORM_NAME}_login_error")
            return

        keywords = self.search_config.get("keywords", [])
        locations = self.search_config.get("locations", [])

        for keyword in keywords:
            for location in locations:
                if self._applied_count >= self.max_applications:
                    self.logger.info(
                        f"Reached max applications ({self.max_applications}). Stopping."
                    )
                    return

                self.logger.info(
                    f"Searching: '{keyword}' in '{location}'"
                )

                try:
                    jobs = await self.search_jobs(keyword, location)
                    self.logger.info(f"Found {len(jobs)} jobs")

                    for job in jobs:
                        if self._applied_count >= self.max_applications:
                            return

                        # Skip blacklisted companies
                        if self._is_blacklisted(job.get("company", "")):
                            self.tracker.log_application(
                                platform=self.PLATFORM_NAME,
                                company=job.get("company", ""),
                                job_title=job.get("title", ""),
                                job_url=job.get("url", ""),
                                status="skipped",
                                error_message="Blacklisted company",
                            )
                            continue

                        # Skip by title patterns
                        if not self._title_passes_filters(job.get("title", "")):
                            self.tracker.log_application(
                                platform=self.PLATFORM_NAME,
                                company=job.get("company", ""),
                                job_title=job.get("title", ""),
                                job_url=job.get("url", ""),
                                status="skipped",
                                error_message="Title filter mismatch",
                            )
                            continue

                        # Skip duplicates
                        if self.tracker.is_already_applied(job.get("url", "")):
                            self.tracker.log_application(
                                platform=self.PLATFORM_NAME,
                                company=job.get("company", ""),
                                job_title=job.get("title", ""),
                                job_url=job.get("url", ""),
                                status="duplicate",
                            )
                            continue

                        # Apply
                        try:
                            success = await self.apply_to_job(job)
                            if success:
                                self._applied_count += 1
                                self.tracker.log_application(
                                    platform=self.PLATFORM_NAME,
                                    company=job.get("company", ""),
                                    job_title=job.get("title", ""),
                                    job_url=job.get("url", ""),
                                    location=job.get("location", ""),
                                    status="applied",
                                    resume_used=self.config.get("documents", {}).get(
                                        "resume_path", ""
                                    ),
                                )
                        except Exception as e:
                            self.logger.error(
                                f"Failed to apply: {job.get('title', '')} at {job.get('company', '')}: {e}"
                            )
                            await self.browser.screenshot(
                                f"{self.PLATFORM_NAME}_apply_error_{self._applied_count}"
                            )
                            self.tracker.log_application(
                                platform=self.PLATFORM_NAME,
                                company=job.get("company", ""),
                                job_title=job.get("title", ""),
                                job_url=job.get("url", ""),
                                status="failed",
                                error_message=str(e)[:200],
                            )

                except Exception as e:
                    self.logger.error(f"Search failed: {e}")
                    await self.browser.screenshot(
                        f"{self.PLATFORM_NAME}_search_error"
                    )

        self.logger.info(
            f"{self.PLATFORM_NAME} complete. Applied to {self._applied_count} jobs."
        )

    def _is_blacklisted(self, company: str) -> bool:
        """Check if a company is on the blacklist."""
        blacklist = self.search_config.get("blacklist_companies", [])
        return company.lower().strip() in [b.lower().strip() for b in blacklist]

    def _title_passes_filters(self, title: str) -> bool:
        """Check if a job title passes include/exclude pattern filters."""
        include = self.search_config.get("title_include_patterns", [])
        exclude = self.search_config.get("title_exclude_patterns", [])

        if include:
            if not any(re.search(p, title) for p in include):
                return False

        if exclude:
            if any(re.search(p, title) for p in exclude):
                return False

        return True
