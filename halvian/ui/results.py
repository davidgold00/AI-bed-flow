"""Load and display the published impact ranges used across the app."""

import json
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

from halvian.ui.components import PROJECT_ROOT
from halvian.ui.design import section_heading
from halvian.ui.theme import PALETTE, PLOTLY_TEMPLATE

IMPACT_RANGES = PROJECT_ROOT / "models" / "impact_ranges.json"
EMPTY_RESULTS = "The rounded simulation estimates have not been published yet."


@st.cache_data(show_spinner=False)
def _read(path: Path, modified_ns: int) -> dict:
    return json.loads(path.read_text())


def load_impact_ranges() -> dict | None:
    """Read the published estimates and refresh after the artifact changes."""
    try:
        results = _read(IMPACT_RANGES, IMPACT_RANGES.stat().st_mtime_ns)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    if not isinstance(results, dict) or "placeholder" in json.dumps(results).lower():
        return None
    return results


def range_text(bounds, prefix: str = "", suffix: str = "") -> str:
    low, high = bounds
    return f"{prefix}{low:,g} to {prefix}{high:,g}{suffix}"


def break_even_sentence(results: dict) -> str:
    minutes = results["break_even"]["minutes_per_admission"]
    return f"Pays for itself if it saves about {minutes:g} minutes per admitted patient"


def show_break_even(results: dict) -> None:
    st.caption("Estimated value of freed emergency department time")
    st.title(break_even_sentence(results))
    st.markdown(results["break_even"]["explanation"])


def scenario_sentence(scenario: dict, threshold: float) -> str:
    low, high = scenario["minutes_saved_per_admission"]
    marker = f"the {threshold:g} minutes needed to break even"
    if low > threshold:
        comparison = f"above {marker}"
    elif high < threshold:
        comparison = f"below {marker}"
    else:
        comparison = f"a range that includes {marker}"
    return (f"The {scenario['name'].lower()} scenario estimates {range_text((low, high))} minutes "
            f"saved per admission, {comparison}")


def show_scenarios(results: dict) -> None:
    """Compare the published endpoints on one axis without deriving new estimates."""
    threshold = results["break_even"]["minutes_per_admission"]
    scenarios = results["scenarios"]
    section_heading(scenario_sentence(scenarios[0], threshold))
    fig = go.Figure()
    for scenario in scenarios:
        low, high = scenario["minutes_saved_per_admission"]
        label = range_text((low, high))
        name = scenario["name"]
        fig.add_scatter(
            x=[low, high], y=[name, name], mode="lines+markers+text",
            line={"color": PALETTE["blue"], "width": 8},
            marker={"color": PALETTE["blue"], "size": 8},
            text=["", label], textposition="middle right", cliponaxis=False,
            hovertemplate=f"{name}: {label} minutes per admitted patient<extra></extra>",
        )
    fig.add_vline(x=threshold, line={"color": PALETTE["muted"], "dash": "dash", "width": 2})
    fig.add_annotation(x=threshold, y=1, xref="x", yref="paper", xanchor="left", yanchor="bottom",
                       xshift=4, yshift=5, showarrow=False, text=f"Break-even · {threshold:g} min",
                       font={"color": PALETTE["muted"], "size": 12})
    fig.update_layout(
        template=PLOTLY_TEMPLATE, height=245, showlegend=False,
        margin={"l": 0, "r": 84, "t": 30, "b": 46},
        xaxis={"title": "Minutes saved per admitted patient", "rangemode": "tozero"},
        yaxis={"categoryorder": "array", "categoryarray": [row["name"] for row in reversed(scenarios)],
               "showgrid": False, "automargin": True},
    )
    st.plotly_chart(fig, width="stretch", theme=None, config={"displayModeBar": False, "staticPlot": True})
    for column, scenario in zip(st.columns(len(scenarios)), scenarios, strict=True):
        with column.container(border=True, key=f"scenario_{scenario['name'].lower().replace(' ', '_')}"):
            st.markdown(f"**{scenario['name']}**")
            st.caption(scenario["settings"])


def fixed_range(bounds, places: int, prefix: str = "", suffix: str = "") -> str:
    """A published range with a fixed number of decimals, for example "$2.8 to $4.0 million"."""
    low, high = bounds
    return f"{prefix}{low:,.{places}f} to {prefix}{high:,.{places}f}{suffix}"


def show_outcomes(scenario: dict) -> None:
    st.markdown(f"**{fixed_range(scenario['freed_capacity_per_year_usd_m'], 1, '$', ' million')}** "
                "of freed ED capacity a year (capacity, not cash).")
    st.markdown(f"**{fixed_range(scenario['provider_wait_change_min'], 0, suffix=' minutes')}** "
                "change in the median wait to see a provider, simulated winter quarter.")
    st.markdown(f"**{fixed_range(scenario['walkout_change_pts'], 1, suffix=' percentage points')}** "
                "change in the share who leave before seeing a provider, simulated winter quarter.")
