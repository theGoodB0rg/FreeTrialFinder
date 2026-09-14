from typing import List, Optional
from freetrialfinder.models import RawDeal, DealItem, ConfidenceLevel
from freetrialfinder.filters.scorer import DealScorer
from freetrialfinder.state import StateManager
from freetrialfinder.sources.base import BaseSource
from freetrialfinder.notifiers.base import BaseNotifier
from freetrialfinder.sources.hacker_news import HackerNewsSource
from freetrialfinder.sources.github_curated import GitHubCuratedSource
from freetrialfinder.sources.google_news import GoogleNewsSource
from freetrialfinder.sources.reddit import RedditSource
from freetrialfinder.notifiers.console import ConsoleNotifier

class FinderEngine:
    """Core orchestrator that runs data ingestion, scoring, deduplication, and alerting."""

    def __init__(
        self,
        sources: Optional[List[BaseSource]] = None,
        notifiers: Optional[List[BaseNotifier]] = None,
        state_file: str = "data/seen_deals.json",
        min_score: int = 40,
    ):
        self.sources = sources if sources is not None else [
            GitHubCuratedSource(),
            HackerNewsSource(),
            GoogleNewsSource(),
            RedditSource(),
        ]
        self.notifiers = notifiers if notifiers is not None else [ConsoleNotifier()]
        self.state_manager = StateManager(storage_path=state_file)
        self.scorer = DealScorer(min_score_threshold=min_score)

    def poll_all_sources(self) -> List[RawDeal]:
        raw_items: List[RawDeal] = []
        for source in self.sources:
            try:
                items = source.fetch()
                raw_items.extend(items)
            except Exception:
                continue
        return raw_items

    def evaluate_deals(self, raw_items: List[RawDeal]) -> List[DealItem]:
        qualified: List[DealItem] = []
        for raw in raw_items:
            deal = self.scorer.evaluate(raw)
            if deal.confidence != ConfidenceLevel.REJECTED:
                qualified.append(deal)
        return qualified

    def run_cycle(self) -> List[DealItem]:
        """Executes one complete polling, scoring, deduplication, and dispatch cycle."""
        raw_items = self.poll_all_sources()
        qualified_deals = self.evaluate_deals(raw_items)
        
        # Deduplicate against persistent state
        new_deals = self.state_manager.filter_unseen(qualified_deals)
        # Prioritize highest scoring deals first
        new_deals.sort(key=lambda d: d.score, reverse=True)

        # Dispatch alerts for new deals with pacing to respect API rate limits
        import time
        for i, deal in enumerate(new_deals):
            for notifier in self.notifiers:
                try:
                    notifier.send(deal)
                except Exception:
                    pass
            self.state_manager.record_deal(deal)
            if i < len(new_deals) - 1:
                time.sleep(0.5)

        return new_deals

    def inspect(self) -> List[DealItem]:
        """Runs a dry-run check without sending alerts or mutating saved state."""
        raw_items = self.poll_all_sources()
        qualified_deals = self.evaluate_deals(raw_items)
        # Sort by score descending
        qualified_deals.sort(key=lambda d: d.score, reverse=True)
        return qualified_deals
