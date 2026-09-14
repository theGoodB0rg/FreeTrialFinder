import requests
from typing import List
from datetime import datetime, timezone
from dateutil import parser as date_parser
from freetrialfinder.models import RawDeal
from freetrialfinder.sources.base import BaseSource

class HackerNewsSource(BaseSource):
    """Monitors Hacker News posts and Show HNs via the free Algolia HN API."""

    name: str = "hacker_news"
    BASE_URL = "https://hn.algolia.com/api/v1/search_by_date"
    SEARCH_QUERIES = [
        "api credits",
        "claude credits",
        "openai credits",
        "openrouter credits",
        "bedrock credits",
        "free tokens",
    ]

    def __init__(self, queries: List[str] = None, timeout: int = 10):
        self.queries = queries or self.SEARCH_QUERIES
        self.timeout = timeout

    def fetch(self) -> List[RawDeal]:
        deals: List[RawDeal] = []
        seen_ids = set()

        for query in self.queries:
            try:
                params = {
                    "query": query,
                    "tags": "story",
                    "hitsPerPage": 15,
                }
                headers = {"User-Agent": "FreeTrialFinder/1.0"}
                resp = requests.get(self.BASE_URL, params=params, headers=headers, timeout=self.timeout)
                if resp.status_code != 200:
                    continue

                data = resp.json()
                for hit in data.get("hits", []):
                    obj_id = hit.get("objectID")
                    if not obj_id or obj_id in seen_ids:
                        continue
                    seen_ids.add(obj_id)

                    title = hit.get("title") or ""
                    url = hit.get("url") or f"https://news.ycombinator.com/item?id={obj_id}"
                    story_text = hit.get("story_text") or ""
                    content = f"{title}. {story_text}".strip()

                    created_str = hit.get("created_at")
                    discovered_at = datetime.now(timezone.utc)
                    if created_str:
                        try:
                            discovered_at = date_parser.isoparse(created_str)
                        except Exception:
                            pass

                    deals.append(
                        RawDeal(
                            title=title,
                            url=url,
                            source=self.name,
                            content=content,
                            discovered_at=discovered_at,
                        )
                    )
            except Exception:
                # Silently catch timeouts / network errors to ensure resilience
                continue

        return deals
