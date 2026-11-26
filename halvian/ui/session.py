"""Coordinate the replay clock and staff decisions across pages.

`app.py` renders the replay controls once per run below the top navigation. Pages read it with `current_clock()` (or
`page_header()`, which returns it). The `DemoClock` provides a timestamp and
minutes from simulation start, for use with the parquet time columns.

Use `tour_callout("admission")`, `tour_callout("discharge")` or
`tour_callout("forecast")` near a relevant action. Call `set_demo_time(time(...))`
in widget callbacks to move the replay clock. Read the current decision using
`latest_action(recommendation_id)` and append decisions with `record_action`.
Use a stable recommendation ID shared across pages for the same action.
"""

from dataclasses import asdict, dataclass, fields
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal

import pandas as pd
import streamlit as st

from halvian import config as C
from halvian.ui import navigation as NAV

_DEFAULT_TIME = time(C.DEMO_START_HOUR)
_DAY, _TIME, _TOUR, _ACTIONS = "halvian_day", "halvian_time", "halvian_tour", "halvian_actions"
_DAY_INPUT, _TIME_INPUT = "_halvian_day_input", "_halvian_time_input"
_TOUR_INPUT = "_halvian_tour_input"
_DAY_NAMES = {"busy": "Busy winter Monday", "typical": "Typical Wednesday"}
# Recording cues specified for the dashboard controls.
STORY_JUMPS = (("Rounds", time(7)), ("Bed request", time(11)), ("Forecast", time(14)))


@dataclass(frozen=True)
class DemoClock:
    day: date
    time: time

    @property
    def timestamp(self) -> datetime:
        return datetime.combine(self.day, self.time)

    @property
    def minutes_from_start(self) -> float:
        return (self.timestamp - datetime.combine(C.WARMUP_START, time.min)) / timedelta(minutes=1)


@dataclass(frozen=True)
class Action:
    recorded_at_utc: str
    replay_time: str
    page: str
    recommendation_id: str
    decision: Literal["approve", "override"]
    role: str
    reason: str


def record_action(
    recommendation_id: str,
    decision: Literal["approve", "override"],
    *,
    page: str,
    role: str,
    clock: DemoClock,
    reason: str = "",
) -> Action:
    """Append one decision to the browser session. An override requires a reason."""
    if decision not in {"approve", "override"}:
        raise ValueError("Choose approve or override.")
    reason = reason.strip()
    if decision == "override" and not reason:
        raise ValueError("An override requires a reason.")
    action = Action(
        recorded_at_utc=datetime.now(UTC).isoformat(timespec="seconds"),
        replay_time=clock.timestamp.isoformat(timespec="minutes"),
        page=page,
        recommendation_id=recommendation_id,
        decision=decision,
        role=role,
        reason=reason,
    )
    st.session_state[_ACTIONS] = (*st.session_state.get(_ACTIONS, ()), action)
    return action


def latest_action(recommendation_id: str) -> Action | None:
    """Return the last decision for a recommendation, if any."""
    return next(
        (action for action in reversed(st.session_state.get(_ACTIONS, ()))
         if action.recommendation_id == recommendation_id),
        None,
    )


def action_log() -> pd.DataFrame:
    """Return the session ledger in entry order for display or export."""
    actions = st.session_state.get(_ACTIONS, ())
    return pd.DataFrame(
        [asdict(action) for action in actions], columns=[field.name for field in fields(Action)]
    )


def set_demo_time(value: time) -> None:
    """Set the durable replay time from a button callback before a rerun."""
    st.session_state[_TIME] = value


def set_demo_day(key: str) -> None:
    """Set the replay day ("busy" or "typical") from a button callback before a rerun."""
    st.session_state[_DAY] = C.DEMO_DAYS[key]


def _store_input(target: str, widget: str) -> None:
    value = st.session_state[widget]
    if value is not None:
        st.session_state[target] = value


def _init_state() -> None:
    state = st.session_state
    state.setdefault(_DAY, C.DEMO_DAYS["busy"])
    if state[_DAY] in C.DEMO_DAYS:  # Sessions opened with the original preset selector.
        state[_DAY] = C.DEMO_DAYS[state[_DAY]]
    state.setdefault(_TIME, _DEFAULT_TIME)
    state.setdefault(_TOUR, False)


def current_clock() -> DemoClock:
    """The replay moment chosen in the context bar (busy winter Monday at 10:00 by default)."""
    _init_state()
    return DemoClock(st.session_state[_DAY], st.session_state[_TIME])


def tour_active() -> bool:
    return bool(st.session_state.get(_TOUR, False))


def _shift_time(direction: int) -> None:
    clock = current_clock()
    step = timedelta(minutes=C.SCORE_REFRESH_MIN)
    start = datetime.combine(clock.day, time.min)
    end = start + timedelta(days=1) - step
    set_demo_time(min(end, max(start, clock.timestamp + direction * step)).time())


def _reset_replay() -> None:
    set_demo_day("busy")
    set_demo_time(_DEFAULT_TIME)
    st.session_state[_TOUR] = False
    st.session_state.pop("halvian_team_step", None)


def _show_decision_log() -> None:
    st.session_state[NAV.OVERSIGHT_TAB_KEY] = NAV.DECISION_LOG_TITLE


def replay_controls(*, on_oversight: bool = False) -> DemoClock:
    """Render the shared day, time, demo highlights and decision log controls."""
    clock = current_clock()
    state = st.session_state
    state[_DAY_INPUT], state[_TIME_INPUT], state[_TOUR_INPUT] = state[_DAY], state[_TIME], state[_TOUR]
    step = timedelta(minutes=C.SCORE_REFRESH_MIN)
    day_end = (datetime.combine(clock.day, time.min) + timedelta(days=1) - step).time()
    with st.container(key="replay_bar"):
        # Row one: what you are viewing, in a plain sentence, and which day.
        sentence, day, featured, reset = st.columns([6, 1.6, 1.3, 1], vertical_alignment="center")
        sentence.html(f'<p class="hv-replay-sentence">{viewing_sentence(clock)}</p>')
        day.date_input(
            "Replay date", key=_DAY_INPUT, min_value=C.YEAR_START, max_value=C.YEAR_END - timedelta(days=1),
            on_change=_store_input, args=(_DAY, _DAY_INPUT), format="YYYY-MM-DD", label_visibility="collapsed",
            help="Inspect any day in the saved synthetic hospital year.",
        )
        with featured.popover("Demo days", help="Jump to a featured replay date.", width="stretch"):
            for key, name in _DAY_NAMES.items():
                st.button(f"{name} · {C.DEMO_DAYS[key]:%b %d}", on_click=set_demo_day, args=(key,))
        reset.button("Reset", on_click=_reset_replay, icon=":material/refresh:", width="stretch",
                     help="Restore the starting day, time and highlights. Keep logged decisions.")
        # Row two: move through the day, then the demo shortcuts.
        earlier, timeline, later, controls_col = st.columns([0.8, 2.9, 0.8, 7.5], vertical_alignment="center")
        earlier.button("Earlier", key="replay_earlier", on_click=_shift_time, args=(-1,),
                       disabled=clock.time == time.min, help="Move back one replay interval.", width="stretch")
        timeline.slider(
            "Time of day", min_value=time.min, max_value=day_end, step=step, format="HH:mm",
            key=_TIME_INPUT, on_change=_store_input, args=(_TIME, _TIME_INPUT), label_visibility="collapsed",
            help=f"Choose the time of day to inspect, in {C.SCORE_REFRESH_MIN}-minute steps.",
        )
        later.button("Later", key="replay_later", on_click=_shift_time, args=(1,),
                     disabled=clock.time >= day_end, help="Move forward one replay interval.", width="stretch")
        controls = controls_col.container(horizontal=True, vertical_alignment="center", gap="small")
        for label, moment in STORY_JUMPS:
            controls.button(f"{moment:%H:%M} {label.lower()}", on_click=set_demo_time, args=(moment,),
                            help=f"Jump to the {label.lower()} moment in the demo.")
        controls.checkbox(
            "Highlight demo patients", key=_TOUR_INPUT, on_change=_store_input,
            args=(_TOUR, _TOUR_INPUT),
        )
        count = len(state.get(_ACTIONS, ()))
        log_label = f"{count} decision{'' if count == 1 else 's'} logged"
        log_help = "Open the decision log in Fairness and Oversight."
        if on_oversight:
            controls.button(log_label, key="replay_log", help=log_help, on_click=_show_decision_log)
        else:
            controls.page_link(NAV.OVERSIGHT.path, label=log_label, help=log_help, query_params=NAV.DECISION_LOG_PARAMS)
    return clock


def viewing_sentence(clock: DemoClock) -> str:
    """The replay moment as a sentence a presenter can read aloud."""
    named = {d: _DAY_NAMES[k].split()[0].lower() for k, d in C.DEMO_DAYS.items()}
    kind = f", the {named[clock.day]} demo day" if clock.day in named else ""
    return (f"You are viewing <strong>{clock.day:%A, %b %-d, %Y} at {clock.time:%H:%M}</strong>{kind}, "
            "in the synthetic hospital replay.")


def start_guided_tour(hour: int | None = None) -> None:
    """Open the same busy Monday replay each time the team starts the demo."""
    set_demo_day("busy")
    st.session_state[_TOUR] = True
    set_demo_time(time(hour) if hour is not None else _DEFAULT_TIME)
    st.session_state.pop("halvian_team_step", None)


_TOUR_STEPS = {
    "admission": ("Bed manager · Review the admission flag",
                  "Check why this patient was flagged, then review the draft bed request."),
    "discharge": ("Rounds team · Clear a discharge task",
                  "Read the note and decide whether to act on the transport barrier."),
    "forecast": ("Charge nurse · Check when a bed could open",
                 "Use the forecast for the same unit to plan for the waiting patient."),
}
_TOUR_NEXT = {
    "admission": (NAV.DISCHARGE, "Continue to discharge readiness"),
    "discharge": (NAV.BED_FORECAST, "Continue to the bed forecast"),
    "forecast": (NAV.OVERSIGHT, "Finish with the decision log and fairness check"),
}


def tour_callout(step: Literal["admission", "discharge", "forecast"], details: str = "") -> None:
    """Show the relevant staff decision and a link to the next tour view."""
    if tour_active():
        title, instructions = _TOUR_STEPS[step]
        spec, label = _TOUR_NEXT[step]
        with st.container(border=True):
            st.markdown(f"**{title}**")
            st.markdown(details or instructions)
            st.page_link(spec.path, label=label, icon=":material/arrow_forward:")
