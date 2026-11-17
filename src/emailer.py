"""
src/emailer.py
--------------
Email delivery module for the News Headline Sentiment Analyser.

Builds an HTML report summarising the sentiment analysis results and delivers
it via SMTP (TLS on port 587 by default, compatible with Gmail App Passwords).

The pie chart is embedded as a base64 inline image in the HTML body **and**
attached as a separate ``MIMEImage`` part so mail clients that block
inline images still show the chart as an attachment.
"""

import base64
import logging
import os
import smtplib
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List

logger = logging.getLogger(__name__)


class EmailSender:
    """Build and deliver HTML sentiment-analysis email reports.

    Args:
        smtp_host: SMTP server hostname.
        smtp_port: SMTP server port (typically 587 for TLS).
        sender:    Sender email address.
        password:  Sender email password / app password.
        receiver:  Recipient email address.
    """

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        sender: str,
        password: str,
        receiver: str,
    ) -> None:
        """Store SMTP credentials and addresses."""
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.sender = sender
        self.password = password
        self.receiver = receiver

    # ------------------------------------------------------------------
    # Report builder
    # ------------------------------------------------------------------

    def build_html_report(
        self,
        results: List[dict],
        query: str,
        timestamp: str,
        chart_paths: dict,
    ) -> str:
        """Build an HTML string summarising the sentiment analysis results.

        The report includes:

        * A branded header with query and timestamp.
        * A summary table (totals and average VADER compound score).
        * Top-5 most positive headlines with hyperlinks.
        * Top-5 most negative headlines with hyperlinks.
        * The pie chart embedded as a base64 inline ``<img>``.

        Args:
            results:     Enriched article list.
            query:       The search query string.
            timestamp:   Human-readable timestamp for the report header.
            chart_paths: Dict with ``"pie"`` and ``"bar"`` filepath keys.

        Returns:
            HTML string.
        """
        totals = self._compute_totals(results)
        top_pos = self._top_n(results, "positive", 5)
        top_neg = self._top_n(results, "negative", 5)
        pie_b64 = self._encode_image(chart_paths.get("pie", ""))

        # --- Summary table rows ---
        summary_rows = f"""
        <tr><td>Total Headlines</td><td><b>{totals['total']}</b></td></tr>
        <tr><td>Positive</td><td style="color:#4CAF50"><b>{totals['positive']}</b></td></tr>
        <tr><td>Negative</td><td style="color:#F44336"><b>{totals['negative']}</b></td></tr>
        <tr><td>Neutral</td><td style="color:#9E9E9E"><b>{totals['neutral']}</b></td></tr>
        <tr><td>Avg VADER Score</td><td><b>{totals['avg_compound']:.4f}</b></td></tr>
        """

        # --- Top-5 positive ---
        pos_items = "".join(
            f'<li><a href="{a.get("url","#")}">{a.get("title","")}</a> '
            f'<span style="color:#4CAF50">'
            f'[{a["sentiment"]["vader_compound"]:.2f}]</span></li>'
            for a in top_pos
        ) or "<li>None</li>"

        # --- Top-5 negative ---
        neg_items = "".join(
            f'<li><a href="{a.get("url","#")}">{a.get("title","")}</a> '
            f'<span style="color:#F44336">'
            f'[{a["sentiment"]["vader_compound"]:.2f}]</span></li>'
            for a in top_neg
        ) or "<li>None</li>"

        # --- Inline pie chart ---
        pie_section = ""
        if pie_b64:
            pie_section = (
                f'<h2>Sentiment Distribution</h2>'
                f'<img src="data:image/png;base64,{pie_b64}" '
                f'alt="Sentiment Pie Chart" style="max-width:500px;" />'
            )

        html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <style>
    body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f9f9f9; }}
    .container {{ max-width: 700px; margin: auto; background: #fff;
                  border-radius: 8px; padding: 30px; box-shadow: 0 2px 8px rgba(0,0,0,.12); }}
    h1 {{ color: #333; }}
    h2 {{ color: #555; border-bottom: 1px solid #eee; padding-bottom: 6px; }}
    table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
    th, td {{ text-align: left; padding: 8px 12px; border-bottom: 1px solid #eee; }}
    th {{ background: #f0f0f0; }}
    ul {{ line-height: 1.8; }}
    a {{ color: #1a73e8; }}
    .footer {{ font-size: 12px; color: #aaa; margin-top: 30px; }}
  </style>
</head>
<body>
<div class="container">
  <h1>📰 News Sentiment Report</h1>
  <p><b>Query:</b> {query}</p>
  <p><b>Generated:</b> {timestamp}</p>

  <h2>Summary</h2>
  <table>
    <tr><th>Metric</th><th>Value</th></tr>
    {summary_rows}
  </table>

  <h2>Top 5 Most Positive Headlines</h2>
  <ul>{pos_items}</ul>

  <h2>Top 5 Most Negative Headlines</h2>
  <ul>{neg_items}</ul>

  {pie_section}

  <div class="footer">Generated by News Headline Sentiment Analyser · Zelvora</div>
</div>
</body>
</html>"""
        return html

    # ------------------------------------------------------------------
    # Delivery
    # ------------------------------------------------------------------

    def send(
        self,
        subject: str,
        html_body: str,
        chart_paths: dict,
    ) -> bool:
        """Send the HTML report via SMTP with the pie chart attached.

        Args:
            subject:     Email subject line.
            html_body:   HTML body produced by :meth:`build_html_report`.
            chart_paths: Dict with ``"pie"`` and ``"bar"`` filepath keys.

        Returns:
            ``True`` on successful delivery, ``False`` otherwise.
        """
        if not self.sender or not self.receiver:
            logger.error(
                "EMAIL_SENDER or EMAIL_RECEIVER is not configured. "
                "Cannot send email."
            )
            return False

        msg = MIMEMultipart("related")
        msg["Subject"] = subject
        msg["From"]    = self.sender
        msg["To"]      = self.receiver

        # Attach HTML body
        alternative = MIMEMultipart("alternative")
        msg.attach(alternative)
        alternative.attach(MIMEText(html_body, "html", "utf-8"))

        # Attach pie chart as inline image
        pie_path = chart_paths.get("pie", "")
        if pie_path and os.path.isfile(pie_path):
            try:
                with open(pie_path, "rb") as fh:
                    img_data = fh.read()
                img_part = MIMEImage(img_data, name=os.path.basename(pie_path))
                img_part.add_header(
                    "Content-Disposition",
                    "attachment",
                    filename=os.path.basename(pie_path),
                )
                img_part.add_header("Content-ID", "<sentiment_pie>")
                msg.attach(img_part)
            except OSError as exc:
                logger.warning("Could not attach pie chart '%s': %s", pie_path, exc)

        # Send via SMTP with TLS
        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(self.sender, self.password)
                server.sendmail(self.sender, self.receiver, msg.as_string())
            logger.info("Email sent to '%s' (subject: '%s').", self.receiver, subject)
            return True
        except smtplib.SMTPAuthenticationError as exc:
            logger.error(
                "SMTP authentication failed for '%s'. "
                "Check EMAIL_SENDER / EMAIL_PASSWORD. Details: %s",
                self.sender,
                exc,
            )
        except smtplib.SMTPException as exc:
            logger.error("SMTP error while sending email: %s", exc)
        except OSError as exc:
            logger.error("Network error while connecting to SMTP server: %s", exc)
        return False

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_totals(results: List[dict]) -> dict:
        """Compute aggregate counts and average VADER compound from *results*."""
        total = len(results)
        pos = neg = neu = 0
        compound_sum = 0.0
        for a in results:
            s = a.get("sentiment") or {}
            label = s.get("label", "neutral")
            if label == "positive":
                pos += 1
            elif label == "negative":
                neg += 1
            else:
                neu += 1
            compound_sum += s.get("vader_compound", 0.0)
        avg = compound_sum / total if total else 0.0
        return {
            "total": total,
            "positive": pos,
            "negative": neg,
            "neutral": neu,
            "avg_compound": avg,
        }

    @staticmethod
    def _top_n(results: List[dict], label: str, n: int) -> List[dict]:
        """Return the top *n* articles with *label*, sorted by compound score."""
        filtered = [
            a for a in results
            if (a.get("sentiment") or {}).get("label") == label
        ]
        reverse = label == "positive"
        return sorted(
            filtered,
            key=lambda a: a["sentiment"]["vader_compound"],
            reverse=reverse,
        )[:n]

    @staticmethod
    def _encode_image(filepath: str) -> str:
        """Return the base64-encoded content of an image file, or ``""``.

        Args:
            filepath: Path to a PNG file.

        Returns:
            Base64 string, or empty string if the file cannot be read.
        """
        if not filepath or not os.path.isfile(filepath):
            return ""
        try:
            with open(filepath, "rb") as fh:
                return base64.b64encode(fh.read()).decode("ascii")
        except OSError as exc:
            logger.warning("Could not read chart file '%s' for embedding: %s", filepath, exc)
            return ""


# ---------------------------------------------------------------------------
# Module-level convenience function
# ---------------------------------------------------------------------------


def send_report(
    results: List[dict],
    config,
    chart_paths: dict,
    timestamp: str,
) -> bool:
    """Build and send the HTML report using settings from *config*.

    Args:
        results:     Enriched article list.
        config:      Module or object exposing SMTP / email config attributes.
        chart_paths: Dict with ``"pie"`` and ``"bar"`` filepath keys.
        timestamp:   Human-readable timestamp for the report header.

    Returns:
        ``True`` on successful delivery, ``False`` otherwise.
    """
    sender = EmailSender(
        smtp_host=config.EMAIL_SMTP_HOST,
        smtp_port=config.EMAIL_SMTP_PORT,
        sender=config.EMAIL_SENDER,
        password=config.EMAIL_PASSWORD,
        receiver=config.EMAIL_RECEIVER,
    )
    html = sender.build_html_report(
        results=results,
        query=config.QUERY,
        timestamp=timestamp,
        chart_paths=chart_paths,
    )
    subject = f"[Sentiment Report] {config.QUERY} – {timestamp}"
    return sender.send(subject=subject, html_body=html, chart_paths=chart_paths)
