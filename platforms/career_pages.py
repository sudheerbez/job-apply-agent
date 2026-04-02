"""
Career Pages automation - handles applications on Greenhouse, Lever, Workday, and other ATS.
"""

import asyncio
import re
from pathlib import Path
from urllib.parse import urlparse
from playwright.async_api import Page, TimeoutError as PlaywrightTimeout
from platforms.base import BasePlatform


class CareerPagesPlatform(BasePlatform):
    """Automates job applications on company career pages (Greenhouse, Lever, Workday, etc.)."""

    PLATFORM_NAME = "career_pages"

    # ATS detection patterns
    ATS_PATTERNS = {
        "greenhouse": [
            r"boards\.greenhouse\.io",
            r"job-boards\.greenhouse\.io",
            r"greenhouse\.io/embed",
        ],
        "lever": [
            r"jobs\.lever\.co",
            r"lever\.co/",
        ],
        "workday": [
            r"myworkdayjobs\.com",
            r"\.wd\d+\.myworkdayjobs",
            r"workday\.com",
        ],
        "ashby": [
            r"jobs\.ashbyhq\.com",
            r"ashbyhq\.com",
        ],
        "icims": [
            r"careers-.*\.icims\.com",
            r"icims\.com",
        ],
    }

    def __init__(self, browser, config, tracker, ai_helper, job_urls: list = None):
        super().__init__(browser, config, tracker, ai_helper)
        self.job_urls = job_urls or []

    async def login(self):
        """No login needed for career pages - each page is independent."""
        self.logger.info("Career pages module ready (no login required)")

    async def search_jobs(self, keyword: str = "", location: str = "") -> list:
        """Return pre-configured job URLs as job dicts."""
        return [
            {
                "title": "Direct Application",
                "company": urlparse(url).netloc,
                "location": "",
                "url": url,
                "platform": "career_pages",
            }
            for url in self.job_urls
        ]

    async def apply_to_job(self, job: dict) -> bool:
        """Apply to a job based on the detected ATS type."""
        page = self.browser.page
        job_url = job.get("url", "")

        self.logger.info(f"Applying via career page: {job_url}")

        await page.goto(job_url, wait_until="networkidle")
        await self.browser.random_delay(2000, 4000)

        # Detect ATS type
        ats_type = self._detect_ats(job_url, page.url)
        self.logger.info(f"Detected ATS: {ats_type}")

        # Extract job details from the page
        job_title = await self._extract_job_title(page)
        company = await self._extract_company(page)
        job["title"] = job_title or job.get("title", "")
        job["company"] = company or job.get("company", "")

        # Route to appropriate handler
        handlers = {
            "greenhouse": self._apply_greenhouse,
            "lever": self._apply_lever,
            "workday": self._apply_workday,
            "ashby": self._apply_ashby,
            "generic": self._apply_generic,
        }

        handler = handlers.get(ats_type, self._apply_generic)
        return await handler(job)

    def _detect_ats(self, original_url: str, current_url: str) -> str:
        """Detect which ATS is being used based on URL patterns."""
        for url in [original_url, current_url]:
            for ats_name, patterns in self.ATS_PATTERNS.items():
                for pattern in patterns:
                    if re.search(pattern, url, re.IGNORECASE):
                        return ats_name
        return "generic"

    async def _extract_job_title(self, page: Page) -> str:
        """Try to extract the job title from the page."""
        selectors = [
            'h1[class*="title"], h1[class*="job"]',
            ".posting-headline h2",
            'h1[data-qa="job-title"]',
            "h1.app-title",
            "h1",
        ]
        for sel in selectors:
            try:
                el = await page.query_selector(sel)
                if el:
                    text = (await el.inner_text()).strip()
                    if text and len(text) < 200:
                        return text
            except Exception:
                continue
        return ""

    async def _extract_company(self, page: Page) -> str:
        """Try to extract the company name from the page."""
        selectors = [
            'span[class*="company"], div[class*="company"]',
            ".posting-categories .sort-by-team",
            'a[data-qa="company-name"]',
            'meta[property="og:site_name"]',
        ]
        for sel in selectors:
            try:
                el = await page.query_selector(sel)
                if el:
                    if sel.startswith("meta"):
                        return (await el.get_attribute("content")) or ""
                    text = (await el.inner_text()).strip()
                    if text and len(text) < 100:
                        return text
            except Exception:
                continue
        return ""

    # ============================================================
    # Greenhouse Handler
    # ============================================================

    async def _apply_greenhouse(self, job: dict) -> bool:
        """Handle Greenhouse job applications."""
        page = self.browser.page

        # Click Apply button if on listing page
        apply_btn = await page.query_selector(
            'a[href*="#app"], a:has-text("Apply"), '
            'button:has-text("Apply for this job"), '
            'a.postings-btn'
        )
        if apply_btn:
            await apply_btn.click()
            await self.browser.random_delay(1500, 2500)

        # Fill standard Greenhouse fields
        field_map = {
            "#first_name": self.profile.get("first_name", ""),
            "#last_name": self.profile.get("last_name", ""),
            "#email": self.profile.get("email", ""),
            "#phone": self.profile.get("phone", ""),
        }

        for selector, value in field_map.items():
            try:
                field = await page.query_selector(selector)
                if field and value:
                    await field.fill(value)
                    await self.browser.random_delay(200, 500)
            except Exception:
                pass

        # Upload resume
        resume_input = await page.query_selector(
            'input[type="file"][id*="resume"], '
            'input[type="file"][name*="resume"], '
            'input[type="file"]'
        )
        if resume_input:
            resume_path = self.config.get("documents", {}).get("resume_path", "")
            if resume_path and Path(resume_path).exists():
                await resume_input.set_input_files(resume_path)
                await self.browser.random_delay(1000, 2000)

        # Fill additional fields using AI
        await self._fill_generic_fields(page, job)

        # Handle custom questions (Greenhouse uses specific patterns)
        custom_fields = await page.query_selector_all(
            '.field, [class*="custom-question"], .application-field'
        )
        for field_group in custom_fields:
            await self._fill_field_group(field_group, job)

        # Submit
        submit_btn = await page.query_selector(
            'input[type="submit"], button[type="submit"], '
            'button:has-text("Submit Application"), '
            '#submit_app'
        )
        if submit_btn:
            await self.browser.random_delay(500, 1000)
            await submit_btn.click()
            await self.browser.random_delay(3000, 5000)

            # Check for success
            success = await page.query_selector(
                ':has-text("Application submitted"), '
                ':has-text("Thank you for applying"), '
                ':has-text("Thanks for applying")'
            )
            if success:
                self.logger.info("Greenhouse application submitted!")
                return True

        return False

    # ============================================================
    # Lever Handler
    # ============================================================

    async def _apply_lever(self, job: dict) -> bool:
        """Handle Lever job applications."""
        page = self.browser.page

        # Click Apply button
        apply_btn = await page.query_selector(
            'a.postings-btn[href*="apply"], '
            'a:has-text("Apply for this job"), '
            '.posting-btn-submit'
        )
        if apply_btn:
            await apply_btn.click()
            await self.browser.random_delay(1500, 2500)

        # Fill Lever's standard fields
        field_map = {
            'input[name="name"]': f"{self.profile.get('first_name', '')} {self.profile.get('last_name', '')}",
            'input[name="email"]': self.profile.get("email", ""),
            'input[name="phone"]': self.profile.get("phone", ""),
            'input[name="org"]': "",  # Current company
            'input[name="urls[LinkedIn]"]': self.profile.get("linkedin_url", ""),
            'input[name="urls[GitHub]"]': self.profile.get("github_url", ""),
            'input[name="urls[Portfolio]"]': self.profile.get("portfolio_url", ""),
        }

        for selector, value in field_map.items():
            try:
                field = await page.query_selector(selector)
                if field and value:
                    await field.fill(value)
                    await self.browser.random_delay(200, 400)
            except Exception:
                pass

        # Upload resume
        resume_input = await page.query_selector(
            'input[type="file"][name="resume"],'
            'input[type="file"]'
        )
        if resume_input:
            resume_path = self.config.get("documents", {}).get("resume_path", "")
            if resume_path and Path(resume_path).exists():
                await resume_input.set_input_files(resume_path)
                await self.browser.random_delay(1000, 2000)

        # Fill custom questions
        await self._fill_generic_fields(page, job)

        # Submit
        submit_btn = await page.query_selector(
            'button[type="submit"], '
            'button:has-text("Submit application"), '
            'input[type="submit"]'
        )
        if submit_btn:
            await self.browser.random_delay(500, 1000)
            await submit_btn.click()
            await self.browser.random_delay(3000, 5000)

            success = await page.query_selector(
                ':has-text("Application submitted"), '
                ':has-text("Thanks for applying"), '
                '.application-confirmation'
            )
            if success:
                self.logger.info("Lever application submitted!")
                return True

        return False

    # ============================================================
    # Workday Handler
    # ============================================================

    async def _apply_workday(self, job: dict) -> bool:
        """Handle Workday job applications."""
        page = self.browser.page

        # Workday has a complex multi-step process
        # Click Apply button
        apply_btn = await page.query_selector(
            'a[data-automation-id="jobPostingApplyButton"], '
            'button[data-automation-id="applyButton"], '
            'a:has-text("Apply"), button:has-text("Apply")'
        )
        if apply_btn:
            await apply_btn.click()
            await self.browser.random_delay(2000, 4000)

        # Workday may require account creation - handle "Create Account" vs "Sign In"
        create_btn = await page.query_selector(
            'button:has-text("Create Account"), '
            'a:has-text("Create Account")'
        )
        if create_btn:
            self.logger.info("Workday requires account creation - filling registration")
            await create_btn.click()
            await self.browser.random_delay(1500, 2500)

            # Fill registration
            email_input = await page.query_selector(
                'input[data-automation-id="email"], input[type="email"]'
            )
            if email_input:
                await email_input.fill(self.profile.get("email", ""))

            pw_input = await page.query_selector(
                'input[data-automation-id="password"], input[type="password"]'
            )
            if pw_input:
                # Use a generated password or configured one
                await pw_input.fill("TempPass123!")

        # Process application steps
        max_steps = 15
        for step in range(max_steps):
            await self.browser.random_delay(1500, 2500)

            # Fill fields on current page
            await self._fill_generic_fields(page, job)

            # Upload resume if file input present
            resume_input = await page.query_selector('input[type="file"]')
            if resume_input:
                resume_path = self.config.get("documents", {}).get("resume_path", "")
                if resume_path and Path(resume_path).exists():
                    try:
                        await resume_input.set_input_files(resume_path)
                        await self.browser.random_delay(1500, 2500)
                    except Exception:
                        pass

            # Check for submit
            submit_btn = await page.query_selector(
                'button[data-automation-id="submitButton"], '
                'button:has-text("Submit"), '
                'button[data-automation-id="bottom-navigation-next-button"]:has-text("Submit")'
            )
            if submit_btn:
                btn_text = (await submit_btn.inner_text()).strip().lower()
                if "submit" in btn_text:
                    await submit_btn.click()
                    await self.browser.random_delay(3000, 5000)
                    self.logger.info("Workday application submitted!")
                    return True

            # Click Next/Continue
            next_btn = await page.query_selector(
                'button[data-automation-id="bottom-navigation-next-button"], '
                'button:has-text("Next"), button:has-text("Continue"), '
                'button:has-text("Save and Continue")'
            )
            if next_btn:
                await next_btn.click()
                await self.browser.random_delay(2000, 3000)
            else:
                break

        return False

    # ============================================================
    # Ashby Handler
    # ============================================================

    async def _apply_ashby(self, job: dict) -> bool:
        """Handle Ashby job applications."""
        page = self.browser.page

        apply_btn = await page.query_selector(
            'a:has-text("Apply"), button:has-text("Apply")'
        )
        if apply_btn:
            await apply_btn.click()
            await self.browser.random_delay(1500, 2500)

        # Fill standard fields
        await self._fill_generic_fields(page, job)

        # Upload resume
        resume_input = await page.query_selector('input[type="file"]')
        if resume_input:
            resume_path = self.config.get("documents", {}).get("resume_path", "")
            if resume_path and Path(resume_path).exists():
                await resume_input.set_input_files(resume_path)
                await self.browser.random_delay(1000, 2000)

        # Submit
        submit_btn = await page.query_selector(
            'button[type="submit"], button:has-text("Submit")'
        )
        if submit_btn:
            await submit_btn.click()
            await self.browser.random_delay(3000, 5000)
            return True

        return False

    # ============================================================
    # Generic Handler (fallback)
    # ============================================================

    async def _apply_generic(self, job: dict) -> bool:
        """Generic application handler for unrecognized ATS platforms."""
        page = self.browser.page

        # Try to find and click an Apply button
        apply_selectors = [
            'a:has-text("Apply")',
            'button:has-text("Apply")',
            'a[href*="apply"]',
            'input[type="submit"][value*="Apply"]',
        ]

        for sel in apply_selectors:
            try:
                btn = await page.query_selector(sel)
                if btn and await btn.is_visible():
                    await btn.click()
                    await self.browser.random_delay(2000, 3000)
                    break
            except Exception:
                continue

        # Fill all form fields
        await self._fill_generic_fields(page, job)

        # Upload resume
        resume_input = await page.query_selector('input[type="file"]')
        if resume_input:
            resume_path = self.config.get("documents", {}).get("resume_path", "")
            if resume_path and Path(resume_path).exists():
                try:
                    await resume_input.set_input_files(resume_path)
                    await self.browser.random_delay(1000, 2000)
                except Exception:
                    pass

        # Submit
        submit_selectors = [
            'button[type="submit"]',
            'input[type="submit"]',
            'button:has-text("Submit")',
            'button:has-text("Apply")',
        ]

        for sel in submit_selectors:
            try:
                btn = await page.query_selector(sel)
                if btn and await btn.is_visible():
                    await btn.click()
                    await self.browser.random_delay(3000, 5000)
                    return True
            except Exception:
                continue

        return False

    # ============================================================
    # Shared Helpers
    # ============================================================

    async def _fill_generic_fields(self, page: Page, job: dict):
        """Fill form fields generically using label detection + AI."""
        # Text inputs
        text_inputs = await page.query_selector_all(
            'input[type="text"], input[type="email"], input[type="tel"], '
            'input[type="number"], input[type="url"], input:not([type="hidden"]):not([type="file"]):not([type="submit"]):not([type="checkbox"]):not([type="radio"])'
        )

        for field in text_inputs:
            try:
                if not await field.is_visible():
                    continue
                current = await field.get_attribute("value")
                if current and current.strip():
                    continue

                label_text = await self._get_field_label(page, field)
                if not label_text:
                    continue

                # Try profile mapping first
                answer = self._map_profile_field(label_text)
                if not answer:
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
                self.logger.debug(f"Error filling field: {e}")

        # Textareas
        textareas = await page.query_selector_all("textarea")
        for ta in textareas:
            try:
                if not await ta.is_visible():
                    continue
                current = await ta.input_value()
                if current and current.strip():
                    continue

                label_text = await self._get_field_label(page, ta)
                if label_text:
                    answer = self.ai.answer_form_question(
                        question=label_text,
                        field_type="textarea",
                        job_title=job.get("title", ""),
                        company=job.get("company", ""),
                    )
                    if answer:
                        await ta.fill(answer)
                        await self.browser.random_delay(300, 700)
            except Exception as e:
                self.logger.debug(f"Error filling textarea: {e}")

        # Select fields
        selects = await page.query_selector_all("select")
        for select in selects:
            try:
                if not await select.is_visible():
                    continue

                label_text = await self._get_field_label(page, select)
                options = await select.query_selector_all("option")
                opt_texts = []
                for opt in options:
                    text = (await opt.inner_text()).strip()
                    val = await opt.get_attribute("value")
                    if val and text and text.lower() not in ["", "select", "choose", "-- select --"]:
                        opt_texts.append(text)

                if label_text and opt_texts:
                    answer = self.ai.answer_form_question(
                        question=label_text,
                        field_type="select",
                        options=opt_texts,
                        job_title=job.get("title", ""),
                        company=job.get("company", ""),
                    )
                    if answer:
                        try:
                            await select.select_option(label=answer)
                        except Exception:
                            # Try matching partially
                            for opt_text in opt_texts:
                                if answer.lower() in opt_text.lower():
                                    await select.select_option(label=opt_text)
                                    break
                        await self.browser.random_delay(200, 500)
            except Exception as e:
                self.logger.debug(f"Error filling select: {e}")

    async def _fill_field_group(self, group, job: dict):
        """Fill a field group (Greenhouse custom questions)."""
        page = self.browser.page
        try:
            label_el = await group.query_selector("label")
            label_text = (await label_el.inner_text()).strip() if label_el else ""
            if not label_text:
                return

            # Text input
            input_el = await group.query_selector("input[type='text'], input:not([type])")
            if input_el:
                answer = self.ai.answer_form_question(
                    question=label_text,
                    field_type="text",
                    job_title=job.get("title", ""),
                    company=job.get("company", ""),
                )
                if answer:
                    await input_el.fill(answer)
                return

            # Textarea
            ta_el = await group.query_selector("textarea")
            if ta_el:
                answer = self.ai.answer_form_question(
                    question=label_text,
                    field_type="textarea",
                    job_title=job.get("title", ""),
                    company=job.get("company", ""),
                )
                if answer:
                    await ta_el.fill(answer)
                return

            # Select
            sel_el = await group.query_selector("select")
            if sel_el:
                options = await sel_el.query_selector_all("option")
                opt_texts = [(await o.inner_text()).strip() for o in options]
                opt_texts = [t for t in opt_texts if t and t.lower() not in ["", "select"]]
                answer = self.ai.answer_form_question(
                    question=label_text,
                    field_type="select",
                    options=opt_texts,
                    job_title=job.get("title", ""),
                    company=job.get("company", ""),
                )
                if answer:
                    try:
                        await sel_el.select_option(label=answer)
                    except Exception:
                        pass

        except Exception as e:
            self.logger.debug(f"Error filling field group: {e}")

    async def _get_field_label(self, page: Page, element) -> str:
        """Get the label text for a form element."""
        try:
            # Try label[for] attribute
            el_id = await element.get_attribute("id")
            if el_id:
                label = await page.query_selector(f'label[for="{el_id}"]')
                if label:
                    return (await label.inner_text()).strip()

            # Try aria-label
            aria = await element.get_attribute("aria-label")
            if aria:
                return aria

            # Try placeholder
            placeholder = await element.get_attribute("placeholder")
            if placeholder:
                return placeholder

            # Try name attribute
            name = await element.get_attribute("name")
            if name:
                return name.replace("_", " ").replace("-", " ").title()

            # Try parent label
            parent = await element.query_selector("xpath=ancestor::label")
            if parent:
                return (await parent.inner_text()).strip()

        except Exception:
            pass
        return ""

    def _map_profile_field(self, label: str) -> str:
        """Map common field labels to profile values."""
        l = label.lower()
        p = self.profile

        mappings = {
            "first name": p.get("first_name", ""),
            "last name": p.get("last_name", ""),
            "full name": f"{p.get('first_name', '')} {p.get('last_name', '')}",
            "name": f"{p.get('first_name', '')} {p.get('last_name', '')}",
            "email": p.get("email", ""),
            "phone": p.get("phone", ""),
            "linkedin": p.get("linkedin_url", ""),
            "github": p.get("github_url", ""),
            "portfolio": p.get("portfolio_url", ""),
            "website": p.get("portfolio_url", ""),
            "location": p.get("location", ""),
            "city": p.get("location", "").split(",")[0].strip() if p.get("location") else "",
        }

        for key, val in mappings.items():
            if key in l and val:
                return val
        return ""

    async def run_for_urls(self, urls: list):
        """Apply to a specific list of URLs."""
        self.job_urls = urls
        jobs = await self.search_jobs()

        for job in jobs:
            if self._applied_count >= self.max_applications:
                break

            if self.tracker.is_already_applied(job["url"]):
                self.tracker.log_application(
                    platform=self.PLATFORM_NAME,
                    company=job.get("company", ""),
                    job_title=job.get("title", ""),
                    job_url=job.get("url", ""),
                    status="duplicate",
                )
                continue

            try:
                success = await self.apply_to_job(job)
                self.tracker.log_application(
                    platform=self.PLATFORM_NAME,
                    company=job.get("company", ""),
                    job_title=job.get("title", ""),
                    job_url=job.get("url", ""),
                    status="applied" if success else "failed",
                    resume_used=self.config.get("documents", {}).get("resume_path", ""),
                )
                if success:
                    self._applied_count += 1
            except Exception as e:
                self.logger.error(f"Error applying to {job['url']}: {e}")
                await self.browser.screenshot(f"career_page_error_{self._applied_count}")
                self.tracker.log_application(
                    platform=self.PLATFORM_NAME,
                    company=job.get("company", ""),
                    job_title=job.get("title", ""),
                    job_url=job.get("url", ""),
                    status="failed",
                    error_message=str(e)[:200],
                )
