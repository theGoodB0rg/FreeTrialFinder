import pytest
from unittest.mock import MagicMock, patch
from freetrialfinder.models import DealItem, ConfidenceLevel, DealCategory
from freetrialfinder.notifiers.telegram import TelegramNotifier
from freetrialfinder.notifiers.discord import DiscordNotifier
from freetrialfinder.notifiers.console import ConsoleNotifier

@pytest.fixture
def sample_deal():
    return DealItem(
        id="deal-telegram-test",
        title="Together AI $25 Free API Credits for Claude & Llama",
        url="https://together.ai/signup?promo=DEV25",
        source="hacker_news",
        provider="Together AI",
        category=DealCategory.API_CREDITS,
        confidence=ConfidenceLevel.DIRECT_IDE,
        score=92,
        reasons=["mentions_api", "mentions_credits", "has_promo_code"],
        promo_code="DEV25",
        estimated_value="$25",
        summary="Use in IDE via OpenAI-compatible endpoint with code DEV25.",
    )

def test_telegram_message_formatting(sample_deal):
    notifier = TelegramNotifier(bot_token="fake-token", chat_id="123456")
    msg = notifier.format_message(sample_deal)
    
    assert "Together AI" in msg
    assert "DEV25" in msg
    assert "DIRECT_IDE" in msg or "IDE Ready" in msg or "VERIFIED" in msg.upper()
    assert "https://together.ai/signup?promo=DEV25" in msg
    assert "92/100" in msg or "92" in msg

@patch("requests.post")
def test_telegram_send_success(mock_post, sample_deal):
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {"ok": True}
    
    notifier = TelegramNotifier(bot_token="fake-token", chat_id="123456")
    success = notifier.send(sample_deal)
    
    assert success is True
    assert mock_post.called
    call_args = mock_post.call_args
    assert "https://api.telegram.org/botfake-token/sendMessage" in call_args[0][0]

def test_discord_payload_formatting(sample_deal):
    notifier = DiscordNotifier(webhook_url="https://discord.com/api/webhooks/fake/test")
    payload = notifier.format_payload(sample_deal)
    
    assert "embeds" in payload
    embed = payload["embeds"][0]
    assert embed["title"] == sample_deal.title
    assert embed["url"] == sample_deal.url
    assert any(f["name"] == "Promo Code" and f["value"] == "`DEV25`" for f in embed["fields"])

@patch("requests.post")
def test_discord_send_success(mock_post, sample_deal):
    mock_post.return_value.status_code = 204
    
    notifier = DiscordNotifier(webhook_url="https://discord.com/api/webhooks/fake/test")
    success = notifier.send(sample_deal)
    
    assert success is True
    assert mock_post.called

def test_console_notifier(sample_deal, capsys):
    notifier = ConsoleNotifier()
    notifier.send(sample_deal)
    captured = capsys.readouterr()
    assert "Together AI" in captured.out
    assert "DEV25" in captured.out
