"""LLM verification agent for borderline (POTENTIAL tier) deals.

The heuristic scorer is fast and free but can only read keywords. Deals it is
unsure about (score 40-74) are handed to a small tool-calling agent that opens
the link, reads the page, and decides whether the offer is real and usable
from code. Every step is traced so the agent's behaviour can be inspected and
evaluated against hand-labelled deals.
"""

from freetrialfinder.agent.verifier import DealVerifier, Verdict, Decision
from freetrialfinder.agent.tracer import JsonlTracer, NullTracer

__all__ = ["DealVerifier", "Verdict", "Decision", "JsonlTracer", "NullTracer"]
