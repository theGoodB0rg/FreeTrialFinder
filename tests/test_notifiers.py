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
    assert "<code>DEV25</code>" in msg                       # tap to copy
    assert 'href="https://together.ai/signup?promo=DEV25"' in msg
    assert "not checked by AI" in msg                        # sample_deal is unverified

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
    assert any(f["name"] == "Code" and f["value"] == "`DEV25`" for f in embed["fields"])

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


def test_telegram_ai_alert_has_copy_button_and_safe_text(sample_deal):
    from freetrialfinder.notifiers.telegram import rich_text
    sample_deal.verified = True
    sample_deal.headline = "Together AI: $25 free API credits"
    sample_deal.why = "Covers weeks of <b>agent</b> calls."
    sample_deal.action = "Set `OPENAI_BASE_URL=https://api.together.xyz/v1` then go to https://evil.example/x"
    n = TelegramNotifier(bot_token="t", chat_id="1")
    msg = n.format_message(sample_deal)

    assert "Together AI: $25 free API credits</a>" in msg
    assert "&lt;b&gt;agent&lt;/b&gt;" in msg                  # AI text is escaped
    assert "<code>OPENAI_BASE_URL=https://api.together.xyz/v1</code>" in msg
    assert "<code>https://evil.example/x</code>" in msg      # AI URLs are never clickable
    assert msg.count("<a href=") == 1                        # the only link is the source URL
    assert "not checked by AI" not in msg
    row = n.keyboard(sample_deal)["inline_keyboard"][0]
    assert row[0]["copy_text"] == {"text": "DEV25"}
    assert row[1]["url"] == sample_deal.url
    assert rich_text("a `b` c") == "a <code>b</code> c"


@patch("requests.post")
def test_telegram_retries_without_buttons_if_rejected(mock_post, sample_deal):
    bad, good = MagicMock(status_code=400, text="bad button"), MagicMock(status_code=200)
    mock_post.side_effect = [bad, good]
    assert TelegramNotifier(bot_token="t", chat_id="1").send(sample_deal) is True
    assert "reply_markup" in mock_post.call_args_list[0].kwargs["json"]
    assert "reply_markup" not in mock_post.call_args_list[1].kwargs["json"]


@patch("requests.post", side_effect=Exception("https://api.telegram.org/botSECRET123/sendMessage timed out"))
def test_telegram_token_never_logged(mock_post, sample_deal, caplog):
    TelegramNotifier(bot_token="SECRET123", chat_id="1").send(sample_deal)
    assert "SECRET123" not in caplog.text


def test_telegram_digest_lists_deals_with_copy_buttons(sample_deal):
    sample_deal.verified = True
    other = sample_deal.model_copy(update={"id": "2", "title": "Unchecked thing", "promo_code": None, "verified": False})
    text, markup = TelegramNotifier(bot_token="t", chat_id="1").format_digest([sample_deal, other], more=3)
    assert "5 offers" in text and "Could not verify" in text and "+3 more" in text
    assert markup["inline_keyboard"][0][0]["copy_text"] == {"text": "DEV25"}


def test_telegram_digest_stays_under_length_limit(sample_deal):
    sample_deal.verified = True
    many = [sample_deal.model_copy(update={"id": str(i), "why": "w" * 230}) for i in range(40)]
    text, _ = TelegramNotifier(bot_token="t", chat_id="1").format_digest(many)
    assert len(text) <= 4096 and "more not shown" in text
