"""
Logging setup with Rich console output and file logging.
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from rich.logging import RichHandler
from rich.console import Console

console = Console()


def setup_logger(config: dict) -> logging.Logger:
    """Configure and return the application logger."""
    log_config = config.get("logging", {})
    level = getattr(logging, log_config.get("level", "INFO").upper(), logging.INFO)

    logger = logging.getLogger("job_agent")
    logger.setLevel(level)

    # Clear existing handlers
    logger.handlers.clear()

    # Rich console handler
    rich_handler = RichHandler(
        console=console,
        show_time=True,
        show_path=False,
        markup=True,
        rich_tracebacks=True,
    )
    rich_handler.setLevel(level)
    logger.addHandler(rich_handler)

    # File handler
    if log_config.get("log_to_file", True):
        log_dir = Path(log_config.get("log_dir", "logs"))
        log_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_handler = logging.FileHandler(log_dir / f"run_{timestamp}.log")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s")
        )
        logger.addHandler(file_handler)

    # Screenshot directory
    if log_config.get("screenshot_on_error", True):
        ss_dir = Path(log_config.get("screenshot_dir", "logs/screenshots"))
        ss_dir.mkdir(parents=True, exist_ok=True)

    return logger


def get_logger() -> logging.Logger:
    """Get the application logger."""
    return logging.getLogger("job_agent")
