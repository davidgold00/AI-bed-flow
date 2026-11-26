"""Value ED room time released in a paired synthetic scenario, and the budget, value and ROI.

Two parts:

* ``estimate_capacity`` values ED room-hours freed in one paired simulation window.
* The budget and ROI functions (``budget``, ``traditional_approach``, ``value_of_gains``,
  ``roi``) turn the assumptions in ``halvian/config.py`` (tagged ``[assumption B<n>]``) and the
  saved impact simulation (``models/scenarios.json``) into the numbers for the Budget and ROI
  section. Staff time uses the brief's hourly rates. Freed ED room time is valued at the
  brief's $350 per hour as capacity, not cash; the cash part we can see (walkouts that become
  completed visits, overtime avoided) is reported separately and never added to it.
"""

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

import numpy as np

from halvian import config


@dataclass(frozen=True)
class CapacityImpact:
    baseline_boarded_hours: float
    scenario_boarded_hours: float
    bed_hours_freed: float
    capacity_value: float
    annualized_bed_hours_freed: float | None
    annualized_capacity_value: float | None


@dataclass(frozen=True)
class PitchCapacityExample:
    mean_reduction_minutes: int
    annual_bed_hours_freed: float
    annual_capacity_value: float


def _boarded_hours(
    intervals: Iterable[tuple[datetime, datetime]],
    window_start: datetime,
    window_end: datetime,
) -> float:
    total = timedelta()
    for admit_decision, ed_departure in intervals:
        if ed_departure < admit_decision:
            raise ValueError("ED departure precedes the admit decision.")
        overlap = min(ed_departure, window_end) - max(admit_decision, window_start)
        total += max(timedelta(), overlap)
    return total / timedelta(hours=1)


def estimate_capacity(
    baseline_intervals: Iterable[tuple[datetime, datetime]],
    scenario_intervals: Iterable[tuple[datetime, datetime]],
    *,
    window_start: datetime,
    window_end: datetime,
    baseline_admissions: int,
) -> CapacityImpact:
    """Value the signed difference in boarded hours inside one reporting window.

    Each interval represents one realized inpatient admission, from admit decision
    to ED departure. Supply intervals that overlap the window even if a visit
    started earlier or ended later. The optional annualized estimate scales the
    paired difference by baseline admissions in the reporting window and the
    case's annual admission volume. Both values represent ED capacity.
    """
    if window_end <= window_start:
        raise ValueError("The reporting window must have a positive duration.")
    if baseline_admissions < 0:
        raise ValueError("Baseline admissions must be nonnegative.")

    baseline_hours = _boarded_hours(baseline_intervals, window_start, window_end)
    scenario_hours = _boarded_hours(scenario_intervals, window_start, window_end)
    hours_freed = baseline_hours - scenario_hours
    annualized_hours = (
        hours_freed / baseline_admissions * config.ED_ADMISSIONS_PER_YEAR
        if baseline_admissions
        else None
    )
    rate = config.BOARDING_COST_PER_BED_HOUR
    return CapacityImpact(
        baseline_boarded_hours=baseline_hours,
        scenario_boarded_hours=scenario_hours,
        bed_hours_freed=hours_freed,
        capacity_value=hours_freed * rate,
        annualized_bed_hours_freed=annualized_hours,
        annualized_capacity_value=annualized_hours * rate if annualized_hours is not None else None,
    )


def pitch_capacity_examples() -> tuple[PitchCapacityExample, ...]:
    """Return the case-volume examples for the pitch's mean reductions."""
    examples = []
    for minutes in config.PITCH_BOARDING_CUTS_MIN:
        hours = timedelta(minutes=minutes) / timedelta(hours=1) * config.ED_ADMISSIONS_PER_YEAR
        examples.append(
            PitchCapacityExample(minutes, hours, hours * config.BOARDING_COST_PER_BED_HOUR)
        )
    return tuple(examples)


# --------------------------------------------------------------------------- budget, value and ROI
PHASE_LABELS = {"pilot": "Phase 1: Pilot (Months 1 to 6)", "scale": "Phase 2: Scale (Months 7 to 18)",
                "run": "Each year after Month 18"}
PHASE_MONTHS = {"pilot": 6, "scale": 12, "run": 12}


@dataclass(frozen=True)
class BudgetLine:
    phase: str
    category: str
    item: str
    quantity: float
    unit: str
    rate: float
    cost: float
    hidden: bool


def _training_lines() -> list[BudgetLine]:
    """Clinician time spent in training, at the brief's rates paid as overtime (a hidden cost)."""
    lines = []
    mult = config.TRAINING_RATE_MULTIPLIER
    for role, (rate, (pilot_n, scale_n), hours) in config.TRAINED_ROLES.items():
        for phase, n in (("pilot", pilot_n), ("scale", scale_n)):
            if n:
                lines.append(BudgetLine(phase, "Training (clinician time)", f"{role}: {n} x {hours:g} h",
                                        n * hours, "h", rate * mult, n * hours * rate * mult, True))
        trained = pilot_n + scale_n
        yearly = trained * (config.ANNUAL_TRAINING_TURNOVER * hours + config.REFRESHER_HOURS)
        lines.append(BudgetLine("run", "Training (clinician time)", f"{role}: new staff and a yearly refresher",
                                yearly, "h", rate * mult, yearly * rate * mult, True))
    return lines


def _oversight_lines() -> list[BudgetLine]:
    per_month = config.OVERSIGHT_MEETING_H * sum(config.OVERSIGHT_MEMBER_RATES)
    return [BudgetLine(phase, "Monitoring and oversight", f"AI oversight committee, monthly, {months} meetings",
                       months, "meetings", per_month, months * per_month, False)
            for phase, months in PHASE_MONTHS.items()]


def budget_lines() -> list[BudgetLine]:
    """Every budget line by phase, including hidden costs and a contingency reserve per phase."""
    lines = [BudgetLine(ph, cat, item, qty, unit, rate, qty * rate, hidden)
             for ph, cat, item, qty, unit, rate, hidden in config.BUDGET_LINES]
    lines += _training_lines() + _oversight_lines()
    for phase in PHASE_MONTHS:
        base = sum(line.cost for line in lines if line.phase == phase)
        lines.append(BudgetLine(phase, "Contingency", f"{config.BUDGET_CONTINGENCY:.0%} reserve", 1, "reserve",
                                base * config.BUDGET_CONTINGENCY, base * config.BUDGET_CONTINGENCY, False))
    order = {p: i for i, p in enumerate(PHASE_MONTHS)}
    return sorted(lines, key=lambda line: order[line.phase])


def budget() -> dict:
    """Totals by phase and category, the 18-month and Year 1 spend, and the checks against the caps.

    Within a phase, spending is spread evenly over its months (Year 1 = the pilot plus half of
    the scale phase).
    """
    lines = budget_lines()
    by_phase = {p: sum(line.cost for line in lines if line.phase == p) for p in PHASE_MONTHS}
    categories = sorted({line.category for line in lines})
    by_category = {p: {c: sum(line.cost for line in lines if line.phase == p and line.category == c)
                       for c in categories} for p in PHASE_MONTHS}
    hidden = {p: sum(line.cost for line in lines if line.phase == p and line.hidden) for p in PHASE_MONTHS}
    total_18 = by_phase["pilot"] + by_phase["scale"]
    year_1 = by_phase["pilot"] + by_phase["scale"] * 6 / 12
    return {
        "lines": [asdict(line) for line in lines],
        "phase_labels": PHASE_LABELS,
        "by_phase": by_phase, "by_category": by_category, "hidden_by_phase": hidden,
        "total_18_months": total_18, "year_1": year_1, "months_13_to_18": by_phase["scale"] * 6 / 12,
        "run_per_year": by_phase["run"],
        "caps": {"per_year": config.ANNUAL_BUDGET, "18_months": config.BUDGET_18_MONTHS},
        "within_caps": {"18_months": total_18 <= config.BUDGET_18_MONTHS,
                        "year_1": year_1 <= config.ANNUAL_BUDGET,
                        "run_per_year": by_phase["run"] <= config.ANNUAL_BUDGET},
        "headroom_18_months": config.BUDGET_18_MONTHS - total_18,
        "alternatives": [{"option": o, "saving": s, "note": n} for o, s, n in config.BUDGET_ALTERNATIVES],
    }


def traditional_approach(run_cost_per_year: float) -> dict:
    """Staff time to give the same coverage by hand, hired, on overtime or through an agency."""
    rows = []
    for task, rate, hours in config.TRADITIONAL_WORK:
        rows.append({"task": task, "hours_per_year": hours, "fte": hours / config.HOURS_PER_FTE_YEAR,
                     "rate": rate, "hired": hours * rate, "overtime": hours * rate * config.OVERTIME_MULTIPLIER,
                     "agency": hours * rate * config.AGENCY_MULTIPLIER})
    total = {k: sum(r[k] for r in rows) for k in ("hours_per_year", "fte", "hired", "overtime", "agency")}
    return {"rows": rows, "total": total, "tool_per_year": run_cost_per_year,
            "tool_vs_hiring_ratio": total["hired"] / run_cost_per_year if run_cost_per_year else None}


def _per_seed(result: dict, key: str) -> list[float]:
    return [float(s[key]) for s in result["per_seed"]]


def _spread(values: list[float]) -> dict:
    return {"mean": float(np.mean(values)), "min": float(min(values)), "max": float(max(values))}


def scenario_value(result: dict) -> dict:
    """Yearly value of one saved scenario: capacity (not cash), recovered walkouts and overtime."""
    rel_lwbs = [(b - t) / b for b, t in zip(_per_seed(result, "lwbs_pct_base"), _per_seed(result, "lwbs_pct_tool"),
                                            strict=True)]
    hours = _per_seed(result, "run_rate_bed_hours")
    walkouts_year = config.ED_VISITS_PER_YEAR * config.LWBS_RATE
    avoided = [walkouts_year * r for r in rel_lwbs]
    revenue = [a * config.NET_REVENUE_PER_VISIT * config.WALKOUT_RECOVERED_SHARE for a in avoided]
    ot_hours = [h * config.ED_NURSE_H_PER_BOARDER_H * config.BOARDER_NURSING_ON_OVERTIME for h in hours]
    overtime = [h * config.COST_NURSE_PER_H * config.OVERTIME_MULTIPLIER for h in ot_hours]
    cash = [r + o for r, o in zip(revenue, overtime, strict=True)]
    return {
        "ed_room_hours_freed": _spread(hours),
        "ed_rooms_around_the_clock": _spread([h / config.HOURS_PER_SEAT_YEAR for h in hours]),
        "capacity_value": _spread(_per_seed(result, "run_rate_value")),
        "minutes_saved_per_admission": _spread(_per_seed(result, "mean_minutes_saved_per_admission")),
        "walkout_relative_reduction": _spread(rel_lwbs),
        "walkouts_avoided": _spread(avoided),
        "walkout_revenue": _spread(revenue),
        "overtime_nurse_hours_avoided": _spread(ot_hours),
        "overtime_avoided": _spread(overtime),
        "cash_value": _spread(cash),
    }


def value_of_gains(scenarios: dict) -> dict:
    """Yearly value at the default settings, with how each number is reached."""
    out = scenario_value(scenarios["results"]["default"])
    out["method"] = {
        "capacity_value": "ED room-hours freed per year (paired simulation, scaled to the brief's 13,600 "
                          "admissions) x the brief's $350 per boarded ED room-hour. Capacity, not cash.",
        "walkout_revenue": "Relative drop in walkouts in the simulation x the brief's 4.0% of 85,000 visits x "
                           f"$1,500 net revenue per visit x {config.WALKOUT_RECOVERED_SHARE:.0%} kept (the rest "
                           "would have come back). Cash, and part of the capacity value, so never added to it.",
        "overtime_avoided": f"ED room-hours freed x {config.ED_NURSE_H_PER_BOARDER_H:g} nurse-hours per boarded "
                            f"patient-hour x {config.BOARDER_NURSING_ON_OVERTIME:.0%} on overtime x $65 x 1.5.",
    }
    out["least_certain"] = [
        "Adoption: the share of flags staff act on (50% in the Cautious scenario). The adoption table shows the "
        "range at 25% to 100%.",
        f"The bed board's {config.BED_BOARD_DELAY_CUT:.0%} cut in bed turnover delays (Expected and Full rollout "
        "only): no study we found backs it.",
        "Discharge time recovered per acted-on barrier (1 h default, tested 0 to 4 h).",
        "EHR vendor interface fees: need a quote.",
        f"Walkouts kept as revenue ({config.WALKOUT_RECOVERED_SHARE:.0%}) and nursing on overtime "
        f"({config.BOARDER_NURSING_ON_OVERTIME:.0%}).",
        "The simulation itself: synthetic patients calibrated to the brief, not Halvian's records.",
    ]
    return out


def _monthly_value(scenarios: dict, basis: str) -> list[float]:
    full = scenario_value(scenarios["results"]["default"])[basis]["mean"] / 12
    pilot = scenario_value(scenarios["results"]["pilot"])[basis]["mean"] / 12
    out = []
    for month in range(1, config.PLAN_MONTHS + 1):
        stage = next(k for k, (a, b) in config.VALUE_RAMP.items() if a <= month <= b)
        out.append({"setup": 0.0, "pilot": pilot, "rollout": full * config.ROLLOUT_VALUE_SHARE,
                    "full": full}[stage])
    return out


def _payback_month(costs: list[float], values: list[float], run_cost: float, run_value: float,
                   horizon: int = 60) -> int | None:
    cum_cost = cum_value = 0.0
    for month in range(1, horizon + 1):
        cum_cost += costs[month - 1] if month <= len(costs) else run_cost / 12
        cum_value += values[month - 1] if month <= len(values) else run_value / 12
        if cum_value >= cum_cost:
            return month
    return None


def roi(scenarios: dict) -> dict:
    """Yearly ROI after Month 18, the 18-month position and payback, on a cash and a capacity basis."""
    b = budget()
    run = b["run_per_year"]
    costs = [b["by_phase"]["pilot"] / 6] * 6 + [b["by_phase"]["scale"] / 12] * 12
    out: dict = {"run_cost_per_year": run, "monthly_cost": costs}
    for basis, label in (("cash_value", "cash"), ("capacity_value", "capacity")):
        value = scenario_value(scenarios["results"]["default"])[basis]
        monthly = _monthly_value(scenarios, basis)
        out[label] = {
            "value_per_year": value,
            "roi_per_year": {k: (v - run) / run for k, v in value.items()},
            "net_per_year": {k: v - run for k, v in value.items()},
            "value_18_months": sum(monthly), "cost_18_months": sum(costs),
            "net_18_months": sum(monthly) - sum(costs),
            "monthly_value": monthly,
            "payback_month": _payback_month(costs, monthly, run, value["mean"]),
            # earliest and latest payback: the same ramp at the highest and lowest synthetic year's value
            "payback_month_range": [
                _payback_month(costs, [m * value[k] / value["mean"] for m in monthly] if value["mean"] else monthly,
                               run, value[k]) for k in ("max", "min")],
        }
    hours = scenario_value(scenarios["results"]["default"])["ed_room_hours_freed"]["mean"]
    out["cost_per_ed_room_hour_freed"] = run / hours if hours else None
    out["by_adoption"] = []
    for level in scenarios["sweeps"]["adoption"]:
        key = "default" if level == config.IMPACT_DEFAULTS["adoption"] else f"adoption={level:g}"
        result = scenarios["results"].get(key)
        if result is None or not level:
            continue
        v = scenario_value(result)
        out["by_adoption"].append({
            "adoption": level, "minutes_saved": v["minutes_saved_per_admission"]["mean"],
            "capacity_value": v["capacity_value"]["mean"], "cash_value": v["cash_value"]["mean"],
            "cash_roi": (v["cash_value"]["mean"] - run) / run,
            "capacity_roi": (v["capacity_value"]["mean"] - run) / run})
    return out
