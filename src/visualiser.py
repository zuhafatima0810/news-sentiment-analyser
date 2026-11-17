"""
src/visualiser.py
-----------------
Chart generation module for the News Headline Sentiment Analyser.

Produces two chart types:

* **Pie chart** – proportion of positive / negative / neutral headlines.
* **Bar chart** – VADER compound scores for the top-20 most polarised
  headlines, colour-coded by sentiment direction.

All charts are saved as PNG files to a configurable output directory.
"""

import logging
import os
from typing import List

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend – safe for headless environments
import matplotlib.pyplot as plt

logger = logging.getLogger(__name__)


class ChartGenerator:
    """Generate Matplotlib sentiment charts from enriched article lists.

    Args:
        output_dir: Directory path where PNG files will be written.
                    The directory is created automatically if it does not exist.
    """

    _POSITIVE_COLOR = "#4CAF50"   # green
    _NEGATIVE_COLOR = "#F44336"   # red
    _NEUTRAL_COLOR  = "#9E9E9E"   # gray

    def __init__(self, output_dir: str) -> None:
        """Initialise the generator and ensure *output_dir* exists."""
        self.output_dir = output_dir
        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as exc:
            logger.error("Could not create chart output directory '%s': %s", output_dir, exc)

    # ------------------------------------------------------------------
    # Public chart methods
    # ------------------------------------------------------------------

    def plot_pie(
        self,
        results: List[dict],
        title: str,
        filename: str,
    ) -> str:
        """Create and save a pie chart of positive / negative / neutral counts.

        Args:
            results: Enriched article list (each item must contain a
                     ``"sentiment"`` dict with a ``"label"`` key).
            title:   Chart title string.
            filename: Base filename (without extension) for the saved PNG.

        Returns:
            Absolute path to the saved PNG, or an empty string on failure.
        """
        counts = self._count_labels(results)
        labels = []
        sizes  = []
        colors = []

        label_map = [
            ("positive", "Positive", self._POSITIVE_COLOR),
            ("negative", "Negative", self._NEGATIVE_COLOR),
            ("neutral",  "Neutral",  self._NEUTRAL_COLOR),
        ]
        for key, display, color in label_map:
            if counts[key] > 0:
                labels.append(display)
                sizes.append(counts[key])
                colors.append(color)

        if not sizes:
            logger.warning("No data to plot for pie chart '%s'.", filename)
            return ""

        fig, ax = plt.subplots(figsize=(7, 7))
        wedges, texts, autotexts = ax.pie(
            sizes,
            labels=labels,
            colors=colors,
            autopct="%1.1f%%",
            startangle=140,
            pctdistance=0.82,
        )
        for autotext in autotexts:
            autotext.set_fontsize(11)
            autotext.set_fontweight("bold")

        ax.set_title(title, fontsize=14, fontweight="bold", pad=20)
        ax.axis("equal")

        filepath = os.path.join(self.output_dir, f"{filename}.png")
        return self._save_figure(fig, filepath)

    def plot_bar(
        self,
        results: List[dict],
        title: str,
        filename: str,
    ) -> str:
        """Create and save a bar chart of VADER compound scores.

        Shows the top-20 most polarised headlines (highest absolute compound
        score), colour-coded green (positive) or red (negative).

        Args:
            results: Enriched article list.
            title:   Chart title string.
            filename: Base filename (without extension) for the saved PNG.

        Returns:
            Absolute path to the saved PNG, or an empty string on failure.
        """
        # Filter articles that have sentiment data
        scored = [
            a for a in results
            if a.get("sentiment") and a["sentiment"].get("vader_compound") is not None
        ]
        if not scored:
            logger.warning("No scored articles to plot for bar chart '%s'.", filename)
            return ""

        # Sort by absolute compound, take top 20
        top20 = sorted(
            scored,
            key=lambda a: abs(a["sentiment"]["vader_compound"]),
            reverse=True,
        )[:20]

        compounds = [a["sentiment"]["vader_compound"] for a in top20]
        # Truncate long titles for readability
        bar_labels = [
            (a.get("title") or "")[:55] + ("…" if len(a.get("title") or "") > 55 else "")
            for a in top20
        ]
        bar_colors = [
            self._POSITIVE_COLOR if c >= 0.05
            else self._NEGATIVE_COLOR if c <= -0.05
            else self._NEUTRAL_COLOR
            for c in compounds
        ]

        fig, ax = plt.subplots(figsize=(12, max(6, len(top20) * 0.5)))
        bars = ax.barh(range(len(top20)), compounds, color=bar_colors)
        ax.set_yticks(range(len(top20)))
        ax.set_yticklabels(bar_labels, fontsize=9)
        ax.set_xlabel("VADER Compound Score", fontsize=11)
        ax.set_title(title, fontsize=13, fontweight="bold")
        ax.axvline(0, color="black", linewidth=0.8, linestyle="--")
        ax.set_xlim(-1.1, 1.1)
        ax.invert_yaxis()

        # Add score annotations on bars
        for bar, score in zip(bars, compounds):
            x_pos = score + (0.03 if score >= 0 else -0.03)
            ha = "left" if score >= 0 else "right"
            ax.text(x_pos, bar.get_y() + bar.get_height() / 2,
                    f"{score:.2f}", va="center", ha=ha, fontsize=8)

        plt.tight_layout()
        filepath = os.path.join(self.output_dir, f"{filename}.png")
        return self._save_figure(fig, filepath)

    def generate_charts(
        self,
        results: List[dict],
        query: str,
        timestamp: str,
    ) -> dict:
        """Generate both pie and bar charts for a single analysis run.

        Args:
            results:   Enriched article list.
            query:     The search query (used in chart titles).
            timestamp: ISO-like timestamp string used for unique filenames.

        Returns:
            Dict with keys ``"pie"`` and ``"bar"``, each holding the absolute
            path to the generated PNG (or ``""`` if generation failed).
        """
        safe_ts = timestamp.replace(":", "-").replace(" ", "_")
        pie_path = self.plot_pie(
            results,
            title=f"Sentiment Distribution – '{query}'",
            filename=f"pie_{safe_ts}",
        )
        bar_path = self.plot_bar(
            results,
            title=f"Top-20 Headline VADER Scores – '{query}'",
            filename=f"bar_{safe_ts}",
        )
        logger.info("Charts generated: pie='%s', bar='%s'", pie_path, bar_path)
        return {"pie": pie_path, "bar": bar_path}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _count_labels(results: List[dict]) -> dict:
        """Count positive / negative / neutral articles in *results*."""
        counts = {"positive": 0, "negative": 0, "neutral": 0}
        for article in results:
            label = (article.get("sentiment") or {}).get("label", "neutral")
            if label in counts:
                counts[label] += 1
        return counts

    @staticmethod
    def _save_figure(fig: plt.Figure, filepath: str) -> str:
        """Save *fig* to *filepath* as PNG and close it.

        Returns:
            *filepath* on success, empty string on failure.
        """
        try:
            fig.savefig(filepath, dpi=120, bbox_inches="tight")
            logger.info("Chart saved: %s", filepath)
            return filepath
        except OSError as exc:
            logger.error("Failed to save chart '%s': %s", filepath, exc)
            return ""
        finally:
            plt.close(fig)


# ---------------------------------------------------------------------------
# Module-level convenience function
# ---------------------------------------------------------------------------


def generate_all_charts(results: List[dict], config, timestamp: str) -> dict:
    """Generate both charts using settings from *config*.

    Args:
        results:   Enriched article list.
        config:    Module or object exposing ``CHART_OUTPUT_DIR``.
        timestamp: Timestamp string for unique filenames.

    Returns:
        Dict with ``"pie"`` and ``"bar"`` filepath keys.
    """
    generator = ChartGenerator(output_dir=config.CHART_OUTPUT_DIR)
    return generator.generate_charts(results, query=config.QUERY, timestamp=timestamp)
