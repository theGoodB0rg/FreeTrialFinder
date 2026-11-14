import time
from datetime import datetime, timedelta, timezone
from typing import Callable, List, Optional

from freetrialfinder.models import RawDeal, DealItem, ConfidenceLevel, Route
from freetrialfinder.filters.scorer import DealScorer
from freetrialfinder.state import StateManager
from freetrialfinder.sources.base import BaseSource
from freetrialfinder.notifiers.base import BaseNotifier
from freetrialfinder.sources.hacker_news import HackerNewsSource
from freetrialfinder.sources.github_curated import GitHubCuratedSource
from freetrialfinder.sources.google_news import GoogleNewsSource
from freetrialfinder.sources.reddit import RedditSource
from freetrialfinder.notifiers.console import ConsoleNotifier

# A deal the AI could not check is retried on later runs; once it is this old
# it goes to the digest marked unverified, so an AI outage never loses a deal.
UNVERIFIED_GRACE = timedelta(days=3)
# Stop calling the AI for the rest of a run after this many failures in a row.
MAX_CONSECUTIVE_AI_FAILURES = 2
DIGEST_MAX_ITEMS = 10


class FinderEngine:
    """Polls sources, scores, deduplicates, lets the AI triage, and routes alerts.

    Routes: NOW is pushed immediately, DIGEST waits for the daily digest,
    DROP is remembered as seen and never sent."""

    def __init__(
        self,
        sources: Optional[List[BaseSource]] = None,
        notifiers: Optional[List[BaseNotifier]] = None,
        state_file: str = "data/seen_deals.json",
        min_score: int = 40,
        verifier=None,
        agent_max_per_run: int = 15,
    ):
        self.verifier = verifier
        self.agent_max_per_run = agent_max_per_run
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
                raw_items.extend(source.fetch())
            except Exception:
                continue
        return raw_items

    def evaluate_deals(self, raw_items: List[RawDeal]) -> List[DealItem]:
        deals = (self.scorer.evaluate(raw) for raw in raw_items)
        return [d for d in deals if d.confidence != ConfidenceLevel.REJECTED]

    def run_cycle(self) -> List[DealItem]:
        """One poll cycle. Returns every deal that was routed this run."""
        new_deals = self.state_manager.filter_unseen(self.evaluate_deals(self.poll_all_sources()))
        new_deals.sort(key=lambda d: d.score, reverse=True)
        routed = self.triage(new_deals)

        pushed = 0
        for deal in routed:
            if deal.route == Route.NOW:
                if pushed:
                    time.sleep(0.5)  # stay under Telegram's per-chat rate limit
                pushed += 1
                if not self._deliver(lambda n: n.send(deal)):
                    continue  # not recorded, so the next run retries it
                self.state_manager.record_deal(deal, sent=True)
            else:
                self.state_manager.record_deal(deal)
        return routed

    # ---- triage -------------------------------------------------------------

    def triage(self, deals: List[DealItem]) -> List[DealItem]:
        """Give each deal a route. Deals left without one are retried next run."""
        if self.verifier is None:
            # No AI configured: only the high-confidence tier interrupts.
            for deal in deals:
                deal.route = Route.NOW if deal.confidence == ConfidenceLevel.DIRECT_IDE else Route.DIGEST
            return deals

        routed: List[DealItem] = []
        budget, failures = self.agent_max_per_run, 0
        for deal in deals:
            verdict = None
            if budget > 0 and failures < MAX_CONSECUTIVE_AI_FAILURES:
                budget -= 1
                try:
                    verdict = self.verifier.verify(deal)
                except Exception:
                    verdict = None
                if verdict is None or "llm_error" in verdict.flags:
                    failures += 1
                    verdict = None
                else:
                    failures = 0

            if verdict is not None:
                self._apply_verdict(deal, verdict)
                routed.append(deal)
            elif self._is_stale(deal):
                deal.route = Route.DIGEST
                deal.reasons.append("ai_unavailable")
                routed.append(deal)
        return routed

    @staticmethod
    def _apply_verdict(deal: DealItem, verdict) -> None:
        from freetrialfinder.agent.verifier import Decision

        if verdict.decision == Decision.KEEP:
            deal.route = Route.NOW if verdict.urgent else Route.DIGEST
        elif verdict.decision == Decision.REJECT:
            deal.route = Route.DROP
        else:
            deal.route = Route.DIGEST
        deal.verified = verdict.decision == Decision.KEEP
        deal.reasons.append(f"agent_{verdict.decision.value}")
        deal.headline, deal.why, deal.action, deal.expires = verdict.headline, verdict.why, verdict.action, verdict.expires
        # The AI read the page, so its (grounded) code replaces the regex guess.
        deal.promo_code = verdict.promo_code or None
        deal.estimated_value = verdict.value or deal.estimated_value

    @staticmethod
    def _is_stale(deal: DealItem) -> bool:
        found = deal.discovered_at if deal.discovered_at.tzinfo else deal.discovered_at.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - found > UNVERIFIED_GRACE

    # ---- delivery -----------------------------------------------------------

    def _deliver(self, send: Callable[[BaseNotifier], bool]) -> bool:
        """True if at least one external channel accepted the message (or none is configured)."""
        external = delivered = False
        for notifier in self.notifiers:
            try:
                ok = bool(send(notifier))
            except Exception:
                ok = False
            if getattr(notifier, "external", True):
                external = True
                delivered = delivered or ok
        return delivered or not external

    def digest_due(self, min_gap: timedelta) -> bool:
        last = self.state_manager.last_digest_at()
        return last is None or datetime.now(timezone.utc) - last >= min_gap

    def send_digest(self, max_items: int = DIGEST_MAX_ITEMS) -> int:
        """Send one message with the pending DIGEST deals. Returns how many were included."""
        pending = self.state_manager.pending_digest()
        if not pending:
            return 0
        pending.sort(key=lambda d: (d.verified, d.score), reverse=True)
        shown, hidden = pending[:max_items], len(pending) - max_items
        if not self._deliver(lambda n: n.send_digest(shown, more=max(0, hidden))):
            return 0
        self.state_manager.mark_sent([d.id for d in pending])
        return len(shown)

    def inspect(self) -> List[DealItem]:
        """Dry run: score current deals without alerting or touching state."""
        deals = self.evaluate_deals(self.poll_all_sources())
        deals.sort(key=lambda d: d.score, reverse=True)
        return deals
