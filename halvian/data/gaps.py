"""Outcome gaps by payer: decomposition, before/after comparison and the equity guardrail.

Computation layer used by the data pipeline, the impact runner and the Fairness and Oversight page. UI-facing
wrappers may live in ``halvian/equity.py`` (owned by the Codex workstream).

An outcome gap (case brief) is a difference in how well the ED serves patients with one
type of coverage versus another. We track two gaps for two measures:

* Uninsured vs Commercial and Medicaid/CHIP vs Commercial,
* median door-to-provider time (minutes) and LWBS rate (percentage points).
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd

from halvian import config as C

GAP_PAIRS = ((C.UNINSURED, C.COMMERCIAL), (C.MEDICAID, C.COMMERCIAL))
GAP_LABELS = {
    (C.UNINSURED, C.COMMERCIAL): "Uninsured vs Commercial",
    (C.MEDICAID, C.COMMERCIAL): "Medicaid/CHIP vs Commercial",
}


def payer_outcomes(ed: pd.DataFrame) -> pd.DataFrame:
    """Median door-to-provider (seen patients) and LWBS rate (all arrivals) by payer."""
    seen = ed[~ed.lwbs & ed.provider_min.notna()]
    d2p = seen.groupby("payer", observed=True).door_to_provider_min.median()
    lwbs = ed.groupby("payer", observed=True).lwbs.mean() * 100
    n = ed.groupby("payer", observed=True).size()
    return pd.DataFrame({"d2p_median": d2p, "lwbs_pct": lwbs, "visits": n}).reindex(list(C.PAYERS))


def gaps(ed: pd.DataFrame) -> dict:
    """The four tracked gaps for one set of visits."""
    po = payer_outcomes(ed)
    out = {}
    for a, b in GAP_PAIRS:
        out[(a, b, "d2p")] = float(po.loc[a, "d2p_median"] - po.loc[b, "d2p_median"])
        out[(a, b, "lwbs")] = float(po.loc[a, "lwbs_pct"] - po.loc[b, "lwbs_pct"])
    return out


def verdict(change: float, tolerance: float) -> str:
    """Plain-language verdict for a change in a gap (negative = narrower)."""
    if change < -tolerance:
        return "narrowed"
    if change > tolerance:
        return "widened"
    return "stayed flat"


def gap_table(base_ed: pd.DataFrame, tool_ed: pd.DataFrame) -> pd.DataFrame:
    """Baseline vs scenario gaps with a verdict per gap.

    'Stayed flat' means the change is within half the guardrail tolerance, which is about
    the size of run-to-run noise in this simulation.
    """
    gb, gt = gaps(base_ed), gaps(tool_ed)
    rows = []
    for (a, b), label in GAP_LABELS.items():
        for measure, unit, tol in (
            ("d2p", "min", C.EQUITY_GUARDRAIL["door_to_provider_gap_min"] / 2),
            ("lwbs", "pts", C.EQUITY_GUARDRAIL["lwbs_gap_pts"] / 2),
        ):
            base, tool = gb[(a, b, measure)], gt[(a, b, measure)]
            rows.append({
                "Gap": label,
                "Measure": "Door-to-provider (median)" if measure == "d2p" else "Left without being seen",
                "Unit": unit,
                "Baseline": base,
                "With tool": tool,
                "Change": tool - base,
                "Verdict": verdict(tool - base, tol),
            })
    return pd.DataFrame(rows)


def monthly_gaps(ed: pd.DataFrame, month_col: str = "month") -> pd.DataFrame:
    rows = []
    for mth, g in ed.groupby(month_col):
        gg = gaps(g)
        rows.append({"month": mth, **{f"{a}|{m}": v for (a, _b, m), v in gg.items()}})
    return pd.DataFrame(rows).set_index("month")


def guardrail(base_monthly: pd.DataFrame, tool_monthly: pd.DataFrame) -> pd.DataFrame:
    """Equity guardrail: flag review or pause if any gap widens beyond tolerance versus
    baseline for ``consecutive_months`` months in a row."""
    tol = {"d2p": C.EQUITY_GUARDRAIL["door_to_provider_gap_min"], "lwbs": C.EQUITY_GUARDRAIL["lwbs_gap_pts"]}
    need = C.EQUITY_GUARDRAIL["consecutive_months"]
    rows = []
    for col in base_monthly.columns:
        payer, measure = col.split("|")
        widen = (tool_monthly[col] - base_monthly[col]) > tol[measure]
        run_len, max_run = 0, 0
        for w in widen:
            run_len = run_len + 1 if w else 0
            max_run = max(max_run, run_len)
        rows.append({
            "Gap": GAP_LABELS[(payer, C.COMMERCIAL)],
            "Measure": "Door-to-provider" if measure == "d2p" else "LWBS",
            "Tolerance": f"+{tol[measure]:g} {'min' if measure == 'd2p' else 'pts'}",
            "Months widened beyond tolerance": int(widen.sum()),
            "Longest run": max_run,
            "Status": "Review or pause" if max_run >= need else "OK",
        })
    return pd.DataFrame(rows)


def gap_decomposition(params: C.SimParams | None = None, seed: int = C.SEED) -> pd.DataFrame:
    """How much of each brief gap comes from mechanisms vs explicit payer adjustments.

    Three full-year runs: no payer-specific terms at all; mechanisms only (explicit
    adjustments switched off); and the calibrated model.
    """
    from halvian.data.cohort import build_cohort
    from halvian.data.simulate import run
    from halvian.validation import year_window

    p = params or C.DEFAULT_PARAMS
    zero = {k: 0.0 for k in C.PAYERS}
    one = {k: 1.0 for k in C.PAYERS}
    scenarios = {
        "No payer-specific terms": dataclasses.replace(
            p, payer_evening_tilt=zero, payer_weekend_tilt=zero, payer_low_acuity_shift=zero,
            payer_peak_low_acuity_extra=zero, patience_mult_by_payer=one,
            registration_extra_by_payer=zero, barrier_payer_logodds=zero, barrier_type_payer_tilt=one),
        "Mechanisms only": dataclasses.replace(p, patience_mult_by_payer=one, registration_extra_by_payer=zero),
        "Calibrated (mechanisms plus explicit adjustments)": p,
    }
    y0, y1 = year_window()
    rows = []
    for name, sp in scenarios.items():
        ed = run(build_cohort(seed=seed, params=sp)).ed
        ed = ed[(ed.arrival_min >= y0) & (ed.arrival_min < y1)]
        g = gaps(ed)
        rows.append({
            "Scenario": name,
            "Medicaid/CHIP vs Commercial, wait (min)": g[(C.MEDICAID, C.COMMERCIAL, "d2p")],
            "Uninsured vs Commercial, wait (min)": g[(C.UNINSURED, C.COMMERCIAL, "d2p")],
            "Medicaid/CHIP vs Commercial, LWBS (pts)": g[(C.MEDICAID, C.COMMERCIAL, "lwbs")],
            "Uninsured vs Commercial, LWBS (pts)": g[(C.UNINSURED, C.COMMERCIAL, "lwbs")],
        })
    brief = {
        "Scenario": "Case brief target",
        "Medicaid/CHIP vs Commercial, wait (min)": C.DOOR_TO_PROVIDER_BY_PAYER_MIN[C.MEDICAID] - C.DOOR_TO_PROVIDER_BY_PAYER_MIN[C.COMMERCIAL],
        "Uninsured vs Commercial, wait (min)": C.DOOR_TO_PROVIDER_BY_PAYER_MIN[C.UNINSURED] - C.DOOR_TO_PROVIDER_BY_PAYER_MIN[C.COMMERCIAL],
        "Medicaid/CHIP vs Commercial, LWBS (pts)": 100 * (C.LWBS_BY_PAYER[C.MEDICAID] - C.LWBS_BY_PAYER[C.COMMERCIAL]),
        "Uninsured vs Commercial, LWBS (pts)": 100 * (C.LWBS_BY_PAYER[C.UNINSURED] - C.LWBS_BY_PAYER[C.COMMERCIAL]),
    }
    return pd.DataFrame(rows + [brief]).round(2)


def explicit_adjustments(params: C.SimParams | None = None) -> pd.DataFrame:
    """Every payer-specific parameter, so nothing is hidden."""
    p = params or C.DEFAULT_PARAMS
    spec = [
        ("Mechanism", "Arrival-timing tilt, evenings and nights", "payer_evening_tilt", "extra share of visits 17:00 to 07:00"),
        ("Mechanism", "Arrival-timing tilt, weekends", "payer_weekend_tilt", "extra share of weekend visits"),
        ("Mechanism", "Lower average visit severity", "payer_low_acuity_shift", "shift of latent severity (more ESI 4 and 5)"),
        ("Mechanism", "Extra low-acuity visits at peak hours", "payer_peak_low_acuity_extra", "added shift at 10-13 and 17-22"),
        ("Mechanism", "More non-medical discharge barriers", "barrier_payer_logodds", "log-odds added to barrier chance"),
        ("Mechanism", "Tilt toward transport, home care, insurance barriers", "barrier_type_payer_tilt", "weight multiplier"),
        ("Explicit adjustment", "Patience before leaving unseen", "patience_mult_by_payer", "multiplier on patience (below 1 = leaves sooner)"),
        ("Explicit adjustment", "Extra registration minutes", "registration_extra_by_payer", "minutes added to registration"),
    ]
    rows = []
    for kind, label, attr, unit in spec:
        vals = getattr(p, attr)
        rows.append({"Type": kind, "Parameter": label, "Config name": attr, "Unit": unit,
                     **{k: vals[k] for k in C.PAYERS}})
    return pd.DataFrame(rows)


def relative_gap(a: float, b: float) -> float:
    return float(a / b) if b else np.nan
