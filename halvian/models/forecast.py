"""Bed forecast by unit: expected net usable beds 4, 8 and 24 hours ahead.

**Net usable beds** on a unit = clean, empty, unassigned beds minus patients already
waiting in that unit's bed queue. Positive means spare beds; negative means patients
will keep waiting (in the ED, that is boarding). Assigning a bed to a waiting patient
does not change the number. It goes up by one when a bed is cleaned and ready, and down
by one when a new bed request joins the queue. So:

    net(t + h) = net(t) + beds made ready in (t, t+h] - new requests in (t, t+h]

Everything uses only what is known at time t (REVIEW finding 4):

* Beds made ready: beds being cleaned now (typical cleaning time), plus inpatients who
  may leave, from the latest 07:00 rounds probability spread over the horizon with the
  time-of-day discharge profile, then cleaned.
* New requests: ED patients already admitted but not yet queued (counted once); ED
  patients still undecided (P(admit) x P(unit) x chance the request lands in time);
  patients not yet arrived and direct or elective admissions (historical rates by hour,
  weekday or weekend, and season).
* The 80% band treats each patient as an independent yes/no event and arrivals as
  Poisson. Its real coverage is checked in the backtest.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from halvian import config as C
from halvian.data.cohort import MIN_PER_DAY

HORIZONS_H = (4, 8, 24)
Z80 = 1.2816
UNSCORED_P24 = 0.04  # inpatients admitted since the last rounds (rarely leave within a day)


@dataclass
class ForecastTables:
    clean_lag_min: float
    profile: np.ndarray  # CDF over hours from rounds to departure (0.25 h grid)
    triage_to_request: np.ndarray  # sorted minutes, admitted patients
    decision_to_request: np.ndarray  # sorted minutes, admitted patients
    future_ed: dict = field(default_factory=dict)  # (unit, h) -> Series indexed (hour, weekend, winter)
    non_ed: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return self.__dict__


def _calendar(t_min: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    day = (t_min // MIN_PER_DAY).astype(int)
    dates = pd.to_datetime(C.WARMUP_START) + pd.to_timedelta(day, unit="D")
    hour = ((t_min % MIN_PER_DAY) // 60).astype(int)
    weekend = np.asarray(dates.day_of_week) >= 5
    winter = np.isin(np.asarray(dates.month), C.WINTER_MONTHS)
    return hour, np.asarray(weekend), np.asarray(winter)


def _window_counts(start_k: np.ndarray, end_k: np.ndarray, n: int) -> np.ndarray:
    """For each grid index k, how many intervals [start_k, end_k) contain k."""
    diff = np.zeros(n + 1)
    s = np.clip(start_k, 0, n)
    e = np.clip(end_k, 0, n)
    keep = e > s
    np.add.at(diff, s[keep], 1)
    np.add.at(diff, e[keep], -1)
    return np.cumsum(diff)[:n]


def fit_tables(ed: pd.DataFrame, stays: pd.DataFrame, rounds_train: pd.DataFrame,
               t0: float, t1: float, profile: np.ndarray) -> ForecastTables:
    """Historical rates from the training window [t0, t1), using only events observable
    before the cutoff t1 (Codex HANDOFF item 7). Demand windows end before t1."""
    adm = ed[ed.admitted & ed.bed_request_min.notna() & (ed.bed_request_min < t1)]
    done = stays[stays.clean_min.notna() & (stays.clean_min < t1)]
    lag = (done.clean_min - done.discharge_min).dropna()
    tables = ForecastTables(
        clean_lag_min=float(lag.median()),
        profile=profile,
        triage_to_request=np.sort((adm.bed_request_min - adm.triage_end_min).dropna().to_numpy()),
        decision_to_request=np.sort((adm.bed_request_min - adm.decision_min).dropna().to_numpy()),
    )
    grid = np.arange(t0, t1 - max(HORIZONS_H) * 60.0, 60.0)  # every window closes before t1
    n = len(grid)
    hour, weekend, winter = _calendar(grid)
    key = pd.MultiIndex.from_arrays([hour, weekend, winter], names=["hour", "weekend", "winter"])
    ne = stays[(stays.kind == "NonED") & (stays.queue_entry_min < t1)]
    for u in C.UNIT_NAMES:
        a = adm[adm.admit_unit == u]
        q = ne[ne.intended_unit == u]
        for h in HORIZONS_H:
            # future-arrival ED requests: t in [request - h, arrival)
            sk = np.ceil((a.bed_request_min.to_numpy() - h * 60 - t0) / 60).astype(int)
            ek = np.ceil((a.arrival_min.to_numpy() - t0) / 60).astype(int)
            cnt = _window_counts(sk, ek, n)
            tables.future_ed[(u, h)] = pd.Series(cnt, index=key).groupby(level=[0, 1, 2]).mean()
            sk = np.ceil((q.queue_entry_min.to_numpy() - h * 60 - t0) / 60).astype(int)
            ek = np.ceil((q.queue_entry_min.to_numpy() - t0) / 60).astype(int)
            cnt = _window_counts(sk, ek, n)
            tables.non_ed[(u, h)] = pd.Series(cnt, index=key).groupby(level=[0, 1, 2]).mean()
    return tables


def _cdf(sorted_vals: np.ndarray, x: np.ndarray) -> np.ndarray:
    return np.searchsorted(sorted_vals, x, side="right") / max(len(sorted_vals), 1)


def _cond(sorted_vals: np.ndarray, elapsed: np.ndarray, h_min: float) -> np.ndarray:
    """P(event within the next h | not yet happened after `elapsed`)."""
    f0 = _cdf(sorted_vals, elapsed)
    f1 = _cdf(sorted_vals, elapsed + h_min)
    return np.where(f0 < 1, (f1 - f0) / np.maximum(1 - f0, 1e-9), 0.0)


def _profile_at(profile: np.ndarray, hours: np.ndarray) -> np.ndarray:
    idx = np.clip(np.round(hours / 0.25).astype(int), 0, len(profile) - 1)
    return profile[idx]


def unit_state(t: float, stays: pd.DataFrame, reserved: dict | None = None) -> pd.DataFrame:
    """Beds by state on each unit at time t, and the bed queue (by intended unit)."""
    s = stays[stays.bed_assigned_min.notna()]
    rows = []
    for u in C.UNIT_NAMES:
        su = s[s.unit == u]
        occupied = int(((su.bed_arrival_min <= t) & (su.discharge_min > t)).sum())
        cleaning = int(((su.discharge_min <= t) & (su.clean_min > t)).sum())
        assigned = int(((su.bed_assigned_min <= t) & (su.bed_arrival_min > t)).sum())
        res = int((reserved or {}).get(u, 0))
        free = C.UNITS[u] - occupied - cleaning - assigned - res
        q = stays[(stays.intended_unit == u) & (stays.queue_entry_min <= t)
                  & ((stays.bed_assigned_min > t) | stays.bed_assigned_min.isna())]
        rows.append({"unit": u, "beds": C.UNITS[u], "occupied": occupied, "cleaning": cleaning,
                     "assigned": assigned, "reserved": res, "clean_free": free, "queue": len(q),
                     "net_now": free - len(q)})
    return pd.DataFrame(rows).set_index("unit")


def forecast(t: float, ed: pd.DataFrame, stays: pd.DataFrame, admit_scores: pd.DataFrame,
             dc_scores: pd.DataFrame, tables: ForecastTables,
             horizons: tuple[int, ...] = HORIZONS_H) -> pd.DataFrame:
    """Expected net usable beds per unit and horizon, with an 80% band and components.

    admit_scores: index aligned with ed, columns p_admit and one probability per unit.
    dc_scores: stay_id, rounds_min, p_discharge_24h.
    """
    state = unit_state(t, stays)
    hour, weekend, winter = _calendar(np.array([t]))
    key = (int(hour[0]), bool(weekend[0]), bool(winter[0]))

    # inpatients present now, with their latest rounds score
    present = stays[(stays.bed_arrival_min <= t) & (stays.discharge_min > t)][["stay_id", "unit"]]
    sc = dc_scores[dc_scores.rounds_min <= t]
    latest = sc.sort_values("rounds_min").groupby("stay_id").tail(1).set_index("stay_id")
    present = present.join(latest[["rounds_min", "p_discharge_24h"]], on="stay_id")
    p24 = present.p_discharge_24h.fillna(UNSCORED_P24).to_numpy()
    since = np.where(present.rounds_min.notna(), (t - present.rounds_min.to_numpy()) / 60, 0.0)
    g_now = _profile_at(tables.profile, np.minimum(since, 24))
    remaining = np.maximum(1 - p24 * g_now, 1e-9)

    dirty = stays[(stays.discharge_min <= t) & (stays.clean_min > t)]
    ed_now = ed[(ed.triage_end_min <= t) & (ed.departure_min > t)]
    undecided = ed_now[ed_now.decision_min.isna() | (ed_now.decision_min > t)]
    decided = ed_now[ed_now.admitted & (ed_now.decision_min <= t)
                     & (ed_now.bed_request_min > t)]
    p_und = admit_scores.loc[undecided.index, "p_admit"].to_numpy()
    unit_p = admit_scores.loc[undecided.index, list(C.UNIT_NAMES)]

    rows = []
    for h in horizons:
        hm = h * 60.0
        usable_h = max(h - tables.clean_lag_min / 60, 0)
        end = np.minimum(since + usable_h, 24)
        p_dis = p24 * (_profile_at(tables.profile, end) - g_now) / remaining
        over = since + usable_h - 24
        p_dis = p_dis + np.where(over > 0, (1 - p_dis) * p24 * _profile_at(tables.profile, np.maximum(over, 0)), 0)
        p_dis = np.clip(p_dis, 0, 1)
        ready_dirty = (dirty.discharge_min + tables.clean_lag_min <= t + hm)
        q_und = _cond(tables.triage_to_request, (t - undecided.triage_end_min).to_numpy(), hm)
        q_dec = _cond(tables.decision_to_request, (t - decided.decision_min).to_numpy(), hm)
        for u in C.UNIT_NAMES:
            m = (present.unit == u).to_numpy()
            dis_mean = float(p_dis[m].sum())
            dis_var = float((p_dis[m] * (1 - p_dis[m])).sum())
            dirty_ready = int(ready_dirty[(dirty.unit == u).to_numpy()].sum())
            pu = p_und * unit_p[u].to_numpy() * q_und
            dec_m = (decided.admit_unit == u).to_numpy()
            dec_mean = float(q_dec[dec_m].sum())
            fut = float(tables.future_ed[(u, h)].get(key, 0.0))
            non = float(tables.non_ed[(u, h)].get(key, 0.0))
            supply = dis_mean + dirty_ready
            demand = dec_mean + float(pu.sum()) + fut + non
            var = dis_var + float((pu * (1 - pu)).sum()) + float((q_dec[dec_m] * (1 - q_dec[dec_m])).sum()) + fut + non
            exp_net = state.loc[u, "net_now"] + supply - demand
            sd = np.sqrt(var)
            rows.append({
                "unit": u, "horizon_h": h, "net_now": int(state.loc[u, "net_now"]),
                "clean_free_now": int(state.loc[u, "clean_free"]), "queue_now": int(state.loc[u, "queue"]),
                "beds_ready_from_cleaning": dirty_ready, "expected_discharges_ready": dis_mean,
                "expected_requests_admitted_waiting": dec_mean,
                "expected_requests_ed_undecided": float(pu.sum()),
                "expected_requests_new_arrivals": fut, "expected_requests_direct_elective": non,
                "expected_net": exp_net, "low80": exp_net - Z80 * sd, "high80": exp_net + Z80 * sd,
            })
    return pd.DataFrame(rows)


def actual_net(t: float, stays: pd.DataFrame) -> pd.Series:
    return unit_state(t, stays)["net_now"]


def backtest(times: list[float], ed: pd.DataFrame, stays: pd.DataFrame, admit_scores: pd.DataFrame,
             dc_scores: pd.DataFrame, tables: ForecastTables) -> pd.DataFrame:
    rows = []
    for t in times:
        fc = forecast(t, ed, stays, admit_scores, dc_scores, tables)
        for h in HORIZONS_H:
            act = actual_net(t + h * 60, stays)
            sub = fc[fc.horizon_h == h].set_index("unit")
            for u in C.UNIT_NAMES:
                rows.append({"t": t, "unit": u, "horizon_h": h, "forecast": sub.loc[u, "expected_net"],
                             "low80": sub.loc[u, "low80"], "high80": sub.loc[u, "high80"],
                             "persistence": sub.loc[u, "net_now"], "actual": act[u]})
    bt = pd.DataFrame(rows)
    bt["abs_err"] = (bt.forecast - bt.actual).abs()
    bt["abs_err_persistence"] = (bt.persistence - bt.actual).abs()
    bt["covered"] = (bt.actual >= bt.low80) & (bt.actual <= bt.high80)
    return bt


def backtest_summary(bt: pd.DataFrame) -> pd.DataFrame:
    return bt.groupby("horizon_h").agg(
        forecasts=("abs_err", "size"),
        mae=("abs_err", "mean"),
        mae_persistence=("abs_err_persistence", "mean"),
        coverage80=("covered", "mean"),
    ).reset_index()
