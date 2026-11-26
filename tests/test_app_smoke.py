"""Open the app and every page in its menu, the way a user would."""

from pathlib import Path

import pytest
from _ui import kpi_value
from streamlit.testing.v1 import AppTest

from halvian import config as C
from halvian.data import live as L
from halvian.ui import navigation as NAV
from halvian.ui.results import break_even_sentence, load_impact_ranges
from halvian.ui.story import ORDER as STORY_PAGES
from halvian.ui.story import STORIES

ROOT = Path(__file__).resolve().parents[1]
APP = str(ROOT / "app.py")
DATA_FILES = (
    "ed_visits.parquet",
    "inpatient_stays.parquet",
    "inpatient_days.parquet",
    "notes.parquet",
    "census_hourly.parquet",
)
NEEDS_NOTHING = {NAV.OVERVIEW.path}


def _skip_without_artifacts(spec: NAV.PageSpec) -> None:
    if spec.path in NEEDS_NOTHING:
        return
    missing = [name for name in DATA_FILES if not (ROOT / "data" / name).is_file()]
    if missing:
        pytest.skip(f"Generate the synthetic data first. Missing: {', '.join(missing)}")
    if not (ROOT / "models" / "metrics.json").is_file():
        pytest.skip("Train the synthetic models to exercise this page.")


def _ok(app: AppTest) -> None:
    assert not app.exception, [item.message for item in app.exception]


def test_menu_lists_every_page_file():
    on_disk = {p.relative_to(ROOT).as_posix() for folder in ("pages", "results") for p in (ROOT / folder).glob("*.py")}
    assert on_disk == {spec.path for spec in NAV.ALL_PAGES}


def test_overview_states_the_problems_and_shows_the_clock():
    app = AppTest.from_file(APP, default_timeout=15).run()
    _ok(app)
    headers = {h.value for h in app.header}
    assert "Where staff act" in headers
    html = " ".join(item.proto.body for item in app.get("html"))
    for spec in STORY_PAGES:  # every dashboard part is explained on the Overview
        assert STORIES[spec.url].problem in html
    assert app.date_input(key="_halvian_day_input").value == C.DEMO_DAYS["busy"]
    assert "hv-brand-mark" in html
    assert "Patient flow and boarding" in html
    assert f"{C.MEDIAN_BOARDING_H:g} hours" in html
    assert f"{C.MEDIAN_DOOR_TO_PROVIDER_MIN} min" in html
    assert f"{C.LWBS_RATE:.0%}" in html and f"{C.TARGET_OCCUPANCY:.0%}" in html
    if results := load_impact_ranges():
        assert break_even_sentence(results) in html
        assert app.get("plotly_chart")
    else:
        assert any("have not been published" in c.value for c in app.caption)
    labels = {link.proto.label for link in app.get("page_link")}
    assert {"See the results", "Try the Ollama note reader"} <= labels
    assert not app.sidebar.selectbox
    for key in ("header_start_demo", "overview_start_demo"):
        assert app.button(key=key).label == "Start the guided demo"


@pytest.mark.parametrize("spec", NAV.ALL_PAGES, ids=lambda spec: spec.url)
def test_every_menu_page_loads(spec):
    _skip_without_artifacts(spec)
    app = AppTest.from_file(APP, default_timeout=30).run()
    app.switch_page(spec.path).run()
    _ok(app)
    assert app.title or app.get("html")


@pytest.mark.parametrize("spec", STORY_PAGES, ids=lambda spec: spec.url)
def test_each_dashboard_page_says_what_problem_it_solves_and_its_impact(spec):
    _skip_without_artifacts(spec)
    app = AppTest.from_file(APP, default_timeout=30).run()
    app.switch_page(spec.path).run()
    _ok(app)
    html = " ".join(item.proto.body for item in app.get("html"))
    story = STORIES[spec.url]
    assert story.problem in html and story.downstream in html and spec.role in html
    assert any("At this replay time" in c.value for c in app.caption)


def test_charge_nurse_can_override_the_forecast_with_a_reason():
    _skip_without_artifacts(NAV.BED_FORECAST)
    app = AppTest.from_file(APP, default_timeout=30).run()
    app.switch_page(NAV.BED_FORECAST.path).run()
    _ok(app)
    unit = app.selectbox(key="fc_unit").value
    beds = next(n for n in app.number_input if n.key.startswith("beds_forecast|"))
    beds.set_value(int(beds.value) - 2).run()
    next(b for b in app.button if b.label == "Confirm override").click().run()
    _ok(app)
    assert any("Overridden by the charge nurse" in item.proto.body for item in app.get("html"))
    app.switch_page(NAV.OVERSIGHT.path).run()
    log = app.session_state["halvian_actions"]
    assert log[-1].decision == "override" and log[-1].role == "Charge nurse" and unit in log[-1].recommendation_id


def test_guided_demo_carries_decisions_into_the_forecast_and_the_log():
    _skip_without_artifacts(NAV.GUIDED_DEMO)
    if not (ROOT / "models" / "forecast_tables.joblib").is_file():
        pytest.skip("Train the synthetic models to exercise the guided demo.")
    app = AppTest.from_file(APP, default_timeout=30).run()
    _ok(app)
    app.switch_page(NAV.GUIDED_DEMO.path).run()
    _ok(app)
    tour = L.tour_patients(C.DEMO_DAYS["busy"])
    assert app.session_state["halvian_time"].hour == tour["ed_patient"]["hour"]  # opened from the menu, the clock jumps to the flag

    def press(label):
        next(button for button in app.button if button.label == label).click().run()
        _ok(app)

    press("Approve request")
    assert any("Request approved for preparation." in item.proto.body for item in app.get("html"))
    press("Next: discharge task")
    assert app.session_state["halvian_time"].hour == L.ROUNDS_HOUR  # the context bar follows the step to 07:00 rounds
    action = next(button.label for button in app.button if button.label.startswith("Record "))
    press(action)
    assert any("Estimated chance of leaving within 24 hours" in item.value for item in app.markdown)
    press("Next: bed forecast")
    assert any("The recorded transport task makes a small change" in item.value for item in app.markdown)

    app.switch_page(NAV.OVERSIGHT.path).run()
    _ok(app)
    assert kpi_value(app, "Staff decisions") == "2"
