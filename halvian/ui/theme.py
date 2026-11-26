"""Palette and Plotly defaults for the Halvian interface."""

import plotly.graph_objects as go
import plotly.io as pio

PALETTE = {
    "blue": "#1F4FD8",
    "blue_hover": "#173FB0",
    "blue_tint": "#E7EEFF",
    "sky": "#7D9CF3",
    "ink": "#0E1B2E",
    "muted": "#5A6B80",
    "white": "#FFFFFF",
    "line": "#DCE3EC",
    "wash": "#F4F7FB",
    "teal": "#006B55",
    "teal_tint": "#E7F5EF",
    "amber": "#795100",
    "amber_tint": "#FFF3DA",
    "vermillion": "#972D32",
    "red_tint": "#FBEAED",
    "purple": "#173FB0",  # Older chart callers use this key for a comparison series.
}

FONT = "Inter, system-ui, sans-serif"
PLOTLY_TEMPLATE = go.layout.Template(pio.templates["plotly_white"])
PLOTLY_TEMPLATE.layout.update(
    colorway=[PALETTE[key] for key in ("blue", "blue_hover", "muted", "sky", "teal")],
    font={"family": FONT, "color": PALETTE["ink"]},
    title={"font": {"family": FONT, "size": 18, "weight": 750}, "x": 0.02},
    hovermode="closest",
    xaxis={"gridcolor": PALETTE["line"], "zerolinecolor": PALETTE["line"]},
    yaxis={"gridcolor": PALETTE["line"], "zerolinecolor": PALETTE["line"]},
    hoverlabel={"bgcolor": PALETTE["white"], "bordercolor": PALETTE["line"], "font": {"family": FONT}},
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    barcornerradius=0,
)
PLOTLY_TEMPLATE.data.scatter = (go.Scatter(marker={"symbol": "square"}),)
