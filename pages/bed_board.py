"""Live Bed Board: every ED space and inpatient bed at the replay time, in place of the whiteboard."""

from html import escape

import plotly.graph_objects as go
import streamlit as st

from halvian import config as C
from halvian.data import live as L
from halvian.ui import navigation as NAV
from halvian.ui.components import number_column, page_header
from halvian.ui.design import capped_table, kpi_row, section_heading, status_tag
from halvian.ui.story import impact_now
from halvian.ui.theme import PALETTE, PLOTLY_TEMPLATE

clock = page_header(
    NAV.BED_BOARD,
    how="Move the replay bar to change the snapshot. A boarding patient has been admitted but still holds an ED "
        "space. A clean, empty bed is ready now. Expected openings use estimated discharge and cleaning times.",
)
t = clock.minutes_from_start
overrides = st.session_state.get("halvian_dc_overrides", {})
snap = L.ed_snapshot(t)
board = L.room_board(t)
units = L.unit_board(t, overrides)
now = L.clock_label(t)

boarders = int((board.status == "Boarding").sum())
waiting = int((snap.status == "Waiting").sum())
clean = int(units.clean_free.sum())
cleaning = int(units.cleaning.sum())

# ------------------------------------------------------------------ headline numbers
kpi_row([
    ("ED spaces held by admitted patients", f"{boarders} of {C.ED_TOTAL_SPACES}", "Waiting for an inpatient bed"),
    ("Patients waiting for an ED space", f"{waiting}", f"{C.WAITING_ROOM_SEATS} waiting-room seats"),
    ("Clean, empty inpatient beds", f"{clean}", "Ready for a patient now"),
    ("Inpatient beds being cleaned", f"{cleaning}", "Vacated, not yet ready"),
])
short = units[units.queue > units.clean_free]
impact_now(f"At {now}, {', '.join(short.index)} {'has' if len(short) == 1 else 'have'} more patients waiting than "
           "clean beds." if len(short) else f"At {now}, every unit has enough clean beds for its queue.")
if waiting > C.WAITING_ROOM_SEATS:
    status_tag("watch", f"{waiting} people are waiting for {C.WAITING_ROOM_SEATS} waiting-room seats.")

# ------------------------------------------------------------------ ED spaces
section_heading("Who is in each ED space", sub=f"{L.boarding_hours_today(t):,.0f} ED room-hours held by admitted "
                                                "patients since midnight.")
TILE = {"Empty": "empty", "In treatment": "treatment", "Discharging": "opening", "Boarding": "boarding",
        "Closed": "cleaning"}
st.html("<p>" + " ".join(f'<span class="hv-swatch hv-tile--{cls}" aria-hidden="true"></span>{escape(name)}&ensp;'
                         for name, cls in TILE.items()) + "</p>")
for space, label in C.ED_SPACE_LABELS.items():
    sub = board[board.space == space]
    used = int(sub.status.isin(["In treatment", "Boarding", "Discharging"]).sum())
    st.markdown(f"**{label}** · {used} of {len(sub)} in use")
    grid = st.container(horizontal=True, gap="small")
    for r in sub.itertuples():
        vid, detail = (x if isinstance(x, str) else "" for x in (r.visit_id, r.detail))
        grid.html(f'<div class="hv-tile hv-tile--{TILE[r.status]}" title="{escape(vid)}">'
                  f"<b>{escape(r.room)}</b><span>{escape(r.status)}</span><span>{escape(detail)}</span></div>",
                  width=112)

# ------------------------------------------------------------------ inpatient units
most_free = units.clean_free.idxmax()
section_heading(f"{most_free} has the most clean beds ({units.clean_free.max()})")
order = list(C.UNIT_NAMES)[::-1]
states = [("occupied", "Occupied", PALETTE["blue"]), ("assigned", "Bed assigned, patient on the way", PALETTE["teal"]),
          ("cleaning", "Being cleaned", PALETTE["sky"]), ("clean_free", "Clean and empty", PALETTE["line"])]
fig = go.Figure()
for col, name, color in states:
    vals = units.loc[order, col]
    fig.add_bar(y=order, x=vals, name=name, orientation="h", marker={"color": color},
                text=[str(v) if v >= 3 else "" for v in vals], textposition="inside",
                insidetextfont={"color": PALETTE["white"] if col == "occupied" else PALETTE["ink"]},
                hovertemplate="%{y}: %{x} " + name.lower() + "<extra></extra>")
fig.update_layout(template=PLOTLY_TEMPLATE, barmode="stack", height=330, margin={"l": 10, "r": 10, "t": 10, "b": 10},
                  legend={"orientation": "h", "y": -0.22, "x": 0, "yanchor": "top"}, xaxis_title="Beds")
st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
tbl = units.reset_index()[["unit", "beds", "occupied", "assigned", "cleaning", "clean_free", "queue", "expected_ready_4h"]]
capped_table(tbl, key="units", column_config={
    "unit": "Unit", "beds": number_column("Beds"), "occupied": number_column("Occupied"),
    "assigned": number_column("Bed assigned"), "cleaning": number_column("Being cleaned"),
    "clean_free": number_column("Clean and empty"), "queue": number_column("Waiting for a bed"),
    "expected_ready_4h": number_column("Ready within 4 h (estimate)", decimals=1),
})
if overrides:
    st.caption("Ready-within-4-hours counts include the discharge tasks staff recorded.")
st.page_link(NAV.BED_FORECAST.path, label="Plan ahead in Bed Forecast", icon=NAV.BED_FORECAST.icon)

# ------------------------------------------------------------------ the day at a glance
series = L.day_series(clock.day)
peak = series.loc[series.boarders.idxmax()]
low = series.loc[series.open_beds.idxmin()]
hour_now = (t - L.day_start(clock.day)) / 60
section_heading(f"Boarding peaks around {int(peak.hour):02d}:00, when clean beds are scarce",
                sub="Discharges cluster in the early afternoon while ED admissions build into the evening. "
                    "The vertical line marks the replay time.")
g1, g2 = st.columns(2)
with g1:
    f1 = go.Figure()
    f1.add_scatter(x=series.hour, y=series.boarders, mode="lines+markers", name="Admitted patients in ED spaces",
                   line={"color": PALETTE["vermillion"], "width": 2}, marker={"size": 6})
    f1.add_scatter(x=series.hour, y=series.waiting, mode="lines", name="Waiting for an ED space",
                   line={"color": PALETTE["blue"], "width": 2, "dash": "dot"})
    f1.add_vline(x=hour_now, line={"color": PALETTE["muted"], "width": 1})
    f1.update_layout(template=PLOTLY_TEMPLATE, height=300, margin={"l": 10, "r": 10, "t": 50, "b": 10},
                     title=f"Boarders peak at {int(peak.boarders)} around {int(peak.hour):02d}:00",
                     xaxis={"title": "Hour of day", "dtick": 3}, yaxis_title="Patients",
                     legend={"orientation": "h", "y": -0.25}, hovermode="x unified")
    st.plotly_chart(f1, width="stretch", config={"displayModeBar": False})
with g2:
    f2 = go.Figure()
    f2.add_scatter(x=series.hour, y=series.open_beds, mode="lines+markers", name="Clean, empty beds",
                   line={"color": PALETTE["teal"], "width": 2}, marker={"size": 6})
    f2.add_vline(x=hour_now, line={"color": PALETTE["muted"], "width": 1})
    f2.update_layout(template=PLOTLY_TEMPLATE, height=300, margin={"l": 10, "r": 10, "t": 50, "b": 10},
                     title=f"Clean beds are fewest around {int(low.hour):02d}:00 ({int(low.open_beds)} hospital-wide)",
                     xaxis={"title": "Hour of day", "dtick": 3}, yaxis_title="Beds", hovermode="x unified")
    st.plotly_chart(f2, width="stretch", config={"displayModeBar": False})
