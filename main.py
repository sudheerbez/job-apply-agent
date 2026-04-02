#!/usr/bin/env python3
"""
Job Application Agent - Main Entry Point

Automates job applications across LinkedIn, Indeed, and company career pages.

Usage:
    python main.py                          # Run all enabled platforms
    python main.py --platform linkedin      # Run LinkedIn only
    python main.py --platform indeed        # Run Indeed only
    python main.py --urls urls.txt          # Apply to specific career page URLs
    python main.py --dry-run                # Search but don't apply
    python main.py --headless               # Run in background (no browser UI)
"""

import asyncio
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from utils.config_loader import load_config
from utils.logger import setup_logger, get_logger
from utils.browser_manager import BrowserManager
from utils.ai_helper import AIHelper
from utils.tracker import ApplicationTracker
from platforms.linkedin import LinkedInPlatform
from platforms.indeed import IndeedPlatform
from platforms.career_pages import CareerPagesPlatform

console = Console()


def print_banner():
    """Print the startup banner."""
    banner = """
     ╔══════════════════════════════════════════╗
     ║      🤖  Job Application Agent  🤖       ║
     ║                                          ║
     ║   Automate your job search with AI       ║
     ╚══════════════════════════════════════════╝
    """
    console.print(Panel(banner, style="bold blue"))


def print_config_summary(config: dict):
    """Print a summary of the current configuration."""
    table = Table(title="Configuration Summary", show_header=True)
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")

    profile = config.get("profile", {})
    search = config.get("search", {})
    platforms = config.get("platforms", {})

    table.add_row("Name", f"{profile.get('first_name', '')} {profile.get('last_name', '')}")
    table.add_row("Email", profile.get("email", ""))
    table.add_row("Location", profile.get("location", ""))
    table.add_row("Keywords", ", ".join(search.get("keywords", [])))
    table.add_row("Locations", ", ".join(search.get("locations", [])))
    table.add_row("Max Apps/Run", str(search.get("max_applications_per_run", 50)))
    table.add_row("LinkedIn", "Enabled" if platforms.get("linkedin", {}).get("enabled") else "Disabled")
    table.add_row("Indeed", "Enabled" if platforms.get("indeed", {}).get("enabled") else "Disabled")
    table.add_row("Resume", config.get("documents", {}).get("resume_path", "Not set"))

    console.print(table)
    console.print()


@click.command()
@click.option("--config", "config_path", default=None, help="Path to config.yaml")
@click.option(
    "--platform",
    type=click.Choice(["linkedin", "indeed", "career_pages", "all"]),
    default="all",
    help="Which platform to run",
)
@click.option("--urls", "urls_file", default=None, help="File with career page URLs (one per line)")
@click.option("--dry-run", is_flag=True, help="Search for jobs but don't apply")
@click.option("--headless", is_flag=True, help="Run browser in headless mode")
@click.option("--max-apps", default=None, type=int, help="Override max applications per run")
def main(config_path, platform, urls_file, dry_run, headless, max_apps):
    """AI-powered job application automation agent."""
    print_banner()

    # Load config
    config = load_config(config_path)

    # Apply CLI overrides
    if headless:
        config["browser"]["headless"] = True
    if max_apps:
        config["search"]["max_applications_per_run"] = max_apps

    # Setup
    logger = setup_logger(config)
    print_config_summary(config)

    if dry_run:
        console.print("[yellow]DRY RUN MODE - will search but not apply[/yellow]\n")

    # Run the async workflow
    asyncio.run(run_agent(config, platform, urls_file, dry_run))


async def run_agent(config: dict, platform: str, urls_file: str, dry_run: bool):
    """Main async workflow."""
    logger = get_logger()
    browser = BrowserManager(config)
    tracker = ApplicationTracker()
    ai_helper = AIHelper(config)

    try:
        page = await browser.start()

        platforms_to_run = []

        if platform in ("linkedin", "all"):
            if config.get("platforms", {}).get("linkedin", {}).get("enabled", False):
                platforms_to_run.append(
                    LinkedInPlatform(browser, config, tracker, ai_helper)
                )

        if platform in ("indeed", "all"):
            if config.get("platforms", {}).get("indeed", {}).get("enabled", False):
                platforms_to_run.append(
                    IndeedPlatform(browser, config, tracker, ai_helper)
                )

        if platform in ("career_pages", "all") and urls_file:
            urls = _load_urls(urls_file)
            if urls:
                cp = CareerPagesPlatform(browser, config, tracker, ai_helper, job_urls=urls)
                platforms_to_run.append(cp)

        if not platforms_to_run:
            logger.warning(
                "No platforms configured to run. "
                "Check config.yaml or use --platform / --urls flags."
            )
            return

        for p in platforms_to_run:
            logger.info(f"\n{'='*50}")
            logger.info(f"Running: {p.PLATFORM_NAME.upper()}")
            logger.info(f"{'='*50}")

            if dry_run:
                await _dry_run_platform(p)
            else:
                await p.run()

        # Print final summary
        console.print()
        tracker.print_summary()

    except KeyboardInterrupt:
        logger.info("Interrupted by user. Saving progress...")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        await browser.screenshot("fatal_error")
    finally:
        await browser.close()


async def _dry_run_platform(platform):
    """Run a platform in dry-run mode (search only)."""
    logger = get_logger()
    try:
        await platform.login()
    except Exception as e:
        logger.error(f"Login failed: {e}")
        return

    keywords = platform.search_config.get("keywords", [])
    locations = platform.search_config.get("locations", [])

    all_jobs = []
    for keyword in keywords:
        for location in locations:
            jobs = await platform.search_jobs(keyword, location)
            all_jobs.extend(jobs)

    # Display found jobs
    table = Table(title=f"Found Jobs ({platform.PLATFORM_NAME})")
    table.add_column("#", style="dim")
    table.add_column("Title", style="cyan")
    table.add_column("Company", style="green")
    table.add_column("Location")
    table.add_column("URL", style="blue")

    for i, job in enumerate(all_jobs[:50], 1):
        table.add_row(
            str(i),
            job.get("title", "")[:50],
            job.get("company", "")[:30],
            job.get("location", "")[:25],
            job.get("url", "")[:60],
        )

    console.print(table)
    logger.info(f"Total jobs found: {len(all_jobs)}")


def _load_urls(filepath: str) -> list:
    """Load URLs from a file (one per line)."""
    path = Path(filepath)
    if not path.exists():
        get_logger().error(f"URLs file not found: {filepath}")
        return []

    urls = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and line.startswith("http"):
                urls.append(line)

    get_logger().info(f"Loaded {len(urls)} URLs from {filepath}")
    return urls


if __name__ == "__main__":
    main()
