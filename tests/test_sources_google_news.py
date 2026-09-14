import pytest
from unittest.mock import patch, MagicMock
from freetrialfinder.sources.google_news import GoogleNewsSource

MOCK_RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Google News - AI Credits</title>
    <item>
      <title>Google Cloud announces $350k startup credits including Vertex AI and Gemini models</title>
      <link>https://news.google.com/rss/articles/CBMiTEST1234</link>
      <pubDate>Mon, 14 Sep 2026 12:00:00 GMT</pubDate>
      <description>&lt;a href="https://cloud.google.com/startup"&gt;Google Cloud for Startups expands Vertex AI credits...&lt;/a&gt;</description>
    </item>
    <item>
      <title>Anthropic expands education program with free Claude API access</title>
      <link>https://news.google.com/rss/articles/CBMiTEST5678</link>
      <pubDate>Mon, 14 Sep 2026 11:00:00 GMT</pubDate>
      <description>Students and researchers get free API credits for Claude 3.5 Sonnet.</description>
    </item>
  </channel>
</rss>
"""

@patch("requests.get")
def test_google_news_source_fetch(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = MOCK_RSS_XML
    mock_get.return_value = mock_resp

    source = GoogleNewsSource()
    deals = source.fetch()

    assert len(deals) == 2
    assert "Google Cloud announces $350k startup credits" in deals[0].title
    assert "https://news.google.com/rss/articles/CBMiTEST1234" in deals[0].url
    assert deals[0].source == "google_news"
    assert "Vertex AI" in deals[0].content

@patch("requests.get")
def test_google_news_source_error(mock_get):
    mock_get.side_effect = Exception("Connection reset")
    source = GoogleNewsSource()
    deals = source.fetch()
    assert deals == []
