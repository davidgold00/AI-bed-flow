"""Follow an early bed request and a discharge task on the same unit."""

from datetime import time

import streamlit as st

from halvian import config as C
from halvian.data import live as L
from halvian.ui import navigation as NAV
from halvian.ui.components import page_header
from halvian.ui.design import callout, card, kpi, section_heading, status_tag
from halvian.ui.discharge_actions import OVERRIDES, REASONS, decide_discharge, discharge_id
from halvian.ui.note_reader import read_control
from halvian.ui.session import DemoClock, latest_action, record_action, set_demo_day, set_demo_time
from halvian.ui.story import STORIES

STEPS = ("Bed request", "Discharge task", "Bed forecast")
STEP_KEY = "halvian_team_step"
STEP_INPUT = "_halvian_team_step_input"


def go_to(step: str, ed_hour: int) -> None:
    st.session_state[STEP_KEY] = step
    set_demo_time(time(L.ROUNDS_HOUR if step == STEPS[1] else ed_hour))


def _sync_clock(ed_hour: int) -> None:
    go_to(st.session_state[STEP_INPUT], ed_hour)


def _record_demo_action(rec_id: str, decision: str, clock: DemoClock, role: str, reason: str = "") -> None:
    record_action(rec_id, decision, page=NAV.GUIDED_DEMO.title, role=role, clock=clock, reason=reason)


def bed_request(ed: dict, clock: DemoClock) -> None:
    rec_id = f"flag|{ed['visit_id']}"
    unit = ed["likely_unit"]
    section_heading(f"Step 1. Prepare a {unit} bed before the admission decision",
                    sub=STORIES[NAV.ADMISSION_FLAGS.url].downstream)
    with card(key="demo_bed_request"):
        st.markdown(f"**{ed['visit_id']}** · {ed['complaint'].replace('_', ' ')} · ESI {ed['esi']}")
        score, explanation = st.columns([1, 2], vertical_alignment="center")
        with score:
            kpi("Chance of admission", f"{ed['p']:.0%}", "From triage information only")
        with explanation:
            st.markdown("**Why this patient was flagged**")
            st.markdown("\n".join(f"- {reason}" for reason in ed["reasons"]))
    st.caption("The bed manager approves preparation. The clinician still decides whether to admit.")
    action = latest_action(rec_id)
    if action:
        status_tag("on-track" if action.decision == "approve" else "watch",
                   "Request approved for preparation." if action.decision == "approve" else action.reason)
    actions = st.container(horizontal=True)
    actions.button("Approve request", type="primary", on_click=_record_demo_action,
                   args=(rec_id, "approve", clock, "Bed manager"))
    with actions.popover("Override"):
        reason = st.selectbox("Reason", ("Already arranged", "Model is missing context", "Clinical team disagrees"))
        st.button("Confirm override", on_click=_record_demo_action,
                  args=(rec_id, "override", clock, "Bed manager", reason))
    actions.button("Next: discharge task", on_click=go_to, args=(STEPS[1], ed["hour"]),
                   icon=":material/arrow_forward:")


def discharge_task(inpatient: dict, clock: DemoClock) -> None:
    rows = L.rounds_list(clock.day, inpatient["unit"])
    row = rows.loc[rows.note_id == inpatient["note_id"]].iloc[0]
    barrier = inpatient["barriers"][0]
    owner = C.BARRIER_OWNER[barrier]
    label = C.BARRIER_LABELS[barrier].lower()
    rec_id = discharge_id(inpatient["stay_id"], barrier)
    overrides = st.session_state.setdefault(OVERRIDES, {})
    rounds_clock = DemoClock(clock.day, time(L.ROUNDS_HOUR))
    section_heading(f"Step 2. Clear a discharge task on {inpatient['unit']}",
                    sub=STORIES[NAV.DISCHARGE.url].downstream)
    st.markdown(f"**{inpatient['stay_id']}** · a different patient, already an inpatient on {inpatient['unit']} · "
                f"task owner: {owner}")
    st.caption("Highlights are saved from an earlier read. Read this note runs the local AI reader again now.")
    result = read_control(row.note, "guided", saved=row.findings)
    if result and result["status"] in {"llm", "fallback"}:
        st.caption("Transport actions update the estimate using the saved rounds record.")
    prior = latest_action(rec_id)
    if inpatient["note_id"] in overrides:
        st.markdown(f"Estimated chance of leaving within 24 hours: **{inpatient['p']:.0%} to "
                    f"{overrides[inpatient['note_id']]:.0%}**.")
    else:
        st.caption(f"Estimated chance of leaving within 24 hours: {inpatient['p']:.0%}.")
    if prior:
        status_tag("on-track" if prior.decision == "approve" else "watch",
                   f"{label.capitalize()} task recorded as arranged." if prior.decision == "approve" else prior.reason)
    st.caption(f"The {owner.lower()} handles the task. The attending makes the discharge decision.")
    buttons = st.container(horizontal=True)
    buttons.button(f"Record {label} as arranged", type="primary", on_click=decide_discharge,
                   args=(row, barrier, "approve", rounds_clock, NAV.GUIDED_DEMO.title))
    with buttons.popover("Override"):
        st.selectbox("Reason", REASONS, key="demo_discharge_reason")
        st.button("Confirm override", on_click=decide_discharge,
                  args=(row, barrier, "override", rounds_clock, NAV.GUIDED_DEMO.title, "demo_discharge_reason"))
    buttons.button("Next: bed forecast", icon=":material/arrow_forward:", on_click=go_to,
                   args=(STEPS[2], clock.time.hour))


def bed_forecast(ed: dict, inpatient: dict, clock: DemoClock) -> None:
    as_of = clock.minutes_from_start
    unit = ed["likely_unit"]
    baseline = L.forecast_at(as_of)
    horizon = baseline.horizon_h.min()
    original = baseline.loc[(baseline.unit == unit) & (baseline.horizon_h == horizon)].iloc[0]
    overrides = st.session_state.get(OVERRIDES, {})
    changed = inpatient["note_id"] in overrides
    if changed:
        after = L.forecast_at(as_of, {inpatient["note_id"]: overrides[inpatient["note_id"]]})
        estimate = after.loc[(after.unit == unit) & (after.horizon_h == horizon)].iloc[0]
    else:
        estimate = original

    when = L.clock_label(as_of + horizon * 60)
    section_heading(f"Step 3. Check usable beds on {unit} by {when}", sub=STORIES[NAV.BED_FORECAST.url].downstream)
    if changed:
        st.markdown("The recorded transport task makes a small change to the forecast:")
        before, after = st.columns(2)
        with before:
            kpi("Net beds before the task", f"{original.low80:+z.1f} to {original.high80:+z.1f}", "80% range")
        with after:
            kpi("Net beds after the task", f"{estimate.low80:+z.1f} to {estimate.high80:+z.1f}", "80% range")
    else:
        kpi("Net beds", f"{estimate.low80:+z.1f} to {estimate.high80:+z.1f}", "80% range")
    st.caption("A negative number means more patients than usable beds. Staff still confirm each bed before "
               "assigning it.")
    id_ = f"forecast|{clock.day}|{L.clock_label(as_of)}|{horizon}h|{unit}"
    prior = latest_action(id_)
    if prior:
        status_tag("on-track" if prior.decision == "approve" else "watch",
                   "Forecast confirmed for planning." if prior.decision == "approve" else prior.reason)
    buttons = st.container(horizontal=True)
    buttons.button("Approve forecast", type="primary", on_click=_record_demo_action,
                   args=(id_, "approve", clock, "Charge nurse"))
    with buttons.popover("Override"):
        issue = st.selectbox("Reason", ("Bed blocked", "Discharge delayed", "New unit information"))
        st.button("Confirm override", on_click=_record_demo_action,
                  args=(id_, "override", clock, "Charge nurse", issue))
    buttons.page_link(NAV.OVERSIGHT.path, label="Finish: see the decisions in the log",
                      icon=":material/arrow_forward:", query_params=NAV.DECISION_LOG_PARAMS)


selected = page_header(NAV.GUIDED_DEMO, how="Three steps on the busy Monday: approve an early bed request, clear a "
                       "discharge task for a different patient on the same unit, then see the bed forecast move. "
                       "Each step opens at its own time; the dashboard pages use the replay bar's time.")
try:
    tour = L.tour_patients(selected.day)
except FileNotFoundError:
    callout("The guided demo needs the synthetic data and models. Run scripts/generate_data.py and "
            "scripts/train_models.py.")
    st.stop()
if not (tour.get("ed_patient") and tour.get("inpatient")):
    callout("This day has no matching admission and discharge task for the walkthrough.")
    st.button("Use the busy Monday example", on_click=set_demo_day, args=("busy",))
    st.stop()

ed_patient, inpatient = tour["ed_patient"], tour["inpatient"]
clock = DemoClock(selected.day, time(ed_patient["hour"]))
if STEP_KEY not in st.session_state or st.session_state.get("guided_day") != selected.day:
    st.session_state["guided_day"] = selected.day
    go_to(STEPS[0], ed_patient["hour"])
    st.rerun()
st.session_state[STEP_INPUT] = st.session_state[STEP_KEY]
step = st.segmented_control(
    "Demo step", STEPS, required=True, key=STEP_INPUT, label_visibility="collapsed", wrap=True,
    on_change=_sync_clock, args=(ed_patient["hour"],),
)
step_time = time(L.ROUNDS_HOUR) if step == STEPS[1] else clock.time
if selected.time != step_time:
    st.caption(f"This guided step uses the {step_time:%H:%M} snapshot. "
               "The full dashboard pages use the time selected above.")
if step == STEPS[0]:
    bed_request(ed_patient, clock)
elif step == STEPS[1]:
    discharge_task(inpatient, clock)
else:
    bed_forecast(ed_patient, inpatient, clock)
with st.expander("Open the full dashboard pages"):
    st.caption("The replay bar carries the selected moment to the full dashboard.")
    for spec in (NAV.ADMISSION_FLAGS, NAV.DISCHARGE, NAV.BED_FORECAST):
        st.page_link(spec.path, label=spec.title, icon=spec.icon)
