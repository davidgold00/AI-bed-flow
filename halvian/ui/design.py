"""The design-system vocabulary every page uses (docs/DESIGN.md), plus two layout helpers.

`section_eyebrow`, `section_heading`, `card`, `kpi`, `callout` and `status_tag` are Codex's helpers in
`halvian.ui.components`; pages import them from here together with `kpi_row` and `capped_table`, so no page
carries its own colors or styles.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from halvian.ui.components import callout, card, kpi, section_eyebrow, section_heading, status_tag

__all__ = ["callout", "capped_table", "card", "kpi", "kpi_row", "section_eyebrow", "section_heading", "status_tag"]


def kpi_row(items: list[tuple[str, str, str]]) -> None:
    """Headline numbers in one row of equal cards: (label, value, note)."""
    for col, (label, value, note) in zip(st.columns(len(items)), items, strict=True):
        with col:
            kpi(label, value, note)


def capped_table(df: pd.DataFrame, *, key: str, rows: int = 8, **kwargs) -> None:
    """A data frame without its index that shows `rows` rows until the reader asks for all of them."""
    kwargs.setdefault("hide_index", True)
    kwargs.setdefault("width", "stretch")
    if len(df) > rows and not st.toggle(f"Show all {len(df)} rows", key=f"show_all_{key}"):
        st.dataframe(df.head(rows), **kwargs)
        st.caption(f"Showing {rows} of {len(df)}.")
        return
    st.dataframe(df, **kwargs)
