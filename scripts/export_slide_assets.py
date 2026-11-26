"""Regenerate the presentation numbers and render the widescreen slide assets."""

from __future__ import annotations

import re

import plotly.graph_objects as go
from export_numbers import (
    PLAN,
    RANGES,
    ROOT,
    SCENARIOS,
    config,
    export_numbers,
    read_json,
)
from kaleido import write_fig_from_object_sync
from plotly.subplots import make_subplots

from halvian import ranges as RG
from halvian.notes.reader import READER_LABEL
from halvian.ui.theme import PALETTE, PLOTLY_TEMPLATE

# The slide is authored at half size so type and lines scale with the PNG.
WIDTH, HEIGHT, SCALE = 960, 540, 2
CAPTION = "Model estimate on synthetic data calibrated to the case brief; not evidence from a real hospital"
VERDICT_COLOR = {"Narrowed": "teal", "Flat": "muted", "Widened": "vermillion"}


def _usd_m(x: float) -> str:
    return f"${x:.1f}M"


def _wrap(text: str, width: int = 16) -> str:
    """Break a label into lines of about ``width`` characters for a horizontal tick label."""
    lines, line = [], ""
    for word in text.split():
        if line and len(line) + 1 + len(word) > width:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    return "<br>".join([*lines, line])


def _mins(r: list) -> str:
    return f"{r[0]:g} to {r[1]:g} min"


def slide(title, subtitle, *, figure=None):
    if figure is None:
        figure = go.Figure()
    figure.update_layout(
        template=PLOTLY_TEMPLATE,
        width=WIDTH,
        height=HEIGHT,
        paper_bgcolor="white",
        plot_bgcolor="white",
        font=dict(family="Arial, sans-serif", color=PALETTE["ink"], size=15),
        margin=dict(l=64, r=64, t=117, b=75),
        showlegend=False,
    )
    caption = dict(xref="paper", yref="paper", x=0, xanchor="left", showarrow=False)
    figure.add_annotation(**caption, y=1.29, text=f"<b>{title}</b>", font=dict(size=29))
    figure.add_annotation(**caption, y=1.135, text=subtitle, font=dict(size=14, color=PALETTE["muted"]))
    figure.add_annotation(**caption, y=-.17, text=CAPTION, font=dict(size=11, color=PALETTE["muted"]))
    figure.add_shape(type="line", xref="paper", yref="paper", x0=0, x1=1, y0=-.115, y1=-.115,
                     line=dict(color=PALETTE["line"], width=1))
    return figure


def annotation(figure, x, y, value, *, size=15, color="ink", anchor="center"):
    figure.add_annotation(xref="paper", yref="paper", x=x, y=y, xanchor=anchor, yanchor="middle",
                          text=value, showarrow=False, align=anchor,
                          font=dict(size=size, color=PALETTE[color]))


def box(figure, x0, x1, y0, y1, title, body, *, accent="blue", title_size=15, body_size=13):
    figure.add_shape(type="rect", xref="paper", yref="paper", x0=x0, x1=x1, y0=y0, y1=y1,
                     fillcolor=PALETTE["wash"], line=dict(color=PALETTE["line"], width=1), layer="below")
    figure.add_shape(type="line", xref="paper", yref="paper", x0=x0, x1=x1, y0=y1, y1=y1,
                     line=dict(color=PALETTE[accent], width=4))
    middle = (x0 + x1) / 2
    annotation(figure, middle, y0 + (y1 - y0) * .73, f"<b>{title}</b>", size=title_size)
    annotation(figure, middle, y0 + (y1 - y0) * .37, body, size=body_size)


def arrow(figure, start, end, *, color="muted"):
    figure.add_annotation(
        xref="x", yref="y", axref="x", ayref="y",
        x=end[0], y=end[1], ax=start[0], ay=start[1], text="",
        showarrow=True, arrowhead=2, arrowwidth=1.5, arrowcolor=PALETTE[color],
    )


def diagram(title, subtitle):
    figure = slide(title, subtitle)
    figure.update_xaxes(range=[0, 1], visible=False)
    figure.update_yaxes(range=[0, 1], visible=False)
    return figure


def ranges_chart(ranges):
    be = ranges["break_even"]["minutes_per_admission"]
    scenarios = ranges["scenarios"]
    clear = all(sc["minutes_saved_per_admission"][0] >= be for sc in scenarios)
    figure = slide(
        f"All three scenarios clear the {be}-minute break-even" if clear
        else f"Not every scenario clears the {be}-minute break-even",
        "Boarding minutes saved per admission across three synthetic years. Break-even: $500,000 / ($350 x 13,600 "
        "admissions) = about 6 min.",
    )
    rows = [(sc["name"], sc["minutes_saved_per_admission"],
             f"{_mins(sc['minutes_saved_per_admission'])}, {RG.span(sc['freed_capacity_per_year_usd_m'], _usd_m)} "
             "a year", "blue") for sc in scenarios]
    rows += [(f"{part['part']} alone", part["minutes_saved_per_admission"], _mins(part["minutes_saved_per_admission"]),
              "sky") for part in ranges["parts"]]
    labels = [name for name, *_ in rows]
    for name, (lo, hi), text, color in rows:
        figure.add_trace(go.Bar(y=[name], x=[hi - lo], base=[lo], orientation="h", width=.56,
                                marker_color=PALETTE[color], hovertemplate=f"{name}: {text}<extra></extra>"))
        figure.add_annotation(x=hi, y=name, xanchor="left", showarrow=False, text=f"  <b>{text}</b>",
                              font=dict(size=13, color=PALETTE["ink"]))
    lows = [lo for _, (lo, _hi), *_ in rows]
    highs = [hi for _, (_lo, hi), *_ in rows]
    figure.add_vline(x=be, line_dash="dash", line_color=PALETTE["ink"], line_width=1.5)
    figure.add_annotation(x=be, y=1.0, yref="paper", yanchor="bottom", showarrow=False,
                          text=f"<b>Break-even {be} min</b>", font=dict(size=12, color=PALETTE["ink"]))
    figure.update_yaxes(categoryorder="array", categoryarray=labels[::-1], showgrid=False, tickfont=dict(size=14))
    figure.update_xaxes(range=[min(0, *lows) - 2, max(highs) * 1.75], zeroline=True, zerolinecolor=PALETTE["line"],
                        title_text="Minutes of boarding saved per admission", title_standoff=6, showgrid=False)
    figure.update_layout(margin=dict(l=210, r=40, t=117, b=75))
    _align_titles(figure, 210, WIDTH - 210 - 40)
    figure.update_yaxes(domain=[.1, .97])
    annotation(figure, 1, -.17, "Parts alone use Cautious settings and overlap", size=11, color="muted",
               anchor="right")
    return figure


def downstream(ranges):
    expected = next(sc for sc in ranges["scenarios"] if sc["name"] == "Expected")
    verdict = {e["gap"].split(" vs ")[0] + "|" + e["gap"].split(", ")[-1]: e["verdict"] for e in ranges["equity"]}
    figure = diagram(
        "Earlier bed work frees ED rooms, and waits and walkouts fall",
        "The arrows show the workflow. Ranges are the Expected scenario across three synthetic years.",
    )

    def fewer(r, unit, places=0):
        return f"{-r[1]:.{places}f} to {-r[0]:.{places}f}{unit}"

    wait = "wait to see a provider"
    flow = (
        ("Earlier bed<br>requests", "Flags at triage<br>start bed work<br>before the decision"),
        ("Beds open<br>sooner", "Rounds list and<br>bed board turn<br>beds over faster"),
        ("ED rooms<br>free up", f"<b>{_mins(expected['minutes_saved_per_admission'])}</b><br>less boarding<br>"
                                "per admission"),
        ("Waits and<br>walkouts fall", f"<b>{fewer(expected['provider_wait_change_min'], ' min')}</b><br>shorter wait"
                                       f"<br><b>{fewer(expected['walkout_change_pts'], ' pts', 1)}</b><br>"
                                       "fewer walkouts<br>(winter quarter)"),
        ("Wait gaps<br>change", f"Medicaid/CHIP<br><b>{verdict[f'{config.MEDICAID}|{wait}']}</b>"
                                f"<br>Uninsured<br><b>{verdict[f'{config.UNINSURED}|{wait}']}</b>"),
    )
    width, gap = .18, .025
    for index, (title, body) in enumerate(flow):
        left = index * (width + gap)
        box(figure, left, left + width, .20, .83, title, body, accent="teal" if index == 4 else "blue",
            body_size=12)
        if index:
            arrow(figure, (left - gap + .003, .51), (left - .003, .51))
    annotation(figure, 0, .055, f"Freed capacity {RG.span(expected['freed_capacity_per_year_usd_m'], _usd_m)} a year "
               "(not cash). Wait gaps use Commercial as the reference group.", size=12, color="muted", anchor="left")
    return figure


def problem_map():
    figure = diagram(
        "Each bottleneck has a place in the dashboard",
        "Patient Flow and Boarding | Staff see the next action and who owns it.",
    )
    annotation(figure, .025, .95, "<b>WHAT SLOWS FLOW</b>", size=13, color="muted", anchor="left")
    annotation(figure, .43, .95, "<b>WHERE STAFF ACT</b>", size=13, color="blue", anchor="left")
    mappings = (
        ("Late bed requests", "ED Admission Flags", "Bed managers review early requests."),
        ("No hospital-wide bed view", "Live Bed Board", "Bed teams see ED rooms and inpatient bed status."),
        ("Stalled discharges", "Discharge Readiness", "The unit team identifies barriers and assigns follow-up."),
        ("Surprise bed openings", "Bed Forecast", "Charge nurses plan cleaning and transport."),
        ("Unequal waits", "Fairness and Oversight", "The tool owner reviews outcome gaps by payer."),
        ("Clinician distrust", "Walkthrough approvals", "Staff review the reasons before approving or overriding."),
    )
    for index, (problem, feature, detail) in enumerate(mappings):
        y = .83 - index * .138
        figure.add_shape(type="rect", xref="paper", yref="paper", x0=0, x1=1, y0=y - .057, y1=y + .057,
                         fillcolor=PALETTE["wash"] if index % 2 == 0 else "white", line_width=0, layer="below")
        annotation(figure, .025, y, f"<b>{problem}</b>", size=17, anchor="left")
        arrow(figure, (.365, y), (.41, y))
        annotation(figure, .43, y, f"<b>{feature}</b> &nbsp; {detail}", size=14, anchor="left")
    return figure


def architecture():
    figure = diagram(
        "Staff own the decisions behind the bed forecast",
        "Prototype runs locally. A proposed hospital deployment would use approved feeds and a monitored host.",
    )
    for x, label in ((.075, "DATA IN"), (.295, "AI STEPS"), (.51, "FORECAST"),
                     (.701, "STAFF REVIEW"), (.91, "OVERSIGHT")):
        annotation(figure, x, .995, f"<b>{label}</b>", color="muted", size=11)
    box(figure, 0, .15, .20, .80, "EHR feeds", "Synthetic here<br>Charts, orders<br>and bed status<br><b>Hospital IT</b>")
    for lower, upper, title, body in (
        (.66, .93, "Admission model", "Likelihood at triage<br><b>Model owner</b>"),
        (.35, .62, "Discharge model", "Likelihood at rounds<br><b>Model owner</b>"),
        (.04, .31, "AI note reader", "Local Llama 3.2 3B,<br>rules as fallback<br><b>Case manager checks</b>"),
    ):
        box(figure, .19, .40, lower, upper, title, body, title_size=14, body_size=12)
    box(figure, .445, .575, .20, .80, "Usable beds", "Expected supply<br>and demand<br><b>Charge nurse</b>")
    box(figure, .62, .785, .20, .80, "Approve or<br>override",
        "Bed prep: bed manager<br>Tasks: case manager<br>Clinical call: clinician", accent="teal", body_size=11)
    box(figure, .83, .995, .20, .80, "Decision log",
        "Track overrides<br>and fairness<br><b>Tool owner</b>", accent="teal")
    for y, target in ((.72, .79), (.50, .49), (.28, .18)):
        arrow(figure, (.155, y), (.185, target))
    arrow(figure, (.295, .316), (.295, .344))
    arrow(figure, (.405, .776), (.44, .67))
    arrow(figure, (.405, .49), (.44, .49))
    arrow(figure, (.58, .5), (.615, .5))
    arrow(figure, (.79, .5), (.825, .5))
    annotation(figure, 0, -.04, "Runs on this machine; no cloud API. " + READER_LABEL, size=11, color="muted",
               anchor="left")
    annotation(figure, 1, -.04, "Recorded discharge work updates the forecast.", size=11, color="muted",
               anchor="right")
    return figure


def payer_gaps(ranges):
    rows = ranges["equity"]
    widened = sum(e["verdict"] == "Widened" for e in rows)
    narrowed = sum(e["verdict"] == "Narrowed" for e in rows)
    figure = diagram(
        (f"No payer gap widened; {narrowed} of {len(rows)} narrowed" if not widened
         else f"{widened} payer gap{'s' if widened > 1 else ''} widened: review before scaling"),
        "Gap against Commercial with the tool versus without, Expected scenario, pooled across three synthetic "
        "years. Payer is never a model input.",
    )
    measures = ("wait to see a provider", "leaving before being seen")
    groups = list(dict.fromkeys(e["gap"].split(" vs ")[0] for e in rows))
    verdict = {(e["gap"].split(" vs ")[0], e["gap"].split(", ")[-1]): e["verdict"] for e in rows}
    left, col_w, top, row_h = .30, .32, .78, .15
    for j, measure in enumerate(measures):
        annotation(figure, left + col_w * (j + .5), top + .07, f"<b>{measure.capitalize()}</b>", size=15)
    for i, group in enumerate(groups):
        y = top - row_h * (i + .5)
        name = "Other coverage" if group == config.OTHER else group
        annotation(figure, left - .02, y, f"<b>{name}</b>", size=15, anchor="right")
        for j, measure in enumerate(measures):
            v = verdict[(group, measure)]
            x0 = left + col_w * j + .01
            figure.add_shape(type="rect", xref="paper", yref="paper", x0=x0, x1=x0 + col_w - .02,
                             y0=y - row_h * .42, y1=y + row_h * .42, line=dict(color=PALETTE["line"], width=1),
                             fillcolor=PALETTE["wash"], layer="below")
            annotation(figure, x0 + (col_w - .02) / 2, y, f"<b>{v}</b>", size=16, color=VERDICT_COLOR[v])
    annotation(figure, 0, .06, "Flat means the change is within the saved tolerance (1 min for waits, 0.15 points for "
               "walkouts).", size=12, color="muted", anchor="left")
    return figure


def sensitivity(scenarios, ranges):
    be = ranges["break_even"]["minutes_per_admission"]
    figure = slide(
        "How many flags staff act on moves the benefit most",
        f"Each sweep changes one setting from the Cautious defaults. Bars span three synthetic years. "
        f"Dashed line: the {be}-minute break-even.",
        figure=make_subplots(rows=1, cols=2, horizontal_spacing=.13, shared_yaxes=True),
    )
    results = scenarios["results"]
    default = results["default"]
    tops = []
    for column, (key, label) in enumerate((("adoption", "Share of flags staff act on"),
                                           ("threshold", "Base alert threshold")), 1):
        records = [default, *(r for name, r in results.items() if name.startswith(f"{key}="))]
        records = sorted((r for r in records if r["scenario"][key] > 0), key=lambda r: r["scenario"][key])
        xs = [r["scenario"][key] for r in records]
        spans = [RG.minutes_range(r) for r in records]
        tops += [hi for _, hi in spans]
        is_default = [x == default["scenario"][key] for x in xs]
        step = min(b - a for a, b in zip(xs, xs[1:], strict=False))
        figure.add_trace(go.Bar(x=xs, y=[hi - lo for lo, hi in spans], base=[lo for lo, _ in spans], width=.55 * step,
                                marker_color=[PALETTE["blue"] if d else PALETTE["sky"] for d in is_default],
                                text=[f"<b>{lo:g} to {hi:g}</b>" if d else f"{lo:g} to {hi:g}"
                                      for (lo, hi), d in zip(spans, is_default, strict=True)],
                                textposition="outside", textfont=dict(size=12, color=PALETTE["ink"]),
                                cliponaxis=False), row=1, col=column)
        figure.add_hline(y=be, row=1, col=column, line_dash="dash", line_color=PALETTE["ink"], line_width=1.2)
        figure.update_xaxes(row=1, col=column, tickvals=xs, tickformat=".0%", title_text=label, title_standoff=6,
                            range=[min(xs) - step * .6, max(xs) + step * .6], showgrid=False)
        figure.update_yaxes(row=1, col=column, domain=[.13, .97], showgrid=False, zeroline=False)
    figure.update_yaxes(range=[0, max(tops) * 1.2])
    figure.update_yaxes(row=1, col=1, title_text="Minutes saved per admission")
    annotation(figure, 1, -.17, "Dark bar = today's default", size=11, color="muted", anchor="right")
    return figure


def _align_titles(figure, left_margin: int, plot_width: int) -> None:
    """Start the title, subtitle and caption at the slide margin when a chart needs a wide left margin."""
    x = -(left_margin - 64) / plot_width
    for item in figure.layout.annotations[:3]:
        item.x = x
    for shape in figure.layout.shapes[:1]:
        shape.x0 = x


def _k(value: float) -> str:
    return f"${value / 1e6:.1f}M" if value >= 1e6 else f"${value / 1e3:,.0f}K"


BUDGET_GROUPS = (  # five groups so the stacked bars stay readable; licensing is $0
    ("Staff to build and run it", ("Build and validation",), "blue"),
    ("Integration and servers", ("Integration", "Infrastructure", "Licensing"), "sky"),
    ("Clinician training time", ("Training (clinician time)",), "teal"),
    ("Security, oversight, trust", ("Security review", "Monitoring and oversight", "Adoption and trust"), "purple"),
    ("Contingency", ("Contingency",), "muted"),
)


def budget_chart(plan):
    b = plan["budget"]
    phases = (("pilot", "Pilot, Months 1 to 6"), ("scale", "Scale, Months 7 to 18"), ("run", "Each year after"))
    figure = slide(
        f"{_k(b['total_18_months'])} over 18 months, inside the {_k(b['caps']['18_months'])} budget",
        f"Year 1 {_k(b['year_1'])} of {_k(b['caps']['per_year'])}. Licensing $0 (open-source, local model). "
        "Hidden: training time, security, vendor fees.",
    )
    labels = [label for _, label in phases][::-1]
    for name, cats, color in BUDGET_GROUPS:
        values = [sum(b["by_category"][p].get(c, 0) for c in cats) for p, _ in phases][::-1]
        figure.add_trace(go.Bar(y=labels, x=values, orientation="h", name=name, marker_color=PALETTE[color],
                                marker_line=dict(color="white", width=2),
                                hovertemplate=f"{name}: %{{x:$,.0f}}<extra></extra>"))
    for phase, label in phases:
        hidden = b["hidden_by_phase"][phase]
        figure.add_annotation(x=b["by_phase"][phase], y=label, xanchor="left", showarrow=False,
                              text=f"  <b>{_k(b['by_phase'][phase])}</b><br>  hidden {_k(hidden)}",
                              font=dict(size=13, color=PALETTE["ink"]), align="left")
    figure.update_layout(barmode="stack", showlegend=True, bargap=.38,
                         legend=dict(orientation="v", x=1.02, y=.5, yanchor="middle", font=dict(size=12),
                                     traceorder="normal"),
                         margin=dict(l=170, r=200, t=117, b=75))
    _align_titles(figure, 170, WIDTH - 170 - 200)
    figure.update_xaxes(showgrid=False, showticklabels=False, zeroline=False,
                        range=[0, max(b["by_phase"].values()) * 1.25])
    figure.update_yaxes(showgrid=False)
    return figure


def value_chart(ranges, plan):
    options = ranges["staffing_alternative"]
    lo, hi = ranges["tool_cost"]["per_year_usd"]
    costs = [o["annual_cost_usd"] for o in options]
    figure = slide(
        "Staffing options cost less, with no estimate of effect" if max(costs) < lo
        else "The tool and staffing options cost about the same",
        f"Cost only, at the brief's rates; we do not estimate their effect on boarding. The tool: {_k(lo)} to "
        f"{_k(hi)} a year.",
        figure=make_subplots(rows=1, cols=2, column_widths=[.6, .4], horizontal_spacing=.08,
                             specs=[[{"type": "xy"}, {"type": "domain"}]]),
    )
    names = ["The tool<br>(a year over 18 months)", *(_wrap(o["option"]) for o in options)]
    figure.add_trace(go.Bar(x=names[:1], y=[hi - lo], base=[lo], marker_color=PALETTE["blue"], width=.6,
                            hovertemplate=f"The tool: {_k(lo)} to {_k(hi)}<extra></extra>"), row=1, col=1)
    figure.add_trace(go.Bar(x=names[1:], y=costs, marker_color=PALETTE["muted"], width=.6,
                            hovertemplate="%{x}: %{y:$,.0f}<extra></extra>"), row=1, col=1)
    for name, value in zip(names, [hi, *costs], strict=True):
        text = f"<b>{_k(lo)} to {_k(hi)}</b>" if value == hi and name == names[0] else f"<b>{_k(value)}</b>"
        figure.add_annotation(x=name, y=value, yanchor="bottom", showarrow=False, text=text, row=1, col=1,
                              font=dict(size=14, color=PALETTE["ink"]))
    figure.update_yaxes(row=1, col=1, showgrid=False, showticklabels=False, range=[0, max(hi, *costs) * 1.2])
    figure.update_xaxes(row=1, col=1, showgrid=False, tickfont=dict(size=12), tickangle=0)
    figure.update_layout(barmode="overlay")
    sc = {x["name"]: x for x in ranges["scenarios"]}
    rows = (
        ("Break-even", f"{ranges['break_even']['minutes_per_admission']} min saved per admission"),
        ("Cautious: freed capacity (not cash)", f"{RG.span(sc['Cautious']['freed_capacity_per_year_usd_m'], _usd_m)}"),
        ("Expected: freed capacity (not cash)", f"{RG.span(sc['Expected']['freed_capacity_per_year_usd_m'], _usd_m)}"),
        ("Running cost after Month 18", f"{_k(plan['budget']['run_per_year'])} a year"),
    )
    for i, (label, value) in enumerate(rows):
        y = .9 - i * .23
        annotation(figure, .64, y, label, size=13, color="muted", anchor="left")
        annotation(figure, .64, y - .08, f"<b>{value}</b>", size=19, anchor="left")
    return figure


def _short(milestone: str) -> str:
    text = re.sub(r"\s*\([^)]*\)", "", milestone)
    return re.split(r"[:;]", text)[0].strip()


def roadmap_chart(plan):
    ms = plan["milestones"]
    gates = plan["pilot_gates"]
    met = sum(g["status"].startswith("Met") for g in gates)
    pending = sum(g["status"].startswith("Measured") for g in gates)
    unmet = len(gates) - met - pending
    figure = slide(
        "A supervised pilot on one unit, then scale if the gates are met",
        f"{len(gates)} gates at Month 6: {met} met in the synthetic test, {pending} need pilot data"
        + (f", {unmet} not met." if unmet else ".") + " Owners and exit criteria: docs/STRATEGY.md.",
    )
    labels = [_short(m["milestone"]) for m in ms][::-1]
    for m, label in zip(ms[::-1], labels, strict=True):
        color = PALETTE["blue"] if m["phase"] == "pilot" else PALETTE["teal"]
        figure.add_trace(go.Bar(y=[label], x=[m["end"] - m["start"] + 1], base=[m["start"] - .5], orientation="h",
                                marker_color=color, marker_line=dict(color="white", width=1),
                                hovertemplate=f"{label}: months {m['start']} to {m['end']}<br>{m['owner']}<extra></extra>"))
    for month, text in ((6.5, "Go or no-go"), (12.5, "Year 1 review")):
        figure.add_vline(x=month, line_dash="dot", line_color=PALETTE["muted"], line_width=1)
        figure.add_annotation(x=month, y=1.0, yref="paper", text=text, showarrow=False, yanchor="bottom",
                              font=dict(size=11, color=PALETTE["muted"]))
    figure.update_layout(barmode="overlay", bargap=.35, margin=dict(l=330, r=40, t=117, b=75))
    _align_titles(figure, 330, WIDTH - 330 - 40)
    figure.update_xaxes(range=[.5, 18.5], tickvals=list(range(1, 19)), title_text="Month", showgrid=False,
                        title_standoff=4)
    figure.update_yaxes(showgrid=False, tickfont=dict(size=12))
    annotation(figure, 1, -.17, "Blue: Phase 1 pilot. Green: Phase 2 scale.", size=11, color="muted", anchor="right")
    return figure


def main():
    scenarios = read_json(SCENARIOS)
    export_numbers(scenarios=scenarios)
    ranges = read_json(RANGES)
    directory = ROOT / "exports"
    directory.mkdir(exist_ok=True)
    figures = {
        "ranges_vs_break_even": ranges_chart(ranges),
        "downstream_chain": downstream(ranges),
        "problem_to_feature": problem_map(),
        "architecture": architecture(),
        "payer_gaps": payer_gaps(ranges),
        "sensitivity": sensitivity(scenarios, ranges),
    }
    plan = read_json(PLAN)
    figures.update({"budget_by_phase": budget_chart(plan), "value_vs_traditional": value_chart(ranges, plan),
                    "roadmap": roadmap_chart(plan)})
    options = dict(format="png", width=WIDTH, height=HEIGHT, scale=SCALE)
    write_fig_from_object_sync(
        [dict(fig=figure.to_plotly_json(), path=directory / f"{name}.png", opts=options)
         for name, figure in figures.items()],
        kopts=dict(mathjax=False),
    )


if __name__ == "__main__":
    main()
