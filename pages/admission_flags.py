"""ED Admission Flags: likely admissions, their reasons and the hourly bed request."""

from datetime import time

import streamlit as st

from halvian import config as C
from halvian.data import live as L
from halvian.ui import navigation as NAV
from halvian.ui.components import hours_column, number_column, page_header
from halvian.ui.design import callout, capped_table, card, kpi_row, section_heading, status_tag
from halvian.ui.session import (
    latest_action,
    record_action,
    set_demo_time,
    tour_active,
    tour_callout,
)
from halvian.ui.story import impact_now

OVERRIDE_REASONS = [
    "Not an admission clinically",
    "Already arranged by phone",
    "Model is missing context",
    "Transfer or patient preference",
    "Other",
]
PAGE = "ED Admission Flags"

clock = page_header(
    NAV.ADMISSION_FLAGS,
    how="A model scores each triaged patient's chance of admission from triage information only (never insurance). "
        "The alert threshold rises and falls with ED crowding. Once an hour, flagged patients are grouped into one "
        "bed request per likely unit. The bed manager approves preparation or overrides it with a reason; the "
        "clinician still decides whether to admit.",
)
t = clock.minutes_from_start
tour = L.tour_patients(clock.day) if tour_active() else {}
tp = tour.get("ed_patient")
q = L.ed_queue(t)
thr = L.threshold_now(t)
nb = L.next_batch(t)
flags = q[q.flagged] if len(q) else q

kpi_row([
    ("Awaiting an admission decision", f"{len(q)}", "Triaged, no disposition yet"),
    ("Flagged as likely admissions", f"{len(flags)}", "At or above the alert threshold"),
    ("Alert threshold now", f"{thr['threshold']:.0%}", f"Base {C.ALERT_THRESHOLD:.0%}, adjusted for crowding"),
    ("Next bed request", L.clock_label(nb), "Sent once an hour per unit"),
])


def _decide(rec_id: str, decision: str, role: str, reason_key: str | None = None) -> None:
    reason = st.session_state.get(reason_key, "") if reason_key else ""
    record_action(rec_id, decision, page=PAGE, role=role, clock=clock, reason=reason)


def request_controls(rec: str, label: str, *, primary: bool) -> None:
    a = latest_action(rec)
    if a:
        if a.decision == "approve":
            status_tag("on-track", f"Approved by the bed manager at {a.replay_time[-5:]}.")
        else:
            status_tag("watch", f"Overridden at {a.replay_time[-5:]}. {a.reason}.")
    controls = st.container(horizontal=True)
    controls.button(label, key=f"ap_{rec}", on_click=_decide, args=(rec, "approve", "Bed manager"),
                    type="primary" if primary else "secondary")
    with controls.popover("Override"):
        st.selectbox("Reason", OVERRIDE_REASONS, key=f"rs_{rec}")
        st.button("Confirm override", key=f"ov_{rec}", on_click=_decide,
                  args=(rec, "override", "Bed manager", f"rs_{rec}"))


overridden = {rid.split("|")[-1] for rid in [f"flag|{v}" for v in q.visit_id] if (a := latest_action(rid)) and
              a.decision == "override"} if len(q) else set()
req = L.batch_requests(q, excluded=overridden) if len(q) else L.batch_requests(q)
active = req[req.patients > 0]
if len(active):
    impact_now(f"The {L.clock_label(nb)} request lets the bed manager prepare **{int(active.beds_to_request.sum())} "
               f"beds** for **{int(active.patients.sum())} flagged patients** before anyone decides to admit them.")
elif len(flags):
    impact_now("Flagged patients join a request once the staff response time has passed.")
else:
    impact_now("No patient is above the threshold, so admissions follow the usual phone request.")

# ------------------------------------------------------------------ the queue
section_heading("Patients waiting for an admission decision",
                sub="Highest chance of admission first. The model never sees insurance.")
if len(q):
    table = q.sort_values("p_admit", ascending=False).assign(
        reasons_text=q.reasons.map("; ".join), complaint=q.chief_complaint.str.replace("_", " ").str.capitalize(),
        p_admit=(100 * q.p_admit).round())
    capped_table(
        table[["visit_id", "esi", "complaint", "age", "hours_in_ed", "p_admit", "flagged", "likely_unit", "reasons_text"]],
        key="ed_queue", column_config={
            "visit_id": "Visit", "esi": number_column("Triage level (ESI)"), "complaint": "Main complaint",
            "age": number_column("Age"), "hours_in_ed": hours_column("Time in ED"),
            "p_admit": st.column_config.ProgressColumn("Chance of admission", format="%d%%", min_value=0, max_value=100),
            "flagged": st.column_config.CheckboxColumn("Flagged"), "likely_unit": "Likely unit",
            "reasons_text": st.column_config.TextColumn("Top reasons", width="large"),
        })
else:
    callout("No triaged patient is waiting for an admission decision at this replay time.")

# ------------------------------------------------------------------ actions
section_heading(f"Approve the {L.clock_label(nb)} bed request")
if active.empty:
    callout("No flagged patient is ready for the next request. Move the replay time or check the patient flags below.")
else:
    focus_unit = tp["likely_unit"] if tp and tour_active() else None
    choices = list(active.unit)
    unit = st.selectbox("Unit", choices, index=choices.index(focus_unit) if focus_unit in choices else 0)
    row = active.loc[active.unit == unit].iloc[0]
    rec = f"batch|{clock.day}|{L.clock_label(nb)}|{unit}"
    with card(key="bed_request"):
        st.markdown(f"**Prepare {row.beds_to_request} {'bed' if row.beds_to_request == 1 else 'beds'} on {unit}**")
        st.caption(f"{row.expected_admissions:.1f} expected admissions among {row.patients} flagged patients: "
                   f"{', '.join(row.visit_ids)}.")
        request_controls(rec, "Approve request", primary=True)
    if overridden:
        st.caption(f"Left out after an override: {', '.join(sorted(overridden))}.")

with st.expander(f"Review one flagged patient ({len(flags)})"):
    if flags.empty:
        st.caption("No patient is above the alert threshold at this replay time.")
    else:
        choices = list(flags.visit_id)
        highlighted = tp["visit_id"] if tp and tour_active() else None
        visit = st.selectbox("Flagged patient", choices, index=choices.index(highlighted) if highlighted in choices else 0)
        row = flags.loc[flags.visit_id == visit].iloc[0]
        st.markdown(f"**{visit} · {row.p_admit:.0%} chance of admission**")
        st.caption(f"{row.chief_complaint.replace('_', ' ').capitalize()} · ESI {row.esi} · Age {row.age} · "
                   f"{row.hours_in_ed:.1f} h in the ED · likely {row.likely_unit}")
        st.markdown("**Why:** " + ". ".join(row.reasons) + ".")
        request_controls(f"flag|{visit}", "Approve early request", primary=False)

if tp:
    tour_callout("admission", f"Patient **{tp['visit_id']}** ({tp['complaint'].replace('_', ' ')}, ESI {tp['esi']}) "
                 f"is flagged at {tp['hour']:02d}:00 for a {tp['likely_unit']} bed. Approve the request above.")
    if tour_active() and clock.time != time(tp["hour"]):
        st.button(f"Go to {tp['hour']:02d}:00 for the tour", on_click=set_demo_time, args=(time(tp["hour"]),))
