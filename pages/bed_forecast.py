"""Bed Forecast: expected usable beds by unit, matched against expected ED admissions."""

import plotly.graph_objects as go
import streamlit as st

from halvian import config as C
from halvian.data import live as L
from halvian.models.forecast import HORIZONS_H
from halvian.ui import navigation as NAV
from halvian.ui.components import number_column, page_header
from halvian.ui.design import kpi_row, section_heading, status_tag
from halvian.ui.session import latest_action, record_action, tour_active, tour_callout
from halvian.ui.story import impact_now
from halvian.ui.theme import PALETTE, PLOTLY_TEMPLATE

PAGE = "Bed Forecast"
FORECAST_REASONS = [
    "Beds closed or blocked",
    "A planned discharge fell through",
    "Extra discharges are confirmed",
    "Surge beds opened",
    "Other",
]

clock = page_header(
    NAV.BED_FORECAST,
    how="Usable beds start from clean beds now, add expected discharges and cleaning, and subtract patients already "
        "waiting plus expected ED, direct and surgical admissions. The 80% range shows the uncertainty: in four of "
        "five similar past moments the real number fell inside it. The charge nurse confirms the estimate for "
        "planning or overrides it with a reason.",
)
t = clock.minutes_from_start
overrides = st.session_state.get("halvian_dc_overrides", {})
tour = L.tour_patients(clock.day) if tour_active() else {}
tp, tip = tour.get("ed_patient"), tour.get("inpatient")
if tp and tip:
    tour_callout("forecast", f"{tp['visit_id']} is likely headed to **{tp['likely_unit']}**. "
                 + ("Your transport task from rounds is included below." if tip["note_id"] in overrides
                    else "Record the transport task on Discharge Readiness to see the forecast change."))

horizon = st.segmented_control("Look ahead", HORIZONS_H, default=HORIZONS_H[1],
                               format_func=lambda h: f"{h} hours", required=True)
fc = L.forecast_at(t, overrides)
base = L.forecast_at(t) if overrides else fc
sel = fc[fc.horizon_h == horizon].set_index("unit")
target = L.clock_label(t + horizon * 60)
focus_unit = tp["likely_unit"] if (tp and tour_active()) else sel.expected_net.idxmin()


def _decide(rec_id: str, decision: str, reason_key: str | None = None, beds_key: str | None = None) -> None:
    reason = st.session_state.get(reason_key, "") if reason_key else ""
    if beds_key:
        reason = f"Expects {st.session_state[beds_key]:+d} usable beds. {reason}"
    record_action(rec_id, decision, page=PAGE, role="Charge nurse", clock=clock, reason=reason)


def staff_view(unit: str):
    """The charge nurse's latest decision on this unit's forecast at this moment and horizon."""
    return latest_action(f"forecast|{clock.day}|{L.clock_label(t)}|{horizon}h|{unit}")


# ------------------------------------------------------------------ headline numbers
items = []
for u in C.UNIT_NAMES:
    v, a = sel.loc[u], staff_view(u)
    note = (f"Charge nurse: {a.reason.split('.')[0].replace('Expects ', '')}" if a and a.decision == "override"
            else "Confirmed by the charge nurse" if a else f"Range {v.low80:+.0f} to {v.high80:+.0f}")
    items.append((u, f"{v.expected_net:+.0f}", note))
kpi_row(items)
st.caption(f"Expected usable beds by {target}. A negative number means more patients than beds.")
short_now = sel[sel.expected_net <= -0.5]
impact_now(f"**{', '.join(short_now.index)}** may have more patients than usable beds by {target}: time to plan "
           "placements and cleaning now." if len(short_now) else
           "No unit needs extra placements or cleaning planned right now. Confirm each bed before assigning it.")
if overrides:
    delta = sel.expected_net - base[base.horizon_h == horizon].set_index("unit").expected_net
    changed = delta[delta.abs() > 0.05]
    if len(changed):
        st.caption("Includes the discharge tasks staff recorded: "
                   + ", ".join(f"{u} {v:+.1f} beds" for u, v in changed.items()) + ".")

# ------------------------------------------------------------------ chart
order = list(C.UNIT_NAMES)[::-1]
s = sel.loc[order]
short_units = [u for u in C.UNIT_NAMES if sel.loc[u, "expected_net"] < -0.5]
section_heading(f"{', '.join(short_units)} may still be short of beds by {target}" if short_units
                else f"Every unit is expected to have usable beds by {target}",
                sub="Dot: expected usable beds. Bar: 80% range. Tick: usable now.")
fig = go.Figure()
fig.add_scatter(x=s.expected_net, y=order, mode="markers", marker={"size": 11, "color": PALETTE["blue"]},
                error_x={"type": "data", "symmetric": False, "array": s.high80 - s.expected_net,
                         "arrayminus": s.expected_net - s.low80, "color": PALETTE["muted"], "thickness": 2},
                name="Expected usable beds",
                customdata=list(zip(s.low80, s.high80, s.net_now, strict=True)),
                hovertemplate="%{y}: %{x:+.1f} usable beds (80% range %{customdata[0]:+.1f} to "
                              "%{customdata[1]:+.1f}); now %{customdata[2]:+d}<extra></extra>")
fig.add_scatter(x=s.net_now, y=order, mode="markers", marker={"size": 9, "symbol": "line-ns-open",
                "color": PALETTE["ink"], "line": {"width": 2}}, name="Now",
                hovertemplate="%{y}: %{x:+d} usable beds now<extra></extra>")
fig.add_vline(x=0, line={"color": PALETTE["ink"], "width": 1})
fig.update_layout(template=PLOTLY_TEMPLATE, height=340, margin={"l": 10, "r": 10, "t": 10, "b": 10},
                  xaxis_title="Usable beds (negative: patients still waiting)",
                  legend={"orientation": "h", "y": -0.25, "x": 0, "yanchor": "top"})
st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

comp = sel.reset_index()
comp["freeing"] = comp.beds_ready_from_cleaning + comp.expected_discharges_ready
comp["ed_demand"] = (comp.expected_requests_admitted_waiting + comp.expected_requests_ed_undecided
                     + comp.expected_requests_new_arrivals)
comp["range"] = [f"{a:+.0f} to {b:+.0f}" for a, b in zip(comp.low80, comp.high80, strict=True)]
with st.expander("Where each number comes from"):
    st.dataframe(comp[["unit", "net_now", "freeing", "ed_demand", "expected_requests_direct_elective",
                       "expected_net", "range"]], hide_index=True, width="stretch", column_config={
        "unit": "Unit", "net_now": number_column("Usable now"),
        "freeing": number_column("Beds freeing up", decimals=1),
        "ed_demand": number_column("Expected ED admissions", decimals=1),
        "expected_requests_direct_elective": number_column("Direct and surgical admissions", decimals=1),
        "expected_net": number_column(f"Usable by {target}", decimals=1), "range": "80% range"})

# ------------------------------------------------------------------ charge nurse decision
section_heading("Confirm or correct the forecast", sub="The charge nurse knows things the model does not, such as "
                                                       "a closed bed or a discharge that fell through.")
u_col, b1, b2 = st.columns([2, 1.3, 1], vertical_alignment="bottom")
pick = u_col.selectbox("Unit", list(C.UNIT_NAMES), index=list(C.UNIT_NAMES).index(focus_unit), key="fc_unit")
rec = f"forecast|{clock.day}|{L.clock_label(t)}|{horizon}h|{pick}"
current = staff_view(pick)
b1.button(f"Confirm {pick} forecast", key=f"ap_{rec}", on_click=_decide, args=(rec, "approve"), type="primary",
          width="stretch")
with b2.popover("Override", width="stretch"):
    st.number_input("Usable beds you expect", value=int(round(sel.loc[pick].expected_net)), step=1,
                    key=f"beds_{rec}")
    st.selectbox("Reason", FORECAST_REASONS, key=f"rs_{rec}")
    st.button("Confirm override", key=f"ov_{rec}", on_click=_decide,
              args=(rec, "override", f"rs_{rec}", f"beds_{rec}"))
if current and current.decision == "approve":
    status_tag("on-track", f"Confirmed: {pick} {sel.loc[pick].expected_net:+.0f} usable beds by {target}.")
elif current:
    status_tag("watch", f"Overridden by the charge nurse. {current.reason}")
