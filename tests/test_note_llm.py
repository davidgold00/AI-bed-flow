"""The AI note reader: verbatim evidence, negation and resolution guards, fallback, cache and evaluation.

Most tests replace the model with a fake, so they run with Ollama off. The cache tests check
what scripts/run_llm_reader.py saved.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from halvian import config as C
from halvian.notes import live, ollama
from halvian.notes.prompt import EXAMPLES, PROMPT_ID, PROMPT_VERSION
from halvian.notes.reader import GUARD_VERSION, LLMNoteReader, locate_evidence, span_is_inactive

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "models" / "llm_note_findings.parquet"
needs_cache = pytest.mark.skipif(not CACHE.is_file(), reason="run scripts/run_llm_reader.py")


def fake_model(monkeypatch, barriers):
    monkeypatch.setattr(ollama, "chat_json", lambda *a, **k: {"barriers": barriers})


# ----------------------------------------------------------------------------- guards
def test_evidence_must_appear_in_the_note():
    text = "pt stable, needs wheelchair van, none avail until Sun"
    assert locate_evidence(text, "needs wheelchair van") == (11, 31)
    assert locate_evidence(text, "NEEDS Wheelchair Van") == (11, 31)  # letter case ignored, offsets from the note
    assert locate_evidence(text, "needs a stretcher van") is None  # not in the note: dropped
    assert locate_evidence(text, "pt") is None  # too short to verify


@pytest.mark.parametrize(("text", "evidence", "barrier", "inactive"), [
    ("lives w/ spouse, ride confirmed for 2pm", "ride confirmed for 2pm", "transport", True),
    ("no transport issues, wife driving", "transport issues", "transport", True),
    ("transport to MRI this am", "transport to MRI", "transport", True),
    ("HH set up, starts Fri", "HH set up", "home_care", True),
    ("denies need for HH", "need for HH", "home_care", True),
    ("needs HH set up before dc", "needs HH set up before dc", "home_care", False),
    ("needs wheelchair van, none avail until Sun", "needs wheelchair van", "transport", False),
    ("home care services not arranged", "home care services not arranged", "home_care", False),
    ("no ride until Thurs", "no ride until Thurs", "transport", False),
])
def test_negated_and_resolved_barriers_are_not_active(text, evidence, barrier, inactive):
    start, end = locate_evidence(text, evidence)
    assert span_is_inactive(text, start, end, barrier) is inactive


def test_reader_keeps_only_active_verbatim_findings(monkeypatch):
    text = "awaiting rehab bed; ride confirmed for 2pm; dtr can't pick up until Fri"
    fake_model(monkeypatch, [
        {"barrier_type": "placement", "evidence": "awaiting rehab bed", "status": "active"},
        {"barrier_type": "transport", "evidence": "ride confirmed for 2pm", "status": "resolved"},
        {"barrier_type": "family_pickup", "evidence": "daughter unable to come", "status": "active"},  # invented
        {"barrier_type": "transport", "evidence": "ride confirmed for 2pm", "status": "active"},  # mislabelled
    ])
    reader = LLMNoteReader()
    findings, status, _ = reader.read_detailed(text)
    assert status == "llm"
    assert [(f["type"], text[slice(*f["evidence_span"])]) for f in findings] == [("placement", "awaiting rehab bed")]
    assert reader.stats["evidence_not_in_note"] == 1 and reader.stats["negated_or_resolved"] == 1
    assert reader.stats["not_active"] == 1


def test_reader_falls_back_to_rules_when_the_model_is_off(monkeypatch):
    def down(*a, **k):
        raise ollama.OllamaUnavailable("connection refused")

    monkeypatch.setattr(ollama, "chat_json", down)
    findings, status, detail = LLMNoteReader().read_detailed("pt has no ride home")
    assert status == "fallback" and "not running" in detail
    assert [f["type"] for f in findings] == ["transport"]


def test_client_refuses_any_host_but_this_machine():
    with pytest.raises(ValueError):
        ollama._url("/api/chat", "https://api.example.com")
    assert ollama._url("/api/tags").startswith("http://127.0.0.1:")


def test_analyze_note_falls_back_and_says_so(monkeypatch):
    def down(*a, **k):
        raise ollama.OllamaUnavailable("connection refused")

    monkeypatch.setattr(live, "installed_models", down)
    live._status_cache.update(at=-1e9, value=None)
    out = live.analyze_note("needs wheelchair van, none avail until Sun", timeout_s=1)
    live._status_cache.update(at=-1e9, value=None)
    assert out["status"] == "fallback" and "fallback" in out["model"].lower()
    assert [f["barrier_type"] for f in out["findings"]] == ["transport"]


def test_analyze_note_uses_the_model_when_available(monkeypatch):
    monkeypatch.setattr(live, "installed_models", lambda **k: [C.LLM_MODEL])
    fake_model(monkeypatch, [{"barrier_type": "transport", "evidence": "needs wheelchair van", "status": "active"}])
    live._status_cache.update(at=-1e9, value=None)
    out = live.analyze_note("needs wheelchair van, none avail until Sun")
    live._status_cache.update(at=-1e9, value=None)
    assert out["status"] == "llm" and out["model"] == C.LLM_DISPLAY_NAME
    f = out["findings"][0]
    assert (f["barrier_type"], f["evidence"], f["start"], f["end"]) == ("transport", "needs wheelchair van", 0, 20)


# ----------------------------------------------------------------------------- prompt
def test_prompt_is_versioned_and_its_examples_are_not_from_the_data():
    assert PROMPT_ID.startswith(f"{PROMPT_VERSION}-") and len(PROMPT_ID) > len(PROMPT_VERSION) + 5
    notes = ROOT / "data" / "notes.parquet"
    if notes.is_file():
        texts = set(pd.read_parquet(notes, columns=["text"]).text)
        assert not any(example in texts for example, _ in EXAMPLES)


def test_evaluation_sample_is_balanced_deterministic_and_test_quarter_only():
    from halvian.notes import evaluate as E

    if not (ROOT / "data" / "notes.parquet").is_file():
        pytest.skip("Generate the synthetic data first.")
    notes = pd.read_parquet(ROOT / "data" / "notes.parquet")
    labels = pd.read_parquet(ROOT / "data" / "note_labels.parquet")
    stays = pd.read_parquet(ROOT / "data" / "inpatient_stays.parquet", columns=["stay_id", "payer"])
    a = E.evaluation_sample(notes, labels, stays)
    b = E.evaluation_sample(notes, labels, stays)
    pd.testing.assert_frame_equal(a, b)
    assert (notes.set_index("note_id").loc[a.note_id, "written_min"] >= E.TEST_START).all()
    kinds = a.stratum.str.split(" | ", regex=False).str[0]
    assert set(C.BARRIER_TYPES) <= set(kinds) and {"no barrier", "no barrier, barrier words"} <= set(kinds)
    assert set(a.payer) == set(C.PAYERS)


# ----------------------------------------------------------------------------- cache and metrics
@needs_cache
def test_cache_records_model_prompt_and_time_and_every_span_is_verbatim():
    from halvian.notes.evaluate import demo_note_ids

    cache = pd.read_parquet(CACHE)
    assert {"note_id", "purpose", "status", "model", "prompt_version", "read_at", "barrier_type", "start", "end",
            "evidence", "confidence"} <= set(cache.columns)
    assert set(cache.model) == {C.LLM_MODEL}
    assert set(cache.prompt_version) == {PROMPT_ID}, "the prompt changed: rerun scripts/run_llm_reader.py"
    assert set(cache.guard_version) == {GUARD_VERSION}, "the checks changed: rerun scripts/run_llm_reader.py"
    assert cache[cache.status == "llm"].answer.notna().all()  # the model's raw answer is kept for audit
    text = pd.read_parquet(ROOT / "data" / "notes.parquet").set_index("note_id").text
    text = pd.concat([text, pd.read_parquet(ROOT / "data" / "stress_notes.parquet").set_index("note_id").text])
    hits = cache[cache.barrier_type.notna()]
    assert all(text[r.note_id][int(r.start):int(r.end)] == r.evidence for r in hits.itertuples())
    days = pd.read_parquet(ROOT / "data" / "inpatient_days.parquet", columns=["note_id", "rounds_min"])
    assert set(demo_note_ids(days)) <= set(cache.note_id)  # every note the app shows on a demo day


@needs_cache
def test_metrics_report_model_rules_and_union_on_the_same_sample():
    nr = json.loads((ROOT / "models" / "metrics.json").read_text())["note_reader"]
    for who in ("llm", "rules", "combined"):
        assert nr[who]["sample_n"] >= 1000 and set(nr[who]["by_barrier"]) == set(C.BARRIER_TYPES)
        assert set(nr[who]["by_payer"]) == set(C.PAYERS)
    assert nr["llm"]["sample_n"] == nr["rules"]["sample_n"] == nr["combined"]["sample_n"]
    assert nr["llm_run"]["model"] == C.LLM_MODEL and nr["llm_run"]["wall_minutes"] <= C.LLM_EVAL_BUDGET_MIN
    assert nr["llm"]["sample"] == "B (sealed)" and nr["llm"]["guard_version"] == GUARD_VERSION
    assert "stress" in nr and nr["stress"]["llm"]["sample_n"] == nr["stress"]["rules"]["sample_n"]
    assert nr["history"][0]["sample"] == "A"  # the first reader's scores are kept, not overwritten


@needs_cache
def test_app_findings_say_which_reader_found_them():
    from halvian.data import live as L

    rows = L.rounds_list(C.DEMO_DAYS["busy"])
    readers = {f["reader"] for fs in rows.findings for f in fs}
    assert readers <= {"llm", "rules"} and "llm" in readers
    for fs in rows.findings:
        for f in fs:
            assert {"note_id", "barrier_type", "start", "end", "confidence", "reader"} <= set(f)


def test_stress_set_is_fixed_and_its_labels_come_from_construction():
    from halvian.notes.stress import ACTIVE, stress_notes

    notes, labels = stress_notes()
    saved = ROOT / "data" / "stress_notes.parquet"
    if saved.is_file():
        pd.testing.assert_frame_equal(notes, pd.read_parquet(saved))
        pd.testing.assert_frame_equal(labels, pd.read_parquet(ROOT / "data" / "stress_labels.parquet"))
    by_id = notes.set_index("note_id").text
    for row in labels.itertuples():
        assert any(p in by_id[row.note_id] for p in ACTIVE[row.barrier_type])
    synthetic = set(pd.read_parquet(ROOT / "data" / "notes.parquet", columns=["text"]).text) if (
        ROOT / "data" / "notes.parquet").is_file() else set()
    assert not synthetic & set(notes.text)  # new wording, not the templates


# ----------------------------------------------------------------------------- guard g2
@pytest.mark.parametrize(("text", "evidence", "barrier", "expect"), [
    ("BP soft, holding meds", "holding meds", "meds_equipment", None),  # inpatient care, not a discharge task
    ("O2 2L NC, up ad lib", "O2 2L NC", "meds_equipment", None),
    ("PT eval pending", "PT eval pending", "placement", None),  # open, but names no discharge task
    ("lives w/ spouse, ride confirmed", "lives w/ spouse", "family_pickup", None),
    ("waiting on family Wed", "waiting on family Wed", "transport", "family_pickup"),  # relabelled by its words
    ("prior auth pending for rehab", "prior auth pending for rehab", "placement", "insurance_auth"),
    ("awaiting rehab bed", "awaiting rehab bed", "placement", "placement"),
    ("neesd home nursing, not yet arranged", "neesd home nursing", "home_care", "home_care"),  # typo tolerated
])
def test_guard_g2_keeps_open_discharge_tasks_only(text, evidence, barrier, expect):
    from halvian.notes.reader import check_open_task

    got = check_open_task(text, locate_evidence(text, evidence), barrier)
    assert (got[0] if got else None) == expect


def test_guard_g2_borrows_the_subject_from_the_clause_before():
    from halvian.notes.reader import check_open_task

    text = "pt stable, needs wheelchair van, none avail until Sun"
    barrier, span = check_open_task(text, locate_evidence(text, "none avail until Sun"), "transport")
    assert barrier == "transport" and text[slice(*span)] == "needs wheelchair van, none avail until Sun"
    text = "home meds reconciled, PT eval pending"  # the clause before is done, so nothing to borrow
    assert check_open_task(text, locate_evidence(text, "PT eval pending"), "meds_equipment") is None
