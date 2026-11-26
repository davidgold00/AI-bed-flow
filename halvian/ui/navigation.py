"""The app menu: one place for each page's file, menu title, icon and URL.

`app.py` builds the grouped top menu from `MENU`. Pages link to each other with
`st.page_link(BED_FORECAST.path, ...)`, so a renamed file only changes here.
"""

from dataclasses import dataclass

import streamlit as st
from streamlit.navigation.page import StreamlitPage
from streamlit.runtime.pages_manager import PagesManager


@dataclass(frozen=True)
class PageSpec:
    path: str
    title: str
    icon: str
    url: str
    role: str = ""

    def page(self, default: bool = False) -> StreamlitPage:
        return st.Page(self.path, title=self.title, icon=self.icon, url_path=self.url, default=default)


OVERVIEW = PageSpec("pages/overview.py", "Overview", ":material/home:", "overview")
GUIDED_DEMO = PageSpec("pages/guided_demo.py", "Guided demo", ":material/play_circle:", "guided_demo",
                       "Anyone new to the tool, including the judges")
BED_BOARD = PageSpec("pages/bed_board.py", "Live Bed Board", ":material/bed:", "bed_board",
                     "Bed manager and ED charge nurse")
ADMISSION_FLAGS = PageSpec("pages/admission_flags.py", "ED Admission Flags", ":material/flag:",
                           "admission_flags", "Bed manager")
DISCHARGE = PageSpec("pages/discharge_readiness.py", "Discharge Readiness", ":material/assignment_turned_in:",
                     "discharge_readiness", "Rounds team and case manager")
BED_FORECAST = PageSpec("pages/bed_forecast.py", "Bed Forecast", ":material/query_stats:", "bed_forecast",
                        "Charge nurses and the house supervisor")
OVERSIGHT = PageSpec("pages/oversight.py", "Fairness and Oversight", ":material/verified_user:", "oversight",
                     "Tool owner and the AI oversight committee")

IMPACT = PageSpec("results/impact.py", "Downstream impact", ":material/trending_down:", "impact")
SIMULATOR = PageSpec("results/simulator.py", "Impact simulator", ":material/tune:", "simulator")
REQUIREMENTS = PageSpec("results/requirements.py", "Requirements check", ":material/checklist:", "requirements")
METHODS = PageSpec("results/methods.py", "Data and methods", ":material/dataset:", "methods")
RESULTS = [IMPACT, SIMULATOR, REQUIREMENTS, METHODS]
NOTE_READER_PARAMS = {"view": "note-reader"}

DECISION_LOG_PARAMS = {"view": "decision-log"}
OVERSIGHT_TAB_KEY = "halvian_oversight_tab"
DECISION_LOG_TITLE = "Decision log"

MENU: dict[str, list[PageSpec]] = {
    "Start here": [OVERVIEW, GUIDED_DEMO],
    "Dashboard": [BED_BOARD, ADMISSION_FLAGS, DISCHARGE, BED_FORECAST],
    "Safeguards": [OVERSIGHT],
    "Results": RESULTS,
}
ALL_PAGES = [spec for specs in MENU.values() for spec in specs]


HOME_ALIAS_TITLE = "Home"


def navigation(*, companion: bool = False) -> StreamlitPage:
    """Register every page and return the selected one (call `.run()` on it).

    The default page is served at "/". A hidden alias keeps its own URL working too (for example
    "/overview" in a bookmark), so it never shows Streamlit's "Page not found" dialog.
    """
    menu = {"Results": [IMPACT, SIMULATOR], "Case evidence": [REQUIREMENTS, METHODS]} if companion else MENU
    home = IMPACT if companion else OVERVIEW
    pages = {name: [st.Page(spec.path, title=spec.title, icon=spec.icon, default=True, url_path=f"{spec.url}-home")
                    if spec is home else spec.page() for spec in specs] for name, specs in menu.items()}
    default = next(page for specs in pages.values() for page in specs if page._default)

    def go_home() -> None:
        st.switch_page(default)

    alias = st.Page(go_home, title=HOME_ALIAS_TITLE, url_path=home.url, visibility="hidden")
    pages[next(iter(pages))].append(alias)
    return st.navigation(pages, position="top")


def ensure_product_navigation() -> None:
    """On a cold deep link Streamlit can dispatch pages/ before it runs app.py."""
    if PagesManager.uses_pages_directory and "halvian_shell_seen" not in st.session_state:
        navigation()
        st.rerun()
