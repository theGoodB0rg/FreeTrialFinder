import pytest
from unittest.mock import patch, MagicMock
from freetrialfinder.sources.github_curated import GitHubCuratedSource

MOCK_MARKDOWN = """
# Free LLM APIs for Coding

| Provider | Models Supported | Free Tier / Credits | Base URL / Compatibility | Link |
| :--- | :--- | :--- | :--- | :--- |
| [AgentRouter](https://agentrouter.org) | Claude 3.5 Sonnet, GPT-4o | $200 free signup credits | OpenAI-compatible `https://api.agentrouter.org/v1` | [Signup](https://agentrouter.org) |
| [Together AI](https://together.ai) | Llama 3, DeepSeek | $25 initial free credits | OpenAI-compatible `https://api.together.xyz/v1` | [Console](https://api.together.ai) |
| [OpenRouter](https://openrouter.ai) | Free models tier (Gemini Flash, Llama) | Unlimited free on :free tag | OpenAI-compatible `https://openrouter.ai/api/v1` | [Docs](https://openrouter.ai/docs) |
"""

@patch("requests.get")
def test_github_curated_source_fetch(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = MOCK_MARKDOWN
    mock_get.return_value = mock_resp

    source = GitHubCuratedSource()
    deals = source.fetch()

    assert len(deals) >= 3
    agent_deal = next(d for d in deals if "AgentRouter" in d.title)
    assert agent_deal.source == "github_curated"
    assert "https://agentrouter.org" in agent_deal.url
    assert "$200" in agent_deal.content
    assert "OpenAI-compatible" in agent_deal.content

@patch("requests.get")
def test_github_curated_source_network_error(mock_get):
    mock_get.side_effect = Exception("404 Repo Not Found")
    source = GitHubCuratedSource()
    deals = source.fetch()
    assert deals == []
