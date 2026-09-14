import pytest
from datetime import datetime, timezone
from freetrialfinder.models import RawDeal, ConfidenceLevel, DealCategory
from freetrialfinder.filters.scorer import DealScorer

@pytest.fixture
def scorer():
    return DealScorer(min_score_threshold=40)

def test_scorer_identifies_direct_ide_deal(scorer):
    raw = RawDeal(
        title="OpenRouter is giving $20 in free API credits for Claude 3.5 and GPT-4o",
        url="https://news.ycombinator.com/item?id=9991",
        source="hacker_news",
        content="Developers can use these credits via the OpenAI-compatible base URL in Cursor, Aide, or Cline.",
        discovered_at=datetime.now(timezone.utc),
    )
    deal = scorer.evaluate(raw)
    assert deal.confidence == ConfidenceLevel.DIRECT_IDE
    assert deal.score >= 80
    assert deal.provider in ["OpenRouter", "Anthropic", "OpenAI"]
    assert deal.is_ide_usable is True
    assert any("api" in r.lower() or "ide" in r.lower() or "base_url" in r.lower() for r in deal.reasons)

def test_scorer_identifies_aws_bedrock_credits(scorer):
    raw = RawDeal(
        title="AWS Activate offers $1,000 Bedrock credits for Anthropic Claude access",
        url="https://aws.amazon.com/bedrock/credits",
        source="google_news",
        content="Apply now for AWS promotional credits usable for Claude 3 Sonnet and Haiku via Bedrock API.",
    )
    deal = scorer.evaluate(raw)
    assert deal.confidence == ConfidenceLevel.DIRECT_IDE
    assert deal.score >= 75
    assert "Bedrock" in deal.provider or "AWS" in deal.provider or "Anthropic" in deal.provider

def test_scorer_lenient_with_potential_trials(scorer):
    # As requested by user: don't be too quick to reject potential trials/promos
    raw = RawDeal(
        title="Claude Pro 1-Month Free Trial Promo Link",
        url="https://reddit.com/r/ClaudeAI/comments/abc123",
        source="reddit",
        content="Anthropic partnered with an educational program to provide 1 month free trial. Check link.",
    )
    deal = scorer.evaluate(raw)
    # Should NOT be rejected! Should be marked as POTENTIAL
    assert deal.confidence == ConfidenceLevel.POTENTIAL
    assert deal.score >= 40
    assert deal.provider == "Anthropic"
    assert deal.category in [DealCategory.FREE_TRIAL, DealCategory.PROMO_CODE]

def test_scorer_penalizes_pure_browser_chatbot_wrapper(scorer):
    raw = RawDeal(
        title="I built a free chatbot website where you can chat with Claude online",
        url="https://reddit.com/r/ClaudeAI/comments/xyz789",
        source="reddit",
        content="Visit my website to chat with Claude for free in your browser. No API key needed, strictly web chat UI only.",
    )
    deal = scorer.evaluate(raw)
    # The anti-chatbot penalty lowers the score significantly
    assert deal.score < 50
    # Confirms reasons mention anti-chatbot penalty
    assert any("chatbot" in r.lower() or "browser_only" in r.lower() for r in deal.reasons)

def test_scorer_rejects_pure_noise(scorer):
    raw = RawDeal(
        title="Free Bitcoin and Crypto Airdrop bonus 2026",
        url="https://spam.com/airdrop",
        source="reddit",
        content="Claim your free crypto tokens now by connecting your wallet.",
    )
    deal = scorer.evaluate(raw)
    assert deal.confidence == ConfidenceLevel.REJECTED
    assert deal.score < 30

def test_scorer_extracts_promo_codes(scorer):
    raw = RawDeal(
        title="Together AI $50 developer credit with coupon code TOGETHERDEV50",
        url="https://together.ai/promo",
        source="hacker_news",
        content="Enter promo code TOGETHERDEV50 at billing to receive $50 API credits for Llama and DeepSeek.",
    )
    deal = scorer.evaluate(raw)
    assert deal.promo_code == "TOGETHERDEV50"
    assert deal.confidence == ConfidenceLevel.DIRECT_IDE
