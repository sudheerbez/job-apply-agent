"""
Configuration loader - reads config.yaml and merges with environment variables.
"""

import os
import yaml
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

_config = None


def load_config(config_path: str = None) -> dict:
    """Load configuration from YAML file and overlay env vars."""
    global _config
    if _config is not None and config_path is None:
        return _config

    if config_path is None:
        config_path = Path(__file__).parent.parent / "config.yaml"

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    # Override with environment variables where set
    env_overrides = {
        ("platforms", "linkedin", "email"): "LINKEDIN_EMAIL",
        ("platforms", "linkedin", "password"): "LINKEDIN_PASSWORD",
        ("platforms", "indeed", "email"): "INDEED_EMAIL",
        ("platforms", "indeed", "password"): "INDEED_PASSWORD",
        ("openai", "api_key"): "OPENAI_API_KEY",
    }

    for key_path, env_var in env_overrides.items():
        env_val = os.getenv(env_var)
        if env_val:
            obj = config
            for key in key_path[:-1]:
                obj = obj[key]
            obj[key_path[-1]] = env_val

    _config = config
    return config


def get_config() -> dict:
    """Get the loaded config (loads if not yet loaded)."""
    if _config is None:
        return load_config()
    return _config
