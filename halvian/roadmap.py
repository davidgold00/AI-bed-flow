"""Roadmap: Month 18 goals, milestones, pilot gates and the Phase 2 adjustment, from saved results.

Goals are tied to the brief's baselines. Each target banks ``config.GOAL_TARGET_SHARE`` of the
improvement the paired simulation shows (its relative change applied to the brief's baseline),
because real adoption and data are messier than a simulation, rounded to the brief's own precision
(``TARGET_STEP``). Simulated results are reported as widened ranges, never as single numbers. Pilot gates are checked against
the synthetic evidence where it exists; the rest can only be measured in the pilot and say so.
Nothing here is hard-coded to pass: a gate the synthetic data fails is reported as not met.
"""

from __future__ import annotations

import numpy as np

from halvian import config as C
from halvian.ranges import (
    capacity_roi_range,
    cost_to_serve_range,
    minutes_range,
    room_hours_range,
    span,
    spread,
    widen,
)

MET, NOT_MET, PILOT_ONLY = "Met in the synthetic test", "Not met in the synthetic test", "Measured in the pilot"


def _rel_change(result: dict, key: str) -> list[float]:
    return [(s[f"{key}_tool"] - s[f"{key}_base"]) / s[f"{key}_base"] for s in result["per_seed"]]


def _gap_row(result: dict, gap: str, measure: str) -> dict:
    return next(r for r in result["gap_table"] if r["Gap"] == gap and r["Measure"].startswith(measure))


# Targets are rounded to the precision the brief uses for each measure  [our rule]
TARGET_STEP = {"h": 0.1, "%": 0.1, "min": 1, "pp": 0.1, "room-hours": 100}


def _round(value: float, unit: str) -> float:
    step = TARGET_STEP[unit]
    return round(round(value / step) * step, 1)


def _target(baseline: float, rel: float, unit: str) -> float:
    return _round(baseline * (1 + C.GOAL_TARGET_SHARE * rel), unit)


def _pct_range(rel: list[float]) -> str:
    """Relative changes across the synthetic years as a range widened to whole percents."""
    return span(widen(100 * min(rel), 100 * max(rel), 1), lambda x: f"{x:+d}%")


def goals(scenarios: dict) -> list[dict]:
    """Three operational and equity goals plus a safe-use goal, with tracking and actions."""
    d = scenarios["results"]["default"]
    out = []
    for gid, name, key, base, unit, label, track, action in (
        ("G1", "Shorter boarding", "boarding_median_h", C.MEDIAN_BOARDING_H, "h", "Median boarding, admit decision to leaving the ED",
         "Monthly median from the EHR: admit decision to leaving the ED room, all admissions.",
         "Two months off track: review the decision log for unworked flags and slow bed turnover; if under 40% "
         "of flags are acted on, run unit huddles and retrain; if flags are acted on but beds still open late, "
         "move discharge work earlier at rounds."),
        ("G2", "Fewer patients leave before being seen", "lwbs_pct", C.LWBS_RATE * 100, "%",
         "Share of arrivals who leave before a provider sees them",
         "Monthly share of arrivals who leave before a provider sees them, from registration and EHR times.",
         "Two months off track: check whether freed rooms are reaching the waiting room (room turnaround), "
         "and escalate to the ED operations lead."),
    ):
        rel = _rel_change(d, key)
        sim = [s[f"{key}_tool"] for s in d["per_seed"]]
        out.append({"id": gid, "kind": "operations", "goal": name, "measure": key, "label": label, "unit": unit,
                    "baseline": base, "target": _target(base, float(np.mean(rel)), unit),
                    "simulated_relative_change": {"mean": float(np.mean(rel)), "min": float(min(rel)),
                                                  "max": float(max(rel))},
                    "simulated_with_tool": {"mean": float(np.mean(sim)), "min": float(min(sim)), "max": float(max(sim))},
                    "track": track, "if_off_track": action})
    # equity: the brief's gaps, moved by the pooled gap change in the simulation
    med = _gap_row(d, "Medicaid/CHIP vs Commercial", "Door")
    uni = _gap_row(d, "Uninsured vs Commercial", "Left")
    med_base = C.DOOR_TO_PROVIDER_BY_PAYER_MIN[C.MEDICAID] - C.DOOR_TO_PROVIDER_BY_PAYER_MIN[C.COMMERCIAL]
    uni_base = 100 * (C.LWBS_BY_PAYER[C.UNINSURED] - C.LWBS_BY_PAYER[C.COMMERCIAL])
    med_rel = (med["With tool"] - med["Baseline"]) / med["Baseline"]
    uni_rel = (uni["With tool"] - uni["Baseline"]) / uni["Baseline"]
    out.append({
        "id": "G3", "kind": "equity", "goal": "Narrow the gaps for Medicaid/CHIP and Uninsured patients",
        "measure": "medicaid_wait_gap_min and uninsured_walkout_gap_pts", "unit": "min and pp",
        "parts": [
            {"measure": "Medicaid/CHIP minus Commercial, median minutes to a provider", "unit": "min",
             "baseline": med_base, "target": _target(med_base, med_rel, "min"),
             "simulated": {"baseline": med["Baseline"], "with_tool": med["With tool"], "verdict": med["Verdict"]}},
            {"measure": "Uninsured minus Commercial, share leaving before being seen", "unit": "pp",
             "baseline": uni_base, "target": _target(uni_base, uni_rel, "pp"),
             "simulated": {"baseline": uni["Baseline"], "with_tool": uni["With tool"], "verdict": uni["Verdict"]}},
        ],
        "guardrail": f"No payer gap may widen by more than {C.EQUITY_GUARDRAIL['door_to_provider_gap_min']:g} min "
                     f"or {C.EQUITY_GUARDRAIL['lwbs_gap_pts']:g} pp for {C.EQUITY_GUARDRAIL['consecutive_months']} "
                     "months in a row.",
        "track": "Monthly gap table by payer group (payer is used only to audit, never to predict).",
        "if_off_track": "A gap that widens past the guardrail pauses the part of the tool involved for review by the "
                        "oversight committee; a gap that stays flat for two quarters triggers the Phase 2 threshold "
                        "review and targeted outreach with registration and social work.",
    })
    out.append({
        "id": "G4", "kind": "adoption and safe use", "goal": "Staff use the tool and still think for themselves",
        "measure": "acted_on_share, override_rate, override_reasons", "unit": "%",
        "parts": [
            {"measure": "Flags acted on (approved or worked)", "unit": "%", "baseline": None,
             "target": 100 * C.IMPACT_DEFAULTS["adoption"]},
            {"measure": "Override rate (healthy band)", "unit": "%", "baseline": None,
             "target": [100 * C.PAUSE_CONDITIONS["min_override_rate"], 100 * C.PAUSE_CONDITIONS["max_override_rate"]]},
            {"measure": "Overrides with a recorded reason", "unit": "%", "baseline": None,
             "target": 100 * C.PILOT_GATES["min_override_reason_share"]},
        ],
        "track": "The decision log: every approve and override with the person, time and reason.",
        "if_off_track": "Under 2% overrides suggests rubber-stamping: audit a sample of approvals with the unit "
                        "lead. Over 40% suggests mistrust or a model problem: review reasons and recalibrate.",
    })
    return out


def milestones() -> list[dict]:
    return [{"start": a, "end": b, "phase": ph, "milestone": m, "owner": o, "done_when": dw}
            for a, b, ph, m, o, dw in C.ROADMAP_MILESTONES]


def pilot_gates(metrics: dict, scenarios: dict, note_precision: float | None = None) -> list[dict]:
    """Criteria to move from the pilot to Phase 2, checked against the synthetic evidence where possible."""
    g = C.PILOT_GATES
    adm = metrics["admission"]["deployed_policy"]
    dis = metrics["discharge"]["at_threshold"]
    case_mix = metrics["admission"].get("fairness_case_mix", {}).get("rows", [])
    worst = max((abs(r["unexplained_pts"]) for r in case_mix if "unexplained_pts" in r), default=None)
    pilot = scenarios["results"]["pilot"]
    saved = [s["mean_minutes_saved_per_admission"] for s in pilot["per_seed"]]
    widened = [r for r in pilot["gap_table"] if r["Verdict"] == "Widened"]

    def row(gate, threshold, value, ok, source):
        status = PILOT_ONLY if value is None else (MET if ok else NOT_MET)
        return {"gate": gate, "threshold": threshold, "synthetic_value": value, "status": status, "source": source}

    rows = [
        row("Admission flags are right often enough", f"precision at least {g['min_admission_precision']:.0%}",
            adm["precision"], adm["precision"] >= g["min_admission_precision"],
            "models/metrics.json admission.deployed_policy.precision"),
        row("Rounds-list flags are right often enough", f"precision at least {g['min_discharge_precision']:.0%}",
            dis["precision"], dis["precision"] >= g["min_discharge_precision"],
            "models/metrics.json discharge.at_threshold.precision"),
        row("Barriers in notes are real when case managers check", f"at least {g['min_barrier_precision']:.0%} confirmed",
            note_precision, (note_precision or 0) >= g["min_barrier_precision"],
            "models/metrics.json note_reader (reader the app shows)"),
        row("No payer group is missed more than its triage levels and ages explain",
            f"unexplained miss rate within {g['max_unexplained_miss_pts']:g} points",
            worst, worst is not None and worst <= g["max_unexplained_miss_pts"],
            "models/metrics.json admission.fairness_case_mix"),
        row("The pilot unit's patients are not worse off", "minutes saved per admission above zero in every run, "
            "no payer gap widened", min(saved), min(saved) > 0 and not widened,
            "models/scenarios.json results.pilot"),
        row("Staff act on the flags", f"at least {g['min_adoption']:.0%} acted on", None, False, "decision log"),
        row("Overrides are explained", f"at least {g['min_override_reason_share']:.0%} with a reason", None, False,
            "decision log"),
        row("Staff find it useful", f"at least {g['min_staff_useful_share']:.0%} say the flags help them plan",
            None, False, "pilot survey"),
        row("No safety event linked to the tool", "zero in 90 days", None, False, "incident reporting system"),
    ]
    return rows


def phase2_adjustment(metrics: dict, scenarios: dict) -> dict:
    """What the pilot would adjust before scaling: the alert threshold, with its trade-offs."""
    by_base = metrics["admission"].get("policy_by_base_threshold", {})
    out = []
    for base in C.POLICY_BASE_THRESHOLDS:
        key = "default" if base == C.ALERT_THRESHOLD else f"threshold={base:g}"
        result = scenarios["results"].get(key)
        pol = by_base.get(f"{base:.2f}", {})
        if result is None:
            continue
        gaps = {f"{r['Gap']} | {r['Measure']}": r["Verdict"] for r in result["gap_table"]}
        out.append({
            "base_threshold": base,
            "minutes_saved": result["summary"]["mean_minutes_saved_per_admission"],
            "precision": pol.get("policy", {}).get("precision"), "recall": pol.get("policy", {}).get("recall"),
            "alerts_per_day": pol.get("alerts_per_day"),
            "case_gaps_narrowed": sum(v == "Narrowed" for k, v in gaps.items()
                                      if k.startswith((C.MEDICAID, C.UNINSURED))),
            "case_gaps_total": sum(1 for k in gaps if k.startswith((C.MEDICAID, C.UNINSURED))),
            "any_gap_widened": [k for k, v in gaps.items() if v == "Widened"],
            "gaps": gaps,
        })
    return {"question": "Should Phase 2 lower the base alert threshold?", "options": out,
            "rule": "Pick the lowest threshold whose flag precision stays at or above the pilot gate and whose "
                    "gap verdicts narrow the Medicaid/CHIP and Uninsured gaps without widening any other; confirm "
                    "on pilot data before changing it."}


def kpis(scenarios: dict, roi_out: dict, goal_rows: list[dict]) -> list[dict]:
    """The KPI list for the Budget and ROI section: operations, equity, use, cost-to-serve and ROI.

    ``simulated`` says what the paired simulation shows for the same measure (test quarter), as a
    range across the synthetic years widened to round numbers, and as a relative change where the
    simulated quarter's level differs from the brief's yearly baseline. Never a single number.
    """
    d = scenarios["results"]["default"]
    by_id = {g["id"]: g for g in goal_rows}
    d2p_rel = _rel_change(d, "d2p_median")
    hours = d["summary"]["run_rate_bed_hours"]

    pct = _pct_range
    run = roi_out["run_cost_per_year"]
    minutes = minutes_range(d)  # capacity measures all follow the minute range, so they agree
    g3 = by_id["G3"]["parts"]
    return [
        {"kpi": "Median boarding", "kind": "operations", "unit": "h", "baseline": by_id["G1"]["baseline"],
         "direction": "down", "target": by_id["G1"]["target"], "simulated": pct(_rel_change(d, "boarding_median_h"))},
        {"kpi": "Share leaving before being seen", "kind": "operations", "unit": "%",
         "baseline": by_id["G2"]["baseline"], "target": by_id["G2"]["target"], "direction": "down",
         "simulated": pct(_rel_change(d, "lwbs_pct"))},
        {"kpi": "Median minutes to a provider", "kind": "operations", "unit": "min",
         "baseline": C.MEDIAN_DOOR_TO_PROVIDER_MIN, "direction": "down",
         "target": _target(C.MEDIAN_DOOR_TO_PROVIDER_MIN, float(np.mean(d2p_rel)), "min"),
         "simulated": pct(d2p_rel)},
        {"kpi": "ED room-hours freed per year", "kind": "operations", "unit": "h", "baseline": 0, "direction": "up",
         "target": _round(C.GOAL_TARGET_SHARE * hours["mean"], "room-hours"),
         "simulated": span(room_hours_range(minutes), lambda x: f"{x:,} h")},
        *({"kpi": p["measure"], "kind": "equity", "unit": p["unit"], "baseline": p["baseline"], "target": p["target"],
           "direction": "down", "simulated": f"gap {p['simulated']['verdict'].lower()}"} for p in g3),
        {"kpi": "Flags acted on", "kind": "use", "unit": "%", "baseline": None, "direction": "up",
         "target": by_id["G4"]["parts"][0]["target"], "simulated": "50% assumed in the simulation"},
        {"kpi": "Override rate", "kind": "use", "unit": "%", "baseline": None, "direction": "band",
         "target": by_id["G4"]["parts"][1]["target"], "simulated": "measured in the pilot"},
        {"kpi": "Cost per ED room-hour freed (cost to serve)", "kind": "cost", "unit": "$", "baseline": None,
         "direction": "down",
         "target": C.BOARDING_COST_PER_BED_HOUR / 2,
         "simulated": span(cost_to_serve_range(minutes, run), lambda x: f"${x:,}")},
        {"kpi": "Yearly ROI on freed capacity (brief's $350 per room-hour)", "kind": "ROI", "unit": "x",
         "baseline": None, "target": 1.0, "direction": "up",
         "simulated": span(capacity_roi_range(minutes, run), lambda x: f"{x:,}%")},
        {"kpi": "Yearly cash ROI (recovered visits and overtime only)", "kind": "ROI", "unit": "x", "baseline": None,
         "target": 0.0, "direction": "up",
         "simulated": span(spread(roi_out["cash"]["roi_per_year"], 10, 100), lambda x: f"{x:,}%")},
    ]
