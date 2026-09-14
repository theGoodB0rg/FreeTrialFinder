import os
import json
from datetime import datetime, timezone
from typing import Dict, Any, List
from pathlib import Path
from freetrialfinder.models import DealItem

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

    def record_deal(self, deal: DealItem) -> None:
        self.seen_data[deal.id] = {
            "title": deal.title,
            "url": deal.url,
            "provider": deal.provider,
            "score": deal.score,
            "confidence": deal.confidence.value,
            "discovered_at": deal.discovered_at.isoformat(),
            "first_alerted_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save()

    def filter_unseen(self, deals: List[DealItem]) -> List[DealItem]:
        return [d for d in deals if not self.is_seen(d.id)]
