"""
Indeed automation - handles login, job search, and applications.
"""

import asyncio
from urllib.parse import quote_plus
from playwright.async_api import Page, TimeoutError as PlaywrightTimeout
from platforms.base import BasePlatform


class IndeedPlatform(BasePlatform):
    """Automates job applications on Indeed."""

    PLATFORM_NAME = "indeed"
    BASE_URL = "https://www.indeed.com"
    LOGIN_URL = "https://secure.indeed.com/auth"
    JOBS_URL = "https://www.indeed.com/jobs"

    # Date posted mapping
    DATE_FILTER_MAP = {
        "past_24h": "1",
        "past_3d": "3",
        "past_week": "7",
        "past_month": "30",
    }

    # Job type mapping
    JOB_TYPE_MAP = {
        "full_time": "fulltime",
        "part_time": "parttime",
        "contract": "contract",
        "temporary": "temporary",
        "internship": "internship",
    }

    async def login(self):
        """Log in to Indeed."""
        page = self.browser.page
        creds = self.config.get("platforms", {}).get("indeed", {})
        email = creds.get("email", "")
        password = creds.get("password", "")

        if not email or not password:
            self.logger.warning(
                "Indeed credentials not configured. "
                "Will attempt to apply without login (limited functionality)."
            )
            await page.goto(self.BASE_URL, wait_until="networkidle")
            return

        self.logger.info("Logging in to Indeed...")
        await page.goto(self.LOGIN_URL, wait_until="networkidle")
        await self.browser.random_delay(1000, 2000)

        # Indeed uses a multi-step login: email first, then password
        try:
            # Enter email
            email_input = await page.wait_for_selector(
                'input[type="email"], input[name="__email"], #ifl-InputFormField-3',
                timeout=10000,
            )
            await email_input.fill("")
            await self.browser.human_type(
                'input[type="email"], input[name="__email"], #ifl-InputFormField-3',
                email,
            )
            await self.browser.random_delay(500, 1000)

            # Click continue/submit
            submit_btn = await page.query_selector(
                'button[type="submit"], button:has-text("Continue"), '
                'button:has-text("Sign in"), button:has-text("Log in")'
            )
            if submit_btn:
                await submit_btn.click()
                await page.wait_for_load_state("networkidle")
                await self.browser.random_delay(2000, 3000)

            # Enter password (may be on next page)
            pw_input = await page.wait_for_selector(
                'input[type="password"]', timeout=10000
            )
            if pw_input:
                await self.browser.human_type('input[type="password"]', password)
                await self.browser.random_delay(500, 1000)

                submit_btn = await page.query_selector(
                    'button[type="submit"], button:has-text("Sign in")'
                )
                if submit_btn:
                    await submit_btn.click()
                    await page.wait_for_load_state("networkidle")
                    await self.browser.random_delay(2000, 4000)

            # Check for CAPTCHA or verification
            if "verify" in page.url or "challenge" in page.url:
                self.logger.warning(
                    "Indeed verification detected. Please complete it manually."
                )
                for _ in range(60):
                    await asyncio.sleep(2)
                    if "indeed.com/jobs" in page.url or page.url == self.BASE_URL + "/":
                        break

            self.logger.info("Indeed login complete")

        except PlaywrightTimeout:
            self.logger.warning("Indeed login flow timed out - proceeding without login")

    async def search_jobs(self, keyword: str, location: str) -> list:
        """Search for jobs on Indeed."""
        page = self.browser.page
        jobs = []

        # Build search URL
        params = {
            "q": keyword,
            "l": location,
        }

        # Date posted filter
        date_posted = self.search_config.get("date_posted", "past_week")
        fromage = self.DATE_FILTER_MAP.get(date_posted, "7")
        params["fromage"] = fromage

        # Job type filter
        job_types = self.search_config.get("job_types", [])
        if job_types:
            jt = self.JOB_TYPE_MAP.get(job_types[0], "")
            if jt:
                params["jt"] = jt

        # Prefer "easily apply" jobs
        params["sc"] = "0kf:attr(DSQF7);"

        query_string = "&".join(f"{k}={quote_plus(str(v))}" for k, v in params.items())
        search_url = f"{self.JOBS_URL}?{query_string}"

        self.logger.info(f"Searching Indeed: {search_url}")
        await page.goto(search_url, wait_until="networkidle")
        await self.browser.random_delay(2000, 4000)

        # Paginate through results (up to 5 pages)
        for page_num in range(5):
            await self.browser.random_delay(1000, 2000)

            # Close any popups
            await self._dismiss_popups()

            # Extract job cards
            job_cards = await page.query_selector_all(
                '.job_seen_beacon, .jobsearch-ResultsList > li, '
                'div[class*="job_seen_beacon"], .resultContent'
            )

            if not job_cards:
                self.logger.info(f"No job cards found on page {page_num + 1}")
                break

            for card in job_cards:
                try:
                    # Title and URL
                    title_el = await card.query_selector(
                        'h2.jobTitle a, a[data-jk], .jobTitle > a, '
                        'a.jcs-JobTitle'
                    )
                    title = ""
                    job_url = ""
                    if title_el:
                        title_span = await title_el.query_selector("span")
                        title = (await title_span.inner_text()).strip() if title_span else (await title_el.inner_text()).strip()
                        href = await title_el.get_attribute("href")
                        if href:
                            job_url = href if href.startswith("http") else f"{self.BASE_URL}{href}"
                            job_url = job_url.split("&")[0] if "&" in job_url else job_url

                    # Company
                    company_el = await card.query_selector(
                        'span[data-testid="company-name"], '
                        '.companyName, .company'
                    )
                    company = (await company_el.inner_text()).strip() if company_el else ""

                    # Location
                    location_el = await card.query_selector(
                        'div[data-testid="text-location"], '
                        '.companyLocation, .location'
                    )
                    loc = (await location_el.inner_text()).strip() if location_el else ""

                    if title and job_url:
                        jobs.append(
                            {
                                "title": title,
                                "company": company,
                                "location": loc,
                                "url": job_url,
                                "platform": "indeed",
                            }
                        )

                except Exception as e:
                    self.logger.debug(f"Error parsing Indeed job card: {e}")
                    continue

            if len(jobs) >= self.max_applications:
                break

            # Next page
            try:
                next_link = await page.query_selector(
                    'a[data-testid="pagination-page-next"], '
                    'a[aria-label="Next Page"], '
                    'a:has-text("Next")'
                )
                if next_link:
                    await next_link.click()
                    await page.wait_for_load_state("networkidle")
                    await self.browser.random_delay(2000, 3000)
                else:
                    break
            except Exception:
                break

        self.logger.info(f"Found {len(jobs)} Indeed jobs for '{keyword}' in '{location}'")
        return jobs

    async def apply_to_job(self, job: dict) -> bool:
        """Apply to an Indeed job."""
        page = self.browser.page
        job_url = job.get("url", "")

        self.logger.info(f"Applying to: {job.get('title')} at {job.get('company')}")

        await page.goto(job_url, wait_until="networkidle")
        await self.browser.random_delay(1500, 3000)
        await self._dismiss_popups()

        # Look for Apply button
        apply_btn = await page.query_selector(
            'button[id="indeedApplyButton"], '
            'button:has-text("Apply now"), '
            'a:has-text("Apply now"), '
            'button:has-text("Apply on company site"), '
            '.jobsearch-IndeedApplyButton-newDesign'
        )

        if not apply_btn:
            self.logger.info(f"No apply button found for {job.get('title')}")
            self.tracker.log_application(
                platform=self.PLATFORM_NAME,
                company=job.get("company", ""),
                job_title=job.get("title", ""),
                job_url=job_url,
                status="skipped",
                error_message="No apply button found",
            )
            return False

        # Check if it's "Apply on company site" (external)
        btn_text = (await apply_btn.inner_text()).strip().lower()
        if "company site" in btn_text:
            self.logger.info("External application - skipping (handled by career_pages module)")
            self.tracker.log_application(
                platform=self.PLATFORM_NAME,
                company=job.get("company", ""),
                job_title=job.get("title", ""),
                job_url=job_url,
                status="skipped",
                error_message="External application site",
            )
            return False

        await apply_btn.click()
        await self.browser.random_delay(2000, 4000)

        # Handle Indeed's apply flow (may open in iframe or new window)
        return await self._process_indeed_apply(job)

    async def _process_indeed_apply(self, job: dict) -> bool:
        """Process Indeed's multi-step application form."""
        page = self.browser.page
        max_steps = 10

        for step in range(max_steps):
            await self.browser.random_delay(1000, 2000)

            # Check for iframe (Indeed Apply opens in an iframe)
            iframe_el = await page.query_selector(
                'iframe[title*="Apply"], iframe[id*="indeed-apply"]'
            )
            
            target = page
            if iframe_el:
                frame = await iframe_el.content_frame()
                if frame:
                    target = frame

            # Check if application is complete
            complete_indicators = await target.query_selector(
                ':has-text("Application submitted"), '
                ':has-text("You have applied"), '
                ':has-text("application has been submitted")'
            )
            if complete_indicators:
                self.logger.info("Indeed application submitted successfully!")
                return True

            # Fill form fields
            await self._fill_indeed_fields(target, job)

            # Look for Continue/Submit button
            continue_btn = await target.query_selector(
                'button:has-text("Continue"), '
                'button:has-text("Submit"), '
                'button:has-text("Apply"), '
                'button:has-text("Next"), '
                'button[type="submit"]'
            )

            if continue_btn:
                btn_text = (await continue_btn.inner_text()).strip().lower()
                await self.browser.random_delay(300, 700)
                await continue_btn.click()
                await self.browser.random_delay(2000, 3000)

                if "submit" in btn_text or "apply" in btn_text:
                    # Wait for confirmation
                    await self.browser.random_delay(2000, 3000)
                    return True
            else:
                self.logger.warning(f"No continue/submit button at step {step + 1}")
                await self.browser.screenshot(f"indeed_stuck_step_{step}")
                return False

        return False

    async def _fill_indeed_fields(self, target, job: dict):
        """Fill form fields on the current Indeed application step."""
        # Text inputs
        text_inputs = await target.query_selector_all(
            'input[type="text"], input[type="email"], input[type="tel"], '
            'input[type="number"], input:not([type])'
        )

        for field in text_inputs:
            try:
                current = await field.get_attribute("value")
                if current and current.strip():
                    continue

                label_text = ""
                field_id = await field.get_attribute("id")
                name = await field.get_attribute("name") or ""
                aria_label = await field.get_attribute("aria-label") or ""

                if field_id:
                    label_el = await target.query_selector(f'label[for="{field_id}"]')
                    label_text = (await label_el.inner_text()).strip() if label_el else ""

                label_text = label_text or aria_label or name

                if label_text:
                    answer = self.ai.answer_form_question(
                        question=label_text,
                        field_type="text",
                        job_title=job.get("title", ""),
                        company=job.get("company", ""),
                    )
                    if answer:
                        await field.fill(answer)
                        await self.browser.random_delay(200, 500)

            except Exception as e:
                self.logger.debug(f"Error filling Indeed field: {e}")

        # Handle resume upload
        file_input = await target.query_selector('input[type="file"]')
        if file_input:
            resume_path = self.config.get("documents", {}).get("resume_path", "")
            if resume_path:
                try:
                    await file_input.set_input_files(resume_path)
                    await self.browser.random_delay(1000, 2000)
                except Exception as e:
                    self.logger.debug(f"Resume upload failed: {e}")

        # Handle select fields
        selects = await target.query_selector_all("select")
        for select in selects:
            try:
                options = await select.query_selector_all("option")
                opt_texts = []
                for opt in options:
                    text = (await opt.inner_text()).strip()
                    val = await opt.get_attribute("value")
                    if val and text and text not in ["", "Select", "Choose"]:
                        opt_texts.append(text)

                select_id = await select.get_attribute("id")
                label_el = await target.query_selector(f'label[for="{select_id}"]') if select_id else None
                label_text = (await label_el.inner_text()).strip() if label_el else ""

                if label_text and opt_texts:
                    answer = self.ai.answer_form_question(
                        question=label_text,
                        field_type="select",
                        options=opt_texts,
                        job_title=job.get("title", ""),
                        company=job.get("company", ""),
                    )
                    if answer:
                        await select.select_option(label=answer)
                        await self.browser.random_delay(200, 500)
            except Exception as e:
                self.logger.debug(f"Error filling Indeed select: {e}")

    async def _dismiss_popups(self):
        """Dismiss common Indeed popups and overlays."""
        page = self.browser.page
        popup_selectors = [
            'button[aria-label="Close"]',
            'button:has-text("No thanks")',
            'button:has-text("Not now")',
            '#onetrust-accept-btn-handler',
            'button[id*="close"]',
        ]
        for sel in popup_selectors:
            try:
                btn = await page.query_selector(sel)
                if btn and await btn.is_visible():
                    await btn.click()
                    await self.browser.random_delay(300, 600)
            except Exception:
                pass
