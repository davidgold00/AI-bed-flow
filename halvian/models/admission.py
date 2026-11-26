"""Admission predictor: chance that an ED patient will be admitted, scored at triage.

Payer-blind by design (PLAN.md decision 1). Only information available at the end of
triage is used. Patients who left without being seen have no disposition, so they are
not in the labelled cohort; their share is reported as outcome coverage.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from halvian import config as C
from halvian.models.common import split_labels
from halvian.models.tabular import TabularModel

PREDICTION_TIME = "end of triage"
NUMERIC = ["age", "heart_rate", "systolic_bp", "resp_rate", "spo2", "temp_c", "recent_ed_visits_12m"]
CATEGORICAL = ["chief_complaint", "esi", "arrival_mode", "arrival_period", "weekend", "winter"]
FEATURES = NUMERIC + CATEGORICAL
# Everything in this set is recorded by the end of triage.
AVAILABLE_AT_PREDICTION = {
    "age", "sex", "heart_rate", "systolic_bp", "resp_rate", "spo2", "temp_c",
    "recent_ed_visits_12m", "chief_complaint", "esi", "arrival_mode", "arrival_period",
    "arrival_hour", "arrival_dow", "weekend", "winter", "arrival_month",
}
LABEL = "admitted"
SCORE_TIME = "triage_end_min"
OUTCOME_TIME = "decision_min"
AGE_BANDS = (0, 18, 45, 65, 80, 200)
AGE_BAND_LABELS = ("0-17", "18-44", "45-64", "65-79", "80+")


def arrival_period(hour: pd.Series) -> pd.Series:
    bins = pd.cut(hour, [-1, 6, 10, 14, 18, 22, 23],
                  labels=["night", "morning", "midday", "afternoon", "evening", "late evening"])
    return bins.astype(str).replace({"late evening": "night"})


def prepare(ed: pd.DataFrame) -> pd.DataFrame:
    """Model-ready features (adds arrival_period and weekend)."""
    X = ed.copy()
    X["arrival_period"] = arrival_period(X.arrival_hour)
    X["weekend"] = X.arrival_dow >= 5
    X["esi"] = X.esi.astype(int)
    return X


def labelled_cohort(ed: pd.DataFrame) -> pd.DataFrame:
    """Seen patients (a disposition exists) with split labels."""
    X = prepare(ed[ed.decision_min.notna() & ~ed.lwbs])
    X["split"] = split_labels(X[SCORE_TIME], X[OUTCOME_TIME]).to_numpy()
    X["y"] = X[LABEL].astype(bool)
    return X


def new_model(kind: str, with_payer: bool = False) -> TabularModel:
    cats = CATEGORICAL + (["payer"] if with_payer else [])
    return TabularModel(kind=kind, numeric=list(NUMERIC), categorical=cats)


def age_band(age: pd.Series) -> pd.Series:
    return pd.cut(age, AGE_BANDS, right=False, labels=AGE_BAND_LABELS).astype(str)


def fit_unit_lookup(admitted: pd.DataFrame, alpha: float = 2.0) -> pd.DataFrame:
    """P(admitting unit | complaint, ESI, age band) with smoothing toward the complaint mix."""
    a = admitted.assign(age_band=age_band(admitted.age))
    units = list(C.UNIT_NAMES)
    by_c = pd.crosstab(a.chief_complaint, a.admit_unit).reindex(columns=units, fill_value=0)
    by_c = (by_c + 0.5).div((by_c + 0.5).sum(axis=1), axis=0)
    full = pd.crosstab([a.chief_complaint, a.esi, a.age_band], a.admit_unit).reindex(columns=units, fill_value=0)
    prior = by_c.loc[full.index.get_level_values(0)].to_numpy()
    probs = (full.to_numpy() + alpha * prior) / (full.sum(axis=1).to_numpy()[:, None] + alpha)
    out = pd.DataFrame(probs, index=full.index, columns=units).reset_index()
    out.attrs["by_complaint"] = by_c
    return out


def unit_probabilities(df: pd.DataFrame, lookup: pd.DataFrame, by_complaint: pd.DataFrame) -> pd.DataFrame:
    keyed = df.assign(age_band=age_band(df.age))[["chief_complaint", "esi", "age_band"]]
    merged = keyed.reset_index().merge(lookup, on=["chief_complaint", "esi", "age_band"], how="left").set_index("index")
    units = list(C.UNIT_NAMES)
    missing = merged[units[0]].isna()
    if missing.any():
        fill = by_complaint.reindex(merged.loc[missing, "chief_complaint"]).to_numpy()
        merged.loc[missing, units] = fill
    return merged.loc[df.index, units].astype(float)


def crowding_series(census: pd.DataFrame) -> pd.Series:
    """ED crowding at each hour: (patients in ED spaces + not yet roomed) / 48 spaces."""
    in_use = census[[c for c in census.columns if c.startswith("ED ") and c.endswith("|in_use")]].sum(axis=1)
    return pd.Series(((in_use + census["ED|not_yet_roomed"]) / C.ED_TOTAL_SPACES).to_numpy(),
                     index=census.hour_min.to_numpy())


def policy_flags(df: pd.DataFrame, p: np.ndarray, crowding: pd.Series, typical: float,
                 base_threshold: float = C.ALERT_THRESHOLD, moving: bool = C.MOVING_THRESHOLD_ON,
                 response_delay_h: float = C.IMPACT_DEFAULTS["staff_response_delay_h"]) -> pd.DataFrame:
    """Replay the deployed policy on recorded visits using only what is known each hour.

    A patient is flagged at the first hourly batch at least ``response_delay_h`` after
    triage, while still undecided and in the ED, at which P(admit) clears the moving
    threshold for that hour's crowding. Lead time = admit decision minus flag time.
    """
    from halvian.models.thresholds import moving_threshold

    hours = crowding.index.to_numpy()
    crowd = crowding.to_numpy()
    thr_by_hour = np.array([moving_threshold(c, typical, base=base_threshold, enabled=moving) for c in crowd])
    first = np.ceil((df.triage_end_min.to_numpy() + response_delay_h * 60) / 60.0) * 60.0
    end = np.fmin(df.decision_min.fillna(np.inf).to_numpy(), df.departure_min.to_numpy())
    flag_time = np.full(len(df), np.nan)
    pos = np.searchsorted(hours, first)
    for i in range(len(df)):
        k = pos[i]
        while k < len(hours) and hours[k] < end[i]:
            if p[i] >= thr_by_hour[k]:
                flag_time[i] = hours[k]
                break
            k += 1
    out = pd.DataFrame({"flag_time_min": flag_time}, index=df.index)
    out["flagged"] = ~np.isnan(flag_time)
    out["lead_h"] = (df.decision_min.to_numpy() - flag_time) / 60
    return out
