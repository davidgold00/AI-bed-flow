"""The tool's effect as rounded ranges, introduced by a break-even point: models/impact_ranges.json.

The results are shown as ranges, never as precise simulated outcomes (no "3.30 h" or "5.53%").
Each range is the spread of one measure across the three synthetic years, widened outward to round
numbers (``config.RANGE_STEP``): minutes to the nearest 5, waits to the nearest minute, walkouts to
0.1 points. Freed capacity is the minute range converted at the brief's rate, so a reader can check
it by hand. The case brief's own numbers (3.5 h, 55 min, 4%, $350 per bed-hour) stay exact.

This file is the one contract the UI reads for results. ``scripts/build_plan.py`` writes it.
"""

from __future__ import annotations

import math

from halvian import config as C

# Scenario keys in models/scenarios.json (halvian.impact.scenario_grid). "default" is the Cautious
# scenario: today's defaults.
RANGE_SCENARIOS = {"Cautious": "default", "Expected": "expected", "Full rollout": "full_rollout"}
RANGE_PARTS = {"Admission flags": "admission_only", "Discharge readiness": "discharge_only",
               "Bed board": "bed_board_only"}

CAVEAT = ("Model estimate from a synthetic Halvian calibrated to the case brief. It shows which levers matter "
          "and how large the payoff could be under stated assumptions. It is not evidence from a real hospital.")

MEASURES = {"Door-to-provider (median)": "wait to see a provider",
            "Left without being seen": "leaving before being seen"}

REFERENCES = (
    {"source": "Johns Hopkins study of discharge predictions in multidisciplinary rounds",
     "finding": "Feeding machine learning discharge predictions into daily rounds was followed by stays more than "
                "12 hours shorter on 2 of 4 units (a medicine and a telemetry unit), with no change on the other two.",
     "url": "https://pure.johnshopkins.edu/en/publications/machine-learning-based-hospital-discharge-predictions-can-support/"},
    {"source": "Proactive Inpatient Bed Requests for ED Admissions (2026 preprint, simulation)",
     "finding": "In a simulation, hourly bed requests driven by admission predictions cut ED boarding by 30 to 70%; "
                "it is a preprint, not a live deployment.",
     "url": "https://arxiv.org/abs/2607.15432"},
)

DOLLARS_STEP = 10_000  # costs are arithmetic from the brief's rates, not simulated: nearest $10K


def _clean(x: float, step: float) -> float | int:
    """Drop floating-point dust and return an int when the step is whole."""
    digits = max(0, -math.floor(math.log10(step))) if step < 1 else 0
    x = round(x, digits)
    return int(x) if step >= 1 else x


def widen(lo: float, hi: float, step: float) -> list:
    """The range ``[lo, hi]`` widened outward to multiples of ``step``; never a single point."""
    a = math.floor(lo / step + 1e-9) * step
    b = math.ceil(hi / step - 1e-9) * step
    if b <= a:
        b = a + step
    return [_clean(a, step), _clean(b, step)]


def spread(reading: dict, step: float, scale: float = 1.0) -> list:
    """A saved ``{"mean", "min", "max"}`` reading as a widened range (the mean is not shown)."""
    return widen(reading["min"] * scale, reading["max"] * scale, step)


def span(r: list, fmt=lambda x: f"{x:,g}") -> str:
    """``[lo, hi]`` as text, for example "10 to 20"."""
    return f"{fmt(r[0])} to {fmt(r[1])}"


def minutes_to_usd_m(minutes: float) -> float:
    """Minutes saved per admission as freed capacity a year, $M: x 13,600 admissions / 60 x $350."""
    return minutes * C.ED_ADMISSIONS_PER_YEAR / 60 * C.BOARDING_COST_PER_BED_HOUR / 1e6


def _per_seed(result: dict, fn) -> list[float]:
    return [float(fn(p)) for p in result["per_seed"]]


def minutes_range(result: dict) -> list:
    v = _per_seed(result, lambda p: p["mean_minutes_saved_per_admission"])
    return widen(min(v), max(v), C.RANGE_STEP["minutes"])


def room_hours_range(minutes: list) -> list:
    """The minute range as ED room-hours freed a year, widened to 100 hours."""
    return widen(*(m * C.ED_ADMISSIONS_PER_YEAR / 60 for m in minutes), 100)


def capacity_roi_range(minutes: list, run_cost: float) -> list:
    """Yearly ROI on freed capacity, percent, from the minute range and the yearly running cost."""
    lo, hi = ((minutes_to_usd_m(m) * 1e6 - run_cost) / run_cost * 100 for m in minutes)
    return widen(lo, hi, 100)


def cost_to_serve_range(minutes: list, run_cost: float) -> list:
    """Yearly cost per ED room-hour freed, dollars, widened to $10."""
    hi_h, lo_h = (m * C.ED_ADMISSIONS_PER_YEAR / 60 for m in (minutes[1], minutes[0]))
    return widen(run_cost / hi_h, run_cost / lo_h if lo_h > 0 else float("inf"), 10)


def usd_m_range(minutes: list) -> list:
    """The minute range at the brief's rate, to the nearest $0.1M (the minute range is already widened)."""
    step = C.RANGE_STEP["usd_m"]
    return [_clean(round(minutes_to_usd_m(m) / step) * step, step) for m in minutes]


def change_range(result: dict, measure: str) -> list:
    """Tool minus baseline for each synthetic year, widened: negative means shorter or fewer."""
    key, step = {"wait": ("d2p_median", C.RANGE_STEP["wait_min"]),
                 "walkouts": ("lwbs_pct", C.RANGE_STEP["walkout_pts"])}[measure]
    v = _per_seed(result, lambda p: p[f"{key}_tool"] - p[f"{key}_base"])
    return widen(min(v), max(v), step)


def break_even() -> dict:
    hours = C.ANNUAL_BUDGET / (C.BOARDING_COST_PER_BED_HOUR * C.ED_ADMISSIONS_PER_YEAR)
    minutes = round(hours * 60)
    return {"minutes_per_admission": minutes,
            "explanation": f"The tool pays for itself when it saves about {minutes} minutes per admission: "
                           f"${C.ANNUAL_BUDGET:,.0f} a year / (${C.BOARDING_COST_PER_BED_HOUR} per bed-hour x "
                           f"{C.ED_ADMISSIONS_PER_YEAR:,} admissions a year) = {hours:.3f} hours, about "
                           f"{minutes} minutes."}


def settings_text() -> dict[str, str]:
    d, f = C.IMPACT_DEFAULTS, C.FULL_ROLLOUT

    def hours(h: float) -> str:
        return f"{h:g} hour{'' if h == 1 else 's'}"

    return {
        "Cautious": f"Today's default settings: staff act on {d['adoption']:.0%} of flags within about "
                    f"{hours(d['staff_response_delay_h'])}, alert threshold {d['threshold']:.0%} (moving with "
                    f"crowding), discharges on the rounds list {hours(d['discharge_hours_saved'])} earlier, and no "
                    "credit for the bed board.",
        "Expected": f"Today's defaults plus the Live Bed Board, which we assume cuts the housekeeping "
                    f"notification delay and bed request processing by {C.BED_BOARD_DELAY_CUT:.0%}.",
        "Full rollout": f"Staff act on {f['adoption']:.0%} of flags, alert threshold {f['threshold']:.0%} (moving with "
                        f"crowding), discharges on the rounds list {hours(f['discharge_hours_saved'])} earlier, and "
                        "the bed board on.",
    }


def scenario_ranges(scenarios: dict) -> list[dict]:
    res, text = scenarios["results"], settings_text()
    out = []
    for name, key in RANGE_SCENARIOS.items():
        minutes = minutes_range(res[key])
        out.append({"name": name, "settings": text[name], "minutes_saved_per_admission": minutes,
                    "freed_capacity_per_year_usd_m": usd_m_range(minutes),
                    "provider_wait_change_min": change_range(res[key], "wait"),
                    "walkout_change_pts": change_range(res[key], "walkouts")})
    return out


def equity(scenarios: dict, key: str = RANGE_SCENARIOS["Expected"]) -> list[dict]:
    """Payer gap verdicts against Commercial in the Expected scenario (pooled across the years)."""
    return [{"gap": f"{g['Gap']}, {MEASURES.get(g['Measure'], g['Measure'])}", "verdict": g["Verdict"]}
            for g in scenarios["results"][key]["gap_table"]]


def staffing_alternative() -> list[dict]:
    return [{"option": name, "annual_cost_usd": int(round(rate * hours * mult / DOLLARS_STEP) * DOLLARS_STEP),
             "assumption": text} for name, rate, hours, mult, text in C.STAFFING_OPTIONS]


def tool_cost(plan: dict) -> dict:
    years = C.PLAN_MONTHS / 12
    lo, hi = (int(round(c / years / DOLLARS_STEP) * DOLLARS_STEP) for c in C.TOOL_COST_18_MONTHS)
    b = plan["budget"]
    k = lambda x: f"${round(x / DOLLARS_STEP) * DOLLARS_STEP / 1e3:,.0f}K"  # noqa: E731
    return {"per_year_usd": [lo, hi],
            "note": f"Our ballpark of ${C.TOOL_COST_18_MONTHS[0] / 1e3:,.0f}K to ${C.TOOL_COST_18_MONTHS[1] / 1e3:,.0f}K "
                    f"over 18 months (the itemized budget comes to about {k(b['total_18_months'])}), spread evenly "
                    f"over 1.5 years; after Month 18 the running cost falls to about {k(b['run_per_year'])} a year."}


def least_certain(scenarios: dict) -> str:
    bed = minutes_range(scenarios["results"][RANGE_PARTS["Bed board"]])
    return (f"The least certain assumption is the bed board's {C.BED_BOARD_DELAY_CUT:.0%} cut in bed turnover delays: "
            f"no study we found backs it, it alone adds {bed[0]} to {bed[1]} minutes per admission, and so the "
            "Cautious range leaves it out.")


def build(scenarios: dict, plan: dict) -> dict:
    return {
        "caveat": CAVEAT,
        "break_even": break_even(),
        "scenarios": scenario_ranges(scenarios),
        "parts": [{"part": name, "minutes_saved_per_admission": minutes_range(scenarios["results"][key])}
                  for name, key in RANGE_PARTS.items()],
        "equity": equity(scenarios),
        "staffing_alternative": staffing_alternative(),
        "tool_cost": tool_cost(plan),
        "references": list(REFERENCES),
        "least_certain": least_certain(scenarios),
    }
