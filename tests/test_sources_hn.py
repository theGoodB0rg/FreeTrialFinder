import pytest
from unittest.mock import patch, MagicMock
from freetrialfinder.sources.hacker_news import HackerNewsSource

MOCK_HN_RESPONSE = {
    "hits": [
        {
            "objectID": "41001",
            "title": "Show HN: Free OpenAI-compatible proxy with $10 starter credits",
            "url": "https://example.com/proxy",
            "author": "dev_guru",
            "story_text": "Use our endpoint in Aide or Cursor to test Claude 3.5 Sonnet.",
            "created_at": "2026-09-14T12:00:00Z",
        },
        {
            "objectID": "41002",
            "title": "Anthropic introduces Claude for Startups with $25k credits",
            "url": "https://anthropic.com/startups",
            "author": "simonw",
            "story_text": None,
            "created_at": "2026-09-14T10:00:00Z",
        },
    ]
}

@patch("requests.get")
def test_hacker_news_source_fetch(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = MOCK_HN_RESPONSE
    mock_get.return_value = mock_resp

    source = HackerNewsSource()
    deals = source.fetch()

    assert len(deals) == 2
    assert deals[0].source == "hacker_news"
    assert "Show HN: Free OpenAI-compatible" in deals[0].title
    assert deals[0].url == "https://example.com/proxy"
    assert "Aide or Cursor" in deals[0].content

@patch("requests.get")
def test_hacker_news_source_error_handling(mock_get):
    mock_get.side_effect = Exception("Network timeout")

    source = HackerNewsSource()
    deals = source.fetch()
    assert deals == []
