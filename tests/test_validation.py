"""The committed synthetic year reproduces every target in the case brief."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from halvian import config as C
from halvian.validation import compute_metrics, run_checks

DATA = Path(__file__).resolve().parents[1] / "data"
pytestmark = pytest.mark.skipif(not (DATA / "ed_visits.parquet").exists(),
                                reason="run scripts/generate_data.py first")


@pytest.fixture(scope="module")
def checks() -> pd.DataFrame:
    ed = pd.read_parquet(DATA / "ed_visits.parquet")
    stays = pd.read_parquet(DATA / "inpatient_stays.parquet")
    return run_checks(compute_metrics(ed, stays))


def test_all_calibration_checks_pass(checks):
    failed = checks[~checks.Pass]
    assert failed.empty, "\n" + failed[["Target", "Simulated", "Tolerance"]].to_string(index=False)


def test_validation_json_matches(checks):
    payload = json.loads((DATA / "validation.json").read_text())
    assert payload["passed"] == payload["total"] == len(checks)


def test_ids_are_synthetic_format():
    ed = pd.read_parquet(DATA / "ed_visits.parquet", columns=["visit_id"])
    st = pd.read_parquet(DATA / "inpatient_stays.parquet", columns=["stay_id"])
    assert ed.visit_id.str.fullmatch(r"ED-\d{6}").all()
    assert st.stay_id.str.fullmatch(r"IP-\d{6}").all()
    assert ed.visit_id.is_unique and st.stay_id.is_unique


def test_no_name_like_columns():
    for f in DATA.glob("*.parquet"):
        cols = pd.read_parquet(f).columns
        assert not any(c.lower() in {"name", "first_name", "last_name", "mrn", "ssn", "address"} for c in cols)


def test_payer_labels():
    ed = pd.read_parquet(DATA / "ed_visits.parquet", columns=["payer"])
    assert set(ed.payer.astype(str).unique()) == set(C.PAYERS)


def test_data_md_admission_counts_match_the_saved_data():
    """docs/DATA.md quotes admission counts; they must equal what the committed data contains."""
    import re
    from datetime import date
    from pathlib import Path

    from halvian.data.cohort import minutes_from_start

    root = Path(__file__).resolve().parents[1]
    if not (root / "data" / "ed_visits.parquet").is_file():
        pytest.skip("Generate the synthetic data first.")
    text = (root / "docs" / "DATA.md").read_text()
    s, e = minutes_from_start(date(2025, 1, 1)), minutes_from_start(date(2026, 1, 1))
    ed = pd.read_parquet(root / "data" / "ed_visits.parquet", columns=["arrival_min", "admitted"])
    st = pd.read_parquet(root / "data" / "inpatient_stays.parquet", columns=["source", "bed_arrival_min"])
    in_year = st[(st.bed_arrival_min >= s) & (st.bed_arrival_min < e)]
    actual = {
        "ED admissions among 2025 ED arrivals": int(ed[(ed.arrival_min >= s) & (ed.arrival_min < e)].admitted.sum()),
        "ED-sourced stays starting in 2025": int((in_year.source == "ED").sum()),
        "direct admissions": int((in_year.source == "Direct").sum()),
        "elective surgery": int((in_year.source == "Elective").sum()),
    }
    quoted = {
        "ED admissions among 2025 ED arrivals": re.findall(r"([\d,]+) ED admissions among 2025 ED arrivals", text),
        "ED-sourced stays starting in 2025": re.findall(r"ED-sourced stays starting in 2025 \(([\d,]+)", text),
        "direct admissions": re.findall(r"direct admissions \(([\d,]+)", text),
        "elective surgery": re.findall(r"elective surgery \(([\d,]+)", text),
    }
    for label, found in quoted.items():
        assert found, f"DATA.md no longer quotes {label}"
        assert {int(x.replace(",", "")) for x in found} == {actual[label]}, (label, found, actual[label])
    # every other mention of an ED admission count must agree with the one in the data
    for n in re.findall(r"([\d,]{5,}) (?:realized )?ED admissions", text):
        assert int(n.replace(",", "")) == actual["ED admissions among 2025 ED arrivals"], n
