import pandas as pd
import pytest

from halvian.notes.reader import LLMNoteReader, RuleBasedNoteReader, score_note_reader


@pytest.mark.parametrize(
    ("note", "expected"),
    [
        ("VSS; home health referral pending", "home_care"),
        ("pt needs HH set up before dc", "home_care"),
        ("HH agency hasnt confirmed", "home_care"),
        ("no ride until Thurs; tolerating PO", "transport"),
        ("transport home not arranged, IV abx", "transport"),
        ("awaiting rehab bed, PT eval pending", "placement"),
        ("dtr can't pick up until Thurs", "family_pickup"),
        ("awaiting insurance auth for SNF", "insurance_auth"),
        ("home O2 not delivered yet", "meds_equipment"),
    ],
)
def test_finds_active_barrier_and_offsets(note, expected):
    result = RuleBasedNoteReader().read(note)
    assert [hit["type"] for hit in result] == [expected]
    start, end = result[0]["evidence_span"]
    assert note[start:end].strip()
    assert 0 < result[0]["confidence"] <= 1


@pytest.mark.parametrize(
    "note",
    [
        "",
        "pain controlled, no barriers to dc",
        "denies needing home care",
        "transport to MRI this am; home meds reconciled",
        "needs transport to CT",
        "no transport issues, wife driving",
        "HH set up for Fri; auth obtained; DME delivered",
        "needs HH, got it arranged",
        "needs transport arranged",
        "dtr at bedside; family meeting held",
        "insurance verified on admission, rx for abx sent",
    ],
)
def test_decoys_and_resolved_barriers_do_not_trigger(note):
    assert RuleBasedNoteReader().read(note) == []


def test_offsets_and_negation_scope_across_clauses():
    note = "no need for HH, awaiting rehab bed but transport home not arranged"
    found = RuleBasedNoteReader().read(note)
    assert [hit["type"] for hit in found] == ["placement", "transport"]
    assert [note[start:end] for start, end in (hit["evidence_span"] for hit in found)] == [
        "awaiting rehab bed", "transport home not arranged"
    ]


def test_scoring_includes_negatives_and_reports_strata():
    notes = pd.DataFrame({
        "note_id": ["1", "2", "3", "4"],
        "text": ["no ride until Thurs", "home health referral pending", "clinically stable", ""],
        "payer": ["A", "A", "B", "B"],
    })
    labels = pd.DataFrame({
        "note_id": ["1", "3"],
        "barrier_type": ["transport", "insurance_auth"],
    })
    score = score_note_reader(notes, labels)
    assert score["overall"] == {
        "notes": 4, "support": 2, "tp": 1, "fp": 1, "fn": 1,
        "precision": 0.5, "recall": 0.5, "f1": 0.5,
    }
    assert score["by_barrier"]["home_care"]["precision"] == 0
    assert score["by_barrier"]["placement"]["f1"] is None
    assert score["by_payer"]["A"]["precision"] == 0.5
    assert score["by_payer"]["B"]["recall"] == 0


def test_llm_reader_falls_back_to_the_rules_instead_of_failing():
    """With no such model on the local server (or no server at all), the rules answer."""
    findings, status, _ = LLMNoteReader(model="halvian-missing-model:0", timeout_s=3).read_detailed("no ride until Thurs")
    assert status == "fallback" and [f["type"] for f in findings] == ["transport"]
