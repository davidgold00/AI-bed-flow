"""Guard the shared visual tokens and their text contrast."""

import re
import tomllib
from pathlib import Path

from streamlit.testing.v1 import AppTest

from halvian.ui.theme import PALETTE, PLOTLY_TEMPLATE

ROOT = Path(__file__).resolve().parents[1]


def luminance(color: str) -> float:
    channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
    return sum(value * weight for value, weight in zip(linear, (0.2126, 0.7152, 0.0722), strict=True))


def test_square_theme_tokens_match_native_widgets_and_charts():
    native = tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text())["theme"]
    assert native["baseRadius"] == native["buttonRadius"] == "none"
    assert native["primaryColor"] == PALETTE["blue"]
    assert native["backgroundColor"] == PALETTE["white"]
    assert native["secondaryBackgroundColor"] == PALETTE["wash"]
    assert PLOTLY_TEMPLATE.layout.barcornerradius == 0
    css = (ROOT / "static" / "clinical.css").read_text()
    colors = {"primary": "blue", "primary-hover": "blue_hover", "bg": "wash", "ink": "ink", "muted": "muted",
              "line": "line", "on-track": "teal", "watch": "amber", "act": "vermillion"}
    for token, color in colors.items():
        assert re.search(rf"--hv-{token}: {PALETTE[color]};", css)


def test_shared_text_colors_meet_aa():
    combinations = [(color, surface) for color in ("ink", "muted", "blue", "blue_hover")
                    for surface in ("white", "wash")]
    combinations += [("blue_hover", "blue_tint"), ("teal", "teal_tint"), ("amber", "amber_tint"),
                     ("vermillion", "red_tint")]
    for foreground, background in combinations:
        dark, light = sorted(luminance(PALETTE[color]) for color in (foreground, background))
        assert (light + 0.05) / (dark + 0.05) >= 4.5, (foreground, background)


def test_shared_components_expose_semantic_headings_and_status_text():
    app = AppTest.from_string("""
from halvian.ui.components import callout, card, kpi, section_eyebrow, section_heading, status_tag

section_eyebrow("Beds & capacity")
section_heading("Review vacant beds", "Use the current replay.")
with card(key="review"):
    kpi("Current state", "Available", "Ready for review")
status_tag("watch", "Waiting for transport")
callout("Check current availability")
""").run()
    assert not app.exception
    html = " ".join(item.proto.body for item in app.get("html"))
    assert "Beds &amp; capacity" in html
    assert "<h2>Review vacant beds</h2>" in html
    assert "hv-kpi-value" in html and "Ready for review" in html
    assert "hv-status-tag hv-watch" in html and ">Watch<" in html and "Waiting for transport" in html
    assert "hv-callout" in html
