"""models/impact_ranges.json: the results contract, as rounded ranges introduced by a break-even point."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest
from test_impact import T_ACT, T_END, _baseline, _cohort, _settings

from halvian import config as C
from halvian import ranges as RG
from halvian.data.simulate import run

ROOT = Path(__file__).resolve().parents[1]
RANGES = ROOT / "models" / "impact_ranges.json"
needs = pytest.mark.skipif(not (ROOT / "models" / "scenarios.json").is_file(), reason="train the models first")

SCENARIO_KEYS = {"name", "settings", "minutes_saved_per_admission", "freed_capacity_per_year_usd_m",
                 "provider_wait_change_min", "walkout_change_pts"}


def _saved():
    return json.loads(RANGES.read_text())


def _on_step(x: float, step: float) -> bool:
    return math.isclose(x / step, round(x / step), abs_tol=1e-6)


# ----------------------------------------------------------------------------- rounding rules
def test_widen_goes_outward_to_round_numbers_and_never_to_a_point():
    assert RG.widen(13.8, 20.0, 5) == [10, 20]
    assert RG.widen(-0.6, 6.8, 5) == [-5, 10]
    assert RG.widen(-0.82, -0.49, 0.1) == [-0.9, -0.4]
    assert RG.widen(-4.9, -2.6, 1) == [-5, -2]
    assert RG.widen(15.0, 15.0, 5) == [15, 20]  # a single point is never reported
    assert RG.widen(13.0, 13.5, 5) == [10, 15]


def test_break_even_is_the_budget_over_the_capacity_value_of_one_admission():
    be = RG.break_even()
    hours = C.ANNUAL_BUDGET / (C.BOARDING_COST_PER_BED_HOUR * C.ED_ADMISSIONS_PER_YEAR)
    assert be["minutes_per_admission"] == round(60 * hours) == 6
    assert "$500,000" in be["explanation"] and "$350" in be["explanation"] and "13,600" in be["explanation"]


def test_staffing_options_use_only_brief_rates_and_cost_only():
    rows = RG.staffing_alternative()
    assert 2 <= len(rows) <= 3
    brief_rates = {C.COST_ADMIN_PER_H, C.COST_NURSE_PER_H}
    for (_name, rate, hours, mult, _), row in zip(C.STAFFING_OPTIONS, rows, strict=True):
        assert rate in brief_rates and mult in (1.0, C.OVERTIME_MULTIPLIER)
        assert abs(row["annual_cost_usd"] - rate * hours * mult) <= RG.DOLLARS_STEP / 2
        assert set(row) == {"option", "annual_cost_usd", "assumption"}  # no invented effect on boarding


# ----------------------------------------------------------------------------- the saved contract
@needs
def test_contract_has_the_agreed_structure():
    r = _saved()
    assert list(r) == ["caveat", "break_even", "scenarios", "parts", "equity", "staffing_alternative", "tool_cost",
                       "references", "least_certain"]
    assert r["caveat"] == RG.CAVEAT
    assert set(r["break_even"]) == {"minutes_per_admission", "explanation"}
    assert [s["name"] for s in r["scenarios"]] == ["Cautious", "Expected", "Full rollout"]
    assert all(set(s) == SCENARIO_KEYS for s in r["scenarios"])
    assert [p["part"] for p in r["parts"]] == ["Admission flags", "Discharge readiness", "Bed board"]
    assert all(e["verdict"] in ("Narrowed", "Flat", "Widened") and " vs Commercial, " in e["gap"] for e in r["equity"])
    assert all(u["url"].startswith("https://") and u["source"] and u["finding"] for u in r["references"])
    assert r["least_certain"]


@needs
def test_every_range_is_a_widened_range_never_a_point_estimate():
    r = _saved()
    steps = {"minutes_saved_per_admission": C.RANGE_STEP["minutes"],
             "freed_capacity_per_year_usd_m": C.RANGE_STEP["usd_m"],
             "provider_wait_change_min": C.RANGE_STEP["wait_min"], "walkout_change_pts": C.RANGE_STEP["walkout_pts"]}
    rows = [*r["scenarios"], *r["parts"]]
    for row in rows:
        for key, step in steps.items():
            if key in row:
                lo, hi = row[key]
                assert lo < hi and _on_step(lo, step) and _on_step(hi, step), (row.get("name", row.get("part")), key)
    lo, hi = r["tool_cost"]["per_year_usd"]
    assert lo < hi


@needs
def test_ranges_cover_every_synthetic_year():
    scenarios = json.loads((ROOT / "models" / "scenarios.json").read_text())
    r = _saved()
    for s in r["scenarios"]:
        result = scenarios["results"][RG.RANGE_SCENARIOS[s["name"]]]
        minutes = [p["mean_minutes_saved_per_admission"] for p in result["per_seed"]]
        wait = [p["d2p_median_tool"] - p["d2p_median_base"] for p in result["per_seed"]]
        walk = [p["lwbs_pct_tool"] - p["lwbs_pct_base"] for p in result["per_seed"]]
        for values, (lo, hi) in ((minutes, s["minutes_saved_per_admission"]), (wait, s["provider_wait_change_min"]),
                                 (walk, s["walkout_change_pts"])):
            assert lo <= min(values) and max(values) <= hi, s["name"]
        # freed capacity is the minute range at the brief's rate, so a reader can check it by hand
        assert s["freed_capacity_per_year_usd_m"] == pytest.approx(
            [round(RG.minutes_to_usd_m(m), 1) for m in s["minutes_saved_per_admission"]])


@needs
def test_ranges_file_is_what_the_code_produces_now():
    scenarios = json.loads((ROOT / "models" / "scenarios.json").read_text())
    plan = json.loads((ROOT / "models" / "plan.json").read_text())
    assert json.loads(json.dumps(RG.build(scenarios, plan))) == _saved(), "run scripts/build_plan.py"


@needs
def test_ranges_file_has_no_dashes():
    text = RANGES.read_text()
    assert "—" not in text and "–" not in text


# ----------------------------------------------------------------------------- the bed board lever
def test_bed_board_lever_alone_shortens_boarding_only_after_go_live():
    co = _cohort()
    # no flags (threshold above 1), no rounds work: only the bed board acts
    board = _settings(co, threshold=2.0, discharge_hours_saved=0.0, rounds_scorer=None,
                      bed_board_cut=C.BED_BOARD_DELAY_CUT)
    run_board = run(co, board, end_min=T_END)
    base = _baseline()
    before = base.ed.departure_min < T_ACT
    assert np.allclose(base.ed.departure_min[before], run_board.ed.departure_min[before])
    after = base.ed.admitted & (base.ed.decision_min >= T_ACT) & (base.ed.departure_min < T_END - 24 * 60)
    boarded = lambda r: (r.ed.departure_min - r.ed.decision_min)[after].mean()  # noqa: E731
    assert boarded(run_board) < boarded(base)
    # with the cut at zero the tool arm without flags or rounds work is the baseline
    none = run(co, _settings(co, threshold=2.0, discharge_hours_saved=0.0, rounds_scorer=None), end_min=T_END)
    assert np.allclose(none.ed.departure_min, base.ed.departure_min, equal_nan=True)
