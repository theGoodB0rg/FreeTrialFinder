from typing import Any, Dict, List

import requests

from freetrialfinder.models import DealItem, Route
from freetrialfinder.notifiers.base import BaseNotifier


class DiscordNotifier(BaseNotifier):
    """Sends deal alerts to Discord channels via webhooks."""

    def __init__(self, webhook_url: str, timeout: int = 10):
        self.webhook_url = webhook_url
        self.timeout = timeout

    def format_payload(self, deal: DealItem) -> Dict[str, Any]:
        color = 0x2ECC71 if deal.verified or deal.route == Route.NOW else 0xE67E22
        fields = []
        if deal.promo_code:
            fields.append({"name": "Code", "value": f"`{deal.promo_code}`", "inline": True})
        if deal.estimated_value:
            fields.append({"name": "Value", "value": deal.estimated_value, "inline": True})
        if deal.expires:
            fields.append({"name": "Expires", "value": deal.expires, "inline": True})
        if deal.action:
            fields.append({"name": "How to claim", "value": deal.action[:1000], "inline": False})

        footer = f"{deal.provider} · {deal.source}" + ("" if deal.verified else " · not checked by AI")
        embed = {
            "title": deal.display_title[:256],
            "url": deal.url,
            "description": (deal.why or deal.summary or "")[:1000],
            "color": color,
            "fields": fields,
            "footer": {"text": footer},
        }
        return {"embeds": [embed]}

    def format_digest(self, deals: List[DealItem], more: int = 0) -> str:
        lines = [f"**Daily digest** · {len(deals) + more} offers worth a look"]
        for deal in deals:
            code = f" · `{deal.promo_code}`" if deal.promo_code else ""
            tag = "" if deal.verified else " _(unverified)_"
            lines.append(f"• [{deal.display_title}](<{deal.url}>){code}{tag}")
        if more:
            lines.append(f"_+{more} more not shown_")
        return "\n".join(lines)[:1990]

    def send(self, deal: DealItem) -> bool:
        return self._post(self.format_payload(deal))

    def send_digest(self, deals: List[DealItem], more: int = 0) -> bool:
        return self._post({"content": self.format_digest(deals, more)})

    def _post(self, payload: Dict[str, Any]) -> bool:
        if not self.webhook_url:
            return False
        try:
            resp = requests.post(self.webhook_url, json=payload, timeout=self.timeout)
            return resp.status_code in (200, 204)
        except Exception:
            return False
