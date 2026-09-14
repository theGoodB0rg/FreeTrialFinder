import urllib.parse
import xml.etree.ElementTree as ET
import requests
from typing import List
from datetime import datetime, timezone
from dateutil import parser as date_parser
from freetrialfinder.models import RawDeal
from freetrialfinder.sources.base import BaseSource

DEFAULT_QUERIES = [
    '"API credits" OR "Claude credits" OR "OpenAI credits"',
    '"Google Cloud credits" "Vertex AI"',
    '"AWS Bedrock" "credits" OR "activate"',
    '"OpenRouter" "free"',
]

class GoogleNewsSource(BaseSource):
    """Monitors Google News RSS for official announcements, startup credits, and promotional grants."""

    name: str = "google_news"
    BASE_URL = "https://news.google.com/rss/search"

    def __init__(self, queries: List[str] = None, timeout: int = 12):
        self.queries = queries or DEFAULT_QUERIES
        self.timeout = timeout

    def fetch(self) -> List[RawDeal]:
        deals: List[RawDeal] = []
        seen_links = set()

        for q in self.queries:
            try:
                params = {
                    "q": q,
                    "hl": "en-US",
                    "gl": "US",
                    "ceid": "US:en",
                }
                headers = {"User-Agent": "FreeTrialFinder/1.0 (Mozilla/5.0)"}
                resp = requests.get(self.BASE_URL, params=params, headers=headers, timeout=self.timeout)
                if resp.status_code != 200:
                    continue

                root = ET.fromstring(resp.text)
                for item in root.findall(".//item"):
                    title_elem = item.find("title")
                    link_elem = item.find("link")
                    desc_elem = item.find("description")
                    pub_elem = item.find("pubDate")

                    title = title_elem.text if title_elem is not None and title_elem.text else ""
                    link = link_elem.text if link_elem is not None and link_elem.text else ""
                    desc = desc_elem.text if desc_elem is not None and desc_elem.text else ""

                    if not link or link in seen_links:
                        continue
                    seen_links.add(link)

                    discovered_at = datetime.now(timezone.utc)
                    if pub_elem is not None and pub_elem.text:
                        try:
                            discovered_at = date_parser.parse(pub_elem.text)
                        except Exception:
                            pass

                    # Clean HTML tags from description if present
                    clean_desc = desc.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
                    content = f"{title}. {clean_desc}".strip()

                    deals.append(
                        RawDeal(
                            title=title,
                            url=link,
                            source=self.name,
                            content=content,
                            discovered_at=discovered_at,
                        )
                    )
            except Exception:
                continue

        return deals
