"""The companion for simulation results, model evidence and the case checklist."""

import streamlit as st

from halvian.ui.chrome import ASSETS, product_frame
from halvian.ui.navigation import navigation

st.set_page_config(page_title="Halvian Bed Flow results", page_icon=ASSETS / "halvian-mark.png", layout="wide",
                   initial_sidebar_state="collapsed")
page = navigation(companion=True)
product_frame(evidence=True)
page.run()
