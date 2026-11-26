"""Pre-draw every ED patient and every non-ED inpatient admission before simulating.

Everything a patient brings with them (arrival time, payer, age, complaint, acuity,
vitals, whether they would be admitted and to which unit, how long each step takes,
how long they will wait before leaving) is drawn here, independent of how crowded the
hospital is. The discrete-event simulation in ``simulate.py`` then only resolves the
queues. Because of this split, a baseline run and a run with the AI tool switched on see
exactly the same patients ("common random numbers"), so any difference between the runs
is caused by the tool and not by luck.

All patients are synthetic. Time is measured in minutes from midnight on
``config.WARMUP_START``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

from halvian import config as C
from halvian.config import SimParams

MIN_PER_DAY = 1440.0

COMPLAINTS = (
    "chest_pain",
    "shortness_of_breath",
    "abdominal_pain",
    "fever_infection",
    "minor_injury",
    "major_trauma_fall",
    "neuro",
    "syncope_dizziness",
    "behavioral_health",
    "back_msk_pain",
    "gi_nvd",
    "skin_wound",
    "ent_dental_eye",
    "urinary",
)
COMPLAINT_LABELS = {
    "chest_pain": "Chest pain",
    "shortness_of_breath": "Shortness of breath",
    "abdominal_pain": "Abdominal pain",
    "fever_infection": "Fever or infection",
    "minor_injury": "Minor injury",
    "major_trauma_fall": "Major trauma or fall",
    "neuro": "Neuro symptoms",
    "syncope_dizziness": "Fainting or dizziness",
    "behavioral_health": "Behavioral health",
    "back_msk_pain": "Back or joint pain",
    "gi_nvd": "Nausea, vomiting or diarrhea",
    "skin_wound": "Skin or wound",
    "ent_dental_eye": "Ear, nose, throat, dental or eye",
    "urinary": "Urinary symptoms",
}
RESPIRATORY = ("shortness_of_breath", "fever_infection")

# Complaint mix by age band (children, adults, 65+)  [assumption, typical ED case mix]
_MIX = {
    "child": [1, 12, 10, 18, 22, 2, 3, 1, 3, 1, 12, 7, 12, 2],
    "adult": [9, 8, 13, 7, 14, 4, 6, 4, 5, 10, 6, 6, 5, 3],
    "older": [14, 13, 11, 8, 8, 9, 10, 8, 1, 6, 4, 4, 2, 5],
}
# How serious a visit with this complaint tends to be (shift of the latent severity)
_SEVERITY_OFFSET = np.array(
    [0.60, 0.70, 0.10, 0.10, -0.90, 0.90, 0.60, 0.30, 0.20, -0.70, -0.30, -0.90, -1.10, -0.30]
)
# Extra admission log-odds by complaint, beyond severity
_ADMIT_OFFSET = np.array(
    [0.40, 0.50, 0.10, 0.20, -1.20, 0.40, 0.40, 0.30, 0.30, -0.80, -0.20, -0.60, -1.50, 0.00]
)
# Admitting unit probabilities by complaint; columns follow config.UNIT_NAMES
# (Medicine A, Medicine B, Telemetry, Surgery, Step-down, ICU). ICU is handled separately.
_UNIT_ROUTING = np.array(
    [
        [0.12, 0.00, 0.83, 0.00, 0.05, 0.0],  # chest pain
        [0.12, 0.66, 0.10, 0.00, 0.12, 0.0],  # shortness of breath
        [0.55, 0.00, 0.00, 0.45, 0.00, 0.0],  # abdominal pain
        [0.30, 0.63, 0.00, 0.00, 0.07, 0.0],  # fever or infection
        [0.30, 0.00, 0.00, 0.70, 0.00, 0.0],  # minor injury
        [0.12, 0.00, 0.00, 0.83, 0.05, 0.0],  # major trauma or fall
        [0.10, 0.58, 0.12, 0.00, 0.20, 0.0],  # neuro
        [0.17, 0.00, 0.78, 0.00, 0.05, 0.0],  # syncope or dizziness
        [1.00, 0.00, 0.00, 0.00, 0.00, 0.0],  # behavioral health (medical admission)
        [0.50, 0.00, 0.00, 0.50, 0.00, 0.0],  # back or joint pain
        [0.85, 0.15, 0.00, 0.00, 0.00, 0.0],  # nausea, vomiting, diarrhea
        [0.60, 0.00, 0.00, 0.40, 0.00, 0.0],  # skin or wound
        [0.00, 0.70, 0.00, 0.30, 0.00, 0.0],  # ENT, dental, eye
        [0.90, 0.00, 0.00, 0.10, 0.00, 0.0],  # urinary
    ]
)
_DX_GROUP = {
    "chest_pain": "Cardiac",
    "syncope_dizziness": "Cardiac",
    "shortness_of_breath": "Respiratory",
    "fever_infection": "Infection",
    "abdominal_pain": "Digestive",
    "gi_nvd": "Digestive",
    "neuro": "Neurological",
    "minor_injury": "Injury or orthopedic",
    "major_trauma_fall": "Injury or orthopedic",
    "back_msk_pain": "Injury or orthopedic",
    "behavioral_health": "Behavioral-medical",
    "urinary": "Renal or urinary",
    "skin_wound": "Skin or soft tissue",
    "ent_dental_eye": "Other medical",
}
DX_GROUPS = (
    "Cardiac",
    "Respiratory",
    "Infection",
    "Digestive",
    "Neurological",
    "Injury or orthopedic",
    "Behavioral-medical",
    "Renal or urinary",
    "Skin or soft tissue",
    "Other medical",
    "Elective surgery",
)
_DIRECT_DX_BY_UNIT = {
    "Medicine A": ["Digestive", "Renal or urinary", "Other medical", "Skin or soft tissue"],
    "Medicine B": ["Respiratory", "Infection", "Neurological"],
    "Telemetry": ["Cardiac"],
    "Surgery": ["Injury or orthopedic", "Digestive"],
    "Step-down": ["Respiratory", "Infection", "Neurological", "Cardiac"],
    "ICU": ["Respiratory", "Infection", "Cardiac", "Neurological"],
}

PEAK_HOURS = frozenset([10, 11, 12, 13, 17, 18, 19, 20, 21, 22])
EVENING_HOURS = frozenset([17, 18, 19, 20, 21, 22, 23, 0, 1, 2, 3, 4, 5, 6])


def minutes_from_start(d: date) -> float:
    return (d - C.WARMUP_START).days * MIN_PER_DAY


def day_dates(start: date, end: date) -> list[date]:
    return [start + timedelta(days=k) for k in range((end - start).days)]


def _streams(seed: int) -> dict[str, np.random.Generator]:
    names = ["arrivals", "attributes", "service", "patience", "beds", "stays", "tool", "nonED"]
    children = np.random.SeedSequence(seed).spawn(len(names))
    return {n: np.random.default_rng(s) for n, s in zip(names, children, strict=True)}


def _hour_weights(params: SimParams, payer: str, days: list[date]) -> np.ndarray:
    """Relative arrival intensity for every hour of every day, for one payer."""
    n = len(days)
    dow = np.array([d.weekday() for d in days])
    winter = np.array([d.month in C.WINTER_MONTHS for d in days])
    weekend = dow >= 5
    prof = np.where(
        weekend[:, None], np.array(params.hourly_weekend)[None, :], np.array(params.hourly_weekday)
    )
    w = prof * np.array(params.dow_multiplier)[dow][:, None]
    w = w * np.where(winter, params.winter_multiplier, 1.0)[:, None]
    evening = np.array([h in EVENING_HOURS for h in range(24)])
    w = w * np.where(evening, 1.0 + params.payer_evening_tilt[payer], 1.0)[None, :]
    w = w * np.where(weekend, 1.0 + params.payer_weekend_tilt[payer], 1.0)[:, None]
    assert w.shape == (n, 24)
    return w


@dataclass
class Cohort:
    """Everything pre-drawn for one synthetic year. Arrays are indexed by patient."""

    ed: pd.DataFrame  # one row per ED arrival, sorted by arrival time
    nonED: pd.DataFrame  # one row per direct or elective admission request
    seed: int
    params: SimParams


def _tri(rng, lo_mode_hi, n):
    lo, mode, hi = lo_mode_hi
    return rng.triangular(lo, mode, hi, n)


def _lognormal(rng, median, sigma, n):
    return median * np.exp(sigma * rng.standard_normal(n))


def build_cohort(seed: int = C.SEED, params: SimParams | None = None,
                 start: date = C.WARMUP_START, end: date = C.YEAR_END) -> Cohort:
    params = params or C.DEFAULT_PARAMS
    rs = _streams(seed)
    days = day_dates(start, end)
    # Rates are always scaled to the full 2025 year, whatever window is simulated, so a
    # short window gets the same daily volume as the same dates in a full-year run.
    year_days = day_dates(C.YEAR_START, C.YEAR_END)
    day0 = minutes_from_start(start)

    # ---------------------------------------------------------------- arrivals
    rng = rs["arrivals"]
    times, payers = [], []
    for payer in C.PAYERS:
        w_year = _hour_weights(params, payer, year_days)
        target = C.ED_VISITS_PER_YEAR * C.PAYER_MIX[payer]
        scale = target / w_year.sum()
        lam = _hour_weights(params, payer, days) * scale
        counts = rng.poisson(lam.ravel())
        hour_starts = day0 + np.arange(lam.size) * 60.0
        t = np.repeat(hour_starts, counts) + rng.uniform(0, 60, counts.sum())
        times.append(t)
        payers.append(np.full(t.size, payer, dtype=object))
    t_all = np.concatenate(times)
    p_all = np.concatenate(payers)
    order = np.argsort(t_all, kind="stable")
    arrival = t_all[order]
    payer = p_all[order]
    n = arrival.size
    hour = ((arrival % MIN_PER_DAY) // 60).astype(int)
    day_index = (arrival // MIN_PER_DAY).astype(int)
    first_day = (start - C.WARMUP_START).days
    arr_dates = [days[k - first_day] for k in day_index]
    dow = np.array([d.weekday() for d in arr_dates])
    month = np.array([d.month for d in arr_dates])
    winter = np.isin(month, C.WINTER_MONTHS)

    # ---------------------------------------------------------------- attributes
    rng = rs["attributes"]
    age = np.empty(n)
    u = rng.uniform(size=n)
    for p in C.PAYERS:
        m = payer == p
        k = int(m.sum())
        uu = u[m]
        if p == C.MEDICARE:
            older = 65 + rng.gamma(2.2, 5.0, k)
            younger = rng.uniform(25, 64, k)
            a = np.where(uu < 0.88, older, younger)
        elif p == C.MEDICAID:
            child = rng.uniform(0, 18, k)
            adult = 18 + rng.gamma(2.5, 7.0, k)
            a = np.where(uu < 0.38, child, adult)
        elif p == C.COMMERCIAL:
            child = rng.uniform(0, 18, k)
            adult = 18 + rng.gamma(3.5, 7.0, k)
            senior = 65 + rng.gamma(1.5, 3.0, k)
            a = np.where(uu < 0.20, child, np.where(uu < 0.96, adult, senior))
        elif p == C.UNINSURED:
            child = rng.uniform(0, 18, k)
            adult = 18 + rng.gamma(2.6, 7.0, k)
            a = np.where(uu < 0.02, child, adult)
        else:
            a = 18 + rng.gamma(3.5, 8.0, k)
        age[m] = a
    age = np.clip(age, 0, 100).round().astype(int)
    age_band = np.where(age < 18, "child", np.where(age < 65, "adult", "older"))

    complaint_idx = np.empty(n, dtype=int)
    resp_idx = np.array([COMPLAINTS.index(c) for c in RESPIRATORY])
    for band, weights in _MIX.items():
        base = np.array(weights, dtype=float)
        base = base / base.sum()
        resp_mix = np.zeros_like(base)
        resp_mix[resp_idx] = [0.6, 0.4]
        winter_mix = (base + (params.winter_multiplier - 1.0) * resp_mix) / params.winter_multiplier
        for is_w, mix in ((False, base), (True, winter_mix)):
            m = (age_band == band) & (winter == is_w)
            complaint_idx[m] = rng.choice(len(COMPLAINTS), size=int(m.sum()), p=mix)
    complaint = np.array(COMPLAINTS, dtype=object)[complaint_idx]
    # Most of the winter surge is lower-acuity viral illness: mark the "extra" winter
    # respiratory visits as seasonal, with lower severity  [assumption A8]
    seasonal = np.zeros(n, dtype=bool)
    for band, weights in _MIX.items():
        base = np.array(weights, dtype=float)
        r_b = base[resp_idx].sum() / base.sum()
        extra = params.winter_multiplier - 1.0
        frac = extra / (r_b + extra)
        m_ = (age_band == band) & winter & np.isin(complaint_idx, resp_idx)
        seasonal[m_] = rng.uniform(size=int(m_.sum())) < frac

    comorbidity = rng.standard_normal(n) + 0.025 * (age - 45)
    low_shift = np.array([params.payer_low_acuity_shift[p] for p in payer])
    peak_extra = np.array([params.payer_peak_low_acuity_extra[p] for p in payer])
    is_peak = np.isin(hour, list(PEAK_HOURS))
    severity = (
        _SEVERITY_OFFSET[complaint_idx]
        + 0.010 * (age - 45)
        + 0.30 * comorbidity
        + rng.standard_normal(n)
        - low_shift
        - np.where(is_peak, peak_extra, 0.0)
        - params.seasonal_severity_drop * seasonal
    )
    # ESI from severity so the overall mix is exactly the assumed US mix  [assumption A3]
    cum = np.cumsum(params.esi_mix)[:-1]  # shares of ESI 1, 1-2, 1-3, 1-4
    cuts = np.quantile(severity, 1.0 - cum)  # descending severity cut points
    esi = np.full(n, 5)
    for level, cut in zip((4, 3, 2, 1), cuts[::-1], strict=True):
        esi[severity >= cut] = level
    z = (severity - severity.mean()) / severity.std()

    is_resp = np.isin(complaint, list(RESPIRATORY))
    is_fever = complaint == "fever_infection"
    is_trauma = complaint == "major_trauma_fall"
    is_syncope = complaint == "syncope_dizziness"
    zpos = np.clip(z, 0, None)
    hr = 82 + 9 * zpos + 10 * is_fever + 8 * is_trauma + 15 * (age < 12) + rng.normal(0, 11, n)
    sbp = 132 + 0.3 * (age - 45) - 7 * np.clip(z - 1, 0, None) - 8 * is_syncope + rng.normal(0, 16, n)
    rr = 16.5 + 2.2 * zpos + 3 * is_resp + 4 * (age < 5) + rng.normal(0, 2.5, n)
    spo2 = 97.6 - np.where(is_resp, 2.6 * zpos + 1.0, 0.6 * zpos) + rng.normal(0, 1.3, n)
    temp = 37.0 + np.where(is_fever, 1.1 + 0.3 * zpos, 0.0) + rng.normal(0, 0.35, n)
    vitals = {
        "heart_rate": np.clip(hr, 40, 190).round(),
        "systolic_bp": np.clip(sbp, 60, 230).round(),
        "resp_rate": np.clip(rr, 8, 45).round(),
        "spo2": np.clip(spo2, 70, 100).round(),
        "temp_c": np.clip(temp, 35.0, 41.5).round(1),
    }
    amb_logit = -2.3 + 0.95 * z + 0.025 * np.clip(age - 50, 0, None)
    ambulance = rng.uniform(size=n) < 1 / (1 + np.exp(-amb_logit))
    visit_mean = {C.COMMERCIAL: 0.35, C.MEDICARE: 0.70, C.MEDICAID: 1.00, C.UNINSURED: 0.90,
                  C.OTHER: 0.45}
    vm = np.array([visit_mean[p] for p in payer]) * np.exp(0.35 * (comorbidity - comorbidity.mean()))
    recent_visits = rng.poisson(rng.gamma(0.8, vm / 0.8))

    admit_logit = (
        params.admit_intercept
        + params.admit_severity_coef * z
        + params.admit_age_coef * (age - 50)
        + params.admit_comorbidity_coef * comorbidity
        + _ADMIT_OFFSET[complaint_idx]
        + params.admit_noise_sd * rng.standard_normal(n)
    )
    would_admit = rng.uniform(size=n) < 1 / (1 + np.exp(-admit_logit))

    # Admitting unit. ICU for the most severe; children go to Medicine B's pediatric section.
    unit_idx = np.empty(n, dtype=int)
    route_u = rng.uniform(size=n)
    cum_route = np.cumsum(_UNIT_ROUTING, axis=1)
    for i_c in range(len(COMPLAINTS)):
        m = complaint_idx == i_c
        unit_idx[m] = np.searchsorted(cum_route[i_c], route_u[m] * cum_route[i_c, -1], side="right")
    icu_p = 1 / (1 + np.exp(-(-6.9 + 2.6 * z)))
    icu = (rng.uniform(size=n) < icu_p) | ((esi == 1) & (rng.uniform(size=n) < 0.65))
    stepdown_bump = (z > 1.8) & ~icu & (rng.uniform(size=n) < 0.12)
    unit_idx = np.where(stepdown_bump, C.UNIT_NAMES.index("Step-down"), unit_idx)
    unit_idx = np.where(icu, C.UNIT_NAMES.index("ICU"), unit_idx)
    peds = (age < 18) & ~icu
    unit_idx = np.where(peds, C.UNIT_NAMES.index("Medicine B"), unit_idx)
    unit = np.array(C.UNIT_NAMES, dtype=object)[unit_idx]
    dx_group = np.array([_DX_GROUP[c] for c in complaint], dtype=object)

    # ---------------------------------------------------------------- ED service times
    rng = rs["service"]
    reg_extra = np.array([params.registration_extra_by_payer[p] for p in payer])
    t_registration = _tri(rng, params.registration_tri, n) + reg_extra
    t_triage = _tri(rng, params.triage_tri, n)
    t_eval = _lognormal(rng, params.provider_eval_median, params.provider_eval_sigma, n)
    t_nurse = _lognormal(rng, params.nurse_assess_median, 0.5, n)
    workup_med = np.array(params.workup_median_by_esi)[esi - 1]
    t_workup = workup_med * np.exp(params.workup_sigma * rng.standard_normal(n))
    t_dispo = _lognormal(rng, params.dispo_task_median, 0.4, n)
    t_accept = _lognormal(rng, params.admit_acceptance_median * params.bed_process_scale,
                          params.process_sigma, n)
    t_ed_discharge = rng.uniform(*params.ed_discharge_range, n)

    rng = rs["patience"]
    pat_med = np.array(params.patience_median_by_esi)[esi - 1] * params.patience_scale
    pat_mult = np.array([params.patience_mult_by_payer[p] for p in payer])
    patience = pat_med * pat_mult * np.exp(params.patience_sigma * rng.standard_normal(n))
    patience = np.maximum(patience, 30.0)

    rng = rs["beds"]
    bed = _bed_draws(rng, params, n)

    rng = rs["stays"]
    stay = _stay_draws(rng, params, n, age, payer, z, unit)

    rng = rs["tool"]
    adopt_u = rng.uniform(size=n)
    adopt_dc_u = rng.uniform(size=n)

    ed = pd.DataFrame(
        {
            "arrival_min": arrival,
            "payer": pd.Categorical(payer, categories=C.PAYERS),
            "age": age,
            "sex": np.where(rng.uniform(size=n) < 0.5, "F", "M"),
            "arrival_mode": np.where(ambulance, "Ambulance", "Walk-in"),
            "chief_complaint": complaint,
            "esi": esi,
            **vitals,
            "recent_ed_visits_12m": recent_visits,
            "arrival_hour": hour,
            "arrival_dow": dow,
            "arrival_month": month,
            "winter": winter,
            "severity_latent": z,
            "comorbidity_latent": comorbidity,
            "would_admit": would_admit,
            "admit_unit": unit,
            "dx_group": dx_group,
            "is_behavioral": complaint == "behavioral_health",
            "t_registration": t_registration,
            "t_triage": t_triage,
            "t_eval": t_eval,
            "t_nurse_assess": t_nurse,
            "t_workup": t_workup,
            "t_dispo": t_dispo,
            "t_admit_acceptance": t_accept,
            "seasonal_respiratory": seasonal,
            "t_ed_discharge": t_ed_discharge,
            "patience": patience,
            **bed,
            **stay,
            "adopt_u": adopt_u,
            "adopt_dc_u": adopt_dc_u,
        }
    )
    nonED = _build_non_ed(rs["nonED"], params, days, day0)
    return Cohort(ed=ed, nonED=nonED, seed=seed, params=params)


def _bed_draws(rng, params: SimParams, n: int) -> dict[str, np.ndarray]:
    s = params.process_sigma
    return {
        "t_bed_request": _lognormal(rng, params.bed_request_median * params.bed_process_scale, s, n),
        "t_bed_readiness": _lognormal(rng, params.bed_readiness_median * params.bed_process_scale, s, n),
        "t_transport": _lognormal(rng, params.transport_median, 0.3, n),
        "t_clean": _lognormal(rng, params.clean_median, 0.35, n),
        "t_clean_notify": _lognormal(rng, params.clean_notify_median, s, n),
    }


def _stay_draws(rng, params: SimParams, n: int, age, payer, z, unit) -> dict[str, np.ndarray]:
    """Inpatient-stay draws: medical length of stay, mobility, barriers, discharge clock."""
    los_med = np.array([params.los_median_h_by_unit[u] for u in unit]) * params.los_scale
    los_h = los_med * np.exp(0.12 * np.clip(z, -2, 3)) * np.exp(params.los_sigma * rng.standard_normal(n))
    los_h = np.clip(los_h, 8, 24 * 40)
    mobility0 = np.clip(19 - 0.08 * (age - 50) - 1.3 * np.clip(z, -1, 3) + rng.normal(0, 3, n), 6, 24)
    barrier_logodds = np.array([params.barrier_payer_logodds[p] for p in payer])
    b_logit = (
        params.barrier_intercept
        + params.barrier_age_coef * (age - 65)
        + params.barrier_mobility_coef * (mobility0 - 15)
        + barrier_logodds
    )
    has_barrier = rng.uniform(size=n) < 1 / (1 + np.exp(-b_logit))
    tilt = np.array([params.barrier_type_payer_tilt[p] for p in payer])
    base = np.array([C.BARRIER_BASE_MIX[b] for b in C.BARRIER_TYPES])
    eq = np.array([b in C.BARRIER_EQUITY_TYPES for b in C.BARRIER_TYPES])
    placement = np.array([b == "placement" for b in C.BARRIER_TYPES])
    w = base[None, :] * np.where(eq[None, :], tilt[:, None], 1.0)
    w = w * np.where(placement[None, :], np.exp(0.10 * (15 - mobility0))[:, None], 1.0)
    w = w / w.sum(axis=1, keepdims=True)
    cw = np.cumsum(w, axis=1)
    pick = (rng.uniform(size=n)[:, None] > cw).sum(axis=1)
    pick = np.minimum(pick, len(C.BARRIER_TYPES) - 1)
    btype = np.where(has_barrier, np.array(C.BARRIER_TYPES, dtype=object)[pick], None)
    delay_med = np.array([C.BARRIER_DELAY_MEDIAN_H.get(b, 0.0) if b else 0.0 for b in btype])
    delay = delay_med * np.exp(C.BARRIER_DELAY_SIGMA * rng.standard_normal(n))
    clock = np.clip(rng.normal(params.discharge_clock_mean_h, params.discharge_clock_sd_h, n), 10.5, 19.5)
    return {
        "ip_los_ready_h": los_h,
        "ip_mobility0": mobility0.round(),
        "ip_barrier": btype,
        "ip_barrier_delay_h": np.where(has_barrier, delay, 0.0),
        "ip_discharge_clock_h": clock,
        "ip_weekend_u": rng.uniform(size=n),
        "ip_note_seed": rng.integers(0, 2**31 - 1, n),
    }


def _build_non_ed(rng, params: SimParams, days: list[date], day0: float) -> pd.DataFrame:
    """Direct admissions and elective surgical admissions  [assumption A6]."""
    rows_t, rows_src = [], []
    n_weekdays = sum(1 for d in day_dates(C.YEAR_START, C.YEAR_END) if d.weekday() < 5)
    n_winter_weekdays = sum(1 for d in day_dates(C.YEAR_START, C.YEAR_END)
                            if d.weekday() < 5 and d.month in C.WINTER_MONTHS)
    el_rate = params.elective_per_year / (
        n_weekdays - n_winter_weekdays * (1 - params.elective_winter_factor))
    dir_weights = np.array([1.15 if d.weekday() < 5 else 0.65 for d in day_dates(C.YEAR_START, C.YEAR_END)])
    dir_rate_unit = params.direct_per_year / dir_weights.sum()
    for k, d in enumerate(days):
        base = day0 + k * MIN_PER_DAY
        if d.weekday() < 5:
            m = rng.poisson(el_rate * (params.elective_winter_factor if d.month in C.WINTER_MONTHS else 1.0))
            rows_t.append(base + rng.uniform(10 * 60, 16 * 60, m))
            rows_src.append(np.full(m, "Elective", dtype=object))
        lam = dir_rate_unit * (1.15 if d.weekday() < 5 else 0.65)
        m = rng.poisson(lam)
        rows_t.append(base + np.clip(rng.normal(15 * 60, 3 * 60, m), 8 * 60, 23.5 * 60))
        rows_src.append(np.full(m, "Direct", dtype=object))
    t = np.concatenate(rows_t)
    src = np.concatenate(rows_src)
    order = np.argsort(t, kind="stable")
    t, src = t[order], src[order]
    n = t.size
    payers = list(C.NON_ED_PAYER_MIX)
    payer = np.array(payers, dtype=object)[
        rng.choice(len(payers), size=n, p=list(C.NON_ED_PAYER_MIX.values()))
    ]
    age = np.where(payer == C.MEDICARE, 65 + rng.gamma(2.2, 5.0, n), 18 + rng.gamma(3.5, 7.0, n))
    age = np.clip(age, 18, 100).round().astype(int)
    d_units, d_p = list(C.DIRECT_UNIT_MIX), list(C.DIRECT_UNIT_MIX.values())
    e_units, e_p = list(C.ELECTIVE_UNIT_MIX), list(C.ELECTIVE_UNIT_MIX.values())
    unit = np.where(
        src == "Elective",
        np.array(e_units, dtype=object)[rng.choice(len(e_units), size=n, p=e_p)],
        np.array(d_units, dtype=object)[rng.choice(len(d_units), size=n, p=d_p)],
    )
    dx = np.array(
        [
            "Elective surgery" if s == "Elective" else _DIRECT_DX_BY_UNIT[u][rng.integers(len(_DIRECT_DX_BY_UNIT[u]))]
            for s, u in zip(src, unit, strict=True)
        ],
        dtype=object,
    )
    z = rng.normal(0.3, 0.8, n)
    stay = _stay_draws(rng, params, n, age, payer, z, unit)
    elective = src == "Elective"
    stay["ip_los_ready_h"] = np.where(
        elective,
        np.clip(params.elective_los_median_h * params.los_scale * np.exp(0.5 * rng.standard_normal(n)), 8, 24 * 20),
        stay["ip_los_ready_h"],
    )
    bed = _bed_draws(rng, params, n)
    return pd.DataFrame(
        {
            "request_min": t,
            "source": src,
            "payer": pd.Categorical(payer, categories=C.PAYERS),
            "age": age,
            "unit": unit,
            "dx_group": dx,
            **bed,
            **stay,
            "adopt_dc_u": rng.uniform(size=n),
        }
    )
