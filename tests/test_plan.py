"""Budget, value, ROI, goals and pilot gates: computed from config and saved results, never typed in."""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from halvian import config as C
from halvian import roadmap as R
from halvian import roi

ROOT = Path(__file__).resolve().parents[1]
needs = pytest.mark.skipif(not (ROOT / "models" / "scenarios.json").is_file(), reason="train the models first")


def _script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def saved():
    if not (ROOT / "models" / "scenarios.json").is_file():
        pytest.skip("train the models first")
    return (json.loads((ROOT / "models" / "scenarios.json").read_text()),
            json.loads((ROOT / "models" / "metrics.json").read_text()))


# ----------------------------------------------------------------------------- budget
def test_budget_fits_the_briefs_caps_and_names_hidden_costs():
    b = roi.budget()
    assert b["total_18_months"] == pytest.approx(b["by_phase"]["pilot"] + b["by_phase"]["scale"])
    assert b["within_caps"] == {"18_months": b["total_18_months"] <= C.BUDGET_18_MONTHS,
                                "year_1": b["year_1"] <= C.ANNUAL_BUDGET,
                                "run_per_year": b["run_per_year"] <= C.ANNUAL_BUDGET}
    assert all(b["within_caps"].values()), "the plan must fit the brief's budget"
    cats = {line["category"] for line in b["lines"] if line["hidden"]}
    assert {"Training (clinician time)", "Security review"} <= cats  # the brief's named hidden costs
    for phase in ("pilot", "scale", "run"):
        assert b["hidden_by_phase"][phase] > 0
        assert set(b["by_category"][phase]) >= {"Licensing", "Integration", "Training (clinician time)",
                                                "Monitoring and oversight", "Security review"}


def test_training_uses_the_briefs_rates_paid_as_overtime():
    brief_rates = {C.COST_NURSE_PER_H, C.COST_PHYSICIAN_PER_H, C.COST_APP_PER_H, C.COST_ADMIN_PER_H}
    for line in roi.budget_lines():
        if line.category.startswith("Training"):
            assert line.rate / C.OVERTIME_MULTIPLIER in brief_rates
            assert line.cost == pytest.approx(line.quantity * line.rate)


def test_each_phase_carries_its_contingency():
    lines = roi.budget_lines()
    for phase in ("pilot", "scale", "run"):
        base = sum(x.cost for x in lines if x.phase == phase and x.category != "Contingency")
        reserve = sum(x.cost for x in lines if x.phase == phase and x.category == "Contingency")
        assert reserve == pytest.approx(base * C.BUDGET_CONTINGENCY)


def test_traditional_approach_follows_the_briefs_rates():
    t = roi.traditional_approach(200_000)
    for row in t["rows"]:
        assert row["overtime"] == pytest.approx(row["hired"] * C.OVERTIME_MULTIPLIER)
        assert row["fte"] == pytest.approx(row["hours_per_year"] / C.HOURS_PER_FTE_YEAR)
    assert t["total"]["hired"] == pytest.approx(sum(r["hired"] for r in t["rows"]))


# ----------------------------------------------------------------------------- value and ROI
def test_value_keeps_cash_and_capacity_apart(saved):
    scenarios, _ = saved
    v = roi.value_of_gains(scenarios)
    d = scenarios["results"]["default"]["summary"]
    assert v["capacity_value"]["mean"] == pytest.approx(d["run_rate_value"]["mean"])
    assert v["cash_value"]["mean"] == pytest.approx(v["walkout_revenue"]["mean"] + v["overtime_avoided"]["mean"])
    assert v["cash_value"]["mean"] < v["capacity_value"]["mean"]
    rel = v["walkout_relative_reduction"]["mean"]
    assert v["walkouts_avoided"]["mean"] == pytest.approx(C.ED_VISITS_PER_YEAR * C.LWBS_RATE * rel)


def test_roi_and_payback_follow_from_costs_and_values(saved):
    scenarios, _ = saved
    r = roi.roi(scenarios)
    run = r["run_cost_per_year"]
    for basis in ("cash", "capacity"):
        x = r[basis]
        assert x["roi_per_year"]["mean"] == pytest.approx((x["value_per_year"]["mean"] - run) / run)
        assert x["cost_18_months"] == pytest.approx(roi.budget()["total_18_months"])
        month = x["payback_month"]
        if month is not None and month <= C.PLAN_MONTHS:
            assert sum(x["monthly_value"][:month]) >= sum(r["monthly_cost"][:month])
            assert sum(x["monthly_value"][:month - 1]) < sum(r["monthly_cost"][:month - 1])
    assert [a["adoption"] for a in r["by_adoption"]] == sorted(a["adoption"] for a in r["by_adoption"])


# ----------------------------------------------------------------------------- roadmap
def test_goals_are_tied_to_brief_baselines_and_include_an_equity_goal(saved):
    scenarios, _ = saved
    goals = R.goals(scenarios)
    assert 3 <= len(goals) <= 4
    assert any(g["kind"] == "equity" for g in goals)
    g1 = goals[0]
    assert g1["baseline"] == C.MEDIAN_BOARDING_H
    rel = g1["simulated_relative_change"]["mean"]
    raw = C.MEDIAN_BOARDING_H * (1 + C.GOAL_TARGET_SHARE * rel)
    # rounded to the brief's precision (0.1 h), never a precise simulated number
    assert abs(g1["target"] - raw) <= R.TARGET_STEP["h"] / 2 + 1e-9
    assert g1["target"] == pytest.approx(round(g1["target"], 1))
    equity = next(g for g in goals if g["kind"] == "equity")
    for part in equity["parts"]:
        narrowed = part["simulated"]["with_tool"] < part["simulated"]["baseline"]
        # a target narrows only if the simulation did (rounding can leave it at the baseline)
        assert part["target"] <= part["baseline"] if narrowed else part["target"] >= part["baseline"]
    for g in goals:
        assert g["track"] and g["if_off_track"]


def test_pilot_gates_follow_the_evidence_not_a_fixed_answer(saved):
    scenarios, metrics = saved
    gates = R.pilot_gates(metrics, scenarios, note_precision=0.95)
    assert gates[0]["status"] == R.MET
    worse = copy.deepcopy(metrics)
    worse["admission"]["deployed_policy"]["precision"] = C.PILOT_GATES["min_admission_precision"] - 0.01
    assert R.pilot_gates(worse, scenarios, note_precision=0.95)[0]["status"] == R.NOT_MET
    low = R.pilot_gates(metrics, scenarios, note_precision=C.PILOT_GATES["min_barrier_precision"] - 0.01)
    assert low[2]["status"] == R.NOT_MET
    assert any(g["status"] == R.PILOT_ONLY for g in gates)  # adoption and safety can only be measured live


def test_milestones_cover_both_phases_in_order():
    ms = R.milestones()
    assert {m["phase"] for m in ms} == {"pilot", "scale"}
    assert all(1 <= m["start"] <= m["end"] <= C.PLAN_MONTHS for m in ms)
    assert ms[-1]["end"] == C.PLAN_MONTHS and all(m["owner"] and m["done_when"] for m in ms)


# ----------------------------------------------------------------------------- saved files are current
@needs
def test_plan_json_is_what_the_code_produces_now(saved):
    scenarios, metrics = saved
    built = json.loads(json.dumps(_script("build_plan").build(scenarios, metrics)))
    assert built == json.loads((ROOT / "models" / "plan.json").read_text()), "run scripts/build_plan.py"


@needs
def test_strategy_md_is_current_and_has_no_dashes(saved):
    scenarios, metrics = saved
    plan = json.loads((ROOT / "models" / "plan.json").read_text())
    text = _script("export_strategy").render(plan, scenarios, metrics)
    assert text == (ROOT / "docs" / "STRATEGY.md").read_text(), "run scripts/export_strategy.py"
    assert "—" not in text and "–" not in text


@needs
def test_overview_impact_summary_reads_the_saved_results(saved):
    from halvian.data import live as L

    ranges = json.loads((ROOT / "models" / "impact_ranges.json").read_text())
    expected = next(s for s in ranges["scenarios"] if s["name"] == "Expected")
    items = {i["key"]: i for i in L.impact_summary()["items"]}
    lo, hi = expected["minutes_saved_per_admission"]
    assert items["minutes_saved"]["value"] == f"{lo} min to {hi} min"  # a range, never a single number
    assert items["break_even"]["value"] == f"{ranges['break_even']['minutes_per_admission']} min per admission"
    assert "not cash" in items["capacity_value"]["label"]
    assert L.impact_summary()["caption"] == ranges["caveat"]
    for item in items.values():
        assert item["label"] and item["value"] and item["note"]


@needs
def test_models_md_bias_table_matches_the_saved_test(saved):
    _, metrics = saved
    text = (ROOT / "docs" / "MODELS.md").read_text()
    for row in metrics["admission"]["fairness_case_mix"]["rows"]:
        if "unexplained_pts" in row:
            line = next(x for x in text.splitlines() if x.startswith(f"| {row['group'].split(' (')[0]} | "
                                                                      f"{row['admissions']:,} |"))
            assert f"{row['observed_miss_rate']:.1%}" in line and f"{row['unexplained_pts']:+.1f} pts" in line
