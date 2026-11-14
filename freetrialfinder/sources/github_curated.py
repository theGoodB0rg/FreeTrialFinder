import re
import requests
from typing import List
from freetrialfinder.models import RawDeal
from freetrialfinder.sources.base import BaseSource

CURATED_URLS = [
    "https://raw.githubusercontent.com/open-free-llm-api/awesome-freellm-apis/main/README.md",
    "https://raw.githubusercontent.com/inmve/free-ai-coding/main/README.md",
]

class GitHubCuratedSource(BaseSource):
    """Monitors curated GitHub directories for free developer AI models, API keys, and gateways."""

    name: str = "github_curated"

    def __init__(self, target_urls: List[str] = None, timeout: int = 15):
        self.target_urls = target_urls or CURATED_URLS
        self.timeout = timeout

    def fetch(self) -> List[RawDeal]:
        deals: List[RawDeal] = []

        for repo_url in self.target_urls:
            try:
                headers = {"User-Agent": "FreeTrialFinder/1.0"}
                resp = requests.get(repo_url, headers=headers, timeout=self.timeout)
                if resp.status_code != 200:
                    continue

                content = resp.text
                parsed_deals = self._parse_markdown(content, repo_url)
                deals.extend(parsed_deals)
            except Exception:
                continue

        return deals

    def _parse_markdown(self, markdown_text: str, repo_url: str) -> List[RawDeal]:
        """One deal per table row that has a link. Handles markdown and HTML links,
        and tables where a blank first cell means 'same provider as the row above'."""
        deals: List[RawDeal] = []
        last_provider = ""
        for line in markdown_text.splitlines():
            row = line.strip()
            if not (row.startswith("|") and row.endswith("|")):
                continue
            parts = [p.strip() for p in row.split("|")[1:-1]]
            if len(parts) < 3 or all(set(p) <= set("-: ") for p in parts):
                continue
            link = _first_link(row)
            if not link:
                continue
            url, link_text = link
            if link_text.lower().strip(" →»>") in _GENERIC_LINK_TEXT or not re.search(r"[A-Za-z0-9]", link_text):
                link_text = ""
            first_cell = _plain(parts[0])
            if first_cell.lower() in {"provider", "name", "service", "model"}:
                continue

            if _first_link(parts[0]):
                provider, name = "", link_text or first_cell
                last_provider = first_cell
            elif first_cell:
                provider, name = first_cell, link_text
                last_provider = first_cell
            else:
                provider, name = last_provider, link_text
            if not name:
                provider, name = "", provider
            if not name:
                continue
            label = f"{provider}: {name}" if provider and provider.lower() not in name.lower() else name
            title = f"{label} Free API / Developer Tier"
            details = " | ".join(_plain(p) for p in parts[1:])
            deals.append(RawDeal(title=title, url=url, source=self.name,
                                 content=f"{title}. Details: {details}. Source repo: {repo_url}"))
        return deals


_GENERIC_LINK_TEXT = {"", "get key", "get api key", "api key", "docs", "doc", "signup", "sign up", "console",
                      "link", "website", "site", "here", "try it", "visit"}
_MD_LINK = re.compile(r"\[([^\]]*)\]\((https?://[^)\s]+)\)")
_HTML_LINK = re.compile(r"<a\s[^>]*href=[\"'](https?://[^\"']+)[\"'][^>]*>(.*?)</a>", re.I)
_BARE_URL = re.compile(r"https?://[^\s|<>\"'`)]+")


def _plain(text: str) -> str:
    """Cell text without HTML tags or markdown link syntax."""
    text = _HTML_LINK.sub(lambda m: m.group(2), text)
    text = _MD_LINK.sub(lambda m: m.group(1), text)
    return re.sub(r"<[^>]+>|[`*]", "", text).strip()


def _first_link(text: str):
    """(url, link_text) for the first link in text, or None."""
    found = [(m.start(), m.group(2), _plain(m.group(1))) for m in _MD_LINK.finditer(text)]
    found += [(m.start(), m.group(1), _plain(m.group(2))) for m in _HTML_LINK.finditer(text)]
    if found:
        _, url, label = min(found)
        return url, label
    bare = _BARE_URL.search(text)
    return (bare.group(0), "") if bare else None
