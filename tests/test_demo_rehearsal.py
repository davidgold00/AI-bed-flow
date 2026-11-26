"""Rehearse the recording sequence and time the dashboard and results routes."""

from pathlib import Path
from time import perf_counter

import pytest
from _ui import kpi_value
from streamlit.testing.v1 import AppTest

from halvian import config
from halvian.data.live import tour_patients
from halvian.ui import navigation as NAV
from halvian.ui import note_reader
from halvian.ui.results import break_even_sentence, load_impact_ranges

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"
PAGE_LIMIT_SECONDS = 3  # Presentation rehearsal requirement
RESULTS = ROOT / "results_app.py"
ROUTES = [
    *((APP, spec.title, spec.path if spec is not NAV.OVERVIEW else None) for spec in NAV.ALL_PAGES),
    (RESULTS, "Downstream impact", None),
    (RESULTS, "Impact simulator", "results/simulator.py"),
    (RESULTS, "Requirements check", "results/requirements.py"),
    (RESULTS, "Data and methods", "results/methods.py"),
]


def run_without_exceptions(element, label):
    app = element.run()
    assert not app.exception, f"{label}: {[item.message for item in app.exception]}"
    return app


def press(app, label):
    button = next((item for item in app.button if item.label == label), None)
    assert button is not None, f"Missing walkthrough button: {label}"
    return run_without_exceptions(button.click(), label)


def visible_markdown(app):
    return "\n".join(item.value for item in app.markdown)


@pytest.fixture(scope="module")
def rehearsed_demo():
    app = run_without_exceptions(AppTest.from_file(APP), "Overview")
    assert app.title

    assert app.button(key="header_start_demo").label == "Start the guided demo"
    app = run_without_exceptions(app.button(key="overview_start_demo").click(), "Start the guided demo")
    assert app.title[0].value == "Guided demo"
    tour = tour_patients(config.DEMO_DAYS["busy"])
    assert tour["ed_patient"]["visit_id"] in visible_markdown(app)
    app = press(app, "Approve request")
    assert any("Request approved for preparation." in item.proto.body for item in app.get("html"))

    app = press(app, "Next: discharge task")
    discharge_text = visible_markdown(app)
    assert any("needs wheelchair van" in item.proto.body for item in app.get("html"))
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(note_reader, "analyze", lambda text: (note_reader._rules(text), {}))
        app = press(app, "Read this note")
    assert any("Evidence: " in item.value for item in app.caption)
    app = press(app, "Record transport as arranged")
    assert "Estimated chance of leaving within 24 hours" in visible_markdown(app)
    assert any("Transport task recorded as arranged." in item.proto.body for item in app.get("html"))

    app = press(app, "Next: bed forecast")
    assert "The recorded transport task makes a small change" in visible_markdown(app)
    assert kpi_value(app, "Net beds before the task") and kpi_value(app, "Net beds after the task")
    assert any("see the decisions" in link.proto.label for link in app.get("page_link"))

    app.switch_page(NAV.OVERSIGHT.path)
    app.query_params.update(NAV.DECISION_LOG_PARAMS)
    app = run_without_exceptions(app, NAV.OVERSIGHT.title)
    assert app.session_state[NAV.OVERSIGHT_TAB_KEY] == NAV.DECISION_LOG_TITLE
    return app, discharge_text, tour["inpatient"]["stay_id"]


def test_demo_rehearsal(rehearsed_demo):
    result, _, _ = rehearsed_demo
    assert result.title[0].value == NAV.OVERSIGHT.title
    log = result.session_state["halvian_actions"]
    tour = tour_patients(config.DEMO_DAYS["busy"])
    assert [(entry.role, entry.decision) for entry in log] == [
        ("Bed manager", "approve"), (config.BARRIER_OWNER["transport"], "approve"),
    ]
    assert tour["ed_patient"]["visit_id"] in log[0].recommendation_id
    assert tour["inpatient"]["stay_id"] in log[1].recommendation_id
    assert kpi_value(result, "Staff decisions") == str(len(log))



def test_demo_closes_on_published_impact(rehearsed_demo):
    app = run_without_exceptions(AppTest.from_file(APP), "Overview")
    app.switch_page(NAV.IMPACT.path)
    results_view = run_without_exceptions(app, NAV.IMPACT.title)
    if estimates := load_impact_ranges():
        assert results_view.title[0].value == break_even_sentence(estimates)
        assert results_view.get("plotly_chart")
    else:
        assert "awaiting publication" in results_view.title[0].value


def test_discharge_step_shows_inpatient_id(rehearsed_demo):
    _, discharge_text, stay_id = rehearsed_demo
    assert stay_id in discharge_text


@pytest.mark.parametrize(("entry", "label", "page"), ROUTES, ids=[label for _, label, _ in ROUTES])
def test_demo_page_load_time(entry, label, page):
    app = AppTest.from_file(entry, default_timeout=15)
    if page:
        app.switch_page(page)
    start = perf_counter()
    try:
        result = run_without_exceptions(app, label)
    except RuntimeError as error:
        if "timed out" in str(error).lower():
            pytest.fail(f"{label} timed out and exceeded the {PAGE_LIMIT_SECONDS}s rehearsal limit: {error}")
        raise
    elapsed = perf_counter() - start
    assert result.title, f"Expected to render {label} via {page}"
    if (estimates := load_impact_ranges()) and label == NAV.OVERVIEW.title:
        assert any(break_even_sentence(estimates) in item.proto.body for item in result.get("html"))
    if estimates and label == NAV.IMPACT.title:
        assert result.title[0].value == break_even_sentence(estimates)
    print(f"{label}: {elapsed:.2f}s")
    assert elapsed <= PAGE_LIMIT_SECONDS, (
        f"{label} took {elapsed:.2f}s, above the {PAGE_LIMIT_SECONDS}s rehearsal limit"
    )
