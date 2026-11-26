"""Export the figures used in the presentation from committed case inputs and results."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from halvian import config  # noqa: E402
from halvian import ranges as RG  # noqa: E402

ARCHITECTURE = "AI Tool Architecture"
ROADMAP = "Roadmap and Milestones"
BUDGET = "Budget and ROI"
RISK = "Risk Assessment and Mitigation"
DEMO = "Working MVP Demo"

CONFIG = "halvian/config.py"
VALIDATION = "data/validation.json"
METRICS = "models/metrics.json"
SCENARIOS = "models/scenarios.json"
PLAN = "models/plan.json"
RANGES = "models/impact_ranges.json"
DEFAULT = "results.default"


@dataclass(frozen=True)
class Number:
    display: str
    meaning: str
    section: str
    file: str
    key: str

    def markdown(self) -> str:
        cells = (self.display, self.meaning, self.section, f"`{self.file}` · `{self.key}`")
        return "| " + " | ".join(cell.replace("|", r"\|") for cell in cells) + " |"


def read_json(file: str) -> dict:
    return json.loads((ROOT / file).read_text(encoding="utf-8"))


def count(value: float) -> str:
    return f"{value:,.0f}"


def percent(value: float) -> str:
    return f"{value:.1%}"


def money(value: float) -> str:
    return f"${value:,.0f}"


def millions(value: float) -> str:
    return f"${value / 1e6:.2f}M"


def percent_whole(value: float) -> str:
    return f"{value:.0%}"


def decimal(unit: str = "", places: int = 1) -> Callable[[float], str]:
    return lambda value: f"{value:,.{places}f}{unit}"


def across_runs(reading: dict, format_value: Callable[[float], str], step: float, scale: float = 1.0) -> str:
    """A saved {mean, min, max} reading as a range across the synthetic years, widened to ``step``."""
    return RG.span(RG.spread(reading, step, scale), format_value)


def span(values: list, format_value: Callable[[float], str]) -> str:
    return RG.span(values, format_value)


def usd_m(value: float) -> str:
    return f"${value:.1f}M"


def signed(unit: str, places: int = 0) -> Callable[[float], str]:
    return lambda value: f"{value:+.{places}f}{unit}"


def scenario_format(key: str, value: float) -> str:
    if key in {"adoption", "threshold"}:
        return f"{value:.0%}"
    return f"{value:g} h"


def collect_numbers(scenarios: dict, metrics: dict, validation: dict, plan: dict | None = None,
                    ranges: dict | None = None) -> dict[str, Number]:
    rows = {}
    plan = read_json(PLAN) if plan is None else plan
    ranges = read_json(RANGES) if ranges is None else ranges

    def add(identifier, display, meaning, section, file, key):
        rows[identifier] = Number(display, meaning, section, file, key)

    def cfg(key, meaning, section, format_value=count):
        add(key, format_value(getattr(config, key)), meaning, section, CONFIG, key)

    cfg("ED_VISITS_PER_YEAR", "Annual ED visits in the brief", ARCHITECTURE)
    cfg("ADMISSION_RATE", "Share of ED visits resulting in an admission in the brief", ARCHITECTURE, percent)
    cfg("ED_ADMISSIONS_PER_YEAR", "Annual ED admissions used to annualize capacity", BUDGET)
    cfg("ED_TOTAL_SPACES", "ED treatment spaces in the brief, including fast-track and specialty rooms", ARCHITECTURE)
    cfg("INPATIENT_BEDS", "Inpatient beds in the brief", ARCHITECTURE)
    cfg("ICU_BEDS", "ICU beds included in the inpatient bed count", ARCHITECTURE)
    cfg("TARGET_OCCUPANCY", "Typical inpatient occupancy in the brief", ARCHITECTURE, percent)
    cfg("TYPICAL_OPEN_BEDS", "Typical open inpatient beds in the brief", ARCHITECTURE)
    cfg("WINTER_UPLIFT", "Additional visit volume in winter in the brief", ARCHITECTURE, percent)
    cfg("MEDIAN_BOARDING_H", "Case median boarding after the admit decision", ARCHITECTURE, decimal(" h"))
    cfg("MEDIAN_DOOR_TO_PROVIDER_MIN", "Case median arrival-to-provider wait", ARCHITECTURE, decimal(" min", 0))
    cfg("LWBS_RATE", "Case share leaving the ED before seeing a provider", ARCHITECTURE, percent)
    cfg("FOLLOW_UP_COMPLETION", "Case follow-up visit completion, outside this prototype's scope", ARCHITECTURE, percent)
    for key, label, fmt in (
        ("boarding_h", "median boarding", decimal(" h")),
        ("door_to_provider_min", "median arrival-to-provider wait", decimal(" min", 0)),
        ("lwbs", "share leaving before seeing a provider", percent),
        ("follow_up", "follow-up completion", percent),
    ):
        low, high = config.NATIONAL[key]
        add(f"national.{key}", f"{fmt(low)} to {fmt(high)}", f"National benchmark in the brief for {label}",
            ARCHITECTURE, CONFIG, f"NATIONAL[{key!r}]")
    for group, share in config.PAYER_MIX_BRIEF.items():
        add(f"mix.{group}", percent(share), f"Case ED payer mix for {group}", ARCHITECTURE,
            CONFIG, f"PAYER_MIX_BRIEF[{group!r}]")
    for key, label, formatter in (
        ("DOOR_TO_PROVIDER_BY_PAYER_MIN", "median arrival-to-provider wait", decimal(" min", 0)),
        ("LWBS_BY_PAYER", "share leaving before seeing a provider", percent),
    ):
        for group, value in getattr(config, key).items():
            add(f"{key}.{group}", formatter(value), f"Case {label} for {group}", RISK, CONFIG, f"{key}[{group!r}]")
    cfg("ANNUAL_BUDGET", "Annual innovation budget cap in the brief", BUDGET, money)
    cfg("BUDGET_18_MONTHS", "Total innovation budget cap for the case rollout", BUDGET, money)
    for key, label in (
        ("BOARDING_COST_PER_BED_HOUR", "Case capacity value of a boarded ED room-hour"),
        ("COST_NURSE_PER_H", "Case hourly cost of an ED nurse"),
        ("COST_PHYSICIAN_PER_H", "Case hourly cost of an ED physician"),
        ("COST_APP_PER_H", "Case hourly cost of an advanced practice provider"),
        ("COST_ADMIN_PER_H", "Case hourly cost of a registration or administrative worker"),
        ("NET_REVENUE_PER_VISIT", "Case average net revenue per ED visit"),
    ):
        cfg(key, label, BUDGET, money)
    cfg("OVERTIME_MULTIPLIER", "Case overtime multiplier", BUDGET, decimal("×"))

    add("validation", f"{validation['passed']} of {validation['total']}",
        "Calibration checks passed in the main synthetic year", ARCHITECTURE, VALIDATION, "passed, total")
    for index, year in enumerate(validation["replication_years"]):
        add(f"validation.replication.{index}", f"{year['passed']} of {year['total']}",
            f"Checks passed in replication with seed {year['seed']}", ARCHITECTURE, VALIDATION,
            f"replication_years[{index}].passed, .total, .seed")

    default = scenarios["results"]["default"]
    summary = default["summary"]
    add("window", scenarios["window"], "Comparison window for each paired run", BUDGET, SCENARIOS, "window")
    add("runs", count(len(scenarios["seeds"])), "Synthetic runs in the paired scenario comparison",
        BUDGET, SCENARIOS, "seeds (entry count)")

    # ---- results as rounded ranges, introduced by the break-even point (models/impact_ranges.json)
    be = ranges["break_even"]
    add("break_even", f"{be['minutes_per_admission']} min", "Break-even: minutes saved per admission at which freed "
        "capacity ($350 x 13,600 admissions) equals the $500,000 yearly budget", BUDGET, RANGES,
        "break_even.minutes_per_admission")
    minutes = lambda x: f"{x:g} min"  # noqa: E731
    for i, sc in enumerate(ranges["scenarios"]):
        name = sc["name"]
        add(f"range.{name}.minutes", span(sc["minutes_saved_per_admission"], minutes),
            f"{name} scenario: minutes of boarding saved per admission", BUDGET, RANGES,
            f"scenarios[{i}].minutes_saved_per_admission")
        add(f"range.{name}.capacity", span(sc["freed_capacity_per_year_usd_m"], usd_m),
            f"{name} scenario: freed capacity a year, not cash", BUDGET, RANGES,
            f"scenarios[{i}].freed_capacity_per_year_usd_m")
        add(f"range.{name}.wait", span(sc["provider_wait_change_min"], signed(" min")),
            f"{name} scenario: change in median wait to see a provider, simulated winter quarter", BUDGET, RANGES,
            f"scenarios[{i}].provider_wait_change_min")
        add(f"range.{name}.walkouts", span(sc["walkout_change_pts"], signed(" pp", 1)),
            f"{name} scenario: change in the share leaving before being seen, simulated winter quarter", BUDGET,
            RANGES,
            f"scenarios[{i}].walkout_change_pts")
    for i, part in enumerate(ranges["parts"]):
        add(f"part.{part['part']}", span(part["minutes_saved_per_admission"], minutes),
            f"{part['part']} alone (Cautious settings): minutes saved per admission", BUDGET, RANGES,
            f"parts[{i}].minutes_saved_per_admission")
    for i, gap in enumerate(ranges["equity"]):
        add(f"equity.{i}", gap["verdict"], f"Payer gap in the Expected scenario: {gap['gap']}", RISK, RANGES,
            f"equity[{i}].verdict")
    for i, option in enumerate(ranges["staffing_alternative"]):
        add(f"staffing.{i}", money(option["annual_cost_usd"]), f"Traditional option, cost a year: {option['option']}",
            BUDGET, RANGES, f"staffing_alternative[{i}].annual_cost_usd")
    add("tool_cost", span(ranges["tool_cost"]["per_year_usd"], money), "Tool cost a year (our $550K to $650K "
        "18-month ballpark, per year)", BUDGET, RANGES, "tool_cost.per_year_usd")
    add("idle_reserved_bed_hours", across_runs(summary["idle_reserved_bed_hours"], count, 100),
        "Trade-off: inpatient bed-hours held idle by reservations, simulated winter quarter (Cautious)", BUDGET,
        SCENARIOS,
        f"{DEFAULT}.summary.idle_reserved_bed_hours.{{min, max}}")
    for index, item in enumerate(default["guardrail"]):
        add(f"guardrail.{index}", item["Status"], f"Equity guardrail (Cautious), {item['Gap']} {item['Measure']}",
            RISK, SCENARIOS, f"{DEFAULT}.guardrail[{index}].Status")
    for key, label, fmt in (
        ("door_to_provider_gap_min", "Wait gap widening tolerance for the equity guardrail", decimal(" min", 0)),
        ("lwbs_gap_pts", "Walkout gap widening tolerance for the equity guardrail", decimal(" pp")),
        ("consecutive_months", "Consecutive months of widening that trigger the equity guardrail", count),
    ):
        add(f"guardrail.rule.{key}", fmt(config.EQUITY_GUARDRAIL[key]), label,
            RISK, CONFIG, f"EQUITY_GUARDRAIL[{key!r}]")

    for model, label in (("admission", "ED admission"), ("discharge", "Discharge")):
        chosen = metrics[model]["chosen"]
        add(f"{model}.auc", f"{metrics[model]['test'][chosen]['auc']:.3f}",
            f"{label} model test AUC, ability to rank outcomes", DEMO, METRICS, f"{model}.test.{chosen}.auc")
        policy = "deployed_policy" if model == "admission" else "at_threshold"
        for key, meaning in (
            ("precision", "share of flags that were correct"),
            ("recall", "share of eventual outcomes caught"),
        ):
            add(f"{model}.{key}", percent(metrics[model][policy][key]), f"{label} flag {key}, {meaning}",
                DEMO, METRICS, f"{model}.{policy}.{key}")
    for model, field, label, fmt in (
        ("admission", "median_h", "Median lead from first batch flag to admission decision for correct flags",
         decimal(" h")),
        ("admission", "alerts_per_day", "ED admission flags per day in the test quarter", decimal()),
        ("discharge", "median_h_true_positive", "Median time from correctly flagged rounds to discharge",
         decimal(" h")),
    ):
        add(f"{model}.{field}", fmt(metrics[model]["lead_time"][field]), label,
            DEMO, METRICS, f"{model}.lead_time.{field}")
    for key in ("precision", "recall"):
        add(f"note_reader.{key}", percent(metrics["note_reader"]["overall"][key]),
            f"Rule-based note reader {key} on all synthetic notes (the discharge model's feature source)",
            DEMO, METRICS, f"note_reader.overall.{key}")
    reader = metrics["note_reader"]
    if "llm" in reader:
        add("note_reader.sample_n", count(reader["llm"]["sample_n"]),
            "Notes in the sealed evaluation sample B read by the local model", DEMO, METRICS,
            "note_reader.llm.sample_n")
        for who, label in (("llm", "AI note reader (local model)"), ("rules", "Rule-based reader"),
                           ("combined", "AI reader and rules combined")):
            for key in ("precision", "recall", "f1"):
                add(f"note_reader.{who}.{key}", percent(reader[who]["overall"][key]),
                    f"{label} {key.upper() if key == 'f1' else key} on the evaluation sample", DEMO, METRICS,
                    f"note_reader.{who}.overall.{key}")
        if "llm_checks_g1" in reader:
            add("note_reader.g1.precision", percent(reader["llm_checks_g1"]["overall"]["precision"]),
                "The same model answers under the first reader's checks (g1): precision on sample B", DEMO, METRICS,
                "note_reader.llm_checks_g1.overall.precision")
        stress = reader.get("stress", {})
        for who, label in (("llm", "AI note reader"), ("rules", "Rule-based reader")):
            if who in stress:
                add(f"note_reader.stress.{who}", f"{percent(stress[who]['overall']['recall'])} recall, "
                    f"{percent(stress[who]['overall']['precision'])} precision",
                    f"{label} on the new-phrasing stress set (wording neither reader was built on)", DEMO, METRICS,
                    f"note_reader.stress.{who}.overall.{{recall, precision}}")
        for i, h in enumerate(reader.get("history", [])):
            add(f"note_reader.history.{i}", f"{percent(h['llm']['overall']['precision'])} precision, F1 "
                f"{h['llm']['overall']['f1']:.2f}", f"First AI reader ({h['reader']}) on sample {h['sample']}, "
                "kept for comparison", DEMO, METRICS, f"note_reader.history[{i}].llm.overall.{{precision, f1}}")
        add("note_reader.llm_run.wall_minutes", decimal(" min")(reader["llm_run"]["wall_minutes"]),
            "Time for the local model to read the evaluation sample, the stress set and every demo-day note",
            ARCHITECTURE, METRICS, "note_reader.llm_run.wall_minutes")
    for index, audit in enumerate(metrics["admission"]["fairness_deployed"]):
        add(f"audit.{audit['group']}", percent(audit["fnr"]), f"Missed share of eventual admissions for {audit['group']}",
            RISK, METRICS, f"admission.fairness_deployed[{index}].fnr")
    # every score the Fairness and Oversight page shows by group (measured on synthetic test months)
    for model, key, label in (("admission", "fairness_deployed", "ED admission flags as deployed"),
                              ("admission", "fairness_fixed", "ED admission flags at a fixed 70% threshold"),
                              ("admission", "fairness_with_payer", "comparison model that sees insurance (not used)"),
                              ("discharge", "fairness", "Discharge list")):
        for index, audit in enumerate(metrics[model].get(key, [])):
            if audit.get("auc") is None:
                continue
            add(f"fair.{model}.{key}.{audit['group']}",
                f"AUC {audit['auc']:.3f}, calibration {audit['calibration_gap_pts']:+.1f} pts, missed "
                f"{percent(audit['fnr'])}, flagged {percent(audit['flag_rate'])}",
                f"{label}, {audit['group']}", RISK, METRICS,
                f"{model}.{key}[{index}].{{auc, calibration_gap_pts, fnr, flag_rate}}")

    for key, meaning in (
        ("adoption", "Share of flags acted on in the default simulated scenario"),
        ("staff_response_delay_h", "Minimum staff response delay after triage in the default simulated scenario"),
        ("threshold", "Base admission alert threshold in the default simulated scenario"),
        ("discharge_hours_saved", "Time a discharge task can recover in the default simulated scenario"),
    ):
        add(f"setting.{key}", scenario_format(key, default["scenario"][key]), meaning,
            ROADMAP, SCENARIOS, f"{DEFAULT}.scenario.{key}")
    for key, meaning in (
        ("moving", "Default use of the crowding-adjusted admission threshold"),
        ("scope", "Default scenario scope"),
        ("admission_side", "Early admission preparation in the default scenario"),
        ("discharge_side", "Discharge work in the default scenario"),
    ):
        value = default["scenario"][key]
        add(f"setting.{key}", ("On" if value else "Off") if isinstance(value, bool) else value,
            meaning, ROADMAP, SCENARIOS, f"{DEFAULT}.scenario.{key}")
    cfg("BED_BOARD_DELAY_CUT", "Our assumption: cut in housekeeping notification and bed request processing with "
        "the bed board (Expected and Full rollout only)", ROADMAP, percent_whole)
    for key, meaning in (("adoption", "Share of flags acted on in the Full rollout scenario"),
                         ("threshold", "Base admission alert threshold in the Full rollout scenario"),
                         ("discharge_hours_saved", "Time a discharge task can recover in the Full rollout scenario")):
        add(f"full_rollout.{key}", scenario_format(key, config.FULL_ROLLOUT[key]), meaning, ROADMAP, CONFIG,
            f"FULL_ROLLOUT[{key!r}]")
    cfg("MOVING_THRESHOLD_FLOOR", "Floor for the crowding-adjusted admission threshold", ROADMAP, percent)
    cfg("MOVING_THRESHOLD_CEILING", "Ceiling for the crowding-adjusted admission threshold", ROADMAP, percent)
    cfg("DISCHARGE_LIST_THRESHOLD", "Threshold for a discharge-probability flag at rounds", DEMO, percent)
    cfg("BATCH_INTERVAL_MIN", "Interval for batching bed requests", ARCHITECTURE, decimal(" min", 0))
    cfg("RESERVATION_EXPIRY_H", "Time after which an unused reservation is released", RISK, decimal(" h", 0))
    for key, result in scenarios["results"].items():
        if key == "default" or not result["scenario"]["adoption"]:  # adoption 0: nothing acted on, no estimate
            continue
        meaning = f"Minutes saved per admission (range), {result['label']}"
        if key == "pilot":
            meaning += f" ({result['scenario']['scope']})"
        add(f"sensitivity.{key}", span(RG.minutes_range(result), minutes), meaning,
            BUDGET, SCENARIOS, f"results[{key!r}].summary.mean_minutes_saved_per_admission.{{min, max}}")
    cfg("PITCH_BOARDING_CUTS_MIN", "Pitch assumptions for minutes saved per admission", BUDGET,
        lambda values: ", ".join(f"{value} min" for value in values))

    # ---- budget, value, ROI, goals and gates (models/plan.json, built by scripts/build_plan.py)
    b = plan["budget"]
    for phase, label in (("pilot", "Budget for Phase 1, the pilot (Months 1 to 6)"),
                         ("scale", "Budget for Phase 2, scale (Months 7 to 18)"),
                         ("run", "Yearly running cost after Month 18")):
        add(f"budget.{phase}", money(b["by_phase"][phase]), label, BUDGET, PLAN, f"budget.by_phase.{phase}")
        add(f"budget.hidden.{phase}", money(b["hidden_by_phase"][phase]),
            f"Hidden costs in that budget (clinician training time, security review, vendor fees): {phase}",
            BUDGET, PLAN, f"budget.hidden_by_phase.{phase}")
    add("budget.total", money(b["total_18_months"]), "Total cost over the 18 months, against the $750,000 cap",
        BUDGET, PLAN, "budget.total_18_months")
    add("budget.year1", money(b["year_1"]), "Year 1 spend (Months 1 to 12), against the $500,000 a year cap",
        BUDGET, PLAN, "budget.year_1")
    add("budget.headroom", money(b["headroom_18_months"]), "Budget left over the 18 months", BUDGET, PLAN,
        "budget.headroom_18_months")
    t = plan["traditional"]["total"]
    add("traditional.fte", decimal(" FTE")(t["fte"]), "Staff needed to give the same coverage by hand",
        BUDGET, PLAN, "traditional.total.fte")
    add("traditional.cost", f"{money(t['hired'])}, {millions(t['overtime'])}, {millions(t['agency'])}",
        "Yearly cost of that coverage hired, on overtime, or through an agency", BUDGET, PLAN,
        "traditional.total.{hired, overtime, agency}")
    v = plan["value"]
    k = lambda x: f"${x:,.0f}K"  # noqa: E731
    for key, label, fmt, step, scale in (
        ("walkouts_avoided", "Walkouts avoided per year (relative drop applied to the brief's baseline)", count, 100, 1),
        ("walkout_revenue", "Cash from recovered visits per year (50% of avoided walkouts at $1,500)", usd_m, .1, 1e-6),
        ("overtime_avoided", "Nurse overtime avoided per year", k, 10, 1e-3),
        ("cash_value", "Total cash value per year (recovered visits plus overtime)", usd_m, .1, 1e-6),
    ):
        add(f"value.{key}", across_runs(v[key], fmt, step, scale), f"{label} (Cautious)", BUDGET, PLAN,
            f"value.{key}.{{min, max}}")
    r = plan["roi"]
    cautious = ranges["scenarios"][0]
    run_cost = r["run_cost_per_year"]
    add("roi.capacity", span(RG.capacity_roi_range(cautious["minutes_saved_per_admission"], run_cost),
                             lambda x: f"{x:,}%"),
        "Yearly ROI on freed capacity (Cautious freed capacity against the yearly running cost)", BUDGET, RANGES,
        "scenarios[0].freed_capacity_per_year_usd_m")
    add("roi.cash", across_runs(r["cash"]["roi_per_year"], lambda x: f"{x:,}%", 10, 100),
        "Yearly cash ROI (recovered visits and overtime only, Cautious)", BUDGET, PLAN,
        "roi.cash.roi_per_year.{min, max}")
    cap_pay, cash_pay = r["capacity"]["payback_month_range"], r["cash"]["payback_month_range"]
    late = lambda m: f"month {m}" if m else "after month 60"  # noqa: E731
    add("roi.payback", f"month {cap_pay[0]} to {cap_pay[1]} (capacity), month {cash_pay[0]} to {late(cash_pay[1])} "
        "(cash)", "Payback counted from the start of the pilot (Cautious)", BUDGET, PLAN,
        "roi.capacity.payback_month_range, roi.cash.payback_month_range")
    add("roi.cost_to_serve", span(RG.cost_to_serve_range(cautious["minutes_saved_per_admission"], run_cost),
                                  lambda x: f"${x:,}"),
        "Yearly cost per ED room-hour freed (Cautious)", BUDGET, RANGES, "scenarios[0].minutes_saved_per_admission")
    for i, g in enumerate(plan["goals"]):
        if "target" in g and g["target"] is not None:
            unit = " h" if g["unit"] == "h" else "%"
            add(f"goal.{g['id']}", f"{g['baseline']:.1f}{unit} to {g['target']:.1f}{unit}",
                f"Month 18 goal {g['id']}: {g['label']}", ROADMAP, PLAN, f"goals[{i}].{{baseline, target}}")
        elif g["kind"] == "equity":
            for j, part in enumerate(g["parts"]):
                fmt = (lambda x: f"{x:.0f}") if part["unit"] == "min" else (lambda x: f"{x:.1f}")
                add(f"goal.{g['id']}.{j}", f"{fmt(part['baseline'])} to {fmt(part['target'])} {part['unit']}",
                    f"Month 18 equity goal: {part['measure']}", ROADMAP, PLAN,
                    f"goals[{i}].parts[{j}].{{baseline, target}}")
    met = sum(gate["status"].startswith("Met") for gate in plan["pilot_gates"])
    add("gates.met", f"{met} of {len(plan['pilot_gates'])}", "Pilot gates met in the synthetic test (the rest "
        "need pilot data or are not met)", ROADMAP, PLAN, "pilot_gates (entry count)")
    cm = metrics["admission"].get("fairness_case_mix", {}).get("rows", [])
    for i, row in enumerate(cm):
        if row["group"] == config.UNINSURED and "unexplained_pts" in row:
            add("bias.uninsured", f"{row['observed_miss_rate']:.1%} missed, {row['expected_from_case_mix']:.1%} "
                f"expected, {row['unexplained_pts']:+.1f} pts unexplained", "Uninsured admissions missed by the flags, "
                "the rate expected from triage level and age, and the part they do not explain (pre-launch bias test)",
                RISK, METRICS,
                f"admission.fairness_case_mix.rows[{i}].{{observed_miss_rate, expected_from_case_mix, unexplained_pts}}")
    for i, o in enumerate(plan["phase2"]["options"]):
        if o["base_threshold"] != config.ALERT_THRESHOLD:
            saved = span(RG.spread(o["minutes_saved"], config.RANGE_STEP["minutes"]), minutes)
            add(f"phase2.{o['base_threshold']}", f"{saved}, {o['precision']:.1%}, "
                f"{o['case_gaps_narrowed']} of {o['case_gaps_total']} gaps narrowed",
                f"Phase 2 option, base threshold {o['base_threshold']:.0%}: minutes saved, flag precision, case gaps",
                ROADMAP, PLAN, f"phase2.options[{i}].{{minutes_saved.min, minutes_saved.max, precision, "
                "case_gaps_narrowed}")
    return rows


def render_numbers(rows: dict[str, Number]) -> str:
    preamble = """# Presentation numbers

Regenerate with `python scripts/export_numbers.py`. This table reads the saved simulation,
model, and calibration outputs and the case values in the app configuration.

Halvian's case baselines describe the fictional hospital and are exact. Simulated results
are never single numbers: each is the spread across three synthetic years (paired runs on
the same synthetic patients, Oct to Dec test quarter), widened outward to round numbers
(minutes to the nearest 5, dollars to $0.1M, waits to the nearest minute, walkouts to 0.1
points), introduced by the break-even point. Freed capacity is the minute range at the
brief's $350 per boarded ED room-hour and 13,600 admissions a year; it is capacity, not
cash. Payer gap verdicts compare the pooled gap against Commercial with the saved flat
tolerance. Goals and ROI use the Cautious scenario (today's defaults). `pp` means
percentage points.

Model estimate from a synthetic Halvian calibrated to the case brief. It shows which levers
matter and how large the payoff could be under stated assumptions. It is not evidence from
a real hospital.

| Number | Plain-English meaning | Rubric section | Source file and key |
| --- | --- | --- | --- |"""
    return "\n".join([preamble, *(row.markdown() for row in rows.values()), ""])


def export_numbers(
    scenarios: dict | None = None, metrics: dict | None = None, validation: dict | None = None
) -> dict[str, Number]:
    rows = collect_numbers(
        read_json(SCENARIOS) if scenarios is None else scenarios,
        read_json(METRICS) if metrics is None else metrics,
        read_json(VALIDATION) if validation is None else validation,
        read_json(PLAN),
    )
    (ROOT / "docs" / "NUMBERS.md").write_text(render_numbers(rows), encoding="utf-8")
    return rows


if __name__ == "__main__":
    export_numbers()
