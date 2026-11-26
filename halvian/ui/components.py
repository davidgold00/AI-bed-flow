"""Shared layout, glossary and data-frame column formatters.

Start each menu page with `page_header(NAV.X, how)` and use its returned clock
(the replay context bar) to select replay data. Use the column helpers in `st.dataframe(column_config=...)`.
Pass `fraction=False` to `percent_column` for values already multiplied by 100.
"""

from html import escape
from pathlib import Path

import streamlit as st

from halvian.ui.navigation import PageSpec, ensure_product_navigation
from halvian.ui.session import DemoClock, current_clock
from halvian.ui.story import story_strip

PROJECT_ROOT = Path(__file__).resolve().parents[2]

GLOSSARY = {
    "Boarding": "Time spent in the emergency department waiting for an inpatient bed after a provider decides to admit.",
    "Left without being seen (LWBS)": "A visit that ends before a physician or advanced practice provider sees the patient.",
    "Emergency Severity Index (ESI)": "An urgency scale from 1 (needs immediate care) to 5 (least urgent).",
    "Area under the ROC curve (AUC)": "How well a model ranks patients who have an outcome ahead of those who do not. 0.5 is chance and 1.0 is perfect on the evaluated data.",
    "Calibration": "How closely predicted probabilities match observed frequencies. If 100 similar cases receive an estimate of 20%, about 20 outcomes should occur.",
    "Door-to-provider": "Time from emergency department arrival to first contact with a physician or advanced practice provider.",
    "Threshold": "The chance of an outcome at which a prediction becomes a staff alert.",
}



def section_eyebrow(text: str) -> None:
    """Render a short section label above its heading."""
    st.html(f'<p class="hv-eyebrow">{escape(text)}</p>')


def section_heading(text: str, sub: str | None = None) -> None:
    """Render an H2 with an optional plain-text subtitle."""
    subtitle = f'<p class="hv-section-subtitle">{escape(sub)}</p>' if sub else ""
    st.html(f'<div class="hv-section-heading"><h2>{escape(text)}</h2>{subtitle}</div>')


def card(*, key: str | None = None):
    """Return a square bordered container for Streamlit content and widgets."""
    return st.container(border=True, key=key)


def kpi(label: str, value: str, note: str = "") -> None:
    """Render a KPI using a display value supplied by the caller."""
    detail = f'<dd class="hv-kpi-note">{escape(note)}</dd>' if note else ""
    st.html(f'<dl class="hv-card hv-kpi"><dt>{escape(label)}</dt>'
            f'<dd class="hv-kpi-value">{escape(str(value))}</dd>{detail}</dl>')


def callout(text: str) -> None:
    """Render a quiet, contextual note."""
    st.html(f'<p class="hv-callout">{escape(text)}</p>')


def page_header(page: PageSpec | str, what: str = "", how: str = "") -> DemoClock:
    """Show the title, role, problem, downstream effect and a collapsed workflow explanation.

    Pass a menu `PageSpec` to draw its role, problem and downstream effect
    (from `halvian.ui.story`). Pass a plain title and a `what` sentence for pages outside the menu.
    Returns the current replay clock.
    """
    ensure_product_navigation()
    if isinstance(page, PageSpec):
        st.title(page.title)
        story_strip(page)
    else:
        st.title(page)
        st.markdown(what)
    if how:
        with st.expander("How it works"):
            st.markdown(how)
    return current_clock()


def glossary() -> None:
    """Render plain-language definitions of shared dashboard terms."""
    with st.expander("Glossary"):
        for term, definition in GLOSSARY.items():
            st.markdown(f"**{term}**  \n{definition}")


def number_column(label: str, *, decimals: int = 0, **kwargs):
    return st.column_config.NumberColumn(label, format=f"%.{decimals}f", **kwargs)


def percent_column(label: str, *, fraction: bool = True, **kwargs):
    return st.column_config.NumberColumn(label, format="percent" if fraction else "%.1f%%", **kwargs)


def hours_column(label: str, **kwargs):
    return st.column_config.NumberColumn(label, format="%.1f h", **kwargs)


def currency_column(label: str, **kwargs):
    return st.column_config.NumberColumn(label, format="dollar", **kwargs)


def page_link(file: str, label: str) -> None:
    """Link to a dashboard page once the file exists in the current checkout."""
    if (PROJECT_ROOT / file).is_file():
        st.page_link(file, label=label)


_STATUS_LABELS = {"on-track": "On track", "watch": "Watch", "act": "Act"}


def status_tag(level: str, text: str) -> None:
    """Show an on-track, watch or act label with its reason."""
    st.html(f'<p class="hv-status-line"><span class="hv-status hv-status-tag hv-{level}">{_STATUS_LABELS[level]}</span>'
            f'<span>{escape(text)}</span></p>')



def status_pill(level: str, message: str) -> None:
    """Keep older callers on the shared square status treatment."""
    status_tag(level, message)
