"""Model fairness by payer group, with explicit denominators and warning levels.

For each payer group: AUC, calibration gap (mean predicted chance minus observed rate,
in percentage points), false negative rate (missed true cases divided by all true cases)
and flag rate (flags divided by eligible predictions). A metric with fewer than 30
positives or negatives reads "insufficient data".

Warning levels (config.FAIRNESS_TOLERANCES), shown in amber and red:
  * AUC more than 0.03 (amber) or 0.05 (red) below the overall AUC
  * calibration gap larger than 2 (amber) or 4 (red) points in either direction
  * false negative rate more than 5 (amber) or 10 (red) points above overall
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from halvian import config as C
from halvian.models.common import binary_metrics

LEVELS = ("ok", "amber", "red")


def _level(value: float | None, amber: float, red: float) -> str:
    if value is None or np.isnan(value):
        return "insufficient data"
    if value > red:
        return "red"
    if value > amber:
        return "amber"
    return "ok"


def fairness_table(df: pd.DataFrame, p_col: str = "p", y_col: str = "y", flag_col: str = "flag",
                   group_col: str = "payer") -> pd.DataFrame:
    tol = C.FAIRNESS_TOLERANCES
    overall = binary_metrics(df[y_col].to_numpy(), df[p_col].to_numpy(), df[flag_col].to_numpy())
    rows = [{"group": "All patients", **overall, "auc_level": "ok", "calibration_level":
             _level(abs(overall["calibration_gap_pts"]), tol["calibration_gap_pts"]["amber"],
                    tol["calibration_gap_pts"]["red"]), "fnr_level": "ok"}]
    for g in C.PAYERS:
        sub = df[df[group_col] == g]
        if sub.empty:
            continue
        m = binary_metrics(sub[y_col].to_numpy(), sub[p_col].to_numpy(), sub[flag_col].to_numpy())
        auc_drop = None if m["auc"] is None or overall["auc"] is None else overall["auc"] - m["auc"]
        fnr_gap = None if m.get("fnr") is None or overall.get("fnr") is None else 100 * (m["fnr"] - overall["fnr"])
        cal = None if m["calibration_gap_pts"] is None else abs(m["calibration_gap_pts"])
        rows.append({
            "group": g, **m,
            "auc_level": _level(auc_drop, tol["auc_below_overall"]["amber"], tol["auc_below_overall"]["red"]),
            "calibration_level": _level(cal, tol["calibration_gap_pts"]["amber"], tol["calibration_gap_pts"]["red"]),
            "fnr_level": _level(fnr_gap, tol["fnr_above_overall_pts"]["amber"], tol["fnr_above_overall_pts"]["red"]),
        })
    out = pd.DataFrame(rows)
    out["worst_level"] = out[["auc_level", "calibration_level", "fnr_level"]].apply(
        lambda r: "red" if "red" in r.values else ("amber" if "amber" in r.values else "ok"), axis=1)
    return out


def tolerance_rows() -> pd.DataFrame:
    t = C.FAIRNESS_TOLERANCES
    return pd.DataFrame([
        {"Check": "AUC below the overall AUC", "Amber if more than": f"{t['auc_below_overall']['amber']:.2f}",
         "Red if more than": f"{t['auc_below_overall']['red']:.2f}"},
        {"Check": "Calibration gap (predicted minus observed), either direction",
         "Amber if more than": f"{t['calibration_gap_pts']['amber']:g} pts", "Red if more than": f"{t['calibration_gap_pts']['red']:g} pts"},
        {"Check": "False negative rate above the overall rate",
         "Amber if more than": f"{t['fnr_above_overall_pts']['amber']:g} pts", "Red if more than": f"{t['fnr_above_overall_pts']['red']:g} pts"},
    ])


AGE_BANDS = (-1, 17, 44, 64, 79, 200)
AGE_LABELS = ("under 18", "18 to 44", "45 to 64", "65 to 79", "80 and over")


def case_mix_check(df: pd.DataFrame, *, flag_col: str = "flag", y_col: str = "y", group_col: str = "payer",
                   strata: tuple[str, ...] = ("esi", "age_band")) -> list[dict]:
    """Pre-launch bias test: is a group's miss rate explained by who arrives, or by the model?

    Among true admissions, a group's *expected* miss rate is what it would be if each of its
    patients were missed at the rate of everyone with the same triage level and age band
    (direct standardization). ``unexplained_pts`` = observed minus expected, in points. A
    large unexplained gap means the model treats similar patients differently by group;
    a gap that standardization removes comes from case mix (younger patients, lower acuity).
    Payer is used here only to audit, never to predict.
    """
    pos = df[df[y_col].astype(bool)].copy()
    if "age_band" in strata and "age_band" not in pos:
        pos["age_band"] = pd.cut(pos["age"], AGE_BANDS, labels=AGE_LABELS).astype(str)
    pos["miss"] = ~pos[flag_col].astype(bool)
    key = pos[list(strata)].astype(str).agg("|".join, axis=1)
    pos["expected"] = key.map(pos.groupby(key)["miss"].mean())
    overall = float(pos["miss"].mean())
    tol = C.CASE_MIX_UNEXPLAINED_PTS
    rows = []
    for g in C.PAYERS:
        sub = pos[pos[group_col] == g]
        if len(sub) < 30:
            rows.append({"group": g, "admissions": int(len(sub)), "level": "insufficient data"})
            continue
        obs, exp = float(sub["miss"].mean()), float(sub["expected"].mean())
        unexplained = 100 * (obs - exp)
        rows.append({"group": g, "admissions": int(len(sub)), "observed_miss_rate": obs,
                     "expected_from_case_mix": exp, "gap_vs_overall_pts": 100 * (obs - overall),
                     "explained_by_case_mix_pts": 100 * (exp - overall), "unexplained_pts": unexplained,
                     "level": _level(abs(unexplained), tol["amber"], tol["red"])})
    return rows
