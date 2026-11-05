"""Offline evaluation of the verification agent against hand-labelled deals.

Each line of the labelled file is JSON: {"title", "url", "summary", "label"}
where label is "keep" or "reject" (the human answer).

Metrics reported:
  accuracy          share of decided deals (keep/reject) that match the label
  false_keep_rate   rejects the agent wrongly kept  (the costly mistake: spam alerts)
  false_reject_rate keeps the agent wrongly rejected (missed real deals)
  unsure_rate       share the agent declined to decide
  avg_tool_calls    cost proxy
"""

import json
from typing import Any, Dict, List

from freetrialfinder.agent.verifier import Decision, DealVerifier
from freetrialfinder.models import DealItem, ConfidenceLevel, generate_deal_id


def load_labelled(path: str) -> List[Dict[str, Any]]:
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("//"):
                rows.append(json.loads(line))
    return rows


def run_eval(verifier: DealVerifier, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    results = []
    for row in rows:
        deal = DealItem(
            id=generate_deal_id(row["url"], row["title"]),
            title=row["title"],
            url=row["url"],
            source="eval",
            summary=row.get("summary", ""),
            confidence=ConfidenceLevel.POTENTIAL,
            score=row.get("score", 55),
        )
        verdict = verifier.verify(deal, context=row.get("summary", ""))
        results.append({"title": row["title"], "label": row["label"], "decision": verdict.decision.value,
                        "flags": verdict.flags, "tool_calls": verdict.tool_calls, "reason": verdict.reason})
    return {"metrics": score(results), "results": results}


def score(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(results)
    decided = [r for r in results if r["decision"] != Decision.UNSURE.value]
    correct = sum(1 for r in decided if r["decision"] == r["label"])
    label_reject = [r for r in results if r["label"] == "reject"]
    label_keep = [r for r in results if r["label"] == "keep"]
    false_keep = sum(1 for r in label_reject if r["decision"] == "keep")
    false_reject = sum(1 for r in label_keep if r["decision"] == "reject")

    def rate(n: int, d: int) -> float:
        return round(n / d, 3) if d else 0.0

    return {
        "total": total,
        "decided": len(decided),
        "accuracy": rate(correct, len(decided)),
        "false_keep_rate": rate(false_keep, len(label_reject)),
        "false_reject_rate": rate(false_reject, len(label_keep)),
        "unsure_rate": rate(total - len(decided), total),
        "avg_tool_calls": round(sum(r["tool_calls"] for r in results) / total, 2) if total else 0.0,
    }
