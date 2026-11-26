"""The note reader contract the UI builds against (halvian.notes.live)."""

from halvian import config as C
from halvian.notes.live import analyze_note, reader_status

FINDING_KEYS = {"barrier_type", "label", "start", "end", "evidence", "confidence", "owner"}


def test_analyze_note_returns_the_contract():
    text = "medically ready, needs wheelchair van, none avail until Sun"
    out = analyze_note(text, timeout_s=5)
    assert set(out) == {"status", "model", "latency_ms", "findings"}
    assert out["status"] in {"llm", "fallback", "error"}
    assert isinstance(out["model"], str) and out["model"]
    assert isinstance(out["latency_ms"], float | int)
    for f in out["findings"]:
        assert set(f) == FINDING_KEYS
        assert f["barrier_type"] in C.BARRIER_TYPES
        assert text[f["start"]:f["end"]] == f["evidence"]
        assert f["label"] == C.BARRIER_LABELS[f["barrier_type"]] and f["owner"] == C.BARRIER_OWNER[f["barrier_type"]]
    assert "transport" in {f["barrier_type"] for f in out["findings"]}


def test_reader_status_returns_the_contract():
    status = reader_status()
    assert set(status) == {"available", "model", "prompt_version"}
    assert isinstance(status["available"], bool)


def test_analyze_note_never_raises_on_odd_input():
    for text in ("", "   ", "no barriers to dc"):
        out = analyze_note(text, timeout_s=1)
        assert out["status"] in {"llm", "fallback", "error"} and out["findings"] == []
