import html
import logging
import time
import requests
from typing import Optional
from freetrialfinder.models import DealItem, ConfidenceLevel
from freetrialfinder.notifiers.base import BaseNotifier

logger = logging.getLogger(__name__)

class TelegramNotifier(BaseNotifier):
    """Sends deal alerts to Telegram via official Bot API."""

    def __init__(self, bot_token: str, chat_id: str, timeout: int = 15):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.timeout = timeout
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

    def format_message(self, deal: DealItem) -> str:
        tier_header = (
            "<b>[VERIFIED DEVELOPER/API CREDIT]</b>"
            if deal.confidence == ConfidenceLevel.DIRECT_IDE
            else "<b>[POTENTIAL DEVELOPER CREDIT - VERIFY API]</b>"
        )
        clean_title = html.escape(deal.title)
        clean_provider = html.escape(deal.provider)
        clean_url = html.escape(deal.url)
        clean_summary = html.escape(deal.summary[:250]) if deal.summary else "No additional description."

        lines = [
            tier_header,
            f"<b>Title:</b> <a href=\"{clean_url}\">{clean_title}</a>",
            f"<b>Provider:</b> {clean_provider}",
            f"<b>Usability Score:</b> {deal.score}/100",
            f"<b>Category:</b> {deal.category.value}",
        ]

        if deal.promo_code:
            lines.append(f"<b>Promo Code:</b> <code>{html.escape(deal.promo_code)}</code> (tap to copy)")

        if deal.estimated_value:
            lines.append(f"<b>Value:</b> {html.escape(deal.estimated_value)}")

        if deal.reasons:
            reasons_str = ", ".join(deal.reasons[:3])
            lines.append(f"<b>Signals:</b> <i>{html.escape(reasons_str)}</i>")

        lines.append(f"\n<b>Summary:</b>\n{clean_summary}")
        lines.append(f"\n<b>Link:</b> <a href=\"{clean_url}\">Open Deal Link</a>")

        return "\n".join(lines)

    def send(self, deal: DealItem) -> bool:
        if not self.bot_token or not self.chat_id:
            logger.warning("Telegram credentials not configured; skipping notification.")
            return False

        message = self.format_message(deal)
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }

        try:
            resp = requests.post(self.api_url, json=payload, timeout=self.timeout)
            if resp.status_code == 200:
                return True
            elif resp.status_code == 429:
                retry_after = resp.json().get("parameters", {}).get("retry_after", 2)
                logger.warning(f"Telegram rate limit hit. Waiting {retry_after}s...")
                time.sleep(retry_after)
                retry_resp = requests.post(self.api_url, json=payload, timeout=self.timeout)
                return retry_resp.status_code == 200
            else:
                logger.error(f"Telegram notification failed (HTTP {resp.status_code}): {resp.text}")
                return False
        except Exception as e:
            logger.error(f"Telegram notification exception: {e}")
            return False
