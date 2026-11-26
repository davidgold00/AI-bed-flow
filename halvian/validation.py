"""Calibration checks: does the synthetic year reproduce the case brief?

Used by ``scripts/validate.py`` and the test suite, so the
two always agree. Inputs are the ED visit table and the inpatient stay table with
``*_min`` columns (minutes from midnight on ``config.WARMUP_START``).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from halvian import config as C
from halvian.data.cohort import MIN_PER_DAY, minutes_from_start

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def year_window() -> tuple[float, float]:
    return minutes_from_start(C.YEAR_START), minutes_from_start(C.YEAR_END)


def census(stays: pd.DataFrame, grid: np.ndarray, unit: str | None = None) -> np.ndarray:
    """Occupied beds at each time in ``grid`` (patient physically in the bed)."""
    s = stays if unit is None else stays[stays.unit == unit]
    s = s[s.bed_arrival_min.notna()]
    a = np.sort(s.bed_arrival_min.to_numpy())
    d = np.sort(s.discharge_min.to_numpy())
    return np.searchsorted(a, grid, side="right") - np.searchsorted(d, grid, side="right")


def compute_metrics(ed: pd.DataFrame, stays: pd.DataFrame) -> dict:
    """Every number the validation table needs, for the 2025 hospital year."""
    y0, y1 = year_window()
    y = ed[(ed.arrival_min >= y0) & (ed.arrival_min < y1)]
    seen = y[~y.lwbs & y.provider_min.notna()]
    m: dict = {}
    m["visits"] = len(y)
    m["payer_share"] = y.payer.value_counts(normalize=True).reindex(C.PAYERS).fillna(0).to_dict()
    m["admission_rate"] = float(y.admitted.mean())

    day = ((y.arrival_min - minutes_from_start(C.WARMUP_START)) // MIN_PER_DAY).astype(int)
    daily = y.groupby(day).size()
    dates = pd.to_datetime(C.WARMUP_START) + pd.to_timedelta(daily.index, unit="D")
    daily_df = pd.DataFrame({"n": daily.to_numpy(), "date": dates})
    daily_df["dow"] = daily_df.date.dt.day_of_week
    daily_df["winter"] = daily_df.date.dt.month.isin(C.WINTER_MONTHS)
    by_dow = daily_df.groupby("dow").n.mean()
    m["mean_by_weekday"] = {WEEKDAYS[k]: float(v) for k, v in by_dow.items()}
    m["busiest_weekday"] = WEEKDAYS[int(by_dow.idxmax())]
    m["winter_uplift"] = float(daily_df[daily_df.winter].n.mean() / daily_df[~daily_df.winter].n.mean() - 1)

    wk = y[y.arrival_dow < 5]
    n_weekdays = int((daily_df.dow < 5).sum())
    hourly = wk.groupby("arrival_hour").size().reindex(range(24), fill_value=0) / n_weekdays
    m["weekday_hourly"] = hourly.to_dict()
    trough = hourly.loc[14:16].min()
    m["morning_peak"] = float(hourly.loc[8:13].max())
    m["evening_peak"] = float(hourly.loc[17:22].max())
    m["afternoon_trough"] = float(trough)
    m["has_two_peaks"] = bool(m["morning_peak"] > trough and m["evening_peak"] > trough
                              and min(m["morning_peak"], m["evening_peak"]) > hourly.loc[0:6].max())

    m["d2p_median"] = float(seen.door_to_provider_min.median())
    m["d2p_by_payer"] = seen.groupby("payer", observed=True).door_to_provider_min.median().to_dict()
    m["lwbs_rate"] = float(y.lwbs.mean())
    m["lwbs_by_payer"] = y.groupby("payer", observed=True).lwbs.mean().to_dict()
    adm = y[y.admitted]
    m["boarding_median_h"] = float(adm.boarding_min.median() / 60)
    m["boarding_mean_h"] = float(adm.boarding_min.mean() / 60)

    surge_cut = daily_df.n.quantile(C.SURGE_DAY_QUANTILE)
    surge_days = set(daily.index[daily.to_numpy() >= surge_cut])
    seen_day = ((seen.arrival_min - minutes_from_start(C.WARMUP_START)) // MIN_PER_DAY).astype(int)
    surge_low = seen[seen_day.isin(surge_days) & (seen.esi >= 4)]
    m["surge_low_acuity_d2p"] = float(surge_low.door_to_provider_min.median())
    m["surge_days"] = len(surge_days)

    grid = np.arange(y0, y1, 15.0)
    occ = census(stays, grid)
    m["occupied_mean"] = float(occ.mean())
    m["occupancy"] = float(occ.mean() / C.INPATIENT_BEDS)
    m["open_beds_mean"] = float(C.INPATIENT_BEDS - occ.mean())
    m["unit_occupancy"] = {u: float(census(stays, grid, u).mean() / C.UNITS[u]) for u in C.UNIT_NAMES}

    walk = y[y.reg_end_min.notna()]
    m["registration_median"] = float(walk.t_registration.median())
    m["triage_median"] = float(y[y.triage_end_min.notna() & (y.esi > 1)].t_triage.median())
    m["eval_treat_median_h"] = float((seen.decision_min - seen.provider_min).median() / 60)
    dc = y[y.disposition == "Discharged"]
    m["ed_discharge_median"] = float((dc.departure_min - dc.decision_min).median())

    st = stays[(stays.bed_arrival_min >= y0) & (stays.bed_arrival_min < y1)]
    m["barrier_share"] = float(st.has_barrier.mean()) if "has_barrier" in st else float("nan")
    dis = stays[(stays.discharge_min >= y0) & (stays.discharge_min < y1)]
    dis_hour = (dis.discharge_min % MIN_PER_DAY) / 60
    adm_hour = (adm.decision_min % MIN_PER_DAY) / 60
    m["discharge_median_hour"] = float(dis_hour.median())
    m["admit_request_median_hour"] = float(adm_hour.median())
    m["discharge_peak_hour"] = int(dis_hour.astype(int).value_counts().idxmax())
    m["admit_request_peak_hour"] = int(adm_hour.astype(int).value_counts().idxmax())

    lam = len(st) / 365.0
    los_days = ((st.discharge_min - st.bed_arrival_min) / MIN_PER_DAY).mean()
    m["admissions_per_day"] = lam
    m["alos_days"] = float(los_days)
    m["littles_law_beds"] = float(lam * los_days)
    m["ed_admissions"] = int(adm.shape[0])
    m["medicare_d2p"] = float(m["d2p_by_payer"].get(C.MEDICARE, np.nan))
    return m


@dataclass
class Check:
    target: str
    simulated: str
    tolerance: str
    passed: bool
    group: str


def _pct(x: float, d: int = 1) -> str:
    return f"{x * 100:.{d}f}%"


def run_checks(m: dict) -> pd.DataFrame:
    """The validation table: Target | Simulated | Tolerance | Pass."""
    rows: list[Check] = []

    def add(target, sim, tol, ok, group):
        rows.append(Check(target, sim, tol, bool(ok), group))

    v = m["visits"]
    add("ED visits per year: 85,000", f"{v:,}", "±1%",
        abs(v / C.ED_VISITS_PER_YEAR - 1) <= C.TOL_VISITS_REL, "Volume")
    for p in C.PAYERS:
        tgt = C.PAYER_MIX[p]
        sim = m["payer_share"][p]
        label = f"Payer share {p}: {_pct(tgt, 0)}" + (" (assumption A1)" if p == C.OTHER else "")
        add(label, _pct(sim), "±1 pt", abs(sim - tgt) * 100 <= C.TOL_PAYER_SHARE_PTS, "Volume")
    add("Admission rate: 16%", _pct(m["admission_rate"]), "±1 pt",
        abs(m["admission_rate"] - C.ADMISSION_RATE) * 100 <= C.TOL_ADMISSION_PTS, "Volume")
    add("Busiest day: Monday", m["busiest_weekday"], "Monday highest",
        m["busiest_weekday"] == C.BUSIEST_WEEKDAY, "Volume")
    lo, hi = C.WINTER_UPLIFT_RANGE
    add("Winter respiratory season adds about 20%", _pct(m["winter_uplift"]), "15 to 25%",
        lo <= m["winter_uplift"] <= hi, "Volume")
    add("Weekday arrivals peak in the morning and evening",
        f"{m['morning_peak']:.1f} and {m['evening_peak']:.1f} per hour vs {m['afternoon_trough']:.1f} mid-afternoon",
        "Both peaks present", m["has_two_peaks"], "Volume")

    def med(label, sim, tgt, group):
        add(f"{label}: {tgt:g} min", f"{sim:.1f} min", "±5%",
            abs(sim / tgt - 1) <= C.TOL_MEDIAN_REL, group)

    med("Median door-to-provider, all", m["d2p_median"], C.MEDIAN_DOOR_TO_PROVIDER_MIN, "Waits")
    for p, tgt in C.DOOR_TO_PROVIDER_BY_PAYER_MIN.items():
        med(f"Median door-to-provider, {p}", m["d2p_by_payer"][p], tgt, "Equity gaps")
    add("LWBS, all: 4.0%", _pct(m["lwbs_rate"], 2), "±0.4 pt",
        abs(m["lwbs_rate"] - C.LWBS_RATE) * 100 <= C.TOL_LWBS_PTS, "Waits")
    for p, tgt in C.LWBS_BY_PAYER.items():
        sim = m["lwbs_by_payer"][p]
        add(f"LWBS, {p}: {_pct(tgt)}", _pct(sim, 2), "±0.4 pt",
            abs(sim - tgt) * 100 <= C.TOL_LWBS_PTS, "Equity gaps")
    add("Median boarding: 3.5 h", f"{m['boarding_median_h']:.2f} h", "±5%",
        abs(m["boarding_median_h"] / C.MEDIAN_BOARDING_H - 1) <= C.TOL_MEDIAN_REL, "Boarding")
    add("Lower-urgency (ESI 4 and 5) waits on surge days: 2+ h",
        f"{m['surge_low_acuity_d2p']:.0f} min median on the busiest 10% of days",
        "at least 120 min", m["surge_low_acuity_d2p"] >= C.SURGE_LOW_ACUITY_WAIT_MIN, "Waits")
    add("Inpatient occupancy: about 88%", _pct(m["occupancy"]), "±2 pt",
        abs(m["occupancy"] - C.TARGET_OCCUPANCY) * 100 <= C.TOL_OCCUPANCY_PTS, "Beds")
    lo, hi = C.OPEN_BEDS_RANGE
    add("Open inpatient beds: about 40", f"{m['open_beds_mean']:.1f}", "36 to 44",
        lo <= m["open_beds_mean"] <= hi, "Beds")
    lo, hi = C.REGISTRATION_RANGE_MIN
    add("Registration: 5 to 10 min", f"{m['registration_median']:.1f} min median", "inside range",
        lo <= m["registration_median"] <= hi, "Process times")
    lo, hi = C.TRIAGE_RANGE_MIN
    add("Triage: 5 to 15 min", f"{m['triage_median']:.1f} min median", "inside range",
        lo <= m["triage_median"] <= hi, "Process times")
    lo, hi = C.EVAL_TREAT_RANGE_H
    add("Evaluation and treatment: 2 to 3 h", f"{m['eval_treat_median_h']:.2f} h median",
        "inside range", lo <= m["eval_treat_median_h"] <= hi, "Process times")
    lo, hi = C.ED_DISCHARGE_RANGE_MIN
    add("ED discharge: 20 to 40 min", f"{m['ed_discharge_median']:.1f} min median", "inside range",
        lo <= m["ed_discharge_median"] <= hi, "Process times")
    lo, hi = C.BARRIER_SHARE_RANGE
    add("Stays with a non-medical discharge barrier: about 1 in 5 (assumption A10)",
        _pct(m["barrier_share"]), "17 to 23%", lo <= m["barrier_share"] <= hi, "Beds")
    add("Discharges cluster before ED admission requests (assumption A9)",
        f"discharges {m['discharge_median_hour']:.1f}h vs ED admit decisions {m['admit_request_median_hour']:.1f}h (median hour)",
        "discharges earlier", m["discharge_median_hour"] < m["admit_request_median_hour"], "Beds")
    ll = m["littles_law_beds"]
    add("Little's law: occupied beds = admissions/day × average stay",
        f"{m['occupied_mean']:.1f} occupied vs {m['admissions_per_day']:.1f}/day × {m['alos_days']:.2f} d = {ll:.1f}",
        "within 3%", abs(ll / m["occupied_mean"] - 1) <= C.LITTLES_LAW_TOL_REL, "Beds")
    df = pd.DataFrame([r.__dict__ for r in rows])
    df.columns = ["Target", "Simulated", "Tolerance", "Pass", "Group"]
    return df


def info_rows(m: dict) -> pd.DataFrame:
    """Reported, not pass/fail."""
    rows = [
        ("Median door-to-provider, Medicare (not in brief, emerges)", f"{m['medicare_d2p']:.1f} min"),
        ("Median door-to-provider, Other (not in brief)", f"{m['d2p_by_payer'].get(C.OTHER, np.nan):.1f} min"),
        ("LWBS, Medicare (not in brief)", _pct(m["lwbs_by_payer"].get(C.MEDICARE, np.nan), 2)),
        ("Mean boarding (long tail)", f"{m['boarding_mean_h']:.2f} h"),
        ("ED admissions in the year", f"{m['ed_admissions']:,}"),
        ("All inpatient admissions per day", f"{m['admissions_per_day']:.1f}"),
        ("Average length of stay", f"{m['alos_days']:.2f} days"),
    ] + [(f"Occupancy, {u}", _pct(v)) for u, v in m["unit_occupancy"].items()]
    return pd.DataFrame(rows, columns=["Measure", "Simulated"])
