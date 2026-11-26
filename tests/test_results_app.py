"""Open every page of the results companion app."""

from pathlib import Path

import pytest
from _ui import html_text, kpi_value
from streamlit.testing.v1 import AppTest

from halvian.ui import results

ROOT = Path(__file__).resolve().parents[1]
APP = str(ROOT / "results_app.py")
PAGES = ["results/impact.py", "results/simulator.py", "results/requirements.py", "results/methods.py"]

@pytest.mark.parametrize("page", PAGES, ids=lambda p: Path(p).stem)
def test_results_page_loads(page):
    app = AppTest.from_file(APP, default_timeout=60).run()
    app.switch_page(page).run()
    assert not app.exception, [item.message for item in app.exception]
    assert app.title


def test_downstream_impact_walks_the_chain():
    app = AppTest.from_file(APP, default_timeout=60).run()
    assert not app.exception
    if not (estimates := results.load_impact_ranges()):
        assert "awaiting publication" in app.title[0].value
        return
    assert app.title[0].value == results.break_even_sentence(estimates)
    assert app.get("plotly_chart")
    for scenario in estimates["scenarios"]:
        assert any(c.value == scenario["settings"] for c in app.caption)
    html = html_text(app)
    for item in estimates["equity"]:
        assert f"{item['verdict']}: {item['gap']}" in html
    # each cost card prints one dollar sign per amount, never "$$"
    low, high = estimates["tool_cost"]["per_year_usd"]
    assert kpi_value(app, "Halvian Bed Flow, a year") == f"${low / 1e3:,.0f}K to ${high / 1e3:,.0f}K"
    for option in estimates["staffing_alternative"]:
        assert kpi_value(app, f"{option['option']}, a year") == f"${option['annual_cost_usd'] / 1e3:,.0f}K"
    assert "$$" not in html and not any("$$" in m.value for m in app.markdown)
    assert not any("$$" in m.value for m in app.metric)
    headings = [h for h in ("Where the minutes come from", "Patients wait less and fewer leave unseen",
                            "No gap between patient groups widened", "What the dashboard costs next to more staff",
                            "Published evidence behind the estimates") if h in html]
    assert len(headings) == 5


def test_unpublished_results_leave_the_operational_dashboard_available(monkeypatch, tmp_path):
    path = tmp_path / "impact_ranges.json"
    monkeypatch.setattr(results, "IMPACT_RANGES", path)
    assert results.load_impact_ranges() is None
    path.write_text('{"caveat": "PLACEHOLDER awaiting rerun"}')
    assert results.load_impact_ranges() is None
    app = AppTest.from_file(str(ROOT / "app.py")).run()
    assert not app.exception
    assert any(button.label == "Start the guided demo" for button in app.button)
    assert any(c.value == results.EMPTY_RESULTS for c in app.caption)
