from datetime import datetime, time, timedelta

import streamlit as st
from streamlit.testing.v1 import AppTest

from halvian import config as C
from halvian.ui.session import STORY_JUMPS, DemoClock


def test_demo_clock_uses_the_simulation_epoch():
    clock = DemoClock(C.DEMO_DAYS["busy"], time(10, 15))
    expected = datetime.combine(C.DEMO_DAYS["busy"], time(10, 15))
    assert clock.timestamp == expected
    assert clock.minutes_from_start == (
        expected - datetime.combine(C.WARMUP_START, time.min)
    ).total_seconds() / 60


def test_shared_controls_remember_time_and_log_an_override(monkeypatch):
    # The isolated test script has no registered pages of its own.
    monkeypatch.setattr(st, "page_link", lambda page, **kw: st.write(kw.get("label", "")))
    monkeypatch.setattr(st.delta_generator.DeltaGenerator, "page_link",
                        lambda container, page, **kw: container.write(kw.get("label", "")))
    app = AppTest.from_string("""
import streamlit as st

from halvian.ui.components import page_header
from halvian.ui.session import latest_action, record_action, replay_controls, start_guided_tour, tour_callout

replay_controls()
clock = page_header("Test page", "A replay.", "Choose the clock.")
tour_callout("admission")
st.button("Approve", on_click=record_action, args=("ED-000001", "approve"),
          kwargs={"page": "Flags", "role": "Bed manager", "clock": clock})
st.button("Override", on_click=record_action, args=("ED-000001", "override"),
          kwargs={"page": "Flags", "role": "Bed manager", "clock": clock,
                  "reason": "Already arranged"})
st.button("Start guided demo", on_click=start_guided_tour)
action = latest_action("ED-000001")
if action:
    st.write(f"Last action was {action.decision}")
""").run()
    assert not app.exception
    assert app.date_input[0].value == C.DEMO_DAYS["busy"]
    next(b for b in app.button if b.label.startswith("Typical Wednesday")).click().run()
    assert app.date_input[0].value == C.DEMO_DAYS["typical"]
    custom_day = C.YEAR_START + timedelta(days=12)
    app.date_input[0].set_value(custom_day).run()
    assert app.session_state["halvian_day"] == custom_day
    app.slider[0].set_value(time(11, 15)).run()
    next(c for c in app.checkbox if c.label == "Highlight demo patients").set_value(True).run()
    next(b for b in app.button if b.label == "Approve").click().run()
    next(b for b in app.button if b.label == "Override").click().run()
    assert not app.exception
    assert app.slider[0].value == time(11, 15)
    assert any("Review the admission flag" in element.value for element in app.markdown)
    assert any(element.value == "Last action was override" for element in app.markdown)
    assert any(element.value == "2 decisions logged" for element in app.markdown)
    next(b for b in app.button if b.label == "Start guided demo").click().run()
    assert app.slider[0].value == time(10)
    assert next(c for c in app.checkbox if c.label == "Highlight demo patients").value

    label, moment = STORY_JUMPS[-1]
    next(b for b in app.button if b.label == f"{moment:%H:%M} {label.lower()}").click().run()
    assert app.slider[0].value == moment
    next(b for b in app.button if b.label == "Reset").click().run()
    assert app.date_input[0].value == C.DEMO_DAYS["busy"]
    assert app.slider[0].value == time(C.DEMO_START_HOUR)
    assert not next(c for c in app.checkbox if c.label == "Highlight demo patients").value
    assert any(element.value == "2 decisions logged" for element in app.markdown)


def test_oversight_replay_count_focuses_decision_log():
    app = AppTest.from_string("""
import streamlit as st

from halvian.ui.navigation import OVERSIGHT_TAB_KEY
from halvian.ui.session import replay_controls

st.session_state.setdefault(OVERSIGHT_TAB_KEY, "Fairness check")
replay_controls(on_oversight=True)
st.caption(st.session_state[OVERSIGHT_TAB_KEY])
""").run()
    assert app.caption[0].value == "Fairness check"
    app.button(key="replay_log").click().run()
    assert not app.exception
    assert app.caption[0].value == "Decision log"


def test_default_page_also_answers_at_its_own_url(monkeypatch):
    """A bookmark to /overview must not show Streamlit's "Page not found" dialog (HANDOFF item 7)."""
    from halvian.ui import navigation as NAV

    for companion in (False, True):
        captured = {}
        monkeypatch.setattr(NAV.st, "navigation", lambda pages, captured=captured, **_: captured.setdefault("pages", pages))
        NAV.navigation(companion=companion)
        pages = [p for group in captured["pages"].values() for p in group]
        defaults = [p for p in pages if p._default]
        # Streamlit sets page URLs only inside a running app, so the URL itself is checked by
        # scripts/qa_browser.py (it opens /overview); here: exactly one hidden, non-default alias
        aliases = [p for p in pages if p._visibility == "hidden"]
        assert len(defaults) == 1 and len(aliases) == 1 and not aliases[0]._default


def test_no_two_pages_claim_the_same_problem_or_downstream_effect():
    from halvian.ui.story import STORIES

    problems = [s.problem.lower() for s in STORIES.values()]
    effects = [s.downstream.lower() for s in STORIES.values()]
    assert len(set(problems)) == len(problems) and len(set(effects)) == len(effects)
    assert all(effects), "every page says what changes downstream"
