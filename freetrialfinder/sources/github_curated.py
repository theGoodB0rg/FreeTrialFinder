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
        deals: List[RawDeal] = []
        lines = markdown_text.splitlines()

        for line in lines:
            line_str = line.strip()
            # Check for Markdown table row with at least 3 columns
            if line_str.startswith("|") and line_str.endswith("|"):
                parts = [p.strip() for p in line_str.split("|")[1:-1]]
                # Skip header and separator lines
                if len(parts) >= 3 and not all(set(p).issubset({"-", ":", " "}) for p in parts):
                    provider_col = parts[0]
                    # Check if provider contains markdown link
                    link_match = re.search(r"\[([^\]]+)\]\((https?://[^\)]+)\)", provider_col)
                    if not link_match and len(parts) >= 5:
                        # Check last column for link
                        link_match = re.search(r"\[([^\]]+)\]\((https?://[^\)]+)\)", parts[-1]) or re.search(r"(https?://[^\s]+)", parts[-1])
                    
                    if link_match:
                        name = link_match.group(1) if len(link_match.groups()) >= 2 else parts[0]
                        url = link_match.group(2) if len(link_match.groups()) >= 2 else link_match.group(1)
                    else:
                        url_search = re.search(r"https?://[^\s|]+", line_str)
                        if not url_search:
                            continue
                        url = url_search.group(0)
                        name = parts[0]

                    clean_name = re.sub(r"[\[\]\(\)]", "", name).strip()
                    if clean_name.lower() in {"provider", "name", "service"}:
                        continue

                    details = " | ".join(parts[1:])
                    title = f"{clean_name} Free API / Developer Tier"
                    full_content = f"{title}. Details: {details}. Source repo: {repo_url}"

                    deals.append(
                        RawDeal(
                            title=title,
                            url=url,
                            source=self.name,
                            content=full_content,
                        )
                    )

        return deals
