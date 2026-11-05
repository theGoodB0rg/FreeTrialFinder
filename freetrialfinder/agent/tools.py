"""Tools the verification agent may call.

fetch_page is the only tool that touches the network, so it carries the
guardrails: http(s) only, no localhost / private / link-local targets (SSRF),
a hard timeout, a response size cap, and HTML reduced to plain text before it
reaches the model.
"""

import ipaddress
import re
import socket
from html import unescape
from typing import Callable, Dict
from urllib.parse import urlparse

import httpx

MAX_BYTES = 400_000
MAX_CHARS = 6_000
TIMEOUT = 12.0


class ToolError(Exception):
    pass


def _host_is_public(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            return False
    return True


def validate_url(url: str, resolver: Callable[[str], bool] = _host_is_public) -> str:
    """Raise ToolError unless url is an http(s) URL pointing at a public host."""
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in ("http", "https"):
        raise ToolError("only http and https URLs are allowed")
    host = parsed.hostname
    if not host:
        raise ToolError("URL has no host")
    if host.lower() in ("localhost",) or host.lower().endswith(".local"):
        raise ToolError("local hosts are blocked")
    try:
        ip = ipaddress.ip_address(host)
        if not ip.is_global:
            raise ToolError("private or reserved IP addresses are blocked")
    except ValueError:
        if not resolver(host):
            raise ToolError("host does not resolve to a public address")
    return parsed.geturl()


def html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript|svg|head)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?s)<!--.*?-->", " ", html)
    html = re.sub(r"(?i)<br\s*/?>|</(p|div|li|h[1-6]|tr)>", "\n", html)
    text = unescape(re.sub(r"<[^>]+>", " ", html))
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def fetch_page(url: str, max_chars: int = MAX_CHARS) -> Dict[str, str]:
    """Fetch a public page and return {"url", "status", "text"} with text truncated."""
    safe_url = validate_url(url)
    headers = {"User-Agent": "FreeTrialFinder/0.1 (+https://github.com/theGoodB0rg/FreeTrialFinder)"}
    try:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=True, headers=headers) as client:
            with client.stream("GET", safe_url) as resp:
                # Redirects could land on a private host; re-check the final URL.
                validate_url(str(resp.url))
                chunks, size = [], 0
                for chunk in resp.iter_bytes():
                    chunks.append(chunk)
                    size += len(chunk)
                    if size >= MAX_BYTES:
                        break
                raw = b"".join(chunks).decode(resp.encoding or "utf-8", errors="replace")
                status = str(resp.status_code)
                final_url = str(resp.url)
    except httpx.HTTPError as exc:
        raise ToolError(f"fetch failed: {exc.__class__.__name__}") from exc
    text = html_to_text(raw) if "<" in raw[:2000] else raw
    return {"url": final_url, "status": status, "text": text[:max_chars]}
