import pytest
from unittest.mock import patch, MagicMock
from freetrialfinder.sources.reddit import RedditSource

MOCK_REDDIT_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>r/ClaudeAI</title>
  <entry>
    <title>Together AI is offering free $25 credits for Claude 3.5 Sonnet with code TOGETHER25</title>
    <link href="https://www.reddit.com/r/ClaudeAI/comments/1example/together_ai_credits/" />
    <content type="html">&lt;p&gt;You can use this in Cursor or Aide directly via their custom endpoint.&lt;/p&gt;</content>
    <updated>2026-09-14T14:30:00+00:00</updated>
  </entry>
</feed>
"""

@patch("requests.get")
def test_reddit_source_fetch(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = MOCK_REDDIT_FEED
    mock_get.return_value = mock_resp

    source = RedditSource(subreddits=["ClaudeAI"])
    deals = source.fetch()

    assert len(deals) >= 1
    assert "Together AI" in deals[0].title
    assert "reddit" in deals[0].source
    assert "https://www.reddit.com/r/ClaudeAI/comments/1example/together_ai_credits/" in deals[0].url

@patch("requests.get")
def test_reddit_source_handles_429_gracefully(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_get.return_value = mock_resp

    source = RedditSource(subreddits=["ClaudeAI"])
    deals = source.fetch()
    # Should not crash, returns empty list
    assert deals == []
