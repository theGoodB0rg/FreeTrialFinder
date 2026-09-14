import xml.etree.ElementTree as ET
import requests
from typing import List
from datetime import datetime, timezone
from dateutil import parser as date_parser
from freetrialfinder.models import RawDeal
from freetrialfinder.sources.base import BaseSource

DEFAULT_SUBREDDITS = ["ClaudeAI", "OpenAI", "LocalLLaMA", "ChatGPTCoding"]

class RedditSource(BaseSource):
    """Monitors developer-centric subreddits via public RSS feeds."""

    name: str = "reddit"

    def __init__(self, subreddits: List[str] = None, timeout: int = 10):
        self.subreddits = subreddits or DEFAULT_SUBREDDITS
        self.timeout = timeout

    def fetch(self) -> List[RawDeal]:
        deals: List[RawDeal] = []

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 FreeTrialFinder/1.0"
        }

        for sub in self.subreddits:
            url = f"https://www.reddit.com/r/{sub}/new.rss"
            try:
                resp = requests.get(url, headers=headers, timeout=self.timeout)
                if resp.status_code != 200:
                    # e.g. 429 rate limit or 403, safely skip this sub
                    continue

                root = ET.fromstring(resp.text)
                ns = {"atom": "http://www.w3.org/2005/Atom"}
                
                entries = root.findall("atom:entry", ns)
                if not entries:
                    entries = root.findall("entry")

                for entry in entries:
                    title_elem = entry.find("atom:title", ns)
                    if title_elem is None:
                        title_elem = entry.find("title")

                    link_elem = entry.find("atom:link", ns)
                    if link_elem is None:
                        link_elem = entry.find("link")

                    content_elem = entry.find("atom:content", ns)
                    if content_elem is None:
                        content_elem = entry.find("content")

                    updated_elem = entry.find("atom:updated", ns)
                    if updated_elem is None:
                        updated_elem = entry.find("updated")

                    title = title_elem.text if title_elem is not None and title_elem.text else ""
                    link = link_elem.attrib.get("href", "") if link_elem is not None else ""
                    content_raw = content_elem.text if content_elem is not None and content_elem.text else ""

                    if not link or not title:
                        continue

                    discovered_at = datetime.now(timezone.utc)
                    if updated_elem is not None and updated_elem.text:
                        try:
                            discovered_at = date_parser.parse(updated_elem.text)
                        except Exception:
                            pass

                    clean_content = f"{title}. {content_raw}".strip()

                    deals.append(
                        RawDeal(
                            title=title,
                            url=link,
                            source=f"{self.name}/r/{sub}",
                            content=clean_content,
                            discovered_at=discovered_at,
                        )
                    )
            except Exception:
                continue

        return deals
