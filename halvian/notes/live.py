"""The note reader as the app calls it: one note in, barriers out, with a safe fallback.

Interface contract for the UI (do not change without a note in HANDOFF.md):

* ``analyze_note(text, timeout_s=20) -> dict`` with keys
  ``status`` ("llm", "fallback" or "error"), ``model`` (display name; on fallback it says why),
  ``latency_ms`` and ``findings`` (list of dicts with ``barrier_type``, ``label``,
  ``start``, ``end``, ``evidence``, ``confidence`` and ``owner``). ``text[start:end] == evidence``.
* ``reader_status() -> dict`` with keys ``available`` (bool), ``model`` (str) and
  ``prompt_version`` (str).

The AI note reader is a local language model (``config.LLM_MODEL`` via Ollama on this machine).
If Ollama is not running, the model is missing or a call times out, the rule-based reader
answers and ``status`` is "fallback". Nothing leaves the machine.
"""

from __future__ import annotations

import time

from halvian import config as C
from halvian.notes.ollama import OllamaUnavailable, installed_models
from halvian.notes.prompt import PROMPT_ID
from halvian.notes.reader import BarrierFinding, LLMNoteReader, RuleBasedNoteReader

_RULES = RuleBasedNoteReader()
_STATUS_TTL_S = 30.0
_status_cache: dict = {"at": -1e9, "value": None}


def _fallback_name(reason: str) -> str:
    return f"Rule-based reader (fallback: {reason})"


def _as_records(text: str, findings: list[BarrierFinding]) -> list[dict]:
    out = []
    for f in findings:
        start, end = (int(x) for x in f["evidence_span"])
        out.append({"barrier_type": f["type"], "label": C.BARRIER_LABELS[f["type"]], "start": start, "end": end,
                    "evidence": text[start:end], "confidence": float(f["confidence"]),
                    "owner": C.BARRIER_OWNER[f["type"]]})
    return out


def reader_status() -> dict:
    """Whether the local model is ready (cached for 30 s so pages stay fast)."""
    now = time.monotonic()
    if _status_cache["value"] is not None and now - _status_cache["at"] < _STATUS_TTL_S:
        return dict(_status_cache["value"])
    try:
        names = installed_models(timeout_s=0.5)
        available = any(n == C.LLM_MODEL or n == f"{C.LLM_MODEL}:latest" for n in names)
        model = C.LLM_DISPLAY_NAME if available else _fallback_name(f"{C.LLM_MODEL} is not installed")
    except OllamaUnavailable:
        available, model = False, _fallback_name("local model not running")
    value = {"available": available, "model": model, "prompt_version": PROMPT_ID}
    _status_cache.update(at=now, value=value)
    return dict(value)


def analyze_note(text: str, timeout_s: float = C.LLM_TIMEOUT_S) -> dict:
    """Read one note with the local model; fall back to the rules if it is unavailable."""
    t0 = time.perf_counter()
    text = text if isinstance(text, str) else ""
    try:
        status = reader_status()
        if not status["available"]:
            findings, state, model = _RULES.read(text), "fallback", status["model"]
        else:
            findings, state, detail = LLMNoteReader(timeout_s=timeout_s).read_detailed(text)
            model = C.LLM_DISPLAY_NAME if state == "llm" else _fallback_name(detail)
            if state == "fallback":
                _status_cache["at"] = -1e9  # re-check the server next time
        records = _as_records(text, findings)
    except Exception:  # noqa: BLE001  the app must never crash on a note
        records, state, model = [], "error", _fallback_name("unexpected error, no barriers read")
    return {"status": state, "model": model, "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
            "findings": records}
