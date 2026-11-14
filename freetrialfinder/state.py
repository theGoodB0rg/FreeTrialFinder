import os
import json
from datetime import datetime, timezone
from typing import Dict, Any, List
from pathlib import Path
from freetrialfinder.models import DealItem, Route

class StateManager:
    """Manages persistent deduplication state so users are only alerted once per deal."""

    def __init__(self, storage_path: str = "data/seen_deals.json"):
        self.storage_path = Path(storage_path)
        self.seen_data: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    self.seen_data = json.load(f)
            except Exception:
                self.seen_data = {}
        else:
            self.seen_data = {}

    def _save(self) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.storage_path.with_suffix(".tmp")
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(self.seen_data, f, indent=2, ensure_ascii=False)
            temp_path.replace(self.storage_path)
        except Exception:
            # Fallback direct write
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(self.seen_data, f, indent=2, ensure_ascii=False)

    def is_seen(self, deal_id: str) -> bool:
        return deal_id in self.seen_data

    def record_deal(self, deal: DealItem, sent: bool = False) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.seen_data[deal.id] = {
            "title": deal.title,
            "url": deal.url,
            "source": deal.source,
            "provider": deal.provider,
            "score": deal.score,
            "confidence": deal.confidence.value,
            "discovered_at": deal.discovered_at.isoformat(),
            "first_alerted_at": now,
            "route": deal.route.value if deal.route else None,
            "sent_at": now if sent else None,
            **{k: getattr(deal, k) for k in _EDITORIAL},
        }
        self._save()

    def filter_unseen(self, deals: List[DealItem]) -> List[DealItem]:
        return [d for d in deals if not self.is_seen(d.id)]

    def pending_digest(self) -> List[DealItem]:
        """Deals routed to the digest that have not been sent yet."""
        return [
            DealItem(id=deal_id, **{k: v for k, v in rec.items() if k in DealItem.model_fields and v is not None})
            for deal_id, rec in self.seen_data.items()
            if rec.get("route") == Route.DIGEST.value and not rec.get("sent_at")
        ]

    def last_digest_at(self):
        """When the last digest went out, from the digest records themselves."""
        stamps = [rec["sent_at"] for rec in self.seen_data.values()
                  if rec.get("route") == Route.DIGEST.value and rec.get("sent_at")]
        return datetime.fromisoformat(max(stamps)) if stamps else None

    def mark_sent(self, deal_ids: List[str]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        for deal_id in deal_ids:
            if deal_id in self.seen_data:
                self.seen_data[deal_id]["sent_at"] = now
        self._save()


# DealItem fields written by triage that the digest needs to render later.
_EDITORIAL = ("verified", "headline", "why", "action", "expires", "promo_code", "estimated_value", "reasons")
