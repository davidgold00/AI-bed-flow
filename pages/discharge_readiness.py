"""Morning rounds, discharge barriers and staff decisions."""

from datetime import time

import pandas as pd
import streamlit as st

from halvian import config as C
from halvian.data import live as L
from halvian.ui import navigation as NAV
from halvian.ui.components import number_column, page_header
from halvian.ui.design import callout, capped_table, card, kpi_row, section_heading, status_tag
from halvian.ui.discharge_actions import (
    OVERRIDES,
    REASONS,
    discharge_id,
    refresh_discharge_estimate,
    rounds_at,
)
from halvian.ui.note_reader import show_saved_note, try_note_reader
from halvian.ui.session import DemoClock, latest_action, record_action, tour_active, tour_callout
from halvian.ui.story import impact_now

clock = page_header(
    NAV.DISCHARGE,
    how="At 07:00 rounds a model estimates each inpatient's chance of going home within 24 hours. The AI note reader "
        "(a local language model with a rule-based backup) highlights open tasks in the morning note, such as "
        "transport, equipment or home care, and quotes its evidence word for word. Staff record a task as arranged or "
        "override it with a reason; the attending physician decides whether the patient leaves.",
)
rounds_clock = DemoClock(clock.day, time(L.ROUNDS_HOUR))
tip = L.tour_patients(clock.day).get("inpatient") if tour_active() else None
default_unit = tip["unit"] if (tip and tour_active()) else "All units"
options = ["All units", *C.UNIT_NAMES]
unit = st.selectbox("Unit", options, index=options.index(default_unit))
rl = rounds_at(clock.day, unit)
overrides = st.session_state.setdefault(OVERRIDES, {})

if rl.empty:
    callout("No inpatients were on this unit at rounds. Choose another unit or day.")
    st.stop()

p_now = rl.apply(lambda row: overrides.get(row.note_id, row.p_discharge_24h), axis=1)
with_barrier = rl[rl.findings.map(bool)]
kpi_row([
    (f"Inpatients at {rounds_clock.time:%H:%M} rounds", f"{len(rl)}", "unit" if unit != "All units" else "all units"),
    ("Likely to go home within 24 h", f"{int((p_now >= C.DISCHARGE_LIST_THRESHOLD).sum())}",
     f"Chance at or above {C.DISCHARGE_LIST_THRESHOLD:.0%}"),
    ("Notes with an open task", f"{len(with_barrier)}", "Found by the note reader"),
    ("Expected discharges", f"{p_now.sum():.0f}", "Sum of the 24-hour estimates"),
])
gain = float(p_now.sum() - rl.p_discharge_24h.sum())
where = "all units" if unit == "All units" else unit
note = f"**{len(with_barrier)} patients** on {where} have an open task in their note that could hold up discharge."
if gain > 0.005:
    note += f" Tasks staff recorded add **{gain:+.1f} expected discharges**."
impact_now(note)

section_heading("Rounds list", sub="Highest chance of going home first.")
table = rl.assign(
    chance=(100 * p_now).round(), barriers=rl.findings.map(lambda fs: ", ".join(C.BARRIER_LABELS[f["barrier_type"]] for f in fs)),
    days=rl.los_so_far_h / 24, reasons_text=rl.reasons.map(". ".join),
).sort_values("chance", ascending=False)
capped_table(table[["stay_id", "unit", "days", "dx_group", "chance", "barriers", "reasons_text"]], key="rounds",
             column_config={
                 "stay_id": "Stay", "unit": "Unit", "days": number_column("Days in hospital", decimals=1),
                 "dx_group": "Diagnosis group",
                 "chance": st.column_config.ProgressColumn("Chance of going home within 24 h", format="%d%%",
                                                           min_value=0, max_value=100),
                 "barriers": "Open task in note", "reasons_text": st.column_config.TextColumn("Reasons", width="large"),
             })


def decide_discharge(row, barrier: str, decision: str, reason_key: str = "") -> None:
    reason = st.session_state.get(reason_key, "") if reason_key else ""
    record_action(discharge_id(row.stay_id, barrier), decision, page=NAV.DISCHARGE.title,
                  role=C.BARRIER_OWNER.get(barrier, "Nurse"), clock=rounds_clock, reason=reason)
    refresh_discharge_estimate(row)


section_heading("Clear a discharge task")
focus = rl[(p_now >= C.DISCHARGE_LIST_THRESHOLD) | rl.findings.map(bool)]
if tip and tour_active():
    focus = pd.concat([rl[rl.stay_id == tip["stay_id"]], focus[focus.stay_id != tip["stay_id"]]])
notes = dict(zip(rl.stay_id, rl.note, strict=True))
if focus.empty:
    callout("No patient on this unit is likely to go home or has an open task.")
else:
    visit = st.selectbox("Patient", list(focus.stay_id))
    row = focus.loc[focus.stay_id == visit].iloc[0]
    p_show = overrides.get(row.note_id, row.p_discharge_24h)
    with card(key="discharge_task"):
        evidence, actions = st.columns([1.6, 1])
        with evidence:
            st.markdown(f"**{row.stay_id} · {row.unit} · {p_show:.0%} chance of going home within 24 h**")
            st.caption("Why: " + ". ".join(row.reasons) + ".")
            show_saved_note(row.note, row.findings)
        with actions:
            choices = {f["barrier_type"]: f for f in row.findings}
            barrier = st.selectbox("Task", list(choices), format_func=C.BARRIER_LABELS.__getitem__,
                                   key=f"barrier_{row.note_id}") if choices else "prep"
            label = C.BARRIER_LABELS[barrier].lower() if choices else "discharge teaching"
            owner = C.BARRIER_OWNER.get(barrier, "Nurse")
            st.caption(f"Owner: {owner}" + (f" · match strength {choices[barrier]['confidence']:.0%}" if choices else ""))
            rec = discharge_id(row.stay_id, barrier)
            prior = latest_action(rec)
            if prior:
                status_tag("on-track" if prior.decision == "approve" else "watch",
                           f"{label.capitalize()} recorded." if prior.decision == "approve" else prior.reason)
            buttons = st.container(horizontal=True)
            buttons.button(f"Record {label} as arranged", type="primary", key=f"approve_{rec}",
                           on_click=decide_discharge, args=(row, barrier, "approve"))
            with buttons.popover("Override"):
                reason_key = f"reason_{rec}"
                st.selectbox("Reason", REASONS, key=reason_key)
                st.button("Confirm override", key=f"override_{rec}", on_click=decide_discharge,
                          args=(row, barrier, "override", reason_key))
            st.caption("The attending physician decides on discharge.")
    notes = {row.stay_id: row.note, **notes}
tour_callout("discharge")
try_note_reader(notes, rounds_clock)
