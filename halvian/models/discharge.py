"""Discharge predictor: chance an inpatient leaves within the next 24 hours, scored at
07:00 rounds.

Features are what the unit team has at rounds: time in hospital so far, unit, diagnosis
group, admission source, mobility score, lab trend, the day of the week and the barrier
flags the (placeholder) note reader found in that morning's note. The reader's output is
used, never the ground-truth labels, so reader mistakes flow through honestly. Payer is
not a feature.

Synthetic-data note: mobility and lab trend are noisy observations of recovery, generated
from the simulator's latent recovery progress in the same way vitals are generated from
latent severity. They are observable at rounds in the synthetic world.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from halvian import config as C
from halvian.data.cohort import MIN_PER_DAY
from halvian.models.common import split_labels
from halvian.models.tabular import TabularModel

PREDICTION_TIME = "07:00 rounds"
BARRIER_FEATURES = [f"note_{b}" for b in C.BARRIER_TYPES]
NUMERIC = ["los_so_far_h", "mobility_score", "lab_trend", *BARRIER_FEATURES]
CATEGORICAL = ["unit", "dx_group", "source", "rounds_dow"]
FEATURES = NUMERIC + CATEGORICAL
AVAILABLE_AT_PREDICTION = {
    "los_so_far_h", "mobility_score", "lab_trend", "unit", "dx_group", "source", "rounds_dow",
    "age", *BARRIER_FEATURES,
}
LABEL = "discharged_24h"
SCORE_TIME = "rounds_min"


def findings_table(notes: pd.DataFrame, findings: list[list[dict]]) -> pd.DataFrame:
    rows = [(nid, f["type"], f["evidence_span"][0], f["evidence_span"][1], f["confidence"])
            for nid, fs in zip(notes.note_id, findings, strict=True) for f in fs]
    return pd.DataFrame(rows, columns=["note_id", "barrier_type", "start", "end", "confidence"])


def add_barrier_flags(days: pd.DataFrame, found: pd.DataFrame) -> pd.DataFrame:
    X = days.copy()
    for b in C.BARRIER_TYPES:
        ids = set(found.loc[found.barrier_type == b, "note_id"])
        X[f"note_{b}"] = X.note_id.isin(ids).astype(float)
    X["note_any_barrier"] = X[BARRIER_FEATURES].max(axis=1)
    return X


def labelled_cohort(days: pd.DataFrame) -> pd.DataFrame:
    X = days.copy()
    outcome_known = X.rounds_min + MIN_PER_DAY  # the 24 h window must have closed
    X["split"] = split_labels(X[SCORE_TIME], outcome_known).to_numpy()
    X["y"] = X[LABEL].astype(bool)
    return X


def new_model(kind: str, with_payer: bool = False) -> TabularModel:
    cats = CATEGORICAL + (["payer"] if with_payer else [])
    return TabularModel(kind=kind, numeric=list(NUMERIC), categorical=cats)


def discharge_time_profile(train: pd.DataFrame, step_h: float = 0.25) -> np.ndarray:
    """CDF of hours from rounds to departure, among rows discharged within 24 h.

    Used by the forecast to spread a 24-hour probability over shorter horizons.
    """
    pos = train[train.y]
    hrs = (pos.discharge_min - pos.rounds_min) / 60
    grid = np.arange(0, 24 + step_h, step_h)
    return np.searchsorted(np.sort(hrs.to_numpy()), grid, side="right") / max(len(hrs), 1)


LEAD_COHORTS = {
    "true_positive_rounds": "Rounds rows flagged (chance at or above the list threshold) and followed by a "
                            "departure within 24 hours. Lead = hours from that 07:00 rounds to departure.",
    "missed_positive_rounds": "Rounds rows not flagged but followed by a departure within 24 hours. Hours from "
                              "that rounds to departure = warning time the list did not give.",
    "eligible_positive_stays": "Stays that left before the end of the test window and had at least one rounds "
                               "row within 24 hours of leaving. Flagged in time = at least one of those rows "
                               "was flagged; missed = none was.",
    "all_flags_diagnostic": "Stays that left before the end of the test window and were flagged at least once. "
                            "Hours from the first flag at any rounds to departure; can exceed 24 hours.",
}


def lead_metrics(days: pd.DataFrame, p: np.ndarray, threshold: float, window_end: float) -> dict:
    """Timing of discharge flags on explicit cohorts (Codex HANDOFF item 8). See ``LEAD_COHORTS``."""
    d = days.assign(p=p, flag=p >= threshold)
    left = d[d.discharge_min < window_end]
    hours = (left.discharge_min - left.rounds_min) / 60
    tp, fn = left.flag & left.y, ~left.flag & left.y
    pos = left[left.y]
    by_stay = pos.groupby("stay_id").flag.any()
    first = left[left.flag].groupby("stay_id").rounds_min.min()
    dep = left.groupby("stay_id").discharge_min.first()
    all_lead = ((dep.loc[first.index] - first) / 60) if len(first) else pd.Series(dtype=float)

    def med(x: pd.Series):
        return float(x.median()) if len(x) else None

    return {
        "definition": " ".join(f"{k}: {v}" for k, v in LEAD_COHORTS.items()),
        "cohorts": LEAD_COHORTS,
        "true_positive_rounds": int(tp.sum()),
        "median_h_true_positive": med(hours[tp]),
        "missed_positive_rounds": int(fn.sum()),
        "median_h_missed_positive": med(hours[fn]),
        "eligible_positive_stays": int(len(by_stay)),
        "stays_flagged_in_time": int(by_stay.sum()),
        "stays_missed": int((~by_stay).sum()),
        "share_flagged_in_time": float(by_stay.mean()) if len(by_stay) else None,
        "all_flags_median_h": med(all_lead),
        "all_flags_share_over_24h": float((all_lead > 24).mean()) if len(all_lead) else None,
        "all_flags_stays": int(len(all_lead)),
    }
