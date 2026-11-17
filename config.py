"""
config.py
---------
Central configuration module for the News Headline Sentiment Analyser.

Loads all settings from environment variables, with optional fallback to a
.env file (via python-dotenv).  No secrets are hardcoded here; every
sensitive value must be supplied through the environment or the .env file.
"""

import os
from dotenv import load_dotenv

# Load .env file if present (values already in the environment take precedence)
load_dotenv(override=False)


def _env_int(key: str, default: int) -> int:
    """Return the integer value of an environment variable, or *default*."""
    raw = os.environ.get(key, "")
    try:
        return int(raw)
    except (ValueError, TypeError):
        return default


# ── NewsAPI ──────────────────────────────────────────────────────────────────
NEWS_API_KEY: str = os.environ.get("NEWS_API_KEY", "YOUR_API_KEY")

# ── Email / SMTP ──────────────────────────────────────────────────────────────
EMAIL_SENDER: str = os.environ.get("EMAIL_SENDER", "")
EMAIL_PASSWORD: str = os.environ.get("EMAIL_PASSWORD", "")
EMAIL_RECEIVER: str = os.environ.get("EMAIL_RECEIVER", "")
EMAIL_SMTP_HOST: str = os.environ.get("EMAIL_SMTP_HOST", "smtp.gmail.com")
EMAIL_SMTP_PORT: int = _env_int("EMAIL_SMTP_PORT", 587)

# ── Query / Sources ───────────────────────────────────────────────────────────
QUERY: str = os.environ.get("QUERY", "technology")
SOURCES: str = os.environ.get("SOURCES", "")
PAGE_SIZE: int = _env_int("PAGE_SIZE", 50)

# ── Scheduler ─────────────────────────────────────────────────────────────────
SCHEDULE_HOUR: int = _env_int("SCHEDULE_HOUR", 8)
SCHEDULE_MINUTE: int = _env_int("SCHEDULE_MINUTE", 0)

# ── Output directories ────────────────────────────────────────────────────────
CHART_OUTPUT_DIR: str = os.environ.get("CHART_OUTPUT_DIR", "output/charts")
REPORT_OUTPUT_DIR: str = os.environ.get("REPORT_OUTPUT_DIR", "output/reports")
