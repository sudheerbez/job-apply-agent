"""
LinkedIn automation - handles login, job search, Easy Apply, and standard apply.
"""

import asyncio
import re
from urllib.parse import quote_plus
from playwright.async_api import Page, TimeoutError as PlaywrightTimeout
from platforms.base import BasePlatform


class LinkedInPlatform(BasePlatform):
    """Automates job applications on LinkedIn."""

    PLATFORM_NAME = "linkedin"
    BASE_URL = "https://www.linkedin.com"
    LOGIN_URL = "https://www.linkedin.com/login"
    JOBS_URL = "https://www.linkedin.com/jobs/search/"

    # Experience level mapping to LinkedIn filter values
    EXP_LEVEL_MAP = {
        "internship": "1",
        "entry_level": "2",
        "associate": "3",
        "mid_senior": "4",
        "director": "5",
        "executive": "6",
    }

    # Job type mapping
    JOB_TYPE_MAP = {
        "full_time": "F",
        "part_time": "P",
        "contract": "C",
        "temporary": "T",
        "internship": "I",
        "volunteer": "V",
    }

    # Date posted mapping
    DATE_POSTED_MAP = {
        "past_24h": "r86400",
        "past_week": "r604800",
        "past_month": "r2592000",
        "any_time": "",
    }

    async def login(self):
        """Log in to LinkedIn."""
        page = self.browser.page
        creds = self.config.get("platforms", {}).get("linkedin", {})
        email = creds.get("email", "")
        password = creds.get("password", "")

        if not email or not password:
            raise ValueError(
                "LinkedIn credentials not configured. "
                "Set them in config.yaml or via LINKEDIN_EMAIL/LINKEDIN_PASSWORD env vars."
            )

        self.logger.info("Logging in to LinkedIn...")
        await page.goto(self.LOGIN_URL, wait_until="networkidle")
        await self.browser.random_delay()

        await self.browser.human_type("#username", email)
        await self.browser.random_delay(300, 700)
        await self.browser.human_type("#password", password)
        await self.browser.random_delay(500, 1000)

        await page.click('button[type="submit"]')
        await page.wait_for_load_state("networkidle")
        await self.browser.random_delay(2000, 4000)

        # Check for security checkpoint
        if "checkpoint" in page.url or "challenge" in page.url:
            self.logger.warning(
                "LinkedIn security checkpoint detected. "
                "Please complete the verification manually in the browser window."
            )
            # Wait up to 120 seconds for user to solve CAPTCHA/verification
            for _ in range(60):
                await asyncio.sleep(2)
                if "feed" in page.url or "jobs" in page.url:
                    break
            else:
                raise Exception("LinkedIn login checkpoint not resolved within 2 minutes")

        # Verify login
        if "login" in page.url:
            await self.browser.screenshot("linkedin_login_failed")
            raise Exception("LinkedIn login failed - still on login page")

        self.logger.info("LinkedIn login successful")

    async def search_jobs(self, keyword: str, location: str) -> list:
        """Search for jobs on LinkedIn and return job listings."""
        page = self.browser.page
        jobs = []

        # Build search URL with filters
        params = {
            "keywords": keyword,
            "location": location,
        }

        # Experience level filter
        exp_levels = self.search_config.get("experience_levels", [])
        if exp_levels:
            f_e = ",".join(
                self.EXP_LEVEL_MAP[lvl]
                for lvl in exp_levels
                if lvl in self.EXP_LEVEL_MAP
            )
            if f_e:
                params["f_E"] = f_e

        # Job type filter
        job_types = self.search_config.get("job_types", [])
        if job_types:
            f_jt = ",".join(
                self.JOB_TYPE_MAP[jt]
                for jt in job_types
                if jt in self.JOB_TYPE_MAP
            )
            if f_jt:
                params["f_JT"] = f_jt

        # Date posted filter
        date_posted = self.search_config.get("date_posted", "past_week")
        f_tpr = self.DATE_POSTED_MAP.get(date_posted, "")
        if f_tpr:
            params["f_TPR"] = f_tpr

        # Easy Apply filter (prefer Easy Apply for automation)
        params["f_AL"] = "true"

        query_string = "&".join(f"{k}={quote_plus(str(v))}" for k, v in params.items())
        search_url = f"{self.JOBS_URL}?{query_string}"

        self.logger.info(f"Navigating to search: {search_url}")
        await page.goto(search_url, wait_until="networkidle")
        await self.browser.random_delay(2000, 4000)

        # Paginate through results (up to 5 pages)
        for page_num in range(5):
            await self.browser.random_delay(1000, 2000)

            # Extract job cards from the sidebar list
            job_cards = await page.query_selector_all(
                ".jobs-search-results__list-item, .job-card-container"
            )

            if not job_cards:
                self.logger.info(f"No job cards found on page {page_num + 1}")
                break

            for card in job_cards:
                try:
                    title_el = await card.query_selector(
                        ".job-card-list__title, .job-card-container__link"
                    )
                    company_el = await card.query_selector(
                        ".job-card-container__primary-description, "
                        ".job-card-container__company-name"
                    )
                    location_el = await card.query_selector(
                        ".job-card-container__metadata-item, "
                        ".job-card-container__metadata-wrapper"
                    )

                    title = (await title_el.inner_text()).strip() if title_el else ""
                    company = (await company_el.inner_text()).strip() if company_el else ""
                    loc = (await location_el.inner_text()).strip() if location_el else ""

                    # Get job URL from card link
                    link_el = await card.query_selector("a[href*='/jobs/view/']")
                    href = await link_el.get_attribute("href") if link_el else ""
                    job_url = href.split("?")[0] if href else ""
                    if job_url and not job_url.startswith("http"):
                        job_url = f"{self.BASE_URL}{job_url}"

                    if title and job_url:
                        jobs.append(
                            {
                                "title": title,
                                "company": company,
                                "location": loc,
                                "url": job_url,
                                "platform": "linkedin",
                            }
                        )
                except Exception as e:
                    self.logger.debug(f"Error parsing job card: {e}")
                    continue

            # Check for enough jobs
            if len(jobs) >= self.max_applications:
                break

            # Try to go to next page
            try:
                next_btn = await page.query_selector(
                    f'button[aria-label="Page {page_num + 2}"]'
                )
                if next_btn:
                    await next_btn.click()
                    await page.wait_for_load_state("networkidle")
                    await self.browser.random_delay(2000, 3000)
                else:
                    break
            except Exception:
                break

        self.logger.info(f"Found {len(jobs)} LinkedIn jobs for '{keyword}' in '{location}'")
        return jobs

    async def apply_to_job(self, job: dict) -> bool:
        """Apply to a LinkedIn job using Easy Apply."""
        page = self.browser.page
        job_url = job.get("url", "")

        self.logger.info(f"Applying to: {job.get('title')} at {job.get('company')}")

        # Navigate to job page
        await page.goto(job_url, wait_until="networkidle")
        await self.browser.random_delay(1500, 3000)

        # Look for Easy Apply button
        easy_apply_btn = await page.query_selector(
            'button.jobs-apply-button, '
            'button[aria-label*="Easy Apply"], '
            'button:has-text("Easy Apply")'
        )

        if not easy_apply_btn:
            self.logger.info(f"No Easy Apply button found for {job.get('title')}")
            self.tracker.log_application(
                platform=self.PLATFORM_NAME,
                company=job.get("company", ""),
                job_title=job.get("title", ""),
                job_url=job_url,
                status="skipped",
                error_message="No Easy Apply button",
            )
            return False

        await easy_apply_btn.click()
        await self.browser.random_delay(1500, 2500)

        # Process the Easy Apply modal steps
        return await self._process_easy_apply_modal(job)

    async def _process_easy_apply_modal(self, job: dict) -> bool:
        """Navigate through the Easy Apply multi-step modal."""
        page = self.browser.page
        max_steps = 10

        for step in range(max_steps):
            await self.browser.random_delay(1000, 2000)

            # Check if we reached the review/submit page
            submit_btn = await page.query_selector(
                'button[aria-label="Submit application"], '
                'button:has-text("Submit application")'
            )

            if submit_btn:
                self.logger.info("Reached submit page - submitting application")
                await self.browser.random_delay(500, 1000)
                await submit_btn.click()
                await self.browser.random_delay(2000, 3000)

                # Check for success
                success_modal = await page.query_selector(
                    'div:has-text("Application sent"), '
                    'h2:has-text("Application sent"), '
                    'div[class*="artdeco-modal"]:has-text("sent")'
                )

                if success_modal:
                    self.logger.info("Application submitted successfully!")
                    # Dismiss success modal
                    dismiss_btn = await page.query_selector(
                        'button[aria-label="Dismiss"], '
                        'button:has-text("Done")'
                    )
                    if dismiss_btn:
                        await dismiss_btn.click()
                    return True
                else:
                    # Even without explicit success confirmation, 
                    # if we clicked submit, assume success
                    return True

            # Fill form fields on current step
            await self._fill_easy_apply_fields(job)

            # Look for Next/Review/Continue button
            next_btn = await page.query_selector(
                'button[aria-label="Continue to next step"], '
                'button[aria-label="Review your application"], '
                'button:has-text("Next"), '
                'button:has-text("Review"), '
                'button:has-text("Continue")'
            )

            if next_btn:
                await self.browser.random_delay(300, 700)
                await next_btn.click()
                await self.browser.random_delay(1000, 2000)
            else:
                # No next or submit button found - might be stuck
                self.logger.warning(f"No next/submit button found at step {step + 1}")
                await self.browser.screenshot(f"linkedin_stuck_step_{step}")
                
                # Try to close the modal and move on
                close_btn = await page.query_selector(
                    'button[aria-label="Dismiss"], '
                    'button[data-test-modal-close-btn]'
                )
                if close_btn:
                    await close_btn.click()
                    # Confirm discard if prompted
                    discard_btn = await page.query_selector(
                        'button[data-test-dialog-primary-btn], '
                        'button:has-text("Discard")'
                    )
                    if discard_btn:
                        await discard_btn.click()
                return False

        self.logger.warning("Exceeded max steps in Easy Apply modal")
        return False

    async def _fill_easy_apply_fields(self, job: dict):
        """Fill out form fields on the current Easy Apply step."""
        page = self.browser.page

        # Handle resume upload
        resume_input = await page.query_selector('input[type="file"]')
        if resume_input:
            resume_path = self.config.get("documents", {}).get("resume_path", "")
            if resume_path:
                try:
                    await resume_input.set_input_files(resume_path)
                    self.logger.debug("Resume uploaded")
                    await self.browser.random_delay(1000, 2000)
                except Exception as e:
                    self.logger.debug(f"Resume upload failed: {e}")

        # Handle text input fields
        text_inputs = await page.query_selector_all(
            '.jobs-easy-apply-form-section__grouping input[type="text"], '
            '.jobs-easy-apply-form-section__grouping input:not([type]), '
            'input[id*="single-line-text"], '
            'input[id*="numeric"]'
        )

        for field in text_inputs:
            try:
                # Check if field is already filled
                current_value = await field.get_attribute("value")
                if current_value and current_value.strip():
                    continue

                # Get the label
                field_id = await field.get_attribute("id")
                label_el = await page.query_selector(f'label[for="{field_id}"]') if field_id else None
                label_text = (await label_el.inner_text()).strip() if label_el else ""

                if not label_text:
                    # Try to find label from parent
                    parent = await field.query_selector("xpath=ancestor::div[contains(@class, 'grouping')]")
                    if parent:
                        label_el = await parent.query_selector("label, span.t-bold")
                        label_text = (await label_el.inner_text()).strip() if label_el else ""

                if label_text:
                    answer = self._get_profile_answer(label_text)
                    if not answer:
                        answer = self.ai.answer_form_question(
                            question=label_text,
                            field_type="text",
                            job_title=job.get("title", ""),
                            company=job.get("company", ""),
                        )
                    if answer:
                        await field.click()
                        await self.browser.random_delay(200, 400)
                        await field.fill(answer)
                        await self.browser.random_delay(200, 500)

            except Exception as e:
                self.logger.debug(f"Error filling text field: {e}")

        # Handle textarea fields
        textareas = await page.query_selector_all(
            '.jobs-easy-apply-form-section__grouping textarea'
        )

        for textarea in textareas:
            try:
                current_value = await textarea.input_value()
                if current_value and current_value.strip():
                    continue

                label_text = ""
                textarea_id = await textarea.get_attribute("id")
                if textarea_id:
                    label_el = await page.query_selector(f'label[for="{textarea_id}"]')
                    label_text = (await label_el.inner_text()).strip() if label_el else ""

                if label_text:
                    answer = self.ai.answer_form_question(
                        question=label_text,
                        field_type="textarea",
                        job_title=job.get("title", ""),
                        company=job.get("company", ""),
                    )
                    if answer:
                        await textarea.fill(answer)
                        await self.browser.random_delay(300, 700)
            except Exception as e:
                self.logger.debug(f"Error filling textarea: {e}")

        # Handle select/dropdown fields
        selects = await page.query_selector_all(
            '.jobs-easy-apply-form-section__grouping select'
        )

        for select in selects:
            try:
                select_id = await select.get_attribute("id")
                label_el = await page.query_selector(f'label[for="{select_id}"]') if select_id else None
                label_text = (await label_el.inner_text()).strip() if label_el else ""

                # Get options
                option_els = await select.query_selector_all("option")
                options = []
                for opt in option_els:
                    val = await opt.get_attribute("value")
                    text = (await opt.inner_text()).strip()
                    if val and text and text != "Select an option":
                        options.append(text)

                if label_text and options:
                    answer = self._get_profile_answer(label_text, options)
                    if not answer:
                        answer = self.ai.answer_form_question(
                            question=label_text,
                            field_type="select",
                            options=options,
                            job_title=job.get("title", ""),
                            company=job.get("company", ""),
                        )
                    if answer:
                        await select.select_option(label=answer)
                        await self.browser.random_delay(300, 600)

            except Exception as e:
                self.logger.debug(f"Error filling select: {e}")

        # Handle radio buttons
        radio_groups = await page.query_selector_all(
            '.jobs-easy-apply-form-section__grouping fieldset'
        )

        for group in radio_groups:
            try:
                legend = await group.query_selector("legend, span.t-bold")
                question_text = (await legend.inner_text()).strip() if legend else ""

                radio_labels = await group.query_selector_all("label")
                options = []
                for lbl in radio_labels:
                    text = (await lbl.inner_text()).strip()
                    if text:
                        options.append(text)

                if question_text and options:
                    answer = self._get_profile_answer(question_text, options)
                    if not answer:
                        answer = self.ai.answer_form_question(
                            question=question_text,
                            field_type="radio",
                            options=options,
                            job_title=job.get("title", ""),
                            company=job.get("company", ""),
                        )
                    if answer:
                        for lbl in radio_labels:
                            lbl_text = (await lbl.inner_text()).strip()
                            if lbl_text.lower() == answer.lower():
                                await lbl.click()
                                await self.browser.random_delay(200, 500)
                                break

            except Exception as e:
                self.logger.debug(f"Error filling radio group: {e}")

    def _get_profile_answer(self, question: str, options: list = None) -> str:
        """
        Try to answer common form questions directly from config profile 
        before falling back to AI.
        """
        q = question.lower().strip()
        p = self.profile
        wa = p.get("work_authorization", {})

        # Direct mappings for common questions
        mappings = {
            "first name": p.get("first_name", ""),
            "last name": p.get("last_name", ""),
            "email": p.get("email", ""),
            "phone": p.get("phone", ""),
            "city": p.get("location", "").split(",")[0].strip() if p.get("location") else "",
            "linkedin": p.get("linkedin_url", ""),
            "github": p.get("github_url", ""),
            "website": p.get("portfolio_url", ""),
            "years of experience": str(p.get("years_of_experience", "")),
        }

        for keyword, value in mappings.items():
            if keyword in q and value:
                return value

        # Work authorization questions
        if any(kw in q for kw in ["authorized", "authorization", "legally", "right to work"]):
            authorized = wa.get("authorized_us", True)
            if options:
                yes_options = [o for o in options if o.lower() in ["yes", "true"]]
                no_options = [o for o in options if o.lower() in ["no", "false"]]
                if authorized and yes_options:
                    return yes_options[0]
                elif not authorized and no_options:
                    return no_options[0]
            return "Yes" if authorized else "No"

        if any(kw in q for kw in ["sponsorship", "visa", "sponsor"]):
            needs = wa.get("require_sponsorship", False)
            if options:
                yes_options = [o for o in options if o.lower() in ["yes", "true"]]
                no_options = [o for o in options if o.lower() in ["no", "false"]]
                if needs and yes_options:
                    return yes_options[0]
                elif not needs and no_options:
                    return no_options[0]
            return "Yes" if needs else "No"

        # GPA
        if "gpa" in q or "grade point" in q:
            edu = p.get("education", [{}])
            if edu:
                return edu[0].get("gpa", "")

        return ""
