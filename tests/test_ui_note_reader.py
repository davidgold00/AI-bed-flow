"""Exercise the reader's saved fallback and the optional local backend UI."""

from types import SimpleNamespace

from streamlit.testing.v1 import AppTest

from halvian import config as C
from halvian.ui import note_reader


def test_missing_reader_uses_saved_rule_contract(monkeypatch):
    def unavailable(module):
        raise ModuleNotFoundError(module)

    monkeypatch.setattr(note_reader, "import_module", unavailable)
    text = "Needs wheelchair van."
    result, _ = note_reader.analyze(text)
    assert result["status"] == "fallback"
    finding, = result["findings"]
    assert finding["reader"] == "rules"
    assert finding["owner"] == C.BARRIER_OWNER["transport"]
    assert finding["evidence"] == text[finding["start"]:finding["end"]]


def test_local_reader_shows_evidence_owner_and_latency(monkeypatch):
    text = "Needs wheelchair van. <example>"
    evidence = "Needs wheelchair van"
    reader = SimpleNamespace(
        analyze_note=lambda note, timeout_s=20: {
            "status": "llm", "model": "Local demo model", "latency_ms": 12,
            "findings": [{
                "barrier_type": "transport", "label": C.BARRIER_LABELS["transport"],
                "start": 0, "end": len(evidence), "evidence": evidence,
                "confidence": .9, "owner": C.BARRIER_OWNER["transport"], "reader": "llm",
            }],
        },
        reader_status=lambda: {"available": True, "model": "Local demo model", "prompt_version": "test"},
    )
    monkeypatch.setattr(note_reader, "import_module", lambda _: reader)
    app = AppTest.from_string(f"""
from halvian.ui.note_reader import read_control

read_control({text!r}, "test")
""").run()
    app.button(key="read_note_test").click().run()
    assert not app.exception
    captions = [item.value for item in app.caption]
    assert any(line.startswith(note_reader.LOCAL) for line in captions)
    assert any("12 ms" in line and "Prompt test" in line for line in captions)
    assert C.BARRIER_OWNER["transport"] in app.markdown[0].value
    assert f"<mark>{evidence}</mark>. &lt;example&gt;" in app.get("html")[0].proto.body
