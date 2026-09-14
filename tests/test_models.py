from datetime import datetime, timezone
import pytest
from freetrialfinder.models import RawDeal, DealItem, ConfidenceLevel, DealCategory

def test_raw_deal_creation():
    raw = RawDeal(
        title="OpenRouter announces $10 free credits for Claude 3.5 Sonnet",
        url="https://news.ycombinator.com/item?id=12345",
        source="hacker_news",
        content="We are providing $10 credits to all developers using our OpenAI-compatible endpoint with Claude Sonnet.",
        discovered_at=datetime.now(timezone.utc),
    )
    assert raw.title == "OpenRouter announces $10 free credits for Claude 3.5 Sonnet"
    assert raw.source == "hacker_news"
    assert raw.id is not None
    assert len(raw.id) > 10

def test_raw_deal_deterministic_id():
    raw1 = RawDeal(
        title="Same Title",
        url="https://example.com/deal?ref=abc",
        source="hn",
        content="hello",
    )
    raw2 = RawDeal(
        title="Same Title",
        url="https://example.com/deal?ref=xyz",  # same base canonical path
        source="hn",
        content="hello",
    )
    # Different URLs should generate distinct or normalized IDs
    raw3 = RawDeal(
        title="Same Title",
        url="https://example.com/deal?ref=abc",
        source="hn",
        content="hello",
    )
    assert raw1.id == raw3.id

def test_deal_item_creation():
    deal = DealItem(
        id="deal-123",
        title="Anthropic Startup Credits: Up to $25,000 for Claude API",
        url="https://www.anthropic.com/startups",
        source="google_news",
        provider="Anthropic",
        category=DealCategory.API_CREDITS,
        confidence=ConfidenceLevel.DIRECT_IDE,
        score=95,
        reasons=["mentions_anthropic", "mentions_api", "mentions_credits"],
        promo_code=None,
        estimated_value="$25,000",
        summary="Official Anthropic startup program offering developer API credits for Claude models.",
    )
    assert deal.confidence == ConfidenceLevel.DIRECT_IDE
    assert deal.score == 95
    assert deal.is_ide_usable is True

def test_deal_item_potential_tier():
    deal = DealItem(
        id="deal-456",
        title="Gemini Advanced 2-month Free Trial Promotion",
        url="https://example.com/gemini-promo",
        source="reddit",
        provider="Google",
        category=DealCategory.FREE_TRIAL,
        confidence=ConfidenceLevel.POTENTIAL,
        score=55,
        reasons=["mentions_gemini", "mentions_trial"],
        promo_code="GEMINI60",
        estimated_value="2 months",
        summary="Google offering 2 months trial for Gemini. Verify API access.",
    )
    assert deal.confidence == ConfidenceLevel.POTENTIAL
    assert deal.promo_code == "GEMINI60"
