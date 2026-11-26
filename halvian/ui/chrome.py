"""The product frame shared by the dashboard and its evidence companion."""

from pathlib import Path

import streamlit as st

from halvian import config as C
from halvian.ui import navigation as NAV
from halvian.ui.session import start_guided_tour

ASSETS = Path(__file__).resolve().parents[2] / "static"
SYNTHETIC_BANNER = "Synthetic demo data. For discussion and demonstration only."


def start_demo() -> None:
    """Start at the first patient in the featured replay."""
    from halvian.data import live as L

    try:
        patient = L.tour_patients(C.DEMO_DAYS["busy"]).get("ed_patient")
    except FileNotFoundError:
        patient = None
    start_guided_tour(patient["hour"] if patient else None)


def product_frame(*, evidence: bool = False) -> None:
    st.session_state["halvian_shell_seen"] = True
    st.html(ASSETS / "clinical.css")
    st.html(f"""
    <header class="hv-masthead" aria-label="Halvian product header">
      <div class="hv-masthead-inner">
        <span class="hv-brand-mark" aria-hidden="true">H</span>
        <div class="hv-brand-name">
          <strong>Halvian Bed Flow</strong>
          <span class="hv-product-description">Halvian Medical Center</span>
        </div>
      </div>
    </header>
    <footer class="hv-footer">{SYNTHETIC_BANNER}</footer>
    """)
    if not evidence:
        with st.container(key="hv_header_action"):
            if st.button("Start the guided demo", type="primary", key="header_start_demo", on_click=start_demo):
                st.switch_page(NAV.GUIDED_DEMO.path)
