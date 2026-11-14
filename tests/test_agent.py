import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from freetrialfinder.agent import DealVerifier, Decision, JsonlTracer
from freetrialfinder.agent.evaluate import score
from freetrialfinder.agent.llm import LLMError
from freetrialfinder.agent.tools import ToolError, html_to_text, validate_url
from freetrialfinder.engine import FinderEngine
from freetrialfinder.models import ConfidenceLevel, DealItem, RawDeal, Route


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
    """decisions maps title -> Decision, or -> a Verdict, or -> an Exception to raise."""

    def __init__(self, decisions):
        self.decisions = decisions
        self.calls = []

    def verify(self, deal):
        from freetrialfinder.agent.verifier import Verdict
        self.calls.append(deal.title)
        d = self.decisions[deal.title]
        if isinstance(d, Exception):
            raise d
        return d if isinstance(d, Verdict) else Verdict(decision=d, reason="checked")


class DummySource:
    def __init__(self, items):
        self.items = items

    def fetch(self):
        return self.items


def raw(title, days_old=0):
    return RawDeal(title=title, url="https://x.example/" + title.replace(" ", "-"), source="dummy",
                   content="Get free credits for the Gemini API",
                   discovered_at=datetime.now(timezone.utc) - timedelta(days=days_old))


def engine_for(tmp_path, raws, verifier, notifier=None, **kw):
    return FinderEngine(sources=[DummySource(raws)], notifiers=[notifier or MagicMock()],
                        state_file=str(tmp_path / "seen.json"), min_score=40, verifier=verifier, **kw)


def test_engine_routes_every_deal_by_verdict(tmp_path):
    from freetrialfinder.agent.verifier import Verdict
    urgent = Verdict(decision=Decision.KEEP, urgent=True, reason="ok", headline="Gemini: $10 free API credits",
                     why="Free calls for your agent.", promo_code="GEM10")
    raws = [raw("Free Gemini API credits now"), raw("Free Gemini API credits later"), raw("Free Gemini API chatter")]
    verifier = FixedVerifier({raws[0].title: urgent, raws[1].title: Decision.KEEP, raws[2].title: Decision.REJECT})
    notifier = MagicMock()
    engine = engine_for(tmp_path, raws, verifier, notifier)

    routed = {d.title: d for d in engine.run_cycle()}

    assert {t: d.route for t, d in routed.items()} == {
        raws[0].title: Route.NOW, raws[1].title: Route.DIGEST, raws[2].title: Route.DROP}
    assert notifier.send.call_count == 1                      # only the urgent one interrupts
    sent = notifier.send.call_args[0][0]
    assert sent.headline == "Gemini: $10 free API credits" and sent.promo_code == "GEM10" and sent.verified
    # Everything is remembered: the next cycle neither re-verifies nor alerts.
    verifier.calls.clear()
    assert engine.run_cycle() == [] and verifier.calls == []

    # The digest goes out once, with only the DIGEST deal.
    assert engine.send_digest() == 1
    digest_deals = notifier.send_digest.call_args[0][0]
    assert [d.title for d in digest_deals] == [raws[1].title]
    assert engine.send_digest() == 0
    assert not engine.digest_due(timedelta(hours=20)) and engine.digest_due(timedelta(0))


def test_heuristic_scorer_alone_never_reaches_the_phone_without_ai(tmp_path):
    potential = raw("Free Gemini API credits")
    notifier = MagicMock()
    routed = engine_for(tmp_path, [potential], verifier=None, notifier=notifier).run_cycle()
    assert routed[0].confidence == ConfidenceLevel.POTENTIAL and routed[0].route == Route.DIGEST
    notifier.send.assert_not_called()


def test_ai_outage_defers_then_digests_old_deals(tmp_path):
    fresh = [raw(f"Free Gemini API credits {i}") for i in range(4)]
    old = raw("Free Gemini API credits old", days_old=5)
    verifier = FixedVerifier({r.title: LLMError("down") for r in fresh + [old]})
    engine = engine_for(tmp_path, fresh + [old], verifier)

    routed = engine.run_cycle()

    assert len(verifier.calls) == 2                            # circuit breaker after 2 failures
    assert [d.title for d in routed] == [old.title]            # fresh deals wait for the next run
    assert routed[0].route == Route.DIGEST and "ai_unavailable" in routed[0].reasons
    assert all(not engine.state_manager.is_seen(r.id) for r in fresh)


def test_llm_error_verdict_counts_as_outage(tmp_path):
    from freetrialfinder.agent.verifier import Verdict
    failed = Verdict(decision=Decision.UNSURE, reason="model call failed", flags=["llm_error"])
    r = raw("Free Gemini API credits")
    engine = engine_for(tmp_path, [r], FixedVerifier({r.title: failed}))
    assert engine.run_cycle() == [] and not engine.state_manager.is_seen(r.id)


def test_failed_delivery_is_retried_next_run(tmp_path):
    from freetrialfinder.agent.verifier import Verdict
    r = raw("Free Gemini API credits")
    notifier = MagicMock()
    notifier.send.return_value = False
    keep = Verdict(decision=Decision.KEEP, urgent=True, reason="ok")
    engine = engine_for(tmp_path, [r], FixedVerifier({r.title: keep}), notifier)
    engine.run_cycle()
    assert not engine.state_manager.is_seen(r.id)


def test_engine_respects_agent_budget(tmp_path):
    # Deals beyond the budget are not routed or recorded; the next run picks them up.
    raws = [RawDeal(title=f"Free $10 Gemini API credits batch {i}", url=f"https://x.example/{i}", source="dummy",
                    content="Get free credits for the Gemini API") for i in range(5)]
    verifier = FixedVerifier({r.title: Decision.KEEP for r in raws})
    engine = FinderEngine(sources=[DummySource(raws)], notifiers=[MagicMock()],
                          state_file=str(tmp_path / "seen.json"), verifier=verifier, agent_max_per_run=2)
    routed = engine.run_cycle()
    assert len(verifier.calls) == 2 and len(routed) == 2


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


def verdict_call_with(evidence="$25 in free API credits", **extra):
    args = {"decision": "keep", "usable_from_code": True, "reason": "Real API credit offer.", "evidence": evidence, **extra}
    return {"content": "", "tool_calls": [call("submit_verdict", args, "c2")]}


def test_promo_code_must_appear_in_what_the_agent_read():
    v = DealVerifier(ScriptedLLM([FETCH, verdict_call_with(promo_code="FAKE99")]), fetcher=fetcher).verify(deal())
    assert v.promo_code == "" and "code_not_found" in v.flags
    page = "Sign up and enter code DEV25 to get $25 in free API credits from any IDE."
    v = DealVerifier(ScriptedLLM([FETCH, verdict_call_with(promo_code="DEV25", evidence="enter code DEV25 to get $25 in free API credits")]),
                     fetcher=lambda u: {"url": u, "status": "200", "text": page}).verify(deal())
    assert v.promo_code == "DEV25" and v.decision == Decision.KEEP


def test_only_a_grounded_keep_can_be_urgent():
    v = DealVerifier(ScriptedLLM([FETCH, verdict_call_with(urgent=True, evidence="invented quote that is nowhere at all")]),
                     fetcher=fetcher).verify(deal())
    assert v.decision == Decision.UNSURE and v.urgent is False


def test_long_editorial_text_is_clipped_not_rejected():
    v = DealVerifier(ScriptedLLM([FETCH, verdict_call_with(headline="x" * 500, why=None)]), fetcher=fetcher).verify(deal())
    assert v.decision == Decision.KEEP and len(v.headline) == 90 and v.why == ""


def test_profile_is_added_to_system_prompt():
    llm = ScriptedLLM([verdict_call()])
    DealVerifier(llm, fetcher=fetcher, profile="I only use Groq.").verify(deal())
    assert "I only use Groq." in llm.seen[0][0]["content"]
