"""Halvian Bed Flow, the staff dashboard."""

import streamlit as st

from halvian.ui.chrome import ASSETS, product_frame
from halvian.ui.navigation import OVERSIGHT, OVERVIEW, RESULTS, navigation
from halvian.ui.session import replay_controls

st.set_page_config(page_title="Halvian Bed Flow", page_icon=ASSETS / "halvian-mark.png", layout="wide",
                   initial_sidebar_state="collapsed")
page = navigation()
product_frame()
if page.url_path and page.url_path not in {OVERVIEW.url, *(spec.url for spec in RESULTS)}:
    replay_controls(on_oversight=page.url_path == OVERSIGHT.url)
page.run()
