import json
from unittest.mock import MagicMock

import pytest

from freetrialfinder.agent import DealVerifier, Decision, JsonlTracer
from freetrialfinder.agent.evaluate import score
from freetrialfinder.agent.llm import LLMError
from freetrialfinder.agent.tools import ToolError, html_to_text, validate_url
from freetrialfinder.engine import FinderEngine
from freetrialfinder.models import ConfidenceLevel, DealItem, RawDeal


PAGE = "Sign up today and get $25 in free API credits. Use the OpenAI-compatible endpoint from any IDE."


def call(name, args, cid="c1"):
    return {"id": cid, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


class ScriptedLLM:
    """Returns pre-written assistant messages in order and records what it was sent."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.seen = []

    def chat(self, messages, tools):
        self.seen.append(list(messages))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def fetcher(url):
    return {"url": url, "status": "200", "text": PAGE}


def deal(**kw):
    base = dict(id="d1", title="Example AI $25 credits", url="https://example.com/promo", source="test",
                confidence=ConfidenceLevel.POTENTIAL, score=55, summary="Example offer")
    base.update(kw)
    return DealItem(**base)


def verdict_call(decision="keep", evidence="$25 in free API credits", usable=True):
    return {"content": "", "tool_calls": [call("submit_verdict", {
        "decision": decision, "usable_from_code": usable, "reason": "Real API credit offer.", "evidence": evidence}, "c2")]}


FETCH = {"content": "", "tool_calls": [call("fetch_page", {"url": "https://example.com/promo"})]}


def test_keep_when_evidence_is_grounded(tmp_path):
    llm = ScriptedLLM([FETCH, verdict_call()])
    v = DealVerifier(llm, fetcher=fetcher, tracer=JsonlTracer(str(tmp_path / "t.jsonl"))).verify(deal())
    assert v.decision == Decision.KEEP
    assert v.tool_calls == 2 and v.flags == []
    # The fetched page text was handed back to the model as a tool result.
    tool_msgs = [m for m in llm.seen[1] if m["role"] == "tool"]
    assert PAGE in tool_msgs[0]["content"]


def test_invented_evidence_is_downgraded():
    llm = ScriptedLLM([FETCH, verdict_call(evidence="unlimited free GPT-5 forever")])
    v = DealVerifier(llm, fetcher=fetcher).verify(deal())
    assert v.decision == Decision.UNSURE
    assert "evidence_not_found" in v.flags


def test_keep_without_api_access_is_downgraded():
    llm = ScriptedLLM([FETCH, verdict_call(usable=False)])
    v = DealVerifier(llm, fetcher=fetcher).verify(deal())
    assert v.decision == Decision.UNSURE
    assert "keep_without_api_access" in v.flags


def test_reject_is_kept_when_grounded():
    llm = ScriptedLLM([FETCH, verdict_call(decision="reject", usable=False, evidence="Use the OpenAI-compatible endpoint from any IDE")])
    assert DealVerifier(llm, fetcher=fetcher).verify(deal()).decision == Decision.REJECT


def test_turn_limit_fails_open():
    llm = ScriptedLLM([{"content": "thinking..."}] * 3)
    v = DealVerifier(llm, fetcher=fetcher, max_turns=3).verify(deal())
    assert v.decision == Decision.UNSURE
    assert "max_turns" in v.flags


def test_llm_error_fails_open():
    v = DealVerifier(ScriptedLLM([LLMError("HTTP 429")]), fetcher=fetcher).verify(deal())
    assert v.decision == Decision.UNSURE
    assert "llm_error" in v.flags


def test_fetch_limit_guard():
    llm = ScriptedLLM([FETCH, FETCH, FETCH, verdict_call()])
    calls = []
    v = DealVerifier(llm, fetcher=lambda u: calls.append(u) or fetcher(u), max_fetches=2).verify(deal())
    assert len(calls) == 2
    assert v.decision == Decision.KEEP


def test_unknown_tool_is_refused():
    bad = {"content": "", "tool_calls": [call("run_shell", {"cmd": "rm -rf /"})]}
    llm = ScriptedLLM([bad, FETCH, verdict_call()])
    v = DealVerifier(llm, fetcher=fetcher).verify(deal())
    assert "unknown_tool" in v.flags
    assert v.decision == Decision.KEEP


def test_tool_error_is_reported_to_model():
    def broken(url):
        raise ToolError("private or reserved IP addresses are blocked")
    llm = ScriptedLLM([FETCH, verdict_call(decision="unsure", evidence="")])
    v = DealVerifier(llm, fetcher=broken).verify(deal())
    assert v.decision == Decision.UNSURE
    assert "blocked" in [m for m in llm.seen[1] if m["role"] == "tool"][0]["content"]


def test_trace_file_records_each_step(tmp_path):
    path = tmp_path / "traces.jsonl"
    DealVerifier(ScriptedLLM([FETCH, verdict_call()]), fetcher=fetcher, tracer=JsonlTracer(str(path))).verify(deal())
    kinds = [json.loads(line)["kind"] for line in path.read_text(encoding="utf-8").splitlines()]
    assert kinds == ["start", "model_turn", "tool", "model_turn", "verdict"]


@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "ftp://example.com", "http://localhost:8080", "http://127.0.0.1/",
    "http://10.0.0.5/admin", "http://169.254.169.254/latest/meta-data", "http://[::1]/", "http://printer.local/",
])
def test_ssrf_guard_blocks_unsafe_urls(url):
    with pytest.raises(ToolError):
        validate_url(url, resolver=lambda host: True)


def test_ssrf_guard_blocks_hostnames_resolving_private():
    with pytest.raises(ToolError):
        validate_url("https://internal.example.com", resolver=lambda host: False)


def test_ssrf_guard_allows_public():
    assert validate_url("https://openrouter.ai/docs", resolver=lambda host: True).startswith("https://openrouter.ai")


def test_html_to_text_drops_scripts():
    text = html_to_text("<html><head><title>x</title></head><body><script>steal()</script><p>Free $10 credits</p></body></html>")
    assert "steal" not in text and "Free $10 credits" in text


class FixedVerifier:
    def __init__(self, decisions):
        self.decisions = decisions
        self.calls = []

    def verify(self, deal):
        self.calls.append(deal.title)
        from freetrialfinder.agent.verifier import Verdict
        return Verdict(decision=self.decisions[deal.title], reason="checked")


class DummySource:
    def __init__(self, items):
        self.items = items

    def fetch(self):
        return self.items


def test_engine_uses_agent_only_on_potential_deals(tmp_path):
    ide = RawDeal(title="OpenRouter free $20 credits for Claude Sonnet", url="https://openrouter.ai/promo",
                  source="dummy", content="OpenAI-compatible base_url for Aide and Cursor IDE.")
    maybe_good = RawDeal(title="Free $10 Gemini API credits", url="https://a.example/gemini", source="dummy",
                         content="Get free credits for the Gemini API")
    maybe_bad = RawDeal(title="Claude Pro free trial for 30 days", url="https://b.example/claude", source="dummy",
                        content="Anthropic offers a free trial of Claude Pro with credits")
    engine = FinderEngine(sources=[DummySource([ide, maybe_good, maybe_bad])], notifiers=[MagicMock()],
                          state_file=str(tmp_path / "seen.json"), min_score=40,
                          verifier=None)
    tiers = {d.title: d.confidence for d in engine.evaluate_deals([ide, maybe_good, maybe_bad])}
    potentials = [t for t, c in tiers.items() if c == ConfidenceLevel.POTENTIAL]
    assert potentials, "fixture needs at least one POTENTIAL deal"

    verifier = FixedVerifier({t: (Decision.REJECT if "Claude" in t else Decision.KEEP) for t in potentials})
    notifier = MagicMock()
    engine = FinderEngine(sources=[DummySource([ide, maybe_good, maybe_bad])], notifiers=[notifier],
                          state_file=str(tmp_path / "seen2.json"), min_score=40, verifier=verifier)
    sent = engine.run_cycle()

    assert sorted(verifier.calls) == sorted(potentials)          # DIRECT_IDE skipped the agent
    sent_titles = [d.title for d in sent]
    assert ide.title in sent_titles
    for t in potentials:
        assert (t in sent_titles) == ("Claude" not in t)         # rejected deals are not alerted
    # Rejected deals are remembered, so the next cycle neither re-verifies nor alerts them.
    verifier.calls.clear()
    assert engine.run_cycle() == []
    assert verifier.calls == []


def test_engine_respects_agent_budget(tmp_path):
    raws = [RawDeal(title=f"Free $10 Gemini API credits batch {i}", url=f"https://x.example/{i}", source="dummy",
                    content="Get free credits for the Gemini API") for i in range(5)]
    verifier = FixedVerifier({r.title: Decision.KEEP for r in raws})
    engine = FinderEngine(sources=[DummySource(raws)], notifiers=[MagicMock()],
                          state_file=str(tmp_path / "seen.json"), verifier=verifier, agent_max_per_run=2)
    engine.run_cycle()
    assert len(verifier.calls) == 2


def test_eval_scoring():
    m = score([
        {"label": "keep", "decision": "keep", "tool_calls": 2},
        {"label": "reject", "decision": "keep", "tool_calls": 2},
        {"label": "reject", "decision": "reject", "tool_calls": 1},
        {"label": "keep", "decision": "unsure", "tool_calls": 3},
    ])
    assert m["accuracy"] == round(2 / 3, 3)
    assert m["false_keep_rate"] == 0.5
    assert m["false_reject_rate"] == 0.0
    assert m["unsure_rate"] == 0.25
    assert m["avg_tool_calls"] == 2.0


# Regression cases taken from the first live eval run (see evals/README.md).
from freetrialfinder.agent.verifier import evidence_is_grounded

CF_PAGE = "Neurons . Our free allocation allows anyone to use a total of 10,000 Neurons per day at no charge . To use more"


@pytest.mark.parametrize("quote", [
    "Our free allocation allows anyone to use a total of 10,000 Neurons per day at no charge.",   # punctuation spacing
    '"Our free allocation allows anyone to use a total of 10,000 Neurons per day"',              # wrapped in quotes
    '"Our free allocation allows anyone" and "10,000 Neurons per day at no charge"',            # two joined quotes
    "Our free allocation\nallows anyone to use a total",                                        # escaped newline
    "Our free allocation allows anyone ... 10,000 Neurons per day",                              # ellipsis
])
def test_grounding_tolerates_formatting(quote):
    assert evidence_is_grounded(quote, CF_PAGE)


@pytest.mark.parametrize("quote", [
    "free",                                                         # too short to prove anything
    "Unlimited free GPT-5 credits forever for every developer",     # invented
    '"Our free allocation allows anyone" and "unlimited GPT-5 for life"',  # one real, one invented fragment
])
def test_grounding_rejects_weak_or_invented(quote):
    assert not evidence_is_grounded(quote, CF_PAGE)


@pytest.mark.parametrize("page", [
    {"url": "https://www.reddit.com/r/x", "status": "403", "text": "Blocked"},
    {"url": "https://ai.google.dev/x", "status": "200", "text": ""},
])
def test_blocked_or_empty_pages_are_reported_as_failures(page):
    llm = ScriptedLLM([FETCH, verdict_call(decision="unsure", evidence="")])
    DealVerifier(llm, fetcher=lambda u: page).verify(deal())
    tool_msg = [m for m in llm.seen[1] if m["role"] == "tool"][0]["content"]
    assert tool_msg.startswith("FAILED")


def test_failed_fetches_count_toward_limit():
    calls = []
    def blocked(url):
        calls.append(url)
        return {"url": url, "status": "403", "text": "Blocked"}
    llm = ScriptedLLM([FETCH, FETCH, FETCH, verdict_call(decision="unsure", evidence="")])
    DealVerifier(llm, fetcher=blocked, max_fetches=2).verify(deal())
    assert len(calls) == 2


# Rate-limit handling (from the Groq free-tier eval run: 8,000 tokens/minute).
import httpx
from freetrialfinder.agent.llm import OpenAICompatibleClient

OK_BODY = {"choices": [{"message": {"content": "hi"}}]}


def _client(responses, monkeypatch):
    seq = list(responses)
    monkeypatch.setattr(httpx, "post", lambda *a, **k: seq.pop(0))
    waits = []
    return OpenAICompatibleClient(api_key="k", model="m", sleep=waits.append), waits


def test_llm_retries_after_per_minute_limit(monkeypatch):
    limited = httpx.Response(429, text='{"error":{"message":"Rate limit reached ... Please try again in 9.5025s."}}')
    client, waits = _client([limited, httpx.Response(200, json=OK_BODY)], monkeypatch)
    assert client.chat([], [])["content"] == "hi"
    assert waits == [pytest.approx(10.0025)]


def test_llm_does_not_wait_out_daily_quota(monkeypatch):
    daily = httpx.Response(429, headers={"retry-after": "36000"}, text="free-models-per-day")
    client, waits = _client([daily], monkeypatch)
    with pytest.raises(LLMError):
        client.chat([], [])
    assert waits == []
