"""Read-only views of the synthetic year at a replay time, shared by pages 1 to 6.

Everything here is a pure function of the committed data and models plus a time in
minutes from ``config.WARMUP_START``. Loaders are cached per process. No Streamlit
imports, so the logic is testable on its own.
"""

from __future__ import annotations

import json
import math
from datetime import date
from functools import cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from halvian import config as C
from halvian.data.cohort import MIN_PER_DAY, minutes_from_start
from halvian.models import admission as A
from halvian.models import discharge as D
from halvian.models import forecast as F
from halvian.models.explain import top_reasons
from halvian.models.thresholds import batch_request, moving_threshold, threshold_reason

ROOT = Path(__file__).resolve().parents[2]
DATA, MODELS = ROOT / "data", ROOT / "models"
ROUNDS_HOUR = 7


# --------------------------------------------------------------------------- loaders
@cache
def data(name: str) -> pd.DataFrame:
    return pd.read_parquet(DATA / f"{name}.parquet")


@cache
def model_bundle(name: str) -> dict:
    return joblib.load(MODELS / f"{name}.joblib")


@cache
def metrics() -> dict:
    return json.loads((MODELS / "metrics.json").read_text())


@cache
def admission_scores() -> pd.DataFrame:
    s = pd.read_parquet(MODELS / "admission_scores.parquet")
    s.index = data("ed_visits").index
    return s


@cache
def discharge_scores() -> pd.DataFrame:
    return pd.read_parquet(MODELS / "discharge_scores.parquet")


@cache
def note_findings() -> pd.DataFrame:
    """Rule-based findings for every note: the discharge model's feature source."""
    return pd.read_parquet(MODELS / "note_findings.parquet")


@cache
def llm_findings() -> pd.DataFrame | None:
    """Cached AI note reader results (local model) for the demo days and the evaluation sample.

    Only notes the model actually read (status "llm") are returned; None if there is no cache.
    """
    path = MODELS / "llm_note_findings.parquet"
    if not path.is_file():
        return None
    df = pd.read_parquet(path)
    return df[df.status == "llm"]


FINDING_COLUMNS = ["note_id", "barrier_type", "start", "end", "confidence"]


def display_findings(note_ids, rules: pd.DataFrame) -> pd.DataFrame:
    """Findings to show for these notes, each tagged ``reader`` ("llm" or "rules").

    Where the local model read the note: its findings, plus any barrier only the rules found
    (so everything that drives the discharge score is visible). Elsewhere: the rule findings.
    """
    ids = set(note_ids)
    rules = rules[rules.note_id.isin(ids)][FINDING_COLUMNS].assign(reader="rules")
    llm = llm_findings()
    if llm is None:
        return rules
    read = ids & set(llm.note_id)
    model = llm[llm.note_id.isin(read) & llm.barrier_type.notna()][FINDING_COLUMNS].assign(reader="llm")
    model = model.astype({"start": int, "end": int, "confidence": float})
    seen = set(zip(model.note_id, model.barrier_type, strict=True))
    extra = rules[rules.note_id.isin(read)]
    extra = extra[[(n, b) not in seen for n, b in zip(extra.note_id, extra.barrier_type, strict=True)]]
    out = pd.concat([model, rules[~rules.note_id.isin(read)], extra], ignore_index=True)
    return out.sort_values(["note_id", "start"]).reset_index(drop=True)


@cache
def forecast_tables() -> F.ForecastTables:
    return joblib.load(MODELS / "forecast_tables.joblib")


@cache
def crowding() -> pd.Series:
    return A.crowding_series(data("census_hourly"))


def day_start(d: date) -> float:
    return minutes_from_start(d)


def rounds_time(d: date) -> float:
    return day_start(d) + ROUNDS_HOUR * 60.0


def clock_label(t: float) -> str:
    ts = pd.Timestamp(C.WARMUP_START) + pd.Timedelta(minutes=float(t))
    return ts.strftime("%H:%M")


def day_label(t: float) -> str:
    ts = pd.Timestamp(C.WARMUP_START) + pd.Timedelta(minutes=float(t))
    return ts.strftime("%a %b %d")


# --------------------------------------------------------------------------- ED state
def ed_snapshot(t: float) -> pd.DataFrame:
    """Everyone in the ED at time t with a plain status."""
    ed = data("ed_visits")
    here = ed[(ed.arrival_min <= t) & (ed.departure_min > t)].copy()
    roomed = here.roomed_min.notna() & (here.roomed_min <= t)
    decided = here.decision_min.notna() & (here.decision_min <= t)
    here["status"] = np.select(
        [~roomed, roomed & ~decided, decided & here.admitted, decided & ~here.admitted],
        ["Waiting", "In treatment", "Boarding", "Discharging"], default="Waiting")
    here["hours_in_ed"] = (t - here.arrival_min) / 60
    here["hours_boarding"] = np.where(here.status == "Boarding", (t - here.decision_min) / 60, np.nan)
    return here


def boarding_hours_today(t: float) -> float:
    """ED space-hours held by admitted patients (decision to admit until they leave the ED), midnight to t."""
    ed = data("ed_visits")
    s0 = math.floor(t / MIN_PER_DAY) * MIN_PER_DAY
    adm = ed[ed.admitted & ed.decision_min.notna() & (ed.decision_min < t) & (ed.departure_min > s0)]
    held = np.minimum(adm.departure_min, t) - np.maximum(adm.decision_min, s0)
    return float(np.clip(held, 0, None).sum() / 60)


def room_board(t: float) -> pd.DataFrame:
    """One row per ED space with who is in it."""
    snap = ed_snapshot(t)
    inroom = snap[snap.status != "Waiting"].set_index("room_label")
    hour = (t % MIN_PER_DAY) / 60
    ft_open = C.FAST_TRACK_HOURS[0] <= hour < C.FAST_TRACK_HOURS[1]
    rows = []
    prefix = {"main": "T", "fast_track": "FT", "resus": "R", "behavioral": "BH"}
    for space, n in C.ED_SPACES.items():
        for k in range(1, n + 1):
            label = f"{prefix[space]}{k}"
            if label in inroom.index:
                r = inroom.loc[label]
                rows.append({"space": space, "room": label, "status": r.status, "visit_id": r.visit_id,
                             "esi": int(r.esi), "detail": (f"{r.admit_unit} · {r.hours_boarding:.1f} h"
                                                           if r.status == "Boarding" else f"ESI {int(r.esi)}")})
            else:
                closed = space == "fast_track" and not ft_open
                rows.append({"space": space, "room": label, "status": "Closed" if closed else "Empty",
                             "visit_id": "", "esi": None, "detail": "Fast-track closed" if closed else ""})
    return pd.DataFrame(rows)


def threshold_now(t: float) -> dict:
    cr = crowding()
    hour_t = math.floor(t / 60) * 60.0
    c = float(cr.get(hour_t, cr.iloc[cr.index.searchsorted(hour_t) - 1]))
    typical = model_bundle("admission")["typical_crowding"]
    thr = moving_threshold(c, typical)
    return {"crowding": c, "typical": typical, "threshold": thr, "reason": threshold_reason(c, typical, thr)}


def ed_queue(t: float) -> pd.DataFrame:
    """Triaged, still-undecided ED patients with P(admit), likely unit and reasons."""
    snap = ed_snapshot(t)
    q = snap[snap.triage_end_min.notna() & (snap.triage_end_min <= t)
             & (snap.decision_min.isna() | (snap.decision_min > t))].copy()
    if q.empty:
        return q
    sc = admission_scores().loc[q.index]
    q["p_admit"] = sc.p_admit.to_numpy()
    q["likely_unit"] = sc.likely_unit.to_numpy()
    q["likely_unit_p"] = sc[list(C.UNIT_NAMES)].max(axis=1).to_numpy()
    thr = threshold_now(t)["threshold"]
    q["flagged"] = q.p_admit >= thr
    nb = next_batch(t)
    q["in_next_batch"] = q.flagged & (q.triage_end_min + C.IMPACT_DEFAULTS["staff_response_delay_h"] * 60 <= nb)
    model = model_bundle("admission")["model"]
    X = A.prepare(q)
    q["reasons"] = top_reasons(model.contributions(X), X)
    return q.sort_values("p_admit", ascending=False)


def next_batch(t: float) -> float:
    return math.floor(t / 60) * 60.0 + 60.0


def batch_requests(queue: pd.DataFrame, excluded: set[str] = frozenset()) -> pd.DataFrame:
    """Hourly per-unit bed request from patients in the next batch, minus overrides."""
    rows = []
    elig = queue[queue.in_next_batch & ~queue.visit_id.isin(excluded)] if len(queue) else queue
    for u in C.UNIT_NAMES:
        sub = elig[elig.likely_unit == u] if len(elig) else elig
        b = batch_request(sub.p_admit.tolist() if len(sub) else [])
        rows.append({"unit": u, **b, "visit_ids": list(sub.visit_id) if len(sub) else []})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- inpatient state
def unit_board(t: float, dc_overrides: dict | None = None) -> pd.DataFrame:
    st = F.unit_state(t, data("inpatient_stays"))
    fc = forecast_at(t, dc_overrides, horizons=(4,))
    st["expected_ready_4h"] = fc.set_index("unit").expected_discharges_ready + fc.set_index("unit").beds_ready_from_cleaning
    return st


def forecast_at(t: float, dc_overrides: dict | None = None, horizons=F.HORIZONS_H) -> pd.DataFrame:
    dcs = discharge_scores()
    if dc_overrides:
        dcs = dcs.copy()
        for note_id, p in dc_overrides.items():
            dcs.loc[dcs.note_id == note_id, "p_discharge_24h"] = p
    sc = admission_scores()[["p_admit", *C.UNIT_NAMES]]
    return F.forecast(t, data("ed_visits"), data("inpatient_stays"), sc, dcs, forecast_tables(), horizons)


def day_series(d: date) -> pd.DataFrame:
    """Hourly boarders, patients not yet roomed and clean open beds over one day."""
    c = data("census_hourly")
    s0 = day_start(d)
    sub = c[(c.hour_min >= s0) & (c.hour_min < s0 + MIN_PER_DAY)].copy()
    sub["hour"] = ((sub.hour_min - s0) / 60).astype(int)
    sub["open_beds"] = sub[[f"{u}|open" for u in C.UNIT_NAMES]].sum(axis=1)
    sub["cleaning"] = sub[[f"{u}|cleaning" for u in C.UNIT_NAMES]].sum(axis=1)
    sub["boarders"] = sub["ED|boarders"]
    sub["waiting"] = sub["ED|not_yet_roomed"]
    return sub[["hour", "hour_min", "boarders", "waiting", "open_beds", "cleaning"]]


# --------------------------------------------------------------------------- rounds
def rounds_list(d: date, unit: str | None = None) -> pd.DataFrame:
    """Inpatients at 07:00 rounds on day d with P(discharge 24 h), note, barriers, reasons."""
    r = rounds_time(d)
    days = data("inpatient_days")
    rows = days[days.rounds_min == r]
    if unit and unit != "All units":
        rows = rows[rows.unit == unit]
    if rows.empty:
        return rows
    found = note_findings()
    X = D.add_barrier_flags(rows, found[found.note_id.isin(rows.note_id)])
    bundle = model_bundle("discharge")
    model = bundle["model"]
    X["p_discharge_24h"] = model.predict_proba(X)
    X["reasons"] = top_reasons(model.contributions(X), X)
    notes = data("notes").set_index("note_id")
    X["note"] = notes.loc[X.note_id, "text"].to_numpy()
    def records(frame: pd.DataFrame) -> list:
        groups = frame.groupby("note_id")
        return [groups.get_group(n).to_dict(orient="records") if n in groups.groups else [] for n in X.note_id]

    X["rule_findings"] = records(found[found.note_id.isin(X.note_id)][FINDING_COLUMNS].assign(reader="rules"))
    X["findings"] = records(display_findings(X.note_id, found))
    X["flagged"] = X.p_discharge_24h >= C.DISCHARGE_LIST_THRESHOLD
    return X.sort_values("p_discharge_24h", ascending=False)


def rescore_without_barriers(row: pd.Series, barriers: list[str]) -> float:
    """P(discharge 24 h) if the listed barriers were cleared (what changes after an action)."""
    X = pd.DataFrame([row])
    for b in barriers:
        X[f"note_{b}"] = 0.0
    X["note_any_barrier"] = X[D.BARRIER_FEATURES].max(axis=1)
    return float(model_bundle("discharge")["model"].predict_proba(X)[0])


def highlight(note: str, findings: list[dict]) -> list[tuple[str, str | None]]:
    """Split a note into (text, barrier type or None) segments for highlighting."""
    spans = sorted((f["start"], f["end"], f["barrier_type"]) for f in findings)
    out, pos = [], 0
    for s, e, b in spans:
        if s < pos:
            continue
        if s > pos:
            out.append((note[pos:s], None))
        out.append((note[s:e], b))
        pos = e
    if pos < len(note):
        out.append((note[pos:], None))
    return out


# --------------------------------------------------------------------------- guided tour
@cache
def tour_patients(d: date) -> dict:
    """Pick the guided-tour patients by a documented rule (no data is edited).

    1. ED patient: the first hour from 09:00 to 12:00 with a patient flagged for the next
       hourly batch whose likely unit is a non-ICU ward; highest P(admit) first.
    2. Inpatient: on that same unit at 07:00 rounds, whose note the reader flags for
       transport (else family pickup, else any barrier), choosing the patient whose
       discharge chance rises most if the barrier is cleared (medically close to ready).
    Preference order: ED patients who were in fact admitted to their likely unit (so the
    tour shows the intended workflow; overall likely-unit accuracy is reported as 69%),
    and inpatients whose cleared-barrier chance is at least 30%. The first match is used.
    """
    rl = rounds_list(d)
    out: dict = {"rule": tour_patients.__doc__}

    def inpatient_on(unit, min_cleared):
        for btype in ("transport", "family_pickup", None):
            pool = rl[(rl.unit == unit) & rl.rule_findings.map(
                lambda fs, b=btype: any(f["barrier_type"] == b for f in fs) if b else bool(fs))]
            if not pool.empty:  # chosen on the rule findings, which drive the score, so the tour is stable
                cleared = pool.apply(lambda r: rescore_without_barriers(
                    r, [f["barrier_type"] for f in r.rule_findings]), axis=1)
                best = pool.assign(p_cleared=cleared).sort_values("p_cleared", ascending=False).iloc[0]
                if best.p_cleared >= min_cleared:
                    return best
        return None

    candidates = []
    for hour in range(C.DEMO_START_HOUR - 1, C.DEMO_START_HOUR + 3):
        q = ed_queue(day_start(d) + hour * 60.0)
        if len(q):
            pool = q[q.in_next_batch & (q.likely_unit != "ICU")]
            candidates += [(hour, e) for _, e in pool.iterrows() if e.visit_id not in {c[1].visit_id for c in candidates}]
    correct = [(h, e) for h, e in candidates if e.admitted and e.admit_unit == e.likely_unit]
    passes = [(correct, 0.30), (candidates, 0.30), (candidates, 0.0)]
    for pool_list, min_cleared in passes:
        for hour, e in pool_list:
            ip = inpatient_on(e.likely_unit, min_cleared)
            if ip is None:
                continue
            out["ed_patient"] = {"visit_id": e.visit_id, "likely_unit": e.likely_unit, "p": float(e.p_admit),
                                 "reasons": e.reasons, "complaint": e.chief_complaint, "esi": int(e.esi),
                                 "hour": hour, "admitted": bool(e.admitted), "admit_unit": e.admit_unit}
            out["inpatient"] = {"stay_id": ip.stay_id, "note_id": ip.note_id, "unit": ip.unit,
                                "note": ip.note, "p": float(ip.p_discharge_24h),
                                "p_cleared": float(ip.p_cleared),
                                "barriers": [f["barrier_type"] for f in ip.rule_findings]}
            return out
    return out


# ----------------------------------------------------------------------------- headline impact
@cache
def plan() -> dict | None:
    path = MODELS / "plan.json"
    return json.loads(path.read_text()) if path.is_file() else None


@cache
def impact_summary() -> dict:
    """The few ranges that say what the tool changes, for a concise Overview strip.

    Read from ``models/impact_ranges.json`` (built by ``scripts/build_plan.py``): rounded ranges across the
    three synthetic years, introduced by the break-even point, never a single simulated number. Each item has
    a short label, the value as text and a one-line note on how it was reached. Freed capacity is not cash
    and is never added to a cash figure. The caption is the results caveat.
    """
    r = json.loads((MODELS / "impact_ranges.json").read_text())
    sc = {s["name"]: s for s in r["scenarios"]}
    exp, cau = sc["Expected"], sc["Cautious"]
    be = r["break_even"]["minutes_per_admission"]

    def rng(x: list, unit: str = "", prefix: str = "") -> str:
        return f"{prefix}{x[0]:g}{unit} to {prefix}{x[1]:g}{unit}"

    def fewer(x: list, unit: str, places: int = 0) -> str:
        return f"{-x[1]:.{places}f} to {-x[0]:.{places}f}{unit}"

    gaps = r["equity"]
    case = [g for g in gaps if g["gap"].startswith((C.MEDICAID, C.UNINSURED))]
    narrowed = sum(g["verdict"] == "Narrowed" for g in case)
    widened = sum(g["verdict"] == "Widened" for g in gaps)
    cost = r["tool_cost"]["per_year_usd"]
    items = [
        {"key": "break_even", "label": "Break-even", "value": f"{be} min per admission",
         "note": r["break_even"]["explanation"]},
        {"key": "minutes_saved", "label": "Less boarding per admitted patient (Expected)",
         "value": rng(exp["minutes_saved_per_admission"], " min"),
         "note": f"Cautious: {rng(cau['minutes_saved_per_admission'], ' min')}. Expected: {exp['settings']}"},
        {"key": "capacity_value", "label": "Freed capacity a year, Expected (not cash)",
         "value": rng(exp["freed_capacity_per_year_usd_m"], "M", "$"),
         "note": "Minutes saved per admission / 60 x 13,600 admissions a year x the brief's $350 per boarded "
                 "room-hour."},
        {"key": "wait", "label": "Shorter wait to see a provider (Expected)",
         "value": fewer(exp["provider_wait_change_min"], " min"), "note": "Median arrival to provider, winter test quarter."},
        {"key": "walkouts", "label": "Fewer patients leave unseen (Expected)",
         "value": fewer(exp["walkout_change_pts"], " points", 1),
         "note": "Share of arrivals leaving before a provider sees them, winter test quarter."},
        {"key": "equity", "label": "Medicaid/CHIP and Uninsured gaps narrowed (Expected)",
         "value": f"{narrowed} of {len(case)}",
         "note": f"{widened} gaps widened; the rest are flat. Payer is never a model input."},
        {"key": "cost", "label": "Tool cost a year", "value": rng([c / 1e3 for c in cost], "K", "$"),
         "note": r["tool_cost"]["note"]},
    ]
    return {"items": items, "caption": r["caveat"]}
