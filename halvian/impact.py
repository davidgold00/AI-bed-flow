"""Impact simulator: paired baseline and tool runs on the same synthetic patients.

Design (REVIEW findings 1, 3, 5, 8, 9 and 10):

* **Paired arms.** The tool arm replays the same pre-drawn patients as the baseline. The
  tool switches on at the start of the test quarter (Oct 1), so both arms are identical
  before then. Three synthetic years (seeds) show run-to-run variation; their spread is a
  description of simulation variability, not a confidence interval.
* **Only information known at the time.** Bed requests come from hourly batches of
  patients flagged at triage after the staff response delay. Discharge actions come from
  07:00 rounds in scenario time, scoring the inpatients present at that moment with that
  morning's note.
* **Capacity accounting.** Bed-hours freed = total boarded ED room-hours in the
  window (baseline minus tool), including visits crossing the window edges; valued at
  $350 per bed-hour as freed capacity, not cash (``halvian.roi.estimate_capacity``). A
  test-quarter run rate scales the paired difference by baseline admissions in the
  window and the case's 13,600 admissions.
* **Trade-offs are reported**: reserved beds left unused, extra waiting for direct and
  elective admissions, and walkouts avoided (valued only under an explicit assumption).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta
from functools import cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from halvian import config as C
from halvian import roi
from halvian.data.cohort import MIN_PER_DAY, Cohort, build_cohort, minutes_from_start
from halvian.data.gaps import guardrail, monthly_gaps, payer_outcomes
from halvian.data.notes import make_note
from halvian.data.simulate import SimResult, ToolSettings, run
from halvian.models import admission as A

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"
WINDOW = (minutes_from_start(datetime(2025, 10, 1).date()), minutes_from_start(C.YEAR_END))
WINDOW_DAYS = 92
PILOT = "Pilot: Medicine A only"
ALL_UNITS = "All units"


@dataclass(frozen=True)
class Scenario:
    adoption: float = C.IMPACT_DEFAULTS["adoption"]
    staff_response_delay_h: float = C.IMPACT_DEFAULTS["staff_response_delay_h"]
    threshold: float = C.IMPACT_DEFAULTS["threshold"]
    discharge_hours_saved: float = C.IMPACT_DEFAULTS["discharge_hours_saved"]
    moving: bool = C.MOVING_THRESHOLD_ON
    scope: str = ALL_UNITS
    admission_side: bool = True
    discharge_side: bool = True
    bed_board: bool = False  # Live Bed Board lever (assumption A22), off in today's defaults

    def label(self) -> str:
        parts = [f"adoption {self.adoption:.0%}", f"response {self.staff_response_delay_h:g} h",
                 f"threshold {self.threshold:.0%}", f"discharge {self.discharge_hours_saved:g} h"]
        if self.scope != ALL_UNITS:
            parts.append("pilot")
        if not self.admission_side and not self.discharge_side:
            return "bed board only" if self.bed_board else "no part switched on"
        if not self.admission_side:
            parts.append("discharge side only")
        if not self.discharge_side:
            parts.append("admission side only")
        if self.bed_board:
            parts.append("bed board on")
        return ", ".join(parts)


# --------------------------------------------------------------------------- inputs
@cache
def cohort(seed: int) -> Cohort:
    return build_cohort(seed=seed)


@cache
def baseline(seed: int) -> SimResult:
    return run(cohort(seed))


@cache
def _models() -> tuple:
    adm = joblib.load(MODELS / "admission.joblib")
    dis = joblib.load(MODELS / "discharge.joblib")
    from halvian.notes.reader import RuleBasedNoteReader

    return adm, dis, RuleBasedNoteReader()


@cache
def admission_inputs(seed: int) -> tuple[np.ndarray, np.ndarray]:
    """P(admit) and likely unit for every pre-drawn ED patient (triage information only)."""
    adm, _, _ = _models()
    ed = cohort(seed).ed
    X = A.prepare(ed)
    p = adm["model"].predict_proba(X)
    probs = A.unit_probabilities(X, adm["unit_lookup"], adm["unit_by_complaint"])
    pred = probs.to_numpy().argmax(axis=1)
    return p, pred


def make_rounds_scorer(seed: int):
    """Score present inpatients at 07:00 rounds in scenario time.

    Features follow the same rules as the generated training data
    (``halvian.data.generate.inpatient_days``): observations from each patient's own
    noise stream, and that morning's note read by the placeholder reader. Notes are
    generated only for stays with a barrier; for the rest the reader's rare false
    positives (precision 0.99) are ignored.
    """
    co = cohort(seed)
    ed, ne = co.ed, co.nonED
    _, dis, reader = _models()
    model = dis["model"]
    cat = lambda a, b: np.concatenate([ed[a].to_numpy(), ne[b].to_numpy()])  # noqa: E731
    note_seed = cat("ip_note_seed", "ip_note_seed").astype(np.int64)
    mob0 = cat("ip_mobility0", "ip_mobility0").astype(float)
    btype = cat("ip_barrier", "ip_barrier")
    bdelay = cat("ip_barrier_delay_h", "ip_barrier_delay_h").astype(float)
    dx = cat("dx_group", "dx_group")
    source = np.concatenate([np.full(len(ed), "ED", dtype=object), ne.source.to_numpy()])
    base_wd = C.WARMUP_START.weekday()
    cache_noise: dict[int, tuple] = {}

    def noise(dk: int):
        if dk not in cache_noise:
            z = np.random.default_rng([int(note_seed[dk]), int(seed), 7]).standard_normal((120, 3))
            cache_noise[dk] = (np.cumsum(0.35 * z[:, 0]), np.cumsum(0.9 * z[:, 1]), z[:, 2],
                               float(np.random.default_rng(int(note_seed[dk])).uniform(3, 8)),
                               float(np.random.default_rng(int(note_seed[dk]) + 1).uniform(6, 48)))
        return cache_noise[dk]

    def scorer(now: float, info: dict):
        day = int(now // MIN_PER_DAY)
        rows, found = [], []
        for dk, arr, ready, unit in zip(info["draw"], info["bed_arrival"], info["ready"], info["unit"], strict=True):
            walk_lab, walk_mob, z2, gain, ident_h = noise(dk)
            first = int(np.ceil((arr - 7 * 60) / MIN_PER_DAY))
            j = min(max(day - first, 0), 119)
            progress = (now - arr) / max(ready - arr, 60.0)
            m_ready = min(24.0, mob0[dk] + gain)
            mobility = float(np.clip(round(mob0[dk] + (m_ready - mob0[dk]) * min(max(progress, 0), 1)
                                           + walk_mob[j] + 1.2 * z2[j]), 6, 24))
            lab_white = np.random.default_rng([int(note_seed[dk]), day, 11]).normal(0, 0.45)
            lab = float(np.clip(1.5 * min(max(progress, 0), 1.2) - 0.6 + walk_lab[j] + lab_white, -2, 2))
            flags = dict.fromkeys(C.BARRIER_TYPES, 0.0)
            hit = None
            b = btype[dk] if isinstance(btype[dk], str) else None
            if b:
                resolved = ready + bdelay[dk] * 60.0
                identified = arr + ident_h * 60.0
                text, _ = make_note(np.random.default_rng([int(note_seed[dk]), day]), now - 60, progress,
                                    mobility, b, identified, resolved, base_wd)
                for f in reader.read(text):
                    flags[f["type"]] = 1.0
                hit = b if flags[b] else None
            found.append(hit)
            rows.append({"los_so_far_h": (now - arr) / 60, "mobility_score": mobility, "lab_trend": lab,
                         **{f"note_{k}": v for k, v in flags.items()}, "unit": unit, "dx_group": dx[dk],
                         "source": source[dk], "rounds_dow": (day + base_wd) % 7})
        p = model.predict_proba(pd.DataFrame(rows)) if rows else np.array([])
        return p, found

    return scorer


def tool_settings(scn: Scenario, seed: int) -> ToolSettings:
    p, pred = admission_inputs(seed)
    adm, _, _ = _models()
    scope = ("Medicine A",) if scn.scope == PILOT else C.UNIT_NAMES
    return ToolSettings(
        enabled=True, start_min=WINDOW[0],
        adoption=scn.adoption, staff_response_delay_h=scn.staff_response_delay_h,
        threshold=scn.threshold if scn.admission_side else 2.0,  # 2.0 = never flags
        moving=scn.moving, typical_crowding=adm["typical_crowding"],
        discharge_hours_saved=scn.discharge_hours_saved if scn.discharge_side else 0.0,
        scope_units=scope, p_admit=p, pred_unit=pred,
        rounds_scorer=make_rounds_scorer(seed) if scn.discharge_side else None,
        bed_board_cut=C.BED_BOARD_DELAY_CUT if scn.bed_board else 0.0,
    )


def run_tool(scn: Scenario, seed: int) -> SimResult:
    return run(cohort(seed), tool_settings(scn, seed))


# --------------------------------------------------------------------------- summaries
def _ts(minutes: float) -> datetime:
    return datetime.combine(C.WARMUP_START, datetime.min.time()) + timedelta(minutes=float(minutes))


def frames(res: SimResult) -> dict:
    """The parts of a run needed for comparison (small enough to store)."""
    ed = res.ed
    w = ed[(ed.arrival_min >= WINDOW[0]) & (ed.arrival_min < WINDOW[1])]
    month = ((pd.Timestamp(C.WARMUP_START) + pd.to_timedelta(w.arrival_min, unit="m")).dt.month).to_numpy()
    window_ed = pd.DataFrame({
        "row": w.index.to_numpy(), "payer": w.payer.astype(str).to_numpy(), "lwbs": w.lwbs.to_numpy(),
        "provider_min": w.provider_min.to_numpy(), "door_to_provider_min": w.door_to_provider_min.to_numpy(),
        "admitted": w.admitted.to_numpy(), "boarding_min": w.boarding_min.to_numpy(), "month": month,
    })
    adm = ed[ed.admitted & (ed.departure_min > WINDOW[0]) & (ed.decision_min < WINDOW[1])]
    intervals = pd.DataFrame({"decision_min": adm.decision_min.to_numpy(), "departure_min": adm.departure_min.to_numpy()})
    st = res.stays
    ne = st[(st.kind == "NonED") & (st.queue_entry_min >= WINDOW[0]) & (st.queue_entry_min < WINDOW[1])]
    return {"window_ed": window_ed, "intervals": intervals,
            "non_ed_wait_h": float(((ne.bed_assigned_min - ne.queue_entry_min) / 60).mean()),
            "baseline_admissions": int((ed.admitted & (ed.decision_min >= WINDOW[0]) & (ed.decision_min < WINDOW[1])).sum()),
            "log": dict(res.tool_log)}


def compare(base: dict, tool: dict) -> dict:
    """Signed effects of the tool for one seed (tool minus baseline unless stated)."""
    b, t = base["window_ed"], tool["window_ed"]
    cap = roi.estimate_capacity(
        [(_ts(a), _ts(z)) for a, z in base["intervals"].itertuples(index=False)],
        [(_ts(a), _ts(z)) for a, z in tool["intervals"].itertuples(index=False)],
        window_start=_ts(WINDOW[0]), window_end=_ts(WINDOW[1]), baseline_admissions=base["baseline_admissions"])

    def med(df, col, mask):
        v = df.loc[mask(df), col]
        return float(v.median()) if len(v) else np.nan

    seen = lambda d: ~d.lwbs & d.provider_min.notna()  # noqa: E731
    adm = lambda d: d.admitted  # noqa: E731
    log = tool["log"]
    out = {
        "boarding_median_h_base": med(b, "boarding_min", adm) / 60, "boarding_median_h_tool": med(t, "boarding_min", adm) / 60,
        "boarding_mean_h_base": float(b.loc[b.admitted, "boarding_min"].mean() / 60),
        "boarding_mean_h_tool": float(t.loc[t.admitted, "boarding_min"].mean() / 60),
        "d2p_median_base": med(b, "door_to_provider_min", seen), "d2p_median_tool": med(t, "door_to_provider_min", seen),
        "lwbs_pct_base": float(100 * b.lwbs.mean()), "lwbs_pct_tool": float(100 * t.lwbs.mean()),
        "walkouts_avoided": int(b.lwbs.sum() - t.lwbs.sum()),
        "admissions_base": int(b.admitted.sum()), "admissions_tool": int(t.admitted.sum()),
        "bed_hours_freed": cap.bed_hours_freed, "capacity_value": cap.capacity_value,
        "run_rate_bed_hours": cap.annualized_bed_hours_freed, "run_rate_value": cap.annualized_capacity_value,
        "mean_minutes_saved_per_admission": 60 * cap.bed_hours_freed / max(base["baseline_admissions"], 1),
        "non_ed_wait_h_base": base["non_ed_wait_h"], "non_ed_wait_h_tool": tool["non_ed_wait_h"],
        "reserved_beds": log.get("reserved", 0), "reserved_claimed": log.get("claimed", 0),
        "reserved_expired": log.get("expired", 0), "idle_reserved_bed_hours": log.get("idle_reserved_min", 0.0) / 60,
        "patients_preprocessed": log.get("preprocessed", 0), "rounds_flags": log.get("rounds_flags", 0),
        "discharges_brought_forward": log.get("accelerated_discharges", 0),
        "discharge_hours_brought_forward": log.get("accel_minutes", 0.0) / 60,
        "accel_barrier": log.get("accel_barrier", 0), "accel_routine": log.get("accel_routine", 0),
    }
    pb, pt = payer_outcomes(b), payer_outcomes(t)
    for p in C.PAYERS:
        out[f"d2p|{p}|base"], out[f"d2p|{p}|tool"] = float(pb.loc[p, "d2p_median"]), float(pt.loc[p, "d2p_median"])
        out[f"lwbs|{p}|base"], out[f"lwbs|{p}|tool"] = float(pb.loc[p, "lwbs_pct"]), float(pt.loc[p, "lwbs_pct"])
    return out


def summarize(per_seed: list[dict]) -> dict:
    df = pd.DataFrame(per_seed)
    return {c: {"mean": float(df[c].mean()), "min": float(df[c].min()), "max": float(df[c].max())}
            for c in df.columns if np.issubdtype(df[c].dtype, np.number)}


def pooled(frames_list: list[dict]) -> pd.DataFrame:
    return pd.concat([f["window_ed"].assign(seed=k) for k, f in enumerate(frames_list)], ignore_index=True)


def evaluate(scn: Scenario, seeds=C.IMPACT_REPLICATION_SEEDS, base_frames: list[dict] | None = None) -> dict:
    """Run the tool arm for each seed and compare with the baseline arm."""
    from halvian.equity import gap_table

    base_frames = base_frames or [frames(baseline(s)) for s in seeds]
    tool_frames = [frames(run_tool(scn, s)) for s in seeds]
    per_seed = [compare(b, t) for b, t in zip(base_frames, tool_frames, strict=True)]
    pb, pt = pooled(base_frames), pooled(tool_frames)
    gt = gap_table(pb, pt)
    guard = guardrail(monthly_gaps(pb, "month"), monthly_gaps(pt, "month"))
    return {"scenario": asdict(scn), "label": scn.label(), "per_seed": per_seed, "summary": summarize(per_seed),
            "gap_table": gt.to_dict(orient="records"), "guardrail": guard.to_dict(orient="records"),
            "monthly_base": monthly_gaps(pb, "month").reset_index().to_dict(orient="records"),
            "monthly_tool": monthly_gaps(pt, "month").reset_index().to_dict(orient="records")}


# --------------------------------------------------------------------------- precomputation
SWEEPS = {
    "adoption": [0.0, 0.25, 0.5, 0.75, 1.0],
    "staff_response_delay_h": [0.0, 0.5, 1.0, 2.0, 3.0],
    "threshold": [0.5, 0.6, 0.7, 0.8, 0.9],
    "discharge_hours_saved": [0.0, 1.0, 2.0, 3.0, 4.0],
}


def scenario_grid() -> list[tuple[str, Scenario]]:
    # "default" is the Cautious scenario (today's defaults); "expected" and "full_rollout" are the other
    # two scenarios shown as rounded ranges, and the "*_only" runs are the parts (halvian/ranges.py).
    # The sweeps below move one setting at a time from the default.
    base = Scenario()
    out = [("default", base), ("pilot", replace(base, scope=PILOT)),
           ("admission_only", replace(base, discharge_side=False)),
           ("discharge_only", replace(base, admission_side=False)),
           ("bed_board_only", replace(base, admission_side=False, discharge_side=False, bed_board=True)),
           ("expected", replace(base, bed_board=True)),
           ("full_rollout", replace(base, **C.FULL_ROLLOUT, moving=True, bed_board=True))]
    seen = {base}
    for knob, values in SWEEPS.items():
        for v in values:
            s = replace(base, **{knob: v})
            if s not in seen:
                seen.add(s)
                out.append((f"{knob}={v:g}", s))
    return out


def precompute(path: Path = MODELS / "scenarios.json", verbose: bool = True) -> dict:
    seeds = C.IMPACT_REPLICATION_SEEDS
    base_frames = [frames(baseline(s)) for s in seeds]
    pooled(base_frames).to_parquet(MODELS / "impact_baseline_window.parquet", index=False, compression="zstd")
    joblib.dump([{k: v for k, v in f.items() if k != "window_ed"} for f in base_frames],
                MODELS / "impact_baseline_extras.joblib", compress=3)
    results = {}
    for name, scn in scenario_grid():
        results[name] = evaluate(scn, seeds, base_frames)
        if verbose:
            s = results[name]["summary"]
            print(f"  {name:28s} boarding {s['boarding_median_h_base']['mean']:.2f} -> "
                  f"{s['boarding_median_h_tool']['mean']:.2f} h, freed {s['bed_hours_freed']['mean']:7.0f} bed-h, "
                  f"{s['mean_minutes_saved_per_admission']['mean']:5.1f} min/admission")
    payload = {"window": "Oct 1 to Dec 31, 2025 (test quarter)", "seeds": list(seeds), "results": results,
               "sweeps": SWEEPS}
    path.write_text(json.dumps(payload, default=float))
    return payload


def stored_baseline_frames() -> list[dict]:
    """Baseline arms saved by ``precompute`` (so live runs simulate only the tool arm)."""
    window = pd.read_parquet(MODELS / "impact_baseline_window.parquet")
    extras = joblib.load(MODELS / "impact_baseline_extras.joblib")
    return [{**extras[k], "window_ed": window[window.seed == k].drop(columns="seed").reset_index(drop=True)}
            for k in range(len(extras))]
