"""A minimal client for a local Ollama server. Loopback only: it refuses any other host.

The app never calls a cloud service. This module talks to the Ollama process on this
machine (``config.OLLAMA_URL``) with the standard library, so there is no extra dependency.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from urllib.parse import urlparse

from halvian import config as C

LOOPBACK = {"127.0.0.1", "localhost", "::1"}


class OllamaUnavailable(RuntimeError):
    """The local server is not running, the model is missing, or the call timed out."""


def _url(path: str, base: str = C.OLLAMA_URL) -> str:
    host = urlparse(base).hostname
    if host not in LOOPBACK:
        raise ValueError(f"The note reader only talks to a local model, not {host!r}.")
    return base.rstrip("/") + path


def installed_models(timeout_s: float = 0.5, base: str = C.OLLAMA_URL) -> list[str]:
    """Names of the models the local server has, or raise OllamaUnavailable."""
    try:
        with urllib.request.urlopen(_url("/api/tags", base), timeout=timeout_s) as r:  # noqa: S310 loopback only
            return [m["name"] for m in json.loads(r.read()).get("models", [])]
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        raise OllamaUnavailable(str(exc)) from exc


def chat_json(messages: list[dict], schema: dict, *, model: str = C.LLM_MODEL, timeout_s: float = C.LLM_TIMEOUT_S,
              base: str = C.OLLAMA_URL) -> dict:
    """One deterministic chat call constrained to ``schema``; returns the parsed JSON object."""
    body = json.dumps({
        "model": model, "messages": messages, "format": schema, "stream": False, "keep_alive": "30m",
        "options": {"temperature": C.LLM_TEMPERATURE, "seed": C.LLM_SEED, "num_predict": C.LLM_MAX_TOKENS},
    }).encode()
    req = urllib.request.Request(_url("/api/chat", base), data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as r:  # noqa: S310 loopback only
            payload = json.loads(r.read())
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise OllamaUnavailable(str(exc)) from exc
    if "error" in payload:
        raise OllamaUnavailable(str(payload["error"]))
    return json.loads(payload["message"]["content"])
