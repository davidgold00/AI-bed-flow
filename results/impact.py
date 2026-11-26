"""Present the rounded comparison published by the simulation workstream."""

import streamlit as st

from halvian.ui.design import callout, card, kpi, section_heading, status_tag
from halvian.ui.results import (
    EMPTY_RESULTS,
    load_impact_ranges,
    range_text,
    show_break_even,
    show_outcomes,
    show_scenarios,
)

results = load_impact_ranges()
if results is None:
    st.title("The impact estimates are awaiting publication")
    st.caption(EMPTY_RESULTS)
    st.stop()

show_break_even(results)
show_scenarios(results)

section_heading("Where the minutes come from", sub="Each part alone, at today's settings. The parts overlap, so "
                                                     "they do not add up to the scenario totals.")
for column, part in zip(st.columns(len(results["parts"])), results["parts"], strict=True):
    with column:
        kpi(part["part"], f"{range_text(part['minutes_saved_per_admission'])} min", "saved per admitted patient")

section_heading("Patients wait less and fewer leave unseen",
                sub="A negative change means a shorter wait or fewer walkouts.")
for column, scenario in zip(st.columns(len(results["scenarios"])), results["scenarios"], strict=True):
    with column, card(key=f"outcomes_{scenario['name'].lower().replace(' ', '_')}"):
        st.markdown(f"**{scenario['name']}**")
        show_outcomes(scenario)

section_heading("No gap between patient groups widened", sub="Expected scenario, each group against Commercial. "
                                                             "Insurance is used only to check, never to predict.")
LEVEL = {"Narrowed": "on-track", "Flat": "watch", "Widened": "act"}
if any(item["verdict"] == "Widened" for item in results["equity"]):
    callout("At least one gap widened. The equity guardrail sends the tool for review.")
for item in results["equity"]:
    status_tag(LEVEL.get(item["verdict"], "watch"), f"{item['verdict']}: {item['gap']}")

section_heading("What the dashboard costs next to more staff",
                sub="Yearly cost at the case's rates. We do not estimate how much a staffing option would cut boarding.")
tool_cost = results["tool_cost"]
tool_low, tool_high = tool_cost["per_year_usd"]
options = [("Halvian Bed Flow", f"${tool_low / 1e3:,.0f}K to ${tool_high / 1e3:,.0f}K", tool_cost["note"])]
options.extend((option["option"], f"${option['annual_cost_usd'] / 1e3:,.0f}K", option["assumption"])
               for option in results["staffing_alternative"])
for column, (name, dollars, assumption) in zip(st.columns(len(options)), options, strict=True):
    with column:
        kpi(f"{name}, a year", dollars, assumption)

section_heading("Published evidence behind the estimates")
for reference in results["references"]:
    with card():
        st.markdown(f"**{reference['source']}**")
        if reference.get("finding"):
            st.caption(reference["finding"])
        if reference.get("url"):
            st.link_button("Read the source", reference["url"])

with st.expander("How we estimated this"):
    st.write("The same synthetic patients are replayed with and without the dashboard over a winter quarter, in three "
             "synthetic years. Each range is the spread across those years, rounded outward. Freed capacity is "
             "minutes saved x 13,600 admissions a year at the case's $350 per boarded room-hour.")
st.caption(f"{results['caveat']} {results['least_certain']}")
