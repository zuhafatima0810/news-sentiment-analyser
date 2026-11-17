"""
src/scheduler.py
----------------
APScheduler integration for the News Headline Sentiment Analyser.

Provides two entry points:

* :func:`run_analysis_job` – execute the full pipeline once (fetch → analyse
  → visualise → email) and persist a JSON report to disk.
* :func:`start_scheduler` – start a blocking daily scheduler that calls
  :func:`run_analysis_job` at a configured time every day.
"""

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED

from src.fetcher import get_headlines
from src.analyser import analyse_all
from src.visualiser import generate_all_charts
from src.emailer import send_report

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pipeline job
# ---------------------------------------------------------------------------


def run_analysis_job(
    config,
    send_email: bool = True,
    generate_charts: bool = True,
) -> Dict[str, Any]:
    """Execute the full sentiment-analysis pipeline and return a summary.

    Steps performed:

    1. Fetch headlines (NewsAPI or RSS fallback).
    2. Analyse sentiment (TextBlob + VADER).
    3. Generate charts (pie + bar) – optional via *generate_charts*.
    4. Send HTML email report – optional via *send_email*.
    5. Save JSON report to ``config.REPORT_OUTPUT_DIR``.

    Args:
        config:          Config module / object with all pipeline settings.
        send_email:      If ``False``, skip the email step.
        generate_charts: If ``False``, skip chart generation.

    Returns:
        A summary dict with keys:
        ``timestamp``, ``query``, ``total``, ``positive``, ``negative``,
        ``neutral``, ``avg_compound``, ``chart_paths``, ``email_sent``,
        ``report_path``.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info("=== Analysis job started at %s ===", timestamp)

    # 1. Fetch
    logger.info("Fetching headlines for query: '%s'", config.QUERY)
    articles = get_headlines(config)
    if not articles:
        logger.warning("No articles retrieved; job will produce an empty report.")

    # 2. Analyse
    logger.info("Analysing sentiment for %d articles.", len(articles))
    results = analyse_all(articles)

    # 3. Charts
    chart_paths: Dict[str, str] = {"pie": "", "bar": ""}
    if generate_charts and results:
        try:
            chart_paths = generate_all_charts(results, config, timestamp)
        except Exception as exc:
            logger.error("Chart generation failed: %s", exc)

    # 4. Email
    email_sent = False
    if send_email and results:
        try:
            email_sent = send_report(results, config, chart_paths, timestamp)
        except Exception as exc:
            logger.error("Email send failed: %s", exc)

    # 5. Build summary
    summary = _build_summary(results, timestamp, config.QUERY, chart_paths, email_sent)

    # 6. Persist JSON report
    report_path = _save_json_report(summary, results, config.REPORT_OUTPUT_DIR, timestamp)
    summary["report_path"] = report_path

    logger.info("=== Analysis job finished. Summary: %s ===", summary)
    return summary


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------


def start_scheduler(config) -> None:
    """Start a blocking daily scheduler that runs the analysis pipeline.

    The job fires every day at ``config.SCHEDULE_HOUR``:``config.SCHEDULE_MINUTE``
    (local time).  Press Ctrl-C to stop.

    Args:
        config: Config module / object with scheduler and pipeline settings.
    """
    scheduler = BlockingScheduler(timezone="local")

    scheduler.add_job(
        func=run_analysis_job,
        trigger="cron",
        hour=config.SCHEDULE_HOUR,
        minute=config.SCHEDULE_MINUTE,
        kwargs={"config": config},
        id="daily_sentiment_analysis",
        name="Daily Sentiment Analysis",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # Event listeners for structured logging
    def _on_job_executed(event) -> None:
        logger.info("Scheduled job executed successfully (job_id=%s).", event.job_id)

    def _on_job_error(event) -> None:
        logger.error(
            "Scheduled job raised an exception (job_id=%s): %s",
            event.job_id,
            event.exception,
        )

    scheduler.add_listener(_on_job_executed, EVENT_JOB_EXECUTED)
    scheduler.add_listener(_on_job_error, EVENT_JOB_ERROR)

    logger.info(
        "Scheduler started. Daily job at %02d:%02d. Press Ctrl-C to stop.",
        config.SCHEDULE_HOUR,
        config.SCHEDULE_MINUTE,
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped by user.")
    except Exception as exc:
        logger.error("Scheduler encountered an unexpected error: %s", exc)
        raise


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _build_summary(
    results: list,
    timestamp: str,
    query: str,
    chart_paths: dict,
    email_sent: bool,
) -> Dict[str, Any]:
    """Construct the pipeline summary dict from *results*."""
    total = len(results)
    pos = sum(1 for a in results if (a.get("sentiment") or {}).get("label") == "positive")
    neg = sum(1 for a in results if (a.get("sentiment") or {}).get("label") == "negative")
    neu = total - pos - neg
    compounds = [
        (a.get("sentiment") or {}).get("vader_compound", 0.0) for a in results
    ]
    avg_compound = sum(compounds) / total if total else 0.0
    return {
        "timestamp": timestamp,
        "query": query,
        "total": total,
        "positive": pos,
        "negative": neg,
        "neutral": neu,
        "avg_compound": round(avg_compound, 4),
        "chart_paths": chart_paths,
        "email_sent": email_sent,
    }


def _save_json_report(
    summary: dict,
    results: list,
    report_dir: str,
    timestamp: str,
) -> str:
    """Serialise *summary* and *results* to a JSON file.

    Args:
        summary:    Pipeline summary dict.
        results:    Full enriched article list.
        report_dir: Directory where the JSON file should be written.
        timestamp:  Timestamp string used to generate the filename.

    Returns:
        Absolute path to the written file, or ``""`` on error.
    """
    safe_ts = timestamp.replace(":", "-").replace(" ", "_")
    filename = f"report_{safe_ts}.json"
    try:
        os.makedirs(report_dir, exist_ok=True)
        filepath = os.path.join(report_dir, filename)
        payload = {"summary": summary, "articles": results}
        with open(filepath, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
        logger.info("JSON report saved: %s", filepath)
        return filepath
    except OSError as exc:
        logger.error("Failed to save JSON report to '%s': %s", report_dir, exc)
        return ""
