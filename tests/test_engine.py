import pytest
from unittest.mock import MagicMock
from freetrialfinder.engine import FinderEngine
from freetrialfinder.models import RawDeal, DealItem, ConfidenceLevel, DealCategory

class DummySource:
    def __init__(self, items):
        self.items = items
    def fetch(self):
        return self.items

def test_engine_end_to_end(tmp_path):
    state_file = str(tmp_path / "seen.json")
    
    raw_ide = RawDeal(
        title="OpenRouter free $20 credits for Claude Sonnet",
        url="https://openrouter.ai/promo",
        source="dummy",
        content="OpenAI-compatible base_url for Aide and Cursor IDE.",
    )
    raw_junk = RawDeal(
        title="Win free casino chips and bitcoin",
        url="https://junk.com",
        source="dummy",
        content="Play roulette online.",
    )
    
    source = DummySource([raw_ide, raw_junk])
    notifier = MagicMock()
    
    engine = FinderEngine(
        sources=[source],
        notifiers=[notifier],
        state_file=state_file,
        min_score=40,
    )
    
    # Run cycle 1
    new_deals = engine.run_cycle()
    
    assert len(new_deals) == 1
    assert new_deals[0].url == "https://openrouter.ai/promo"
    assert new_deals[0].confidence == ConfidenceLevel.DIRECT_IDE
    assert notifier.send.call_count == 1
    
    # Run cycle 2 with same source items
    new_deals_2 = engine.run_cycle()
    # Should be deduplicated!
    assert len(new_deals_2) == 0
    assert notifier.send.call_count == 1  # Not sent again
