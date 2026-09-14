import os
import json
import pytest
from datetime import datetime, timezone
from freetrialfinder.state import StateManager
from freetrialfinder.models import DealItem, ConfidenceLevel, DealCategory

@pytest.fixture
def temp_state_file(tmp_path):
    return str(tmp_path / "seen_deals.json")

def test_state_manager_records_and_deduplicates(temp_state_file):
    sm = StateManager(storage_path=temp_state_file)
    
    assert sm.is_seen("deal-1") is False
    
    deal = DealItem(
        id="deal-1",
        title="OpenRouter Free Tier",
        url="https://openrouter.ai/free",
        source="hn",
        provider="OpenRouter",
        category=DealCategory.API_CREDITS,
        confidence=ConfidenceLevel.DIRECT_IDE,
        score=90,
        reasons=["mentions_api"],
        summary="Free openrouter models.",
    )
    
    sm.record_deal(deal)
    assert sm.is_seen("deal-1") is True
    
    # Reload from disk to ensure persistence
    sm_reloaded = StateManager(storage_path=temp_state_file)
    assert sm_reloaded.is_seen("deal-1") is True
    assert sm_reloaded.is_seen("deal-2") is False

def test_state_manager_filters_unseen(temp_state_file):
    sm = StateManager(storage_path=temp_state_file)
    
    deal1 = DealItem(
        id="deal-1",
        title="Deal 1",
        url="https://example.com/1",
        source="hn",
        provider="Anthropic",
        category=DealCategory.API_CREDITS,
        confidence=ConfidenceLevel.DIRECT_IDE,
        score=85,
        summary="Test 1",
    )
    deal2 = DealItem(
        id="deal-2",
        title="Deal 2",
        url="https://example.com/2",
        source="hn",
        provider="OpenAI",
        category=DealCategory.PROMO_CODE,
        confidence=ConfidenceLevel.POTENTIAL,
        score=65,
        summary="Test 2",
    )
    
    sm.record_deal(deal1)
    
    unseen = sm.filter_unseen([deal1, deal2])
    assert len(unseen) == 1
    assert unseen[0].id == "deal-2"
