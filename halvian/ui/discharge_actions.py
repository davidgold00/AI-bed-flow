"""Keep staff decisions and the corresponding scenario estimate in sync."""

from datetime import date
from functools import lru_cache

import streamlit as st

from halvian.config import BARRIER_OWNER
from halvian.data.live import rescore_without_barriers, rounds_list
from halvian.ui.session import DemoClock, latest_action, record_action

OVERRIDES = "halvian_dc_overrides"
REASONS = ("Task already arranged", "Evidence is incomplete", "Prioritize another task", "Clinical team disagrees", "Other")


def discharge_id(stay_id: str, barrier: str) -> str:
    return f"discharge|{stay_id}|{barrier}"


def decide_discharge(row, barrier: str, decision: str, clock: DemoClock, page: str, reason_key: str = "") -> None:
    record_action(
        discharge_id(row.stay_id, barrier), decision, clock=clock, page=page,
        role=BARRIER_OWNER.get(barrier, "Nurse"), reason=st.session_state.get(reason_key, "") if reason_key else "",
    )
    refresh_discharge_estimate(row)


def refresh_discharge_estimate(row) -> None:
    cleared = [
        item["barrier_type"] for item in row.findings
        if (action := latest_action(discharge_id(row.stay_id, item["barrier_type"])))
        and action.decision == "approve"
    ]
    overrides = st.session_state.setdefault(OVERRIDES, {})
    if cleared:
        overrides[row.note_id] = rescore_without_barriers(row, cleared)
    else:
        overrides.pop(row.note_id, None)



@lru_cache
def rounds_at(day: date, unit: str):
    """Reuse the same read-only rounds snapshot across widget reruns."""
    return rounds_list(day, unit)
