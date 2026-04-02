"""
Browser manager - handles Playwright browser lifecycle with anti-detection.
"""

import asyncio
import random
from pathlib import Path
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from utils.logger import get_logger


class BrowserManager:
    """Manages Playwright browser instance with stealth and human-like behavior."""

    def __init__(self, config: dict):
        self.config = config
        self.browser_config = config.get("browser", {})
        self.stealth_config = self.browser_config.get("stealth", {})
        self.logger = get_logger()
        self._playwright = None
        self._browser: Browser = None
        self._context: BrowserContext = None
        self._page: Page = None

    async def start(self) -> Page:
        """Launch browser and return a page."""
        self.logger.info("Launching browser...")
        self._playwright = await async_playwright().start()

        launch_args = {
            "headless": self.browser_config.get("headless", False),
            "slow_mo": self.browser_config.get("slow_mo", 100),
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-web-security",
            ],
        }

        self._browser = await self._playwright.chromium.launch(**launch_args)

        context_args = {
            "viewport": {"width": 1366, "height": 768},
            "locale": "en-US",
            "timezone_id": "America/Chicago",
        }

        user_agent = self.browser_config.get("user_agent")
        if user_agent:
            context_args["user_agent"] = user_agent

        self._context = await self._browser.new_context(**context_args)

        # Anti-detection: override navigator.webdriver
        await self._context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            window.chrome = { runtime: {} };
        """)

        self._page = await self._context.new_page()
        self._page.set_default_timeout(self.browser_config.get("timeout", 30000))

        self.logger.info("Browser launched successfully")
        return self._page

    @property
    def page(self) -> Page:
        return self._page

    async def random_delay(self, min_ms: int = None, max_ms: int = None):
        """Add a random delay to mimic human behavior."""
        if not self.stealth_config.get("random_delays", True):
            return
        min_d = min_ms or self.stealth_config.get("min_delay_ms", 500)
        max_d = max_ms or self.stealth_config.get("max_delay_ms", 2000)
        delay = random.randint(min_d, max_d) / 1000
        await asyncio.sleep(delay)

    async def human_type(self, selector: str, text: str, clear_first: bool = True):
        """Type text character by character with random delays."""
        if clear_first:
            await self._page.click(selector, click_count=3)
            await self._page.keyboard.press("Backspace")
            await self.random_delay(100, 300)

        if self.stealth_config.get("human_like_typing", True):
            min_t = self.stealth_config.get("typing_min_delay_ms", 50)
            max_t = self.stealth_config.get("typing_max_delay_ms", 150)
            for char in text:
                await self._page.keyboard.type(char)
                await asyncio.sleep(random.randint(min_t, max_t) / 1000)
        else:
            await self._page.fill(selector, text)

    async def safe_click(self, selector: str, timeout: int = 10000):
        """Click an element with wait and random delay."""
        await self._page.wait_for_selector(selector, timeout=timeout)
        await self.random_delay(200, 600)
        await self._page.click(selector)

    async def scroll_down(self, pixels: int = 300):
        """Scroll down the page."""
        await self._page.mouse.wheel(0, pixels)
        await self.random_delay(300, 800)

    async def screenshot(self, name: str = "error"):
        """Take a screenshot for debugging."""
        ss_dir = Path(self.config.get("logging", {}).get("screenshot_dir", "logs/screenshots"))
        ss_dir.mkdir(parents=True, exist_ok=True)
        path = ss_dir / f"{name}.png"
        await self._page.screenshot(path=str(path), full_page=True)
        self.logger.info(f"Screenshot saved: {path}")
        return str(path)

    async def close(self):
        """Clean up browser resources."""
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self.logger.info("Browser closed")
