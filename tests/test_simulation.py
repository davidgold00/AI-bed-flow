"""The discrete-event engine: invariants, determinism and the boarding mechanism."""

from __future__ import annotations

import dataclasses
from datetime import date
from functools import lru_cache

import numpy as np
import pandas as pd

from halvian import config as C
from halvian.data.cohort import build_cohort, minutes_from_start
from halvian.data.simulate import run

START, END = date(2025, 2, 1), date(2025, 3, 8)


@lru_cache(maxsize=4)
def _short_run(bed_process_scale: float | None = None):
    params = C.DEFAULT_PARAMS
    if bed_process_scale is not None:
        params = dataclasses.replace(params, bed_process_scale=bed_process_scale)
    cohort = build_cohort(seed=C.SEED, params=params, start=START, end=END)
    return cohort, run(cohort, end_min=minutes_from_start(END))


def _max_concurrent(starts: np.ndarray, ends: np.ndarray) -> int:
    ev = np.concatenate([np.c_[starts, np.ones_like(starts)], np.c_[ends, -np.ones_like(ends)]])
    ev = ev[np.lexsort((ev[:, 1], ev[:, 0]))]  # ends before starts at equal times
    return int(np.cumsum(ev[:, 1]).max())


def test_every_patient_leaves_exactly_once():
    _, res = _short_run()
    ed = res.ed
    assert ed.departure_min.notna().all()
    assert (ed.departure_min >= ed.arrival_min).all()
    outcomes = ed.lwbs.astype(int) + ed.admitted.astype(int) + (ed.disposition == "Discharged").astype(int)
    assert (outcomes == 1).all()


def test_timestamps_are_ordered():
    _, res = _short_run()
    seen = res.ed[~res.ed.lwbs]
    assert (seen.roomed_min >= seen.arrival_min).all()
    assert (seen.provider_min >= seen.roomed_min).all()
    assert (seen.decision_min >= seen.provider_min).all()
    assert (seen.departure_min >= seen.decision_min).all()
    adm = res.ed[res.ed.admitted]
    assert (adm.boarding_min >= 0).all()


def test_ed_rooms_never_double_booked_or_over_capacity():
    _, res = _short_run()
    roomed = res.ed[res.ed.roomed_min.notna()]
    for space, cap in C.ED_SPACES.items():
        r = roomed[roomed.room_type == space]
        if len(r):
            assert _max_concurrent(r.roomed_min.to_numpy(), r.departure_min.to_numpy()) <= cap
    for _, g in roomed.groupby("room_label"):
        g = g.sort_values("roomed_min")
        assert (g.roomed_min.to_numpy()[1:] >= g.departure_min.to_numpy()[:-1] - 1e-9).all()


def test_staffed_space_limit_respected_except_esi1():
    _, res = _short_run()
    r = res.ed[res.ed.roomed_min.notna() & (res.ed.esi > 1)]
    assert _max_concurrent(r.roomed_min.to_numpy(), r.departure_min.to_numpy()) <= C.ED_TOTAL_SPACES


def test_boarders_hold_their_ed_room_until_the_bed_is_ready():
    _, res = _short_run()
    adm = res.ed[res.ed.admitted]
    st = res.stays[res.stays.kind == "ED"].set_index("row")
    arrival_in_bed = st.loc[adm.index, "bed_arrival_min"].to_numpy()
    assert np.allclose(adm.departure_min.to_numpy(), arrival_in_bed)


def test_inpatient_beds_never_double_booked_or_over_capacity():
    _, res = _short_run()
    st = res.stays[res.stays.bed_arrival_min.notna()]
    for unit, cap in C.UNITS.items():
        su = st[st.unit == unit]
        assert _max_concurrent(su.bed_arrival_min.to_numpy(), su.discharge_min.to_numpy()) <= cap
        for _, g in su.groupby("bed_number"):
            g = g.sort_values("bed_assigned_min")
            # a bed is held from assignment until it is clean again
            assert (g.bed_assigned_min.to_numpy()[1:] >= g.clean_min.to_numpy()[:-1] - 1e-9).all()


def test_off_service_placement_respects_icu_rule():
    _, res = _short_run()
    st = res.stays[res.stays.bed_arrival_min.notna()]
    icu_req = st[st.intended_unit == "ICU"]
    assert icu_req.unit.isin(["ICU", "Step-down"]).all()
    non_icu = st[st.intended_unit != "ICU"]
    assert (non_icu.unit != "ICU").all()


def test_discharges_never_before_medical_readiness():
    _, res = _short_run()
    st = res.stays[res.stays.discharge_min.notna()]
    assert (st.discharge_min >= st.ready_min).all()


def test_simulation_is_deterministic():
    cohort = build_cohort(seed=C.SEED, start=START, end=date(2025, 2, 15))
    a = run(cohort, end_min=minutes_from_start(date(2025, 2, 15)))
    b = run(cohort, end_min=minutes_from_start(date(2025, 2, 15)))
    pd.testing.assert_frame_equal(a.ed, b.ed)
    pd.testing.assert_frame_equal(a.stays, b.stays)
    c2 = build_cohort(seed=C.SEED, start=START, end=date(2025, 2, 15))
    pd.testing.assert_frame_equal(cohort.ed, c2.ed)


def test_boarding_blocks_rooms_and_drives_waits_and_walkouts():
    """The core mechanism: slower inpatient bed turnaround (nothing else changed) means
    boarders hold ED rooms longer, so door-to-provider times and LWBS rise."""
    _, base = _short_run()
    _, slow = _short_run(bed_process_scale=C.DEFAULT_PARAMS.bed_process_scale * 2.0)
    b_adm, s_adm = base.ed[base.ed.admitted], slow.ed[slow.ed.admitted]
    assert s_adm.boarding_min.median() > b_adm.boarding_min.median() + 60
    b_seen, s_seen = base.ed[~base.ed.lwbs], slow.ed[~slow.ed.lwbs]
    assert s_seen.door_to_provider_min.median() > b_seen.door_to_provider_min.median()
    assert slow.ed.lwbs.mean() > base.ed.lwbs.mean()


def test_short_window_has_full_year_daily_volume():
    """A window must get the same daily arrival rate as those dates in a full year."""
    short = build_cohort(seed=C.SEED, start=START, end=END).ed
    days = (END - START).days
    per_day = len(short) / days
    # Feb is winter (x1.2 of the ~222/day base) and early March is not
    assert 215 < per_day < 275


def test_short_window_is_operationally_sane():
    _, res = _short_run()
    ed = res.ed
    assert ed.lwbs.mean() < 0.12
    assert ed[~ed.lwbs].door_to_provider_min.median() < 120
