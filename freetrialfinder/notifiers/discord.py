import requests
from typing import Dict, Any
from freetrialfinder.models import DealItem, ConfidenceLevel
from freetrialfinder.notifiers.base import BaseNotifier

class DiscordNotifier(BaseNotifier):
    """Sends deal alerts to Discord channels via Webhooks."""

    def __init__(self, webhook_url: str, timeout: int = 10):
        self.webhook_url = webhook_url
        self.timeout = timeout

    def format_payload(self, deal: DealItem) -> Dict[str, Any]:
        # Green for Direct IDE, Orange for Potential
        color = 0x2ECC71 if deal.confidence == ConfidenceLevel.DIRECT_IDE else 0xE67E22
        
        fields = [
            {"name": "Provider", "value": deal.provider, "inline": True},
            {"name": "Usability Score", "value": f"{deal.score}/100", "inline": True},
            {"name": "Category", "value": deal.category.value, "inline": True},
        ]

        if deal.promo_code:
            fields.append({"name": "Promo Code", "value": f"`{deal.promo_code}`", "inline": True})

        if deal.estimated_value:
            fields.append({"name": "Value", "value": deal.estimated_value, "inline": True})

        if deal.reasons:
            fields.append({"name": "Detected Signals", "value": ", ".join(deal.reasons[:3]), "inline": False})

        embed = {
            "title": deal.title[:256],
            "url": deal.url,
            "description": deal.summary[:1000] if deal.summary else "No additional description.",
            "color": color,
            "fields": fields,
            "footer": {
                "text": f"FreeTrialFinder • {deal.confidence.value} • Source: {deal.source}"
            },
        }

        return {"embeds": [embed]}

    def send(self, deal: DealItem) -> bool:
        if not self.webhook_url:
            return False

        payload = self.format_payload(deal)
        try:
            resp = requests.post(self.webhook_url, json=payload, timeout=self.timeout)
            return resp.status_code in [200, 204]
        except Exception:
            return False
