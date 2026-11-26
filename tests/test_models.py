"""Models, explanations, thresholds, fairness rules and the bed forecast."""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

from halvian import config as C
from halvian.models import admission as A
from halvian.models import forecast as F
from halvian.models.explain import top_reasons
from halvian.models.fairness import fairness_table
from halvian.models.thresholds import batch_request, moving_threshold

ROOT = Path(__file__).resolve().parents[1]
DATA, MODELS = ROOT / "data", ROOT / "models"
needs = pytest.mark.skipif(not (MODELS / "metrics.json").exists(), reason="run scripts/train_models.py")


def test_moving_threshold_direction_and_bounds():
    typical = 1.0
    assert moving_threshold(typical, typical) == pytest.approx(C.ALERT_THRESHOLD)
    crowded, quiet = moving_threshold(1.4, typical), moving_threshold(0.6, typical)
    assert crowded < C.ALERT_THRESHOLD < quiet
    assert moving_threshold(10, typical) == pytest.approx(C.MOVING_THRESHOLD_FLOOR)
    assert moving_threshold(-10, typical) == pytest.approx(C.MOVING_THRESHOLD_CEILING)
    assert moving_threshold(1.4, typical, enabled=False) == C.ALERT_THRESHOLD


def test_batch_request_is_rounded_expected_count():
    assert batch_request([0.9, 0.8, 0.75])["beds_to_request"] == 2
    assert batch_request([0.9, 0.8, 0.75], already_reserved=1)["beds_to_request"] == 1
    assert batch_request([0.72], already_reserved=3)["beds_to_request"] == 0


def test_fairness_levels_follow_the_stated_rule():
    rng = np.random.default_rng(0)
    n = 4000
    payer = rng.choice(list(C.PAYERS[:4]), size=n)
    y = rng.uniform(size=n) < 0.3
    p = np.clip(0.3 + 0.4 * (y - 0.3) + rng.normal(0, 0.15, n), 0, 1)
    flag = p >= 0.5
    flag[(payer == C.UNINSURED) & y] = False  # miss every uninsured positive
    t = fairness_table(pd.DataFrame({"payer": payer, "y": y, "p": p, "flag": flag}))
    row = t.set_index("group").loc[C.UNINSURED]
    assert row.fnr_level == "red"
    assert t.set_index("group").loc[C.COMMERCIAL].fnr_level in ("ok", "amber")


@needs
def test_metrics_are_plausible_and_reported():
    m = json.loads((MODELS / "metrics.json").read_text())
    for key in ("admission", "discharge"):
        best = m[key]["test"][m[key]["chosen"]]
        assert best["auc"] > 0.75
        assert abs(best["calibration_gap_pts"]) < 3
        assert {"logistic", "boosting"} <= set(m[key]["test"])
    assert m["admission"]["lead_time"]["median_h"] > 0
    assert m["note_reader"]["overall"]["precision"] > 0.8


@needs
def test_reasons_are_plain_english_and_additive():
    model = joblib.load(MODELS / "admission.joblib")["model"]
    ed = pd.read_parquet(DATA / "ed_visits.parquet").head(50)
    X = A.prepare(ed)
    contrib = model.contributions(X)
    reasons = top_reasons(contrib, X)
    assert all(len(r) == 3 for r in reasons)
    assert all(("raises" in s or "lowers" in s) for r in reasons for s in r)
    assert reasons[0][0].endswith("the chance") and reasons[0][1].endswith("it")
    # logistic contributions add up to the prediction's log-odds minus a constant
    logit = np.log(model.predict_proba(X) / (1 - model.predict_proba(X)))
    diff = logit - contrib.sum(axis=1).to_numpy()
    assert np.allclose(diff, diff[0], atol=1e-6)


@needs
def test_forecast_state_and_net_identity():
    stays = pd.read_parquet(DATA / "inpatient_stays.parquet")
    t = 365.0 * 1440
    st = F.unit_state(t, stays)
    total = st.occupied + st.cleaning + st.assigned + st.reserved + st.clean_free
    assert (total == st.beds).all()
    # net changes only through beds made ready and new requests
    t2 = t + 8 * 60
    st2 = F.unit_state(t2, stays)
    for u in ("Medicine A", "Telemetry"):
        s = stays
        cleans = ((s.unit == u) & (s.clean_min > t) & (s.clean_min <= t2)).sum()
        reqs = ((s.intended_unit == u) & (s.queue_entry_min > t) & (s.queue_entry_min <= t2)).sum()
        off_in = ((s.unit == u) & (s.intended_unit != u) & (s.bed_assigned_min > t) & (s.bed_assigned_min <= t2)).sum()
        off_out = ((s.unit != u) & (s.intended_unit == u) & (s.bed_assigned_min > t) & (s.bed_assigned_min <= t2)).sum()
        assert st2.loc[u, "net_now"] - st.loc[u, "net_now"] == cleans - reqs - off_in + off_out


@needs
def test_forecast_band_and_components():
    m = json.loads((MODELS / "metrics.json").read_text())
    rows = pd.DataFrame(m["forecast"]["backtest"])
    four = rows[rows.horizon_h == 4].iloc[0]
    assert four.mae < four.mae_persistence  # beats "no change" at 4 hours


def test_forecast_tables_use_only_events_observable_by_the_cutoff():
    """Changing anything that happens after the training cutoff must not change the fitted tables."""
    from datetime import date

    from halvian.data.cohort import minutes_from_start

    root = Path(__file__).resolve().parents[1] / "data"
    if not (root / "ed_visits.parquet").is_file():
        pytest.skip("Generate the synthetic data first.")
    ed = pd.read_parquet(root / "ed_visits.parquet")
    stays = pd.read_parquet(root / "inpatient_stays.parquet")
    t0, t1 = minutes_from_start(date(2025, 7, 1)), minutes_from_start(date(2025, 10, 1))
    profile = np.linspace(0, 1, 97)
    a = F.fit_tables(ed, stays, None, t0, t1, profile)
    ed2, st2 = ed.copy(), stays.copy()
    late = ed2.bed_request_min >= t1
    ed2.loc[late, "bed_request_min"] += 600.0
    ed2.loc[late, "decision_min"] -= 120.0
    st2.loc[st2.clean_min >= t1, "clean_min"] += 900.0
    st2.loc[st2.queue_entry_min >= t1, "queue_entry_min"] += 300.0
    b = F.fit_tables(ed2, st2, None, t0, t1, profile)
    assert a.clean_lag_min == b.clean_lag_min
    np.testing.assert_array_equal(a.triage_to_request, b.triage_to_request)
    np.testing.assert_array_equal(a.decision_to_request, b.decision_to_request)
    for key in a.future_ed:
        pd.testing.assert_series_equal(a.future_ed[key], b.future_ed[key])
        pd.testing.assert_series_equal(a.non_ed[key], b.non_ed[key])


def test_forecast_demand_windows_close_a_full_horizon_before_the_cutoff():
    """An admission that arrives and is requested just after the cutoff must not reach any window."""
    from datetime import date

    from halvian.data.cohort import minutes_from_start

    root = Path(__file__).resolve().parents[1] / "data"
    if not (root / "ed_visits.parquet").is_file():
        pytest.skip("Generate the synthetic data first.")
    ed = pd.read_parquet(root / "ed_visits.parquet")
    stays = pd.read_parquet(root / "inpatient_stays.parquet")
    t0, t1 = minutes_from_start(date(2025, 8, 1)), minutes_from_start(date(2025, 10, 1))
    a = F.fit_tables(ed, stays, None, t0, t1, np.linspace(0, 1, 97))
    extra = ed[ed.admitted].iloc[[0]].copy()
    extra["arrival_min"], extra["bed_request_min"] = t1 + 1.0, t1 + 2.0  # observable only after the cutoff
    b = F.fit_tables(pd.concat([ed, extra]), stays, None, t0, t1, np.linspace(0, 1, 97))
    for key in a.future_ed:
        pd.testing.assert_series_equal(a.future_ed[key], b.future_ed[key])


def test_discharge_lead_metrics_use_explicit_cohorts():
    from halvian.models.discharge import LEAD_COHORTS, lead_metrics

    day = 1440.0
    rows = pd.DataFrame([
        # stay A: flagged two mornings; leaves 6 h after the second, so only the second is a true positive
        {"stay_id": "A", "rounds_min": 7 * 60, "discharge_min": day + 13 * 60, "y": False},
        {"stay_id": "A", "rounds_min": day + 7 * 60, "discharge_min": day + 13 * 60, "y": True},
        # stay B: never flagged, leaves 10 h after rounds: a missed positive
        {"stay_id": "B", "rounds_min": 7 * 60, "discharge_min": 17 * 60, "y": True},
        # stay C: leaves after the window, excluded from every cohort
        {"stay_id": "C", "rounds_min": 7 * 60, "discharge_min": 5 * day, "y": False},
    ])
    p = np.array([0.9, 0.9, 0.1, 0.9])
    out = lead_metrics(rows, p, 0.5, window_end=3 * day)
    assert out["true_positive_rounds"] == 1 and out["median_h_true_positive"] == 6
    assert out["missed_positive_rounds"] == 1 and out["median_h_missed_positive"] == 10
    assert (out["eligible_positive_stays"], out["stays_flagged_in_time"], out["stays_missed"]) == (2, 1, 1)
    assert out["all_flags_stays"] == 1 and out["all_flags_median_h"] == 30
    assert set(out["cohorts"]) == set(LEAD_COHORTS)
