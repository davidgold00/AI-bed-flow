"""Generate the synthetic year: baseline simulation plus all derived tables.

Outputs (in ``data/``):

* ``ed_visits.parquet``        one row per 2025 ED visit, IDs like ED-000123
* ``inpatient_stays.parquet``  one row per inpatient stay in house during 2025, IDs like IP-004512
* ``inpatient_days.parquet``   one row per inpatient per 07:00 rounds (discharge-model data)
* ``notes.parquet``            one typed note per inpatient day
* ``note_labels.parquet``      ground-truth active barriers per note (scoring only)
* ``census_hourly.parquet``    hourly unit census and ED space use
* ``validation.json``          the calibration table
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from halvian import config as C
from halvian.data.cohort import MIN_PER_DAY, Cohort, build_cohort, minutes_from_start
from halvian.data.notes import make_note
from halvian.data.simulate import SimResult, run
from halvian.validation import compute_metrics, info_rows, run_checks

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
ROUNDS_HOUR = 7

ED_KEEP = [
    "visit_id", "cohort_row", "arrival_min", "payer", "age", "sex", "arrival_mode", "chief_complaint",
    "esi", "heart_rate", "systolic_bp", "resp_rate", "spo2", "temp_c", "recent_ed_visits_12m",
    "arrival_hour", "arrival_dow", "arrival_month", "winter", "t_registration", "t_triage",
    "reg_start_min", "reg_end_min", "triage_end_min", "roomed_min", "room_type", "room_label",
    "provider_min", "decision_min", "departure_min", "door_to_provider_min", "disposition",
    "lwbs", "admitted", "admit_unit", "bed_request_min", "bed_assigned_min", "boarding_min",
    "dx_group",
]


def ed_table(res: SimResult) -> pd.DataFrame:
    ed = res.ed.copy()
    ed["cohort_row"] = np.arange(len(ed))
    y0, y1 = minutes_from_start(C.YEAR_START), minutes_from_start(C.YEAR_END)
    ed = ed[(ed.arrival_min >= y0) & (ed.arrival_min < y1)].copy()
    ed["visit_id"] = [f"ED-{k:06d}" for k in range(1, len(ed) + 1)]
    ed.loc[~ed.admitted, "admit_unit"] = None
    ed.loc[~ed.admitted, "dx_group"] = None
    return ed[ED_KEEP].reset_index(drop=True)


def stays_table(res: SimResult, cohort: Cohort, ed_ids: pd.Series,
                start: date = C.YEAR_START, end: date = C.YEAR_END) -> pd.DataFrame:
    st = res.stays.copy()
    st["request_row"] = np.arange(len(st))
    t0, t1 = minutes_from_start(start), minutes_from_start(end)
    st = st[st.bed_arrival_min.notna() & (st.bed_arrival_min < t1) & (st.discharge_min >= t0)].copy()
    ed, ne = cohort.ed, cohort.nonED
    is_ed = st.kind == "ED"
    rows = st.row.to_numpy()
    cols = ["payer", "age", "dx_group", "ip_los_ready_h", "ip_barrier", "ip_barrier_delay_h",
            "ip_mobility0", "ip_note_seed"]
    for c in cols:
        vals = np.where(is_ed, ed[c].to_numpy()[np.where(is_ed, rows, 0)],
                        ne[c].to_numpy()[np.where(~is_ed, rows, 0)])
        st[c] = vals
    st["payer"] = pd.Categorical(st.payer, categories=C.PAYERS)
    st["source"] = np.where(is_ed, "ED", ne.source.to_numpy()[np.where(~is_ed, rows, 0)])
    id_map = dict(zip(ed_ids.index, ed_ids.to_numpy(), strict=True))
    st["ed_visit_id"] = [id_map.get(r) if k else None for r, k in zip(rows, is_ed, strict=True)]
    st = st.sort_values(["bed_arrival_min", "request_row"]).reset_index(drop=True)
    st["stay_id"] = [f"IP-{k:06d}" for k in range(1, len(st) + 1)]
    st["barrier"] = st.pop("ip_barrier")
    st["barrier_delay_h"] = st.pop("ip_barrier_delay_h")
    st["los_h"] = (st.discharge_min - st.bed_arrival_min) / 60
    return st


def inpatient_days(stays: pd.DataFrame, seed: int, start: date = C.YEAR_START,
                   end: date = C.YEAR_END) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """07:00 rounds snapshots, one note each, and the note ground truth."""
    t0, t1 = minutes_from_start(start), minutes_from_start(end)
    r_off = ROUNDS_HOUR * 60.0
    first = np.ceil((stays.bed_arrival_min.to_numpy() - r_off) / MIN_PER_DAY)
    last = np.floor((stays.discharge_min.to_numpy() - r_off - 1e-6) / MIN_PER_DAY)
    count = np.maximum(0, last - first + 1).astype(int)
    idx = np.repeat(np.arange(len(stays)), count)
    offset = np.concatenate([np.arange(c) for c in count]) if len(count) else np.array([])
    t = (np.repeat(first, count) + offset) * MIN_PER_DAY + r_off
    # Per-stay noise streams drawn over each stay's full run of days, so a patient's
    # observations depend only on their own history (and not on other patients or on
    # how long their own stay will last).
    seeds_all = stays.ip_note_seed.to_numpy()
    z = np.empty((len(t), 3))
    pos = 0
    for k, c in enumerate(count):
        if c:
            z[pos:pos + c] = np.random.default_rng([int(seeds_all[k]), int(seed), 7]).standard_normal((c, 3))
            pos += c
    walk_lab_all = pd.Series(0.35 * z[:, 0]).groupby(idx).cumsum().to_numpy()
    walk_mob_all = pd.Series(0.9 * z[:, 1]).groupby(idx).cumsum().to_numpy()
    keep = (t >= t0) & (t < t1)
    idx, t, z = idx[keep], t[keep], z[keep]
    walk_lab, walk_mob = walk_lab_all[keep], walk_mob_all[keep]
    s = stays.iloc[idx].reset_index(drop=True)
    arrival = s.bed_arrival_min.to_numpy()
    ready = s.ready_min.to_numpy()
    progress = (t - arrival) / np.maximum(ready - arrival, 60.0)
    # per-stay mobility gain and barrier identification, deterministic per stay
    gain = np.array([np.random.default_rng(int(v)).uniform(3, 8) for v in seeds_all])[idx]
    ident_h = np.array([np.random.default_rng(int(v) + 1).uniform(6, 48) for v in seeds_all])[idx]
    m0 = s.ip_mobility0.to_numpy().astype(float)
    m_ready = np.minimum(24, m0 + gain)
    # Observations follow the patient's (hidden) recovery plus day-to-day random-walk noise,
    # so they are informative but not a clean readout of the readiness time.
    mobility = np.clip(m0 + (m_ready - m0) * np.clip(progress, 0, 1) + walk_mob + 1.2 * z[:, 2], 6, 24).round()
    lab_white = np.array([np.random.default_rng([int(v), int(tt // MIN_PER_DAY), 11]).normal(0, 0.45)
                          for v, tt in zip(seeds_all[idx], t, strict=True)])
    lab = np.clip(1.5 * np.clip(progress, 0, 1.2) - 0.6 + walk_lab + lab_white, -2, 2).round(2)
    resolved = ready + s.barrier_delay_h.to_numpy() * 60
    # Case management identifies a barrier 6 to 48 h into the stay, independent of when it
    # will be resolved (no future information). If it resolves first, it is never noted.
    identified = arrival + ident_h * 60
    days = pd.DataFrame({
        "stay_id": s.stay_id,
        "rounds_min": t,
        "rounds_dow": ((t // MIN_PER_DAY).astype(int) + C.WARMUP_START.weekday()) % 7,
        "unit": s.unit,
        "dx_group": s.dx_group,
        "source": s.source,
        "payer": s.payer,
        "age": s.age,
        "los_so_far_h": (t - arrival) / 60,
        "mobility_score": mobility,
        "lab_trend": lab,
        "discharge_min": s.discharge_min,
        "hours_to_discharge": (s.discharge_min.to_numpy() - t) / 60,
        "discharged_24h": (s.discharge_min.to_numpy() > t) & (s.discharge_min.to_numpy() <= t + MIN_PER_DAY),
        "true_barrier": s.barrier,
        "barrier_active": s.barrier.notna().to_numpy() & (t >= identified) & (t < resolved),
    })
    base_wd = C.WARMUP_START.weekday()
    texts, label_rows = [], []
    note_ids = [f"N-{k:07d}" for k in range(1, len(days) + 1)]
    seeds = s.ip_note_seed.to_numpy()
    barriers = s.barrier.to_numpy()
    for k in range(len(days)):
        nrng = np.random.default_rng([int(seeds[k]), int(t[k] // MIN_PER_DAY)])
        b = barriers[k] if isinstance(barriers[k], str) else None
        text, labels = make_note(nrng, t[k] - 60, progress[k], mobility[k], b, identified[k],
                                 resolved[k], base_wd)
        texts.append(text)
        for lab_type in labels:
            label_rows.append((note_ids[k], lab_type))
    days.insert(0, "note_id", note_ids)
    notes = pd.DataFrame({"note_id": note_ids, "stay_id": s.stay_id, "written_min": t - 60, "text": texts})
    labels = pd.DataFrame(label_rows, columns=["note_id", "barrier_type"])
    return days, notes, labels


def census_hourly(res: SimResult, start: date = C.YEAR_START, end: date = C.YEAR_END) -> pd.DataFrame:
    grid = np.arange(minutes_from_start(start), minutes_from_start(end), 60.0)
    rows = {"hour_min": grid}
    st = res.stays[res.stays.bed_arrival_min.notna()]

    def count(a, b, sub):
        a = np.sort(sub[a].to_numpy())
        b = np.sort(sub[b].to_numpy())
        return np.searchsorted(a, grid, side="right") - np.searchsorted(b, grid, side="right")

    for u in C.UNIT_NAMES:
        su = st[st.unit == u]
        occ = count("bed_arrival_min", "discharge_min", su)
        dirty = count("discharge_min", "clean_min", su)
        incoming = count("bed_assigned_min", "bed_arrival_min", su)
        rows[f"{u}|occupied"] = occ
        rows[f"{u}|cleaning"] = dirty
        rows[f"{u}|assigned"] = incoming
        rows[f"{u}|open"] = C.UNITS[u] - occ - dirty - incoming
    ed = res.ed[res.ed.roomed_min.notna()]
    for sp in C.ED_SPACES:
        rows[f"ED {sp}|in_use"] = count("roomed_min", "departure_min", ed[ed.room_type == sp])
    adm = res.ed[res.ed.admitted]
    rows["ED|boarders"] = count("decision_min", "departure_min", adm)
    arr = res.ed.copy()
    arr["roomed_or_left"] = arr.roomed_min.fillna(arr.departure_min)
    rows["ED|not_yet_roomed"] = count("arrival_min", "roomed_or_left", arr)
    return pd.DataFrame(rows)


def replication_summary(main_seed: int) -> list[dict]:
    """Calibration checks on the other synthetic years used for impact replications."""
    out = []
    for s in C.IMPACT_REPLICATION_SEEDS:
        if s == main_seed:
            continue
        res = run(build_cohort(seed=s))
        chk = run_checks(compute_metrics(res.ed, res.stays))
        out.append({"seed": s, "passed": int(chk.Pass.sum()), "total": len(chk),
                    "failed": [f"{r.Target} (simulated {r.Simulated})" for r in chk[~chk.Pass].itertuples()]})
    return out


def generate(seed: int = C.SEED, params=None, out_dir: Path | None = DATA_DIR, verbose: bool = True) -> dict:
    cohort = build_cohort(seed=seed, params=params)
    res = run(cohort)
    ed = ed_table(res)
    ed_ids = ed.set_index("cohort_row").visit_id
    stays = stays_table(res, cohort, ed_ids)
    days, notes, labels = inpatient_days(stays, seed)
    census = census_hourly(res)
    metrics = compute_metrics(res.ed, res.stays)
    checks = run_checks(metrics)
    out = {"ed_visits": ed, "inpatient_stays": stays.drop(columns=["ip_note_seed"]),
           "inpatient_days": days, "notes": notes, "note_labels": labels, "census_hourly": census}
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        for name, df in out.items():
            df.to_parquet(out_dir / f"{name}.parquet", index=False, compression="zstd")
        payload = {
            "seed": seed,
            "passed": int(checks.Pass.sum()),
            "total": len(checks),
            "checks": checks.to_dict(orient="records"),
            "info": info_rows(metrics).to_dict(orient="records"),
            "metrics": {k: v for k, v in metrics.items() if isinstance(v, int | float | str | bool)},
            "unit_occupancy": metrics["unit_occupancy"],
        }
        payload["replication_years"] = replication_summary(seed)
        payload["open_calibration_misses"] = [c["Target"] for c in payload["checks"] if not c["Pass"]]
        payload["notes"] = (
            "Only the main synthetic year (config.SEED) is calibrated. replication_years shows the "
            "same checks on the two other synthetic years used for impact replications; their misses "
            "are ordinary year-to-year variation, not calibration targets."
        )
        (out_dir / "validation.json").write_text(json.dumps(payload, indent=2, default=float))
    if verbose:
        print(f"ED visits: {len(ed):,}  stays: {len(stays):,}  rounds rows: {len(days):,}  "
              f"notes with a barrier label: {labels.note_id.nunique():,}")
        print(f"Validation: {int(checks.Pass.sum())} of {len(checks)} checks pass")
    out["checks"] = checks
    out["metrics"] = metrics
    out["result"] = res
    out["cohort"] = cohort
    return out
