from datetime import datetime, timezone
from enum import Enum
import hashlib
import re
from typing import Optional, List
from urllib.parse import urlparse, urlunparse
from pydantic import BaseModel, Field

class ConfidenceLevel(str, Enum):
    DIRECT_IDE = "DIRECT_IDE"        # Verified API / IDE / Cursor / Aide / OpenRouter / Cloud credits
    POTENTIAL = "POTENTIAL"          # AI trial / promo needing user review (lenient)
    REJECTED = "REJECTED"            # Unrelated spam / non-AI / locked browser only

class Route(str, Enum):
    NOW = "now"          # pushed to the phone immediately
    DIGEST = "digest"    # held for the daily digest
    DROP = "drop"        # recorded as seen, never sent

class DealCategory(str, Enum):
    API_CREDITS = "api_credits"
    PROMO_CODE = "promo_code"
    FREE_TRIAL = "free_trial"
    CLOUD_CREDITS = "cloud_credits"
    IDE_DISCOUNT = "ide_discount"
    GATEWAY_TIER = "gateway_tier"

def generate_deal_id(url: str, title: str) -> str:
    """Generates a deterministic hash ID from normalized URL and title."""
    try:
        parsed = urlparse(url)
        # Strip tracking query params if any
        normalized_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
    except Exception:
        normalized_url = url.strip().lower()
    
    clean_title = re.sub(r"\s+", " ", title.strip().lower())
    payload = f"{normalized_url}::{clean_title}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

class RawDeal(BaseModel):
    id: str = ""
    title: str
    url: str
    source: str
    content: str = ""
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def __init__(self, **data):
        super().__init__(**data)
        if not self.id:
            self.id = generate_deal_id(self.url, self.title)

class DealItem(BaseModel):
    id: str
    title: str
    url: str
    source: str
    provider: str = "Unknown"
    category: DealCategory = DealCategory.API_CREDITS
    confidence: ConfidenceLevel = ConfidenceLevel.POTENTIAL
    score: int = 50
    reasons: List[str] = Field(default_factory=list)
    promo_code: Optional[str] = None
    estimated_value: Optional[str] = None
    summary: str = ""
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Set by triage. The editorial fields are written by the AI; empty without it.
    route: Optional[Route] = None
    verified: bool = False
    headline: str = ""
    why: str = ""
    action: str = ""
    expires: str = ""

    @property
    def display_title(self) -> str:
        return self.headline or self.title

    @property
    def is_ide_usable(self) -> bool:
        return self.confidence == ConfidenceLevel.DIRECT_IDE or (self.confidence == ConfidenceLevel.POTENTIAL and self.score >= 50)
