"""Step-level tracing for the verification agent.

Every model call, tool call, guard trip and final verdict is written as one
JSON line, so a run can be replayed and audited afterwards (and summarised by
`freetrialfinder traces`).
"""

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict


class NullTracer:
    def event(self, run_id: str, kind: str, **data: Any) -> None:
        pass


class JsonlTracer:
    def __init__(self, path: str = "data/agent_traces.jsonl"):
        self.path = path
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)

    def event(self, run_id: str, kind: str, **data: Any) -> None:
        record: Dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "run_id": run_id,
            "kind": kind,
            **data,
        }
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
