import html
import logging
import re
import time
from typing import Any, Dict, List, Optional

import requests

from freetrialfinder.models import DealItem
from freetrialfinder.notifiers.base import BaseNotifier

logger = logging.getLogger(__name__)

MAX_MESSAGE_CHARS = 3800  # Telegram's hard limit is 4096
MAX_COPY_BUTTONS = 8
_URL = re.compile(r"https?://[^\s<]+")


def rich_text(text: str) -> str:
    """Escape AI-written text for Telegram HTML. `backticked` parts and bare URLs
    become <code>: tap to copy, and never a clickable link (the only link in an
    alert is the deal URL that came from the source)."""
    parts = (text or "").split("`")
    out = []
    for i, part in enumerate(parts):
        escaped = html.escape(part)
        if i % 2:  # inside backticks
            out.append(f"<code>{escaped}</code>" if escaped.strip() else escaped)
        else:
            out.append(_URL.sub(lambda m: f"<code>{m.group(0)}</code>", escaped))
    return "".join(out)


def copy_button(label: str, value: str) -> Dict[str, Any]:
    return {"text": f"📋 {label}"[:60], "copy_text": {"text": value[:256]}}


class TelegramNotifier(BaseNotifier):
    """Sends deal alerts to Telegram via the Bot API."""

    def __init__(self, bot_token: str, chat_id: str, timeout: int = 15):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.timeout = timeout
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

    # ---- formatting ---------------------------------------------------------

    @staticmethod
    def _link(deal: DealItem) -> str:
        return f'<a href="{html.escape(deal.url, quote=True)}">{html.escape(deal.display_title)}</a>'

    @staticmethod
    def _facts(deal: DealItem) -> List[str]:
        facts = []
        if deal.promo_code:
            facts.append(f"<b>Code</b>  <code>{html.escape(deal.promo_code)}</code>")
        if deal.estimated_value:
            facts.append(f"<b>Value</b>  {html.escape(deal.estimated_value)}")
        if deal.expires:
            facts.append(f"<b>Expires</b>  {html.escape(deal.expires)}")
        return facts

    def format_message(self, deal: DealItem) -> str:
        lines = [f"<b>{self._link(deal)}</b>"]
        if deal.why:
            lines.append(f"<i>{rich_text(deal.why)}</i>")
        elif deal.summary:
            lines.append(html.escape(deal.summary[:280]))

        facts = self._facts(deal)
        if facts:
            lines += [""] + facts
        if deal.action:
            lines += ["", "<b>How to claim</b>", rich_text(deal.action)]

        footer = f"{html.escape(deal.provider)} · {html.escape(deal.source.replace('_', ' '))}"
        if not deal.verified:
            footer += " · not checked by AI"
        lines += ["", f"<i>{footer}</i>"]
        return "\n".join(lines)

    def keyboard(self, deal: DealItem) -> Dict[str, Any]:
        row = []
        if deal.promo_code:
            row.append(copy_button(f"Copy {deal.promo_code}", deal.promo_code))
        row.append({"text": "Open offer ↗", "url": deal.url})
        return {"inline_keyboard": [row]}

    def format_digest(self, deals: List[DealItem], more: int = 0) -> tuple:
        """Returns (html, reply_markup). Items are added until the length budget is used."""
        verified = [d for d in deals if d.verified]
        unchecked = [d for d in deals if not d.verified]
        header = f"<b>Daily digest</b> · {len(deals) + more} offer{'s' if len(deals) + more != 1 else ''} worth a look"
        blocks, buttons, skipped = [header], [], 0
        size = len(header)

        def add(block: str) -> bool:
            nonlocal size
            if size + len(block) > MAX_MESSAGE_CHARS:
                return False
            blocks.append(block)
            size += len(block) + 2
            return True

        for n, deal in enumerate(verified, 1):
            parts = [f"<b>{n}. {self._link(deal)}</b>"]
            if deal.why:
                parts.append(rich_text(deal.why))
            extras = [f"<code>{html.escape(deal.promo_code)}</code>"] if deal.promo_code else []
            extras += [html.escape(x) for x in (deal.estimated_value, deal.expires and f"until {deal.expires}") if x]
            if extras:
                parts.append(" · ".join(extras))
            if not add("\n".join(parts)):
                skipped += 1
            elif deal.promo_code and len(buttons) < MAX_COPY_BUTTONS:
                buttons.append([copy_button(f"{n} · {deal.promo_code}", deal.promo_code)])

        if unchecked:
            add("<b>Could not verify</b> <i>(page unreadable or AI unavailable)</i>")
            for deal in unchecked:
                if not add(f"• {self._link(deal)}"):
                    skipped += 1

        if more + skipped:
            add(f"<i>+{more + skipped} more not shown</i>")
        markup = {"inline_keyboard": buttons} if buttons else None
        return "\n\n".join(blocks), markup

    # ---- sending ------------------------------------------------------------

    def send(self, deal: DealItem) -> bool:
        return self._post(self.format_message(deal), self.keyboard(deal))

    def send_digest(self, deals: List[DealItem], more: int = 0) -> bool:
        text, markup = self.format_digest(deals, more)
        return self._post(text, markup)

    def _post(self, text: str, reply_markup: Optional[Dict[str, Any]] = None) -> bool:
        if not self.bot_token or not self.chat_id:
            logger.warning("Telegram credentials not configured; skipping notification.")
            return False
        payload: Dict[str, Any] = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "link_preview_options": {"is_disabled": True},
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            resp = requests.post(self.api_url, json=payload, timeout=self.timeout)
            if resp.status_code == 429:
                retry_after = resp.json().get("parameters", {}).get("retry_after", 2)
                time.sleep(min(retry_after, 30))
                resp = requests.post(self.api_url, json=payload, timeout=self.timeout)
            if resp.status_code == 400 and reply_markup:
                # A client or URL that rejects the buttons must not cost us the alert.
                logger.warning("Telegram rejected buttons (%s); resending without them.", resp.text[:200])
                payload = {k: v for k, v in payload.items() if k != "reply_markup"}
                resp = requests.post(self.api_url, json=payload, timeout=self.timeout)
            if resp.status_code == 200:
                return True
            logger.error("Telegram send failed (HTTP %s): %s", resp.status_code, resp.text[:300])
            return False
        except Exception as e:
            # The bot token is part of the URL; keep it out of logs.
            logger.error("Telegram send exception: %s", str(e).replace(self.bot_token, "***"))
            return False
