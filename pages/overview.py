"""The Halvian case, staff workflow and published impact estimates."""

from html import escape

import streamlit as st

from halvian import config as C
from halvian.ui import navigation as NAV
from halvian.ui.chrome import start_demo
from halvian.ui.components import callout, card, glossary, kpi, section_eyebrow, section_heading
from halvian.ui.results import (
    EMPTY_RESULTS,
    break_even_sentence,
    load_impact_ranges,
    show_scenarios,
)
from halvian.ui.session import replay_controls
from halvian.ui.story import ORDER, STORIES, display_range

NAV.ensure_product_navigation()
with st.container(key="overview"):
    with st.container(key="overview_hero"):
        lead, baseline = st.columns([1.35, 1], gap="large", vertical_alignment="center")
        with lead:
            section_eyebrow("Patient flow and boarding")
            st.title("Get admitted patients to a bed sooner")
            st.write("Help staff prepare inpatient beds earlier and free emergency rooms for the patients still waiting.")
            actions = st.container(horizontal=True, vertical_alignment="center", key="overview_actions")
            if actions.button("Start the guided demo", type="primary", key="overview_start_demo", on_click=start_demo):
                st.switch_page(NAV.GUIDED_DEMO.path)
            actions.page_link(NAV.IMPACT.page(), label="See the results")
        with baseline, st.container(key="overview_baseline"):
            section_eyebrow("Halvian today")
            kpi("Median wait for an inpatient bed", f"{C.MEDIAN_BOARDING_H:g} hours",
                f"National benchmark · {display_range(C.NATIONAL['boarding_h'])} hours")

    with st.container(key="overview_benchmarks"):
        first, second, third = st.columns(3)
        with first:
            kpi("Median wait to see a provider", f"{C.MEDIAN_DOOR_TO_PROVIDER_MIN} min",
                f"National benchmark · {display_range(C.NATIONAL['door_to_provider_min'])} min")
        with second:
            kpi("Left before seeing a provider", f"{C.LWBS_RATE:.0%}",
                f"National benchmark · {display_range(C.NATIONAL['lwbs'], '{:.0%}')}")
        with third:
            kpi("Inpatient occupancy", f"{C.TARGET_OCCUPANCY:.0%}",
                f"About {C.TYPICAL_OPEN_BEDS} of {C.INPATIENT_BEDS} beds open")

    with st.container(key="overview_workflow"):
        section_eyebrow("How it works")
        section_heading("From early flags to usable beds")
        steps = (
            ("Flag likely admissions", "The bed manager reviews the suggested request before an admission decision."),
            ("Clear discharge barriers", "At rounds, staff review the note and act on tasks such as arranging transport."),
            ("Forecast usable beds", "The charge nurse reviews when beds may open and plans placements."),
        )
        for column, (title, description) in zip(st.columns(len(steps)), steps, strict=True):
            with column, card():
                st.markdown(f"### {title}")
                st.write(description)
        st.page_link(NAV.DISCHARGE.path, label="Try the Ollama note reader", icon=":material/description:",
                     query_params=NAV.NOTE_READER_PARAMS)

    with st.container(key="overview_parts"):
        section_eyebrow("What each part solves")
        st.header("Where staff act")
        with st.container(key="overview_map"):
            widths = [1.15, 1.1, 1.15, 1.65]
            labels = ("Problem", "Dashboard page", "Who uses it", "Staff action")
            for column, label in zip(st.columns(widths), labels, strict=True):
                column.html(f'<span class="hv-map-head">{label}</span>')
            for spec in (*ORDER, NAV.GUIDED_DEMO):
                problem, link, role, effect = st.columns(widths, vertical_alignment="center")
                story = STORIES[spec.url]
                problem.html(f"<strong>{escape(story.problem)}</strong>")
                link.page_link(spec.path, label=spec.title)
                role.html(f"<span>{escape(spec.role or 'Staff reviewing the tool')}</span>")
                effect.html(f"<span>{escape(story.chain[0])}</span>")

    with st.container(key="overview_impact"):
        section_eyebrow("Estimated impact")
        impact = load_impact_ranges()
        if impact is None:
            section_heading("The impact estimates are awaiting publication")
            st.caption(EMPTY_RESULTS)
        else:
            section_heading(break_even_sentence(impact))
            callout(impact["break_even"]["explanation"])
            with st.container(key="overview_scenarios"):
                show_scenarios(impact)
            st.caption(impact["caveat"])

    with st.container(key="overview_safeguards"):
        section_heading("What it never does")
        decisions, insurance, records = st.columns(3)
        decisions.markdown("**Make clinical or placement decisions.** Staff approve or override recommendations.")
        insurance.markdown("**Use insurance to predict.** It is used to audit model performance and patient outcomes.")
        records.markdown("**Use real patient records.** The replay and notes are synthetic.")
        case, definitions = st.columns(2)
        with case.expander("Outcome gaps in the case brief"):
            waits = C.DOOR_TO_PROVIDER_BY_PAYER_MIN
            st.caption(f"Median wait to see a provider is {waits[C.UNINSURED]} minutes for uninsured patients "
                       f"and {waits[C.COMMERCIAL]} minutes for commercially insured patients.")
        with definitions:
            glossary()
        with st.expander("Hospital replay settings"):
            st.caption("Choose the moment shown on the staff pages.")
            replay_controls()
