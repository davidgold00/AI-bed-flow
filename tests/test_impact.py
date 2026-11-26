"""Causal guarantees of the impact simulator (REVIEW findings 1, 3 and 5)."""

from __future__ import annotations

import dataclasses
from datetime import date
from functools import lru_cache

import numpy as np
import pandas as pd

from halvian import config as C
from halvian.data.cohort import build_cohort, minutes_from_start
from halvian.data.simulate import ToolSettings, run

START, ACTIVATE, END = date(2025, 9, 10), date(2025, 10, 1), date(2025, 10, 22)
T_ACT, T_END = minutes_from_start(ACTIVATE), minutes_from_start(END)


@lru_cache(maxsize=2)
def _cohort():
    return build_cohort(seed=C.SEED, start=START, end=END)


def _settings(cohort, **kw) -> ToolSettings:
    rng = np.random.default_rng(0)
    n = len(cohort.ed)
    base = dict(enabled=True, start_min=T_ACT, adoption=1.0, threshold=0.6, moving=False,
                p_admit=np.clip(cohort.ed.would_admit * 0.5 + rng.uniform(0, 0.5, n), 0, 1).to_numpy(),
                pred_unit=np.array([C.UNIT_NAMES.index(u) for u in cohort.ed.admit_unit]),
                discharge_hours_saved=2.0)
    base.update(kw)
    return ToolSettings(**base)


def _always_flag(now, info):
    return np.ones(len(info["k"])), [None] * len(info["k"])


@lru_cache(maxsize=2)
def _baseline():
    return run(_cohort(), end_min=T_END)


def test_zero_adoption_reproduces_the_baseline():
    co = _cohort()
    zero = run(co, _settings(co, adoption=0.0, rounds_scorer=_always_flag), end_min=T_END)
    pd.testing.assert_series_equal(zero.ed.departure_min, _baseline().ed.departure_min)
    assert zero.tool_log["reserved"] == 0 and zero.tool_log["accelerated_discharges"] == 0


def test_arms_are_identical_before_activation():
    co = _cohort()
    tool = run(co, _settings(co, rounds_scorer=_always_flag), end_min=T_END)
    base = _baseline()
    before = base.ed.departure_min < T_ACT
    assert np.allclose(base.ed.departure_min[before], tool.ed.departure_min[before])
    for col in ("decision_min", "provider_min", "roomed_min"):
        assert np.allclose(base.ed[col][before], tool.ed[col][before], equal_nan=True)
    key = ["kind", "row"]
    b = base.stays[base.stays.discharge_min < T_ACT].set_index(key).sort_index()
    t = tool.stays.set_index(key).loc[b.index]
    assert np.allclose(b.discharge_min, t.discharge_min) and np.allclose(b.bed_arrival_min, t.bed_arrival_min)
    assert not t.accelerated.any() and t.acted_rounds_min.isna().all()
    assert tool.tool_log["reserved"] > 0 or tool.tool_log["preprocessed"] > 0


def test_batch_trigger_ignores_future_workup_time():
    """Lengthening one patient's future workup must not change when they were flagged."""
    co = _cohort()
    s = _settings(co)
    a = run(co, s, end_min=T_END)
    flagged = a.ed[(a.ed.flag_time_min.notna()) & (a.ed.triage_end_min > T_ACT)]
    i = flagged.index[len(flagged) // 2]
    ed2 = co.ed.copy()
    ed2.loc[i, "t_workup"] = ed2.loc[i, "t_workup"] + 240.0
    b = run(dataclasses.replace(co, ed=ed2), s, end_min=T_END)
    assert a.ed.loc[i, "flag_time_min"] == b.ed.loc[i, "flag_time_min"]
    assert b.ed.loc[i, "decision_min"] > a.ed.loc[i, "decision_min"]


def test_discharges_respect_readiness_barriers_and_the_hours_limit():
    co = _cohort()
    hours = 2.0
    tool = run(co, _settings(co, discharge_hours_saved=hours, rounds_scorer=_always_flag), end_min=T_END)
    st = tool.stays[tool.stays.accelerated]
    assert len(st) > 0
    assert (st.discharge_min >= st.ready_min + 60 - 1e-6).all()
    assert (st.discharge_base_min - st.discharge_min <= hours * 60 + 1e-6).all()
    assert (st.discharge_min >= st.acted_rounds_min - 1e-6).all()
    # the scorer never reports a barrier, so barrier stays cannot leave before it resolves
    draws = np.where(st.kind == "ED", st.row, len(co.ed) + st.row)
    delay = np.concatenate([co.ed.ip_barrier_delay_h, co.nonED.ip_barrier_delay_h])[draws]
    resolved = st.ready_min.to_numpy() + delay * 60
    has = st.has_barrier.to_numpy()
    assert (st.discharge_min.to_numpy()[has] >= resolved[has] + 60 - 1e-6).all()
    assert (st.accel_component == "routine").all()


def _true_barrier_scorer(cohort):
    """Report each patient's real barrier at rounds, so barrier work can start (the best case)."""
    btype = np.concatenate([cohort.ed.ip_barrier.to_numpy(), cohort.nonED.ip_barrier.to_numpy()])

    def scorer(now, info):
        return np.ones(len(info["k"])), [b if isinstance(b, str) else None for b in btype[info["draw"]]]

    return scorer


def test_a_detected_barrier_is_worked_on_never_skipped():
    """Clearing a barrier the reader found can shorten it by at most the hours-saved setting, from rounds."""
    co = _cohort()
    hours = 2.0
    tool = run(co, _settings(co, discharge_hours_saved=hours, rounds_scorer=_true_barrier_scorer(co)),
               end_min=T_END)
    st = tool.stays[tool.stays.accelerated & (tool.stays.accel_component == "barrier")]
    assert len(st) > 0
    draws = np.where(st.kind == "ED", st.row, len(co.ed) + st.row)
    delay = np.concatenate([co.ed.ip_barrier_delay_h, co.nonED.ip_barrier_delay_h])[draws]
    resolved = st.ready_min.to_numpy() + delay * 60
    earliest = np.maximum.reduce([st.ready_min.to_numpy(), st.acted_rounds_min.to_numpy(), resolved - hours * 60])
    assert (st.discharge_min.to_numpy() >= earliest + 60 - 1e-6).all()
    assert (st.acted_rounds_min.to_numpy() >= T_ACT).all()
    assert ((st.acted_rounds_min.to_numpy() % 1440) == 7 * 60).all()  # flags come from 07:00 rounds
