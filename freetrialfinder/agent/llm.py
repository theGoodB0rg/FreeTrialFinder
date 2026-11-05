"""Minimal client for any OpenAI-compatible chat completions API with tool calling.

Kept dependency-free (uses httpx, already a project dependency) so the agent
works with OpenRouter, OpenAI, Together, a local server, or anything else that
speaks the same protocol.
"""

import re
import time
from typing import Any, Callable, Dict, List, Optional, Protocol

import httpx


class ChatClient(Protocol):
    def chat(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Return the assistant message dict: {"content": ..., "tool_calls": [...]}"""
        ...


class LLMError(RuntimeError):
    pass


class OpenAICompatibleClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://openrouter.ai/api/v1",
        timeout: float = 45.0,
        temperature: float = 0.0,
        max_retries: int = 3,
        max_wait: float = 30.0,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if not api_key:
            raise ValueError("api_key is required")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.temperature = temperature
        self.last_usage: Optional[Dict[str, Any]] = None
        self.max_retries = max_retries
        self.max_wait = max_wait
        self.sleep = sleep
        self.retries_used = 0

    def chat(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "temperature": self.temperature,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-Title": "FreeTrialFinder",
        }
        for attempt in range(self.max_retries + 1):
            try:
                resp = httpx.post(f"{self.base_url}/chat/completions", json=payload, headers=headers, timeout=self.timeout)
            except httpx.HTTPError as exc:
                raise LLMError(f"request failed: {exc}") from exc
            if resp.status_code not in (429, 503) or attempt == self.max_retries:
                break
            wait = self._retry_after(resp)
            if wait is None or wait > self.max_wait:
                break  # e.g. a daily quota: waiting will not help, fail fast
            self.retries_used += 1
            self.sleep(wait)
        if resp.status_code != 200:
            raise LLMError(f"HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        if data.get("error"):
            raise LLMError(str(data["error"])[:300])
        choices = data.get("choices") or []
        if not choices:
            raise LLMError("no choices in response")
        self.last_usage = data.get("usage")
        return choices[0].get("message") or {}

    @staticmethod
    def _retry_after(resp: httpx.Response) -> Optional[float]:
        """Seconds to wait before retrying, from Retry-After or the provider's message."""
        header = resp.headers.get("retry-after")
        if header:
            try:
                return float(header) + 0.5
            except ValueError:
                pass
        match = re.search(r"try again in ([0-9.]+)\s*(ms|s)", resp.text)
        if match:
            value = float(match.group(1))
            return (value / 1000 if match.group(2) == "ms" else value) + 0.5
        return None
