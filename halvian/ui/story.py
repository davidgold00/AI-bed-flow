"""Why each page exists: one problem from the case brief, the staff action and one downstream effect.

No two pages claim the same problem or the same downstream effect (tests/test_ui_helpers.py checks).
`chain[0]` is the staff action (the Overview's map reads it); `downstream` is what changes because of it.
"""

from dataclasses import dataclass
from html import escape

import streamlit as st

from halvian.ui import navigation as NAV


@dataclass(frozen=True)
class Story:
    problem: str
    chain: tuple[str, ...]
    downstream: str = ""


def display_range(lo_hi, fmt="{:g}") -> str:
    lo, hi = lo_hi
    return f"{fmt.format(lo)} to {fmt.format(hi)}"


STORIES = {
    NAV.BED_BOARD.url: Story(
        "No one sees every ED space and inpatient bed at once",
        ("Match waiting patients to clean beds across units.",),
        "Clean beds are found by looking, not by phone calls, so admitted patients leave ED rooms sooner.",
    ),
    NAV.ADMISSION_FLAGS.url: Story(
        "Bed requests start only after the admission decision",
        ("Prepare a bed before the admission decision.",),
        "Bed work overlaps the ED workup instead of following it, which shortens boarding.",
    ),
    NAV.DISCHARGE.url: Story(
        "Discharges wait on transport, home care and approvals found too late",
        ("Arrange transport and home support at rounds.",),
        "Beds open earlier in the day, before the afternoon wave of admissions.",
    ),
    NAV.BED_FORECAST.url: Story(
        "Bed shortages are noticed only when a patient is already waiting",
        ("Plan cleaning or transfers ahead of a bed shortage.",),
        "Placements and cleaning are planned hours ahead instead of in a rush.",
    ),
    NAV.OVERSIGHT.url: Story(
        "AI could widen gaps between patient groups or be followed blindly",
        ("Review decisions, check gaps by group and pause the tool if needed.",),
        "Waits and walkouts for Medicaid/CHIP and uninsured patients are tracked and must not get worse.",
    ),
    NAV.GUIDED_DEMO.url: Story(
        "Clinicians distrust tools they have not seen work",
        ("Rehearse one bed request and one discharge task.",),
        "Staff see that a person approves every step before the tool goes live.",
    ),
}
ORDER = [NAV.BED_BOARD, NAV.ADMISSION_FLAGS, NAV.DISCHARGE, NAV.BED_FORECAST, NAV.OVERSIGHT]


def story_strip(spec: NAV.PageSpec) -> None:
    """Who uses the page, the problem it solves and what changes downstream."""
    story = STORIES[spec.url]
    st.html(f"""
    <div class="hv-page-story">
      <p><b>For:</b> {escape(spec.role)}</p>
      <p><b>Problem:</b> {escape(story.problem)}</p>
      <p><b>What changes:</b> {escape(story.downstream)}</p>
    </div>
    """)


def story_line(spec: NAV.PageSpec) -> None:
    story = STORIES[spec.url]
    st.caption(f"{story.problem}. {story.downstream}")


def impact_now(text: str) -> None:
    """What the numbers mean at the current replay time, next to the headline numbers."""
    with st.container(key="impact_now"):
        st.caption("At this replay time")
        st.markdown(text)
    st.space("small")  # keep the next heading clear of the note
