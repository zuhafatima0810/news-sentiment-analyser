"""
main.py
-------
CLI entry point for the News Headline Sentiment Analyser.

Usage examples::

    python main.py run
    python main.py run --query "AI breakthroughs" --no-email
    python main.py run --no-chart --output-dir results
    python main.py schedule
    python main.py schedule --query "climate change"

Sub-commands
~~~~~~~~~~~~
* ``run``      – Execute the full pipeline once and exit.
* ``schedule`` – Start the blocking daily APScheduler loop (Ctrl-C to stop).

Global options
~~~~~~~~~~~~~~
* ``--query TEXT``      Override the ``QUERY`` setting from config.
* ``--no-email``        Skip sending the email report.
* ``--no-chart``        Skip generating charts.
* ``--output-dir DIR``  Override both ``CHART_OUTPUT_DIR`` and
                         ``REPORT_OUTPUT_DIR`` with ``DIR/charts`` and
                         ``DIR/reports`` respectively.
* ``--log-level LEVEL`` Set logging verbosity (default: ``INFO``).
"""

import argparse
import json
import logging
import sys
import types
from datetime import datetime

import config as cfg
from src.scheduler import run_analysis_job, start_scheduler


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------


def _configure_logging(level: str) -> None:
    """Configure root logger with a timestamped console handler.

    Args:
        level: Logging level string (``"DEBUG"``, ``"INFO"``, etc.).
    """
    numeric = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric,
        format="%(asctime)s [%(levelname)-8s] %(name)s – %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


# ---------------------------------------------------------------------------
# Config overlay helper
# ---------------------------------------------------------------------------


def _apply_overrides(args: argparse.Namespace) -> types.ModuleType:
    """Return a shallow copy of *config* with CLI overrides applied.

    Uses a :class:`types.SimpleNamespace` so the rest of the code can access
    settings via attribute syntax regardless of whether they come from the
    module or the CLI.

    Args:
        args: Parsed argument namespace.

    Returns:
        A SimpleNamespace mirroring *config* with overrides applied.
    """
    # Copy all config attributes into a simple namespace
    overlay = types.SimpleNamespace(**{
        k: getattr(cfg, k)
        for k in dir(cfg)
        if not k.startswith("_")
    })

    if args.query:
        overlay.QUERY = args.query

    if args.output_dir:
        overlay.CHART_OUTPUT_DIR  = f"{args.output_dir}/charts"
        overlay.REPORT_OUTPUT_DIR = f"{args.output_dir}/reports"

    return overlay


# ---------------------------------------------------------------------------
# Pretty-print summary
# ---------------------------------------------------------------------------


def _print_summary(summary: dict) -> None:
    """Print the pipeline summary in a human-readable table to stdout.

    Args:
        summary: Dict returned by :func:`~src.scheduler.run_analysis_job`.
    """
    sep = "─" * 50
    print(f"\n{sep}")
    print("  📰 Sentiment Analysis Summary")
    print(sep)
    print(f"  Query     : {summary.get('query', 'N/A')}")
    print(f"  Timestamp : {summary.get('timestamp', 'N/A')}")
    print(f"  Total     : {summary.get('total', 0)}")
    print(f"  Positive  : {summary.get('positive', 0)}")
    print(f"  Negative  : {summary.get('negative', 0)}")
    print(f"  Neutral   : {summary.get('neutral', 0)}")
    print(f"  Avg VADER : {summary.get('avg_compound', 0.0):.4f}")
    print(f"  Email sent: {summary.get('email_sent', False)}")
    chart_paths = summary.get("chart_paths", {})
    if chart_paths.get("pie"):
        print(f"  Pie chart : {chart_paths['pie']}")
    if chart_paths.get("bar"):
        print(f"  Bar chart : {chart_paths['bar']}")
    if summary.get("report_path"):
        print(f"  JSON report: {summary['report_path']}")
    print(f"{sep}\n")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    """Build and return the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="main.py",
        description=(
            "News Headline Sentiment Analyser – fetch, analyse, visualise "
            "and email daily news sentiment reports."
        ),
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set the logging verbosity level (default: INFO).",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # Shared options factory
    def _add_shared(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--query",
            default=None,
            metavar="TEXT",
            help="Override the QUERY setting from config.",
        )
        p.add_argument(
            "--no-email",
            action="store_true",
            help="Skip sending the email report.",
        )
        p.add_argument(
            "--no-chart",
            action="store_true",
            help="Skip generating charts.",
        )
        p.add_argument(
            "--output-dir",
            default=None,
            metavar="DIR",
            help="Override chart and report output directory.",
        )

    # run sub-command
    run_parser = sub.add_parser(
        "run",
        help="Run the analysis pipeline once and exit.",
    )
    _add_shared(run_parser)

    # schedule sub-command
    sched_parser = sub.add_parser(
        "schedule",
        help="Start the daily APScheduler loop (Ctrl-C to stop).",
    )
    _add_shared(sched_parser)

    return parser


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Parse CLI arguments and dispatch to the appropriate action."""
    parser = _build_parser()
    args = parser.parse_args()

    _configure_logging(args.log_level)
    logger = logging.getLogger(__name__)

    effective_config = _apply_overrides(args)

    if args.command == "run":
        logger.info("Running one-shot analysis for query: '%s'", effective_config.QUERY)
        try:
            summary = run_analysis_job(
                config=effective_config,
                send_email=not args.no_email,
                generate_charts=not args.no_chart,
            )
            _print_summary(summary)
        except Exception as exc:
            logger.error("Pipeline failed with an unexpected error: %s", exc, exc_info=True)
            sys.exit(1)

    elif args.command == "schedule":
        logger.info(
            "Starting scheduler – daily job at %02d:%02d. Press Ctrl-C to stop.",
            effective_config.SCHEDULE_HOUR,
            effective_config.SCHEDULE_MINUTE,
        )
        try:
            start_scheduler(effective_config)
        except KeyboardInterrupt:
            logger.info("Scheduler stopped by KeyboardInterrupt.")
        except Exception as exc:
            logger.error("Scheduler failed: %s", exc, exc_info=True)
            sys.exit(1)


if __name__ == "__main__":
    main()
