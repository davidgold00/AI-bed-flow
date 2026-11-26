"""Inspect the published range for any of the saved scenarios."""

import streamlit as st

from halvian.ui.results import EMPTY_RESULTS, load_impact_ranges, scenario_sentence, show_outcomes

results = load_impact_ranges()
if results is None:
    st.title("The scenarios are awaiting publication")
    st.caption(EMPTY_RESULTS)
    st.stop()

scenarios = {scenario["name"]: scenario for scenario in results["scenarios"]}
picked = st.segmented_control("Compare saved scenarios", list(scenarios),
                              default="Expected" if "Expected" in scenarios else next(iter(scenarios)), required=True)
scenario = scenarios[picked]
st.caption("Estimates from synthetic patients")
st.title(scenario_sentence(scenario, results["break_even"]["minutes_per_admission"]))
st.markdown(scenario["settings"])
with st.container(border=True):
    show_outcomes(scenario)
st.caption("A negative change means a shorter wait or fewer walkouts. Dollar ranges value freed room time.")
with st.expander("How we estimated this"):
    st.write(results["break_even"]["explanation"])
    st.write("The estimates use saved synthetic scenarios. Use the scenario selector to compare their assumptions.")
st.caption(f"{results['caveat']} {results['least_certain']}")
