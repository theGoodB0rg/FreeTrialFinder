"""Tool-calling agent that verifies borderline deals.

Loop: the model sees the deal, may call fetch_page to read the offer, and must
finish by calling submit_verdict. Guardrails:
  * hard cap on model turns and on tool calls (no runaway loops or cost)
  * only the two declared tools are executed; anything else is refused
  * the verdict is schema-validated
  * evidence must be a quote that really appears in text the agent saw;
    an invented quote downgrades the verdict to UNSURE
  * any failure (API error, bad JSON, cap reached) fails OPEN to UNSURE, so
    the deal still goes out under the old heuristic rules and nothing is lost
"""

import json
import re
import uuid
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError

from freetrialfinder.agent.llm import ChatClient, LLMError
from freetrialfinder.agent.tools import ToolError, fetch_page
from freetrialfinder.agent.tracer import NullTracer
from freetrialfinder.models import DealItem


class Decision(str, Enum):
    KEEP = "keep"
    REJECT = "reject"
    UNSURE = "unsure"


class Verdict(BaseModel):
    decision: Decision
    usable_from_code: bool = False
    reason: str = ""
    evidence: str = ""
    flags: List[str] = Field(default_factory=list)
    steps: int = 0
    tool_calls: int = 0
    run_id: str = ""


class _VerdictArgs(BaseModel):
    decision: Decision
    usable_from_code: bool
    reason: str = Field(min_length=3, max_length=400)
    evidence: str = Field(default="", max_length=400)


SYSTEM_PROMPT = """You verify free AI credit, trial and promo offers for developers.
A deal is worth keeping only if ALL are true:
1. The offer is real and currently claimable (not expired, not a rumour, not a waitlist only).
2. It gives programmatic access: an API key, API credits, an OpenAI-compatible endpoint, cloud credits, or an IDE/coding-agent plan. Browser-only chat apps do not count.
3. It is free or has free credits/trial value.

Use fetch_page to read the deal URL before deciding. Fetch at most 2 pages.
Then call submit_verdict exactly once.
- evidence must be one full sentence (8+ words) copied exactly from a fetched page or the deal text that supports your decision. Headings or single phrases are not enough.
- Use decision "unsure" if the page could not be read or the facts are unclear. Never guess."""

TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "fetch_page",
            "description": "Fetch a public web page and return its readable text (truncated).",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "http(s) URL to read"}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_verdict",
            "description": "Submit the final decision for this deal. Call exactly once.",
            "parameters": {
                "type": "object",
                "properties": {
                    "decision": {"type": "string", "enum": ["keep", "reject", "unsure"]},
                    "usable_from_code": {"type": "boolean"},
                    "reason": {"type": "string", "description": "One or two sentences."},
                    "evidence": {"type": "string", "description": "Exact short quote supporting the decision."},
                },
                "required": ["decision", "usable_from_code", "reason", "evidence"],
            },
        },
    },
]


def _words(text: str) -> str:
    """Lowercase words only: ignores punctuation, quotes, spacing and escaped newlines,
    so formatting differences between the page and the model's quote do not matter."""
    text = (text or "").replace("\\n", " ").replace("\\t", " ").lower()
    return " ".join(re.findall(r"[a-z0-9]+", text))


_QUOTE_SPLIT = re.compile(r"\.\.\.|…|[\"“”]\s*(?:and|,|;|\+)\s*[\"“”]|\n|\\n")


def evidence_is_grounded(evidence: str, corpus: str) -> bool:
    """True when every substantial fragment of the quote appears in the corpus,
    and at least one fragment has 4+ words (so 'free' alone cannot pass)."""
    corpus_words = f" {_words(corpus)} "
    fragments = [_words(f) for f in _QUOTE_SPLIT.split(evidence or "")]
    fragments = [f for f in fragments if len(f.split()) >= 3]
    if not fragments or max(len(f.split()) for f in fragments) < 4:
        return False
    return all(f" {f} " in corpus_words for f in fragments)


class DealVerifier:
    def __init__(
        self,
        llm: ChatClient,
        fetcher: Callable[[str], Dict[str, str]] = fetch_page,
        tracer: Any = None,
        max_turns: int = 5,
        max_fetches: int = 2,
    ):
        self.llm = llm
        self.fetcher = fetcher
        self.tracer = tracer or NullTracer()
        self.max_turns = max_turns
        self.max_fetches = max_fetches

    def verify(self, deal: DealItem, context: str = "") -> Verdict:
        run_id = uuid.uuid4().hex[:12]
        seen_text: List[str] = [deal.title, deal.summary, context]
        fetches = 0
        tool_calls = 0
        flags: List[str] = []

        self.tracer.event(run_id, "start", deal_id=deal.id, title=deal.title, url=deal.url,
                          heuristic_score=deal.score, tier=deal.confidence.value)

        user_msg = (
            f"Deal title: {deal.title}\nURL: {deal.url}\nSource: {deal.source}\n"
            f"Provider guess: {deal.provider}\nHeuristic score: {deal.score}/100 ({', '.join(deal.reasons)})\n"
            f"Deal text: {(context or deal.summary)[:1500]}"
        )
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]

        for turn in range(1, self.max_turns + 1):
            try:
                reply = self.llm.chat(messages, TOOLS)
            except LLMError as exc:
                self.tracer.event(run_id, "llm_error", turn=turn, error=str(exc))
                return self._finish(run_id, Verdict(decision=Decision.UNSURE, reason="model call failed",
                                                     flags=flags + ["llm_error"], steps=turn, tool_calls=tool_calls))

            calls = reply.get("tool_calls") or []
            self.tracer.event(run_id, "model_turn", turn=turn, text=(reply.get("content") or "")[:500],
                              tool_calls=[c.get("function", {}).get("name") for c in calls])
            if not calls:
                flags.append("no_tool_call")
                messages.append({"role": "assistant", "content": reply.get("content") or ""})
                messages.append({"role": "user", "content": "Finish by calling submit_verdict."})
                continue

            messages.append({"role": "assistant", "content": reply.get("content") or "", "tool_calls": calls})
            for call in calls:
                tool_calls += 1
                name = call.get("function", {}).get("name")
                call_id = call.get("id") or f"call_{tool_calls}"
                try:
                    args = json.loads(call.get("function", {}).get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = None

                if name == "submit_verdict":
                    verdict = self._parse_verdict(args, seen_text, flags)
                    verdict.steps, verdict.tool_calls = turn, tool_calls
                    return self._finish(run_id, verdict)

                if name == "fetch_page":
                    result = self._run_fetch(run_id, args, fetches)
                    if result.get("attempted"):
                        fetches += 1
                    if result.get("ok"):
                        seen_text.append(result["text"])
                        # Plain text, not JSON, so the model quotes the page as written.
                        content = f"OK. Final URL: {result['url']} (HTTP {result['status']})\n\n{result['text']}"
                    else:
                        content = f"FAILED: {result['error']}"
                else:
                    flags.append("unknown_tool")
                    self.tracer.event(run_id, "guard", rule="unknown_tool", tool=name)
                    content = f"FAILED: tool {name!r} does not exist"
                messages.append({"role": "tool", "tool_call_id": call_id, "content": content})

        self.tracer.event(run_id, "guard", rule="max_turns", limit=self.max_turns)
        return self._finish(run_id, Verdict(decision=Decision.UNSURE, reason="agent did not finish within the turn limit",
                                             flags=flags + ["max_turns"], steps=self.max_turns, tool_calls=tool_calls))

    def _run_fetch(self, run_id: str, args: Optional[Dict[str, Any]], fetches: int) -> Dict[str, Any]:
        if fetches >= self.max_fetches:
            self.tracer.event(run_id, "guard", rule="max_fetches", limit=self.max_fetches)
            return {"ok": False, "error": "fetch limit reached, decide now with submit_verdict"}
        url = (args or {}).get("url", "")
        try:
            page = self.fetcher(url)
        except ToolError as exc:
            self.tracer.event(run_id, "tool", tool="fetch_page", url=url, ok=False, error=str(exc))
            return {"ok": False, "attempted": True, "error": str(exc)}
        except Exception as exc:  # never let a tool crash the run
            self.tracer.event(run_id, "tool", tool="fetch_page", url=url, ok=False, error=exc.__class__.__name__)
            return {"ok": False, "attempted": True, "error": "unexpected fetch error"}

        status, text = str(page.get("status", "")), page.get("text", "") or ""
        error = None
        if status and not status.startswith("2"):
            error = f"HTTP {status}: the site blocked or refused the request"
        elif len(text.strip()) < 40:
            error = "page has no readable text (likely rendered by JavaScript or behind a login)"
        self.tracer.event(run_id, "tool", tool="fetch_page", url=url, ok=error is None,
                          status=status, chars=len(text), error=error)
        if error:
            return {"ok": False, "attempted": True, "error": error + ". Decide from the deal text or answer unsure."}
        return {"ok": True, "attempted": True, **page}

    def _parse_verdict(self, args: Optional[Dict[str, Any]], seen_text: List[str], flags: List[str]) -> Verdict:
        try:
            parsed = _VerdictArgs(**(args or {}))
        except (ValidationError, TypeError):
            return Verdict(decision=Decision.UNSURE, reason="invalid verdict payload", flags=flags + ["invalid_verdict"])

        verdict = Verdict(decision=parsed.decision, usable_from_code=parsed.usable_from_code,
                          reason=parsed.reason, evidence=parsed.evidence, flags=list(flags))

        # Grounding guard: a KEEP or REJECT must quote something the agent actually saw.
        if verdict.decision != Decision.UNSURE:
            if not evidence_is_grounded(parsed.evidence, " ".join(seen_text)):
                verdict.flags.append("evidence_not_found")
                verdict.decision = Decision.UNSURE
                verdict.reason = f"downgraded: evidence quote not found in fetched text. Model said: {parsed.reason}"

        # Consistency guard: keep requires programmatic access.
        if verdict.decision == Decision.KEEP and not verdict.usable_from_code:
            verdict.flags.append("keep_without_api_access")
            verdict.decision = Decision.UNSURE
        return verdict

    def _finish(self, run_id: str, verdict: Verdict) -> Verdict:
        verdict.run_id = run_id
        self.tracer.event(run_id, "verdict", decision=verdict.decision.value, usable_from_code=verdict.usable_from_code,
                          reason=verdict.reason, evidence=verdict.evidence, flags=verdict.flags,
                          steps=verdict.steps, tool_calls=verdict.tool_calls)
        return verdict
