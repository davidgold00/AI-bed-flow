"""Write docs/STRATEGY.md: slide-ready roadmap, budget, ROI and risk content for the video.

    python scripts/build_plan.py && python scripts/export_strategy.py

Every number comes from models/plan.json, models/scenarios.json, models/metrics.json or
halvian/config.py; tests/test_strategy.py fails if the file is stale.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from halvian import config as C  # noqa: E402
from halvian import ranges as RG  # noqa: E402

OUT = ROOT / "docs" / "STRATEGY.md"


def money(v: float) -> str:
    if abs(v) >= 1e6:
        return f"${v / 1e6:.2f}M"
    return f"${v:,.2f}" if abs(v) < 1000 and v != round(v) else f"${v:,.0f}"


def rng(d: dict, fmt, step: float, scale: float = 1.0) -> str:
    """A saved {mean, min, max} reading as a range across the synthetic years, widened to ``step``."""
    lo, hi = RG.spread(d, step, scale)
    return f"{fmt(lo)} to {fmt(hi)}"


def pct_change(rel: list[float] | dict) -> str:
    lo, hi = (min(rel), max(rel)) if isinstance(rel, list) else (rel["min"], rel["max"])
    return RG.span(RG.widen(100 * lo, 100 * hi, 1), lambda x: f"{x:+d}%")


def usd_m(x: float) -> str:
    return f"${x:.1f}M"


def table(head: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(head) + " |", "| " + " | ".join("---" for _ in head) + " |"]
    lines += ["| " + " | ".join(str(c).replace("|", "/") for c in r) + " |" for r in rows]
    return "\n".join(lines)


def num(v, unit: str) -> str:
    if v is None:
        return "new measure"
    if isinstance(v, list):
        return f"{v[0]:g}% to {v[1]:g}%"
    if unit == "h":
        return f"{v:,.0f} h" if v >= 100 else ("0 h" if v == 0 else f"{v:.1f} h")
    if unit == "min":
        return f"{v:.0f} min"
    if unit in ("%",):
        return f"{v:.1f}%" if v < 10 else f"{v:.0f}%"
    if unit == "pp":
        return f"{v:.1f} pp"
    if unit == "$":
        return f"${v:,.0f}"
    if unit == "x":
        return f"{v:.0%}"
    return f"{v:,.0f}"


def target_text(k: dict) -> str:
    value = num(k["target"], k["unit"])
    if k.get("direction") == "band":
        return f"between {value.replace(' to ', ' and ')}"
    if k["unit"] == "x" and k["target"] == 0:
        return "break-even or better"
    return f"{value} or {'less' if k.get('direction') == 'down' else 'more'}"


def scenarios_section(ranges: dict) -> str:
    """Break-even first, then the three scenarios and the parts as ranges, staffing costs and sources."""
    be = ranges["break_even"]
    lines = ["### Break-even and the simulated range (rubric 3.2 and 3.3)", "",
             f"**Break-even: about {be['minutes_per_admission']} minutes saved per admission.** {be['explanation']}", "",
             f"*{ranges['caveat']}*", "",
             table(["Scenario", "Settings", "Minutes saved per admission", "Freed capacity a year (not cash)",
                    "Change in wait to see a provider (winter quarter)",
                    "Change in share leaving unseen (winter quarter)"],
                   [[s["name"], s["settings"], RG.span(s["minutes_saved_per_admission"]),
                     RG.span(s["freed_capacity_per_year_usd_m"], usd_m),
                     RG.span(s["provider_wait_change_min"], lambda x: f"{x:+d} min"),
                     RG.span(s["walkout_change_pts"], lambda x: f"{x:+.1f} pts")] for s in ranges["scenarios"]]),
             ""]
    below = [s["name"] for s in ranges["scenarios"] if s["minutes_saved_per_admission"][0] < be["minutes_per_admission"]]
    lines += [("Every scenario's range sits above the break-even." if not below else
               f"Below or straddling the break-even: {', '.join(below)}."), "",
              "Each part of the tool on its own (Cautious settings; the parts overlap, so they do not add up):", "",
              table(["Part", "Minutes saved per admission"],
                    [[x["part"], RG.span(x["minutes_saved_per_admission"])] for x in ranges["parts"]]), "",
              "Payer gaps against Commercial in the Expected scenario (payer is never a model input):", "",
              table(["Gap", "Verdict"], [[e["gap"], e["verdict"]] for e in ranges["equity"]]), "",
              "Traditional staffing options, cost only at the brief's rates (we do not estimate how much boarding "
              "each would cut):", "",
              table(["Option", "Cost a year", "Assumption"],
                    [[x["option"], f"${x['annual_cost_usd'] / 1e3:,.0f}K", x["assumption"]]
                     for x in ranges["staffing_alternative"]]
                    + [["**The tool**", RG.span([c / 1e3 for c in ranges["tool_cost"]["per_year_usd"]],
                                                lambda x: f"${x:,.0f}K"), ranges["tool_cost"]["note"]]]), "",
              "Published evidence:", ""]
    lines += [f"- [{x['source']}]({x['url']}): {x['finding']}" for x in ranges["references"]]
    lines += ["", ranges["least_certain"], ""]
    return "\n".join(lines)


def adoption_rows(scenarios: dict, be: int) -> list[list[str]]:
    rows = []
    for level in scenarios["sweeps"]["adoption"]:
        key = "default" if level == C.IMPACT_DEFAULTS["adoption"] else f"adoption={level:g}"
        result = scenarios["results"].get(key)
        if result is None or not level:
            continue
        minutes = RG.minutes_range(result)
        rows.append([f"{level:.0%}", RG.span(minutes), RG.span(RG.usd_m_range(minutes), usd_m),
                     "yes" if minutes[0] >= be else ("no" if minutes[1] <= be else "partly")])
    return rows


def render(plan: dict, scenarios: dict, metrics: dict) -> str:
    b, t, v, r = plan["budget"], plan["traditional"], plan["value"], plan["roi"]
    ranges = RG.build(scenarios, plan)
    cautious = ranges["scenarios"][0]
    be = ranges["break_even"]["minutes_per_admission"]
    run_cost, minutes = r["run_cost_per_year"], cautious["minutes_saved_per_admission"]
    # capacity measures all follow the Cautious minute range, so they agree with each other
    cost_to_serve = RG.span(RG.cost_to_serve_range(minutes, run_cost), lambda x: f"${x:,}")
    hours = RG.room_hours_range(minutes)

    def value_18(x: dict) -> str:
        per_year = x["value_per_year"]
        lo, hi = (x["value_18_months"] * per_year[k] / per_year["mean"] for k in ("min", "max"))
        return RG.span(RG.widen(lo / 1e6, hi / 1e6, 0.1), usd_m)

    def payback(x: dict) -> str:
        early, late = x.get("payback_month_range", [x["payback_month"]] * 2)
        late_text = f"month {late}" if late else "after Month 60"
        text = f"in month {early} to {late_text}" if early != late else f"in month {early}"
        return text + (" (after the 18 months, at the yearly run cost)" if (late or 999) > C.PLAN_MONTHS else "")
    out: list[str] = []
    w = out.append
    w("# Strategy numbers for the slides")
    w("")
    w("Generated by `python scripts/build_plan.py && python scripts/export_strategy.py`. Every figure comes "
      "from `models/plan.json`, `models/scenarios.json`, `models/metrics.json` or `halvian/config.py`. "
      "Simulated results are estimates from synthetic patients, not real-world evidence, and are shown only as "
      "ranges across three synthetic years widened to round numbers (minutes to the nearest 5, dollars to $0.1M), "
      "never as single numbers. The case brief's own numbers are exact. Goals and ROI use the Cautious scenario "
      "(today's default settings). Budget assumptions are "
      "tagged B1 to B20 in `halvian/config.py` and listed at the end. The rubric lines this page serves: "
      "1.3 and 1.4, 2.1 to 2.3, 3.1 to 3.3 and 4.1 to 4.3.")
    w("")
    # ------------------------------------------------------------------ architecture
    w(architecture(metrics, plan))
    # ------------------------------------------------------------------ roadmap
    w("## 2. Roadmap and milestones")
    w("")
    w("### Month 18 goals (rubric 2.1)")
    w("")
    w(f"Each target is the brief's baseline moved by {C.GOAL_TARGET_SHARE:.0%} of the change the paired "
      "simulation shows in the Cautious scenario, because real adoption is messier than a simulation, rounded to "
      "the brief's own precision.")
    w("")
    rows = []
    for g in plan["goals"]:
        if "parts" in g and g["kind"] != "adoption and safe use":
            for p in g["parts"]:
                sim = p["simulated"]
                rows.append([g["id"] + " " + g["goal"], p["measure"], num(p["baseline"], p["unit"]),
                             num(p["target"], p["unit"]), f"Gap {sim['verdict'].lower()}"])
        elif "parts" in g:
            for p in g["parts"]:
                rows.append([g["id"] + " " + g["goal"], p["measure"], "new measure", num(p["target"], p["unit"]),
                             "measured in the pilot"])
        else:
            rows.append([g["id"] + " " + g["goal"], g["label"], num(g["baseline"], g["unit"]),
                         num(g["target"], g["unit"]), pct_change(g["simulated_relative_change"])])
    w(table(["Goal", "Measure", "Baseline (brief)", "Month 18 target", "Simulated change (range)"], rows))
    w("")
    w("How we track each goal and what we do if it slips:")
    w("")
    for g in plan["goals"]:
        w(f"- **{g['id']}.** Track: {g['track']} If off track: {g['if_off_track']}")
    w(f"- **Equity guardrail.** {plan['goals'][2]['guardrail']}")
    w("")
    w("### Milestones (rubric 2.2 and 2.3)")
    w("")
    w(table(["Months", "Phase", "Milestone", "Owner", "Done when"],
            [[f"{m['start']}" if m["start"] == m["end"] else f"{m['start']} to {m['end']}",
              "Pilot" if m["phase"] == "pilot" else "Scale", m["milestone"], m["owner"], m["done_when"]]
             for m in plan["milestones"]]))
    w("")
    w("### Gates to move from the pilot to Phase 2 (rubric 2.2)")
    w("")
    w("Checked against the synthetic evidence where it exists. A gate the synthetic data does not meet is "
      "shown as not met; the rest can only be measured with Halvian's staff in the pilot.")
    w("")

    def gate_value(g):
        x = g["synthetic_value"]
        if x is None:
            return "pilot data"
        if "minutes" in g["threshold"]:  # a simulated result: say whether it holds, with the range
            lo, hi = RG.minutes_range(scenarios["results"]["pilot"])
            return f"{'above' if x > 0 else 'not above'} zero in every run ({lo} to {hi} min range)"
        return f"{x:.1%}" if x <= 1 and "points" not in g["threshold"] and "minutes" not in g["threshold"] else (
            f"{x:.1f} points" if "points" in g["threshold"] else f"{x:.1f} min (worst run)")
    w(table(["Gate", "Threshold", "Synthetic value", "Status"],
            [[g["gate"], g["threshold"], gate_value(g), g["status"]] for g in plan["pilot_gates"]]))
    w("")
    cm = metrics["admission"].get("fairness_case_mix", {}).get("rows", [])
    if cm:
        w("**Pre-launch bias test (admission flags).** " + metrics["admission"]["fairness_case_mix"]["definition"])
        w("")
        w(table(["Payer group", "Admissions", "Missed", "Expected from case mix", "Unexplained"],
                [[x["group"], f"{x['admissions']:,}", f"{x['observed_miss_rate']:.1%}",
                  f"{x['expected_from_case_mix']:.1%}", f"{x['unexplained_pts']:+.1f} pts"]
                 for x in cm if "unexplained_pts" in x]))
        w("")
        w("The higher miss rate for Uninsured and Medicaid/CHIP admissions comes from who arrives (younger "
          "patients, fewer at triage levels 1 and 2), not from the model scoring similar patients differently. "
          "Triage levels themselves can carry bias in real data, so the pilot reruns this test on Halvian's "
          "records in silent mode. A missed flag means the usual process, never a lower priority.")
        w("")
    w("Pilot success metrics, tracked weekly on Medicine A and its ED admissions (rubric 2.2):")
    w("")
    w(table(["Area", "Metric", "Source"], [
        ["Operations", "Boarding for patients admitted to Medicine A; Medicine A discharges before noon; minutes from "
         "a bed request to an assigned bed", "EHR timestamps"],
        ["Adoption", "Share of flags acted on; override rate and reasons; rounds-list items worked by the case manager",
         "Decision log"],
        ["Patient experience", "Waiting-room minutes to a provider; a two-question survey at discharge (\"I knew what "
         "was happening next\", \"my discharge was not delayed by paperwork\"); complaints about discharge delays",
         "Survey, patient relations"],
        ["Equity", "Gap table by payer for waits, walkouts and boarding; the bias test on live flags", "EHR, monthly"],
        ["Safety (balancing)", "72-hour ED returns and 30-day readmissions for patients discharged from the rounds list; "
         "safety events linked to the tool", "EHR, incident reports"],
    ]))
    w("")
    w("Adoption plan for skeptical clinicians and patients (rubric 2.2):")
    w("")
    for line in ADOPTION:
        w(f"- {line}")
    w("")
    p2 = plan["phase2"]
    w("### Using pilot results to adjust before scaling (rubric 2.3)")
    w("")
    w(f"{p2['question']} The same synthetic patients at three base thresholds (payer-blind):")
    w("")
    w(table(["Base threshold", "Minutes saved per admission", "Flag precision", "Alerts a day",
             "Medicaid/CHIP and Uninsured gaps narrowed", "Gaps that widened"],
            [[f"{o['base_threshold']:.0%}", rng(o["minutes_saved"], lambda x: f"{x:g}", C.RANGE_STEP["minutes"]),
              f"{o['precision']:.1%}" if o["precision"] is not None else "n/a",
              f"{o['alerts_per_day']:.1f}" if o["alerts_per_day"] is not None else "n/a",
              f"{o['case_gaps_narrowed']} of {o['case_gaps_total']}",
              "; ".join(o["any_gap_widened"]) or "none"] for o in p2["options"]]))
    w("")
    w(f"Rule: {p2['rule']}")
    w("")
    w("Metrics as we scale (rubric 2.3): efficiency (boarding, room-hours freed, discharges before noon), patient "
      "outcomes (72-hour returns, 30-day readmissions, walkouts), clinician override rates by unit, the payer gap "
      "table, and cost to serve (yearly cost per ED room-hour freed). Targets are in the KPI table below.")
    w("")
    w("Long-term ownership (rubric 2.3): clinical informatics owns the tool (the tool owner), a data scientist "
      "maintains the models, and the AI oversight committee decides on retraining, pausing or retiring. After "
      f"Month 18 the tool costs {money(b['run_per_year'])} a year from the operating budget "
      "(budget table below). A tool is retired when it misses its goals for two quarters after a recovery plan, "
      "when a better approach replaces it, or when the EHR provides the same function.")
    w("")
    # ------------------------------------------------------------------ budget
    w("## 3. Budget and ROI")
    w("")
    w("### Budget by phase (rubric 3.1)")
    w("")
    cats = list(b["by_category"]["pilot"])
    w(table(["Category", "Phase 1: Pilot (Months 1 to 6)", "Phase 2: Scale (Months 7 to 18)",
             "Each year after Month 18"],
            [[c, *(money(b["by_category"][p][c]) for p in ("pilot", "scale", "run"))] for c in cats]
            + [["**Total**", *(f"**{money(b['by_phase'][p])}**" for p in ("pilot", "scale", "run"))],
               ["of which hidden costs (clinician training time, security, vendor fees)",
                *(money(b["hidden_by_phase"][p]) for p in ("pilot", "scale", "run"))]]))
    w("")
    ok = b["within_caps"]
    w(f"18 months: {money(b['total_18_months'])} against the brief's {money(b['caps']['18_months'])} "
      f"({'within' if ok['18_months'] else 'over'} the cap, {money(b['headroom_18_months'])} left). Year 1: "
      f"{money(b['year_1'])} against {money(b['caps']['per_year'])} a year "
      f"({'within' if ok['year_1'] else 'over'}). Spending is spread evenly within each phase.")
    w("")
    w("Every line, with quantity and rate (brief rates for nurses, physicians, advanced practice providers and "
      "administrative staff; training paid at the brief's 1.5x overtime because it happens off-shift):")
    w("")
    w(table(["Phase", "Category", "Item", "Quantity", "Rate", "Cost", "Hidden"],
            [["Pilot" if x["phase"] == "pilot" else "Scale" if x["phase"] == "scale" else "Yearly",
              x["category"], x["item"], f"{x['quantity']:,.1f} {x['unit']}".replace(".0 ", " "),
              money(x["rate"]), money(x["cost"]), "yes" if x["hidden"] else ""] for x in b["lines"]]))
    w("")
    w("Lower-cost and other alternatives:")
    w("")
    for a in b["alternatives"]:
        saving = f" (saves {money(-a['saving'])})" if a["saving"] else ""
        w(f"- **{a['option']}**{saving}. {a['note']}")
    w("")
    w("### Value against the traditional approach (rubric 3.2)")
    w("")
    w("The traditional approach: hire, pay overtime or contract staff to give the same coverage by hand.")
    w("")
    w(table(["Work done by hand", "Hours a year", "FTE", "Hired", "On overtime (1.5x)",
             f"Agency ({C.AGENCY_MULTIPLIER:g}x, least certain)"],
            [[x["task"], f"{x['hours_per_year']:,.0f}", f"{x['fte']:.1f}", money(x["hired"]), money(x["overtime"]),
              money(x["agency"])] for x in t["rows"]]
            + [["**Total**", f"{t['total']['hours_per_year']:,.0f}", f"{t['total']['fte']:.1f}",
                money(t["total"]["hired"]), money(t["total"]["overtime"]), money(t["total"]["agency"])],
               ["**The tool, each year after Month 18**", "", "", money(t["tool_per_year"]), "", ""]]))
    w("")
    w(f"Hiring for the same coverage costs {t['tool_vs_hiring_ratio']:.1f} times the tool's yearly cost.")
    w("")
    w(scenarios_section(ranges))
    w("Value of the gains each year in the Cautious scenario (today's default settings; ranges across the three "
      "synthetic years, widened to round numbers):")
    w("")
    k = lambda x: f"${x:,.0f}K"  # noqa: E731
    w(table(["Gain", "Per year", "How it is reached"],
            [["ED room-hours freed", RG.span(hours, lambda x: f"{x:,} h"),
              "Minutes saved per admission / 60 x the brief's 13,600 admissions"],
             ["Equivalent ED rooms open around the clock",
              RG.span(RG.widen(hours[0] / C.HOURS_PER_SEAT_YEAR, hours[1] / C.HOURS_PER_SEAT_YEAR, 0.1)),
              "Room-hours freed divided by 8,760 hours"],
             ["Freed capacity value (not cash)", RG.span(cautious["freed_capacity_per_year_usd_m"], usd_m),
              v["method"]["capacity_value"]],
             ["Walkouts avoided", rng(v["walkouts_avoided"], lambda x: f"{x:,}", 100),
              "Relative drop in the simulation applied to the brief's 3,400 walkouts a year"],
             ["Revenue from recovered visits (cash)", rng(v["walkout_revenue"], usd_m, 0.1, 1e-6),
              v["method"]["walkout_revenue"]],
             ["Overtime avoided (cash)", rng(v["overtime_avoided"], k, 10, 1e-3), v["method"]["overtime_avoided"]]]))
    w("")
    w("Least certain assumptions: " + " ".join(f"({i}) {x}" for i, x in enumerate(v["least_certain"], 1)))
    w("")
    w("### KPIs and ROI (rubric 3.3)")
    w("")
    w(table(["KPI", "Kind", "Baseline", "Month 18 target", "Simulated (range, Cautious)"],
            [[k["kpi"], k["kind"], num(k["baseline"], k["unit"]), target_text(k),
              k.get("simulated", "")] for k in plan["kpis"]]))
    w("")
    cap, cash = r["capacity"], r["cash"]
    w(f"ROI each year after Month 18, against {money(r['run_cost_per_year'])} a year:")
    w("")
    pct = lambda x: f"{x:,}%"  # noqa: E731
    w(f"- **On freed capacity (the brief's $350 per room-hour):** "
      f"{RG.span(RG.capacity_roi_range(minutes, run_cost), pct)} a year. "
      f"Over the 18 months, value {value_18(cap)} against cost {money(cap['cost_18_months'])}; pays back "
      f"{payback(cap)}.")
    w(f"- **Cash only (recovered visits and overtime):** {rng(cash['roi_per_year'], pct, 10, 100)} a year. "
      f"Over the 18 months, {value_18(cash)} against {money(cash['cost_18_months'])}; pays back {payback(cash)}.")
    w(f"- **Cost to serve:** {cost_to_serve} per ED room-hour freed, against the brief's $350 value.")
    w("")
    w("Freed capacity is the brief's own measure and the main case. The cash figure is the floor: it counts only "
      "money Halvian would see. The two are never added. The value ramp assumes no live value in Months 1 to 3 "
      "(setup, training, silent mode), the Medicine A pilot in Months 4 to 6, half of the full value during "
      "rollout in Months 7 to 9 and the full value from Month 10.")
    w("")
    w("The share of flags staff act on moves the result most (Cautious settings otherwise):")
    w("")
    w(table(["Staff act on", "Minutes saved per admission", "Freed capacity a year (not cash)",
             f"Clears the {be}-minute break-even"], adoption_rows(scenarios, be)))
    w("")
    # ------------------------------------------------------------------ risk
    w("## 4. Risk assessment and mitigation")
    w("")
    w(RISK_TEXT.strip())
    w("")
    # ------------------------------------------------------------------ assumptions
    w("## Budget and plan assumptions (B1 to B20)")
    w("")
    w("All in `halvian/config.py` under \"Budget, value and roadmap\". Change one there and rerun the two scripts.")
    w("")
    w(table(["Tag", "Assumption"], [[tag, text] for tag, text in ASSUMPTIONS]))
    w("")
    return "\n".join(out)


def reader_block(metrics: dict) -> list[str]:
    """How the AI note reader compares with the rules, on the sealed sample and on new wording."""
    nr = metrics.get("note_reader", {})
    if "llm" not in nr:
        return []
    rows = []
    for label, block in (("Sealed test sample (synthetic templated notes)", nr),
                         ("New-phrasing stress set (wording neither reader was built on)", nr.get("stress", {}))):
        for who, name in (("llm", "AI reader"), ("rules", "Rules"), ("combined", "AI reader and rules together")):
            if who in block:
                o = block[who]["overall"]
                rows.append([label, name, f"{block[who]['sample_n']:,}", f"{o['precision']:.2f}", f"{o['recall']:.2f}",
                             f"{o['f1']:.2f}"])
    st = nr.get("stress", {})
    if "llm" in st and "rules" in st:
        a, r = st["llm"]["overall"], st["rules"]["overall"]
        better = a["f1"] > r["f1"]
        finding = (f"On wording the rules were not written for, the AI reader scored F1 {a['f1']:.2f} against the "
                   f"rules' {r['f1']:.2f} (recall {a['recall']:.2f} against {r['recall']:.2f})"
                   + (", which is the argument for a language model on real free-text notes (still to be tested "
                      "on real, de-identified notes in the pilot)." if better else
                      "; the AI reader did not beat the rules there either, so its case rests on the combined reader "
                      "and on real notes, which this test does not include."))
        if "llm_checks_g1" in st:
            g1 = st["llm_checks_g1"]["overall"]
            finding += (f" The stricter checks that remove false alarms also cost recall on new wording: the same "
                        f"model answers under the first checks found {g1['recall']:.0%} at {g1['precision']:.0%} "
                        "precision. Building the check vocabulary from real notes is a pilot task; nothing was tuned "
                        "on the stress set.")
    else:
        finding = "The new-phrasing stress test has not been run."
    out = ["Why both an AI reader and rules: on the templated synthetic notes, the rules were written for the same "
           f"templates, so they are hard to beat. {finding} The app shows both readers' findings, tagged with which "
           "one found each, and the rules always answer if the model is down.", "",
           table(["Notes", "Reader", "Notes read", "Precision", "Recall", "F1"], rows), ""]
    return out


def _model_name(chosen: str) -> str:
    return "gradient boosting" if chosen == "boosting" else f"{chosen} regression"


def architecture(metrics: dict, plan: dict) -> str:
    adm, dis = metrics["admission"], metrics["discharge"]
    run = metrics.get("note_reader", {}).get("llm_run", {})
    per_note = run.get("sizing", {}).get("measured_s_per_note")
    occupied = round(C.INPATIENT_BEDS * C.TARGET_OCCUPANCY)
    minutes = occupied * per_note / 60 if per_note else None
    b = plan["budget"]
    lines = ["## 1. AI tool architecture", "",
             "### Tools and why they fit an ED and a small team (rubric 1.3)", "",
             table(["Tool", "What it does", "Why it fits", "Cost"], [
                 ["Read-only feeds from the EHR and registration system (HL7 ADT events, FHIR notes and vitals)",
                  "Bed status, admissions, discharges, transfers, triage data and morning notes", "The brief says both "
                  "systems can export data and connect to outside tools; staff enter nothing twice and the tool "
                  "writes nothing to the chart", "Interface build and vendor fees (budget)"],
                 [f"Admission model: {_model_name(adm['chosen'])} on {len(adm['features'])} triage-time fields",
                  "Chance of admission and the likely unit at the end of triage; the top three reasons",
                  f"Explainable, retrains in minutes, test AUC {adm['test'][adm['chosen']]['auc']:.2f} on synthetic data",
                  "Open source, $0 licence"],
                 [f"Discharge model: {_model_name(dis['chosen'])} on {len(dis['features'])} fields known at rounds",
                  "Chance of going home in 24 h "
                  "at 07:00 rounds", f"Test AUC {dis['test'][dis['chosen']]['auc']:.2f} on synthetic data; reasons "
                  "shown", "Open source, $0 licence"],
                 ["AI note reader: Llama 3.2 3B open weights through Ollama, with a rule-based fallback",
                  "Finds the open discharge task in the note and quotes the evidence", "Runs on Halvian's own server, "
                  "so no patient text leaves the network and there are no per-call fees; the rules answer if it is "
                  "down", "$0 licence; a small GPU server"],
                 ["Bed forecast: statistical tables of arrivals, discharges and cleaning time",
                  "Usable beds per unit in 4, 8 and 24 hours with an 80% range", "Transparent and cheap to maintain",
                  "Open source"],
                 ["Dashboard: Streamlit web page on the hospital network", "Bed board, flags, rounds list, forecast, "
                  "approve or override, decision log, fairness check", "No install on clinical PCs; one data "
                  "scientist can maintain it in Python", "Open source"],
             ]), "",
             *reader_block(metrics),
             "### Technical design: data, flow, where it runs (rubric 1.4)", "",
             table(["Step", "Data in", "When", "Output", "Who acts on it"], [
                 ["ED admission flags", "Age, vital signs, triage level, complaint, arrival mode, ED visits in the past "
                  "year (never insurance)", f"Scores refresh every {C.SCORE_REFRESH_MIN} min; bed requests batched "
                  f"every {C.BATCH_INTERVAL_MIN} min per unit", "Likely admissions, likely unit, reasons, a drafted "
                  "bed request", "Bed manager approves or overrides"],
                 ["Discharge readiness", "Length of stay so far, mobility, lab trend, diagnosis group, unit, how the "
                  "patient was admitted, day of week, and the barriers read from the morning note",
                  "07:00 rounds", "Chance of going home in 24 h, the barrier quoted from the note, its owner",
                  "Unit team at rounds; the case manager works the barrier"],
                 ["Bed forecast", "Bed status, flags, the rounds list, cleaning times", "Every hour",
                  "Usable beds per unit at 4, 8 and 24 h with an 80% range", "Charge nurse confirms or corrects"],
                 ["Oversight", "The decision log, outcomes by payer group", "Monthly, and on any pause trigger",
                  "Accuracy, fairness, override rates, gap table", "Tool owner; AI oversight committee"],
             ]), "",
             "- **Where it runs.** One hospital-hosted server inside Halvian's network (in the pilot), with a "
             "standby server from Phase 2. Staff open it in a browser with their single sign-on. It reads copies "
             "of EHR data and writes nothing back to the chart; people record decisions in the EHR as today.",
             "- **What it requires.** Read-only interfaces from the EHR and registration system, a server with a "
             "small GPU, one data scientist (0.5 to 1.0 FTE) and a clinical informatics nurse as tool owner. "
             f"Cost: {money(b['total_18_months'])} over 18 months, then {money(b['run_per_year'])} a year (section 3).",
             "- **Scalability.** The models are small; adding a unit means adding its feeds and training its "
             "staff. " + (f"The local model reads a morning's {occupied} notes in about {minutes:.0f} minutes at the "
                          f"measured {per_note:.2f} s per note on a laptop; a server GPU is faster." if minutes else ""),
             f"- **Reliability.** If a feed is down for more than {C.PAUSE_CONDITIONS['max_feed_outage_min']} minutes, "
             "units return to phone calls and the whiteboard with a bed huddle every 2 hours. If the language model is "
             "down, the rules read the notes and the screen says so. The standby server takes over if the main one "
             "fails.",
             "- **Maintenance.** Monthly accuracy, fairness and override checks; a quarterly retraining check; a yearly "
             "bias audit and security assessment; each change to a model, the prompt or the note checks gets a new "
             "version, and is tested in silent mode first.",
             "- **Privacy.** Minimum necessary fields; insurance is never a model input (used only to audit "
             "fairness); no patient data leaves the network; role-based access, encrypted disks and an audit log.",
             "- **Clinical risk.** Nothing executes automatically. Every recommendation shows its reasons and needs a "
             "person to approve or override it; admission and discharge decisions stay with clinicians.",
             ""]
    return "\n".join(lines)


ADOPTION = (
    "**Clinicians design it with us.** A charge nurse, a case manager, a hospitalist and a bed manager sit on the "
    "pilot team from Month 1 and approve the screens, the wording of every reason and the override reasons.",
    "**Silent mode first.** Staff see how often the tool would have been right on their own patients before it "
    "shows them anything; the results are shared at unit meetings, misses included.",
    "**Nothing happens without a person.** Every recommendation shows its reasons, the evidence quoted from the "
    "note, and an approve or override control. The tool never places an order, moves a patient or contacts a "
    "family.",
    "**Overrides are welcome.** Each override reason goes to the weekly huddle; the most common reasons change "
    "the tool, and staff see the change.",
    "**Super-users on every shift** answer questions at the bedside, and unit leaders report adoption and "
    "overrides openly.",
    "**Patients hear it from people.** The patient and family advisory council reviews how staff explain the "
    "tool. Patients are told that a nurse or doctor makes every decision, and that their insurance is never "
    "used to rank them.",
)

ASSUMPTIONS = (
    ("B1", "A full-time equivalent works 2,080 hours a year; a post staffed around the clock is 8,760 hours."),
    ("B2", f"Data scientist ${C.COST_DATA_SCIENTIST_PER_H} an hour, loaded."),
    ("B3", f"Contracted EHR interface engineer ${C.COST_INTEGRATION_ENGINEER_PER_H} an hour."),
    ("B4", f"Project manager ${C.COST_PROJECT_MANAGER_PER_H} an hour."),
    ("B5", f"Security analyst ${C.COST_SECURITY_ANALYST_PER_H} an hour."),
    ("B6", f"Agency staff cost {C.AGENCY_MULTIPLIER:g} times the employed rate (least certain)."),
    ("B7", "Training happens off-shift and is paid at the brief's 1.5x overtime."),
    ("B8", f"A {C.BUDGET_CONTINGENCY:.0%} contingency reserve on every phase."),
    ("B9", "Headcounts trained by role and the hours each (budget table)."),
    ("B10", f"{C.ANNUAL_TRAINING_TURNOVER:.0%} of trained users are replaced each year; everyone gets a "
            f"{C.REFRESHER_HOURS:g} h refresher."),
    ("B11", "Budget line quantities and prices (interface hours, vendor fees, servers, security reviews)."),
    ("B12", f"A monthly {C.OVERSIGHT_MEETING_H:g} h oversight committee with four paid members."),
    ("B13", "The alternatives named on the budget slide."),
    ("B14", "Hand coverage of the same work: a flow nurse around the clock, 3 min per occupied chart each "
            "morning, and 4 forecasts a day of 45 min."),
    ("B15", f"A boarded patient needs {C.ED_NURSE_H_PER_BOARDER_H:g} of an ED nurse (1:4)."),
    ("B16", f"{C.BOARDER_NURSING_ON_OVERTIME:.0%} of boarder nursing is covered by overtime (least certain)."),
    ("B17", f"{C.WALKOUT_RECOVERED_SHARE:.0%} of avoided walkouts become revenue Halvian keeps (least certain)."),
    ("B18", "Value ramp: none in Months 1 to 3, the pilot unit in Months 4 to 6, half during rollout, full "
            "from Month 10."),
    ("B19", f"Month 18 targets bank {C.GOAL_TARGET_SHARE:.0%} of the simulated improvement, rounded to the brief's "
            "precision."),
    ("B20", "Traditional staffing options for comparison, costed at the brief's rates: "
            + " ".join(x[4] for x in C.STAFFING_OPTIONS) + " Cost only; we do not estimate their effect."),
)

RISK_TEXT = """
### Risks and why they matter (rubric 4.1)

| Risk | Why it matters here | What we do | Where it shows in the demo |
| --- | --- | --- | --- |
| Algorithmic bias | The brief warns that tools have failed patients who were already underserved. A model trained on past flow can favor groups who already move fastest. | Payer is never a model input. A pre-launch bias test separates case mix from model behavior. Monthly gap tables by payer with a guardrail that pauses the tool. | Oversight: Fairness check, Waits and walkouts by group, When to pause |
| Patient privacy | Notes and triage data are protected health information. | Everything runs inside Halvian's network; the language model is local, with no cloud API. Read-only feeds, role-based access, an audit log. | Note reader status line: running locally |
| Over-reliance on AI | Staff can defer to a confident screen, and a wrong discharge or bed decision harms patients. | Nothing executes automatically. Every recommendation shows its reasons and needs an approve or override; overrides need a reason; AI-only note findings say "check the note"; an override rate under 2% triggers an audit of approvals. | Approve or override on every page, decision log |
| Loss of human connection | Faster flow can turn discharge into a transaction, and patients may feel processed by a machine. | The tool removes chart-hunting and phone calls, not conversations: case managers spend the time saved with patients and families, discharge teaching stays face to face, and the tool never contacts patients. The patient advisory council reviews what patients are told. | Discharge Readiness: the owner is a person, not the tool |

### Data security and the response plan (rubric 4.2)

Protection: the tool reads copies of EHR data through read-only interfaces and writes nothing back to the
chart. It runs on hospital-hosted servers inside the network, with encrypted disks, single sign-on with
role-based access, and an audit log of every view and decision. The language model is open-weight and local,
so no patient text leaves Halvian. Vendors get no standing access; the third-party assessment and yearly
re-test are in the budget.

If Halvian's or a vendor's systems are compromised:

1. **Contain (first hour).** The tool owner and IT security cut the tool's interfaces and take it offline.
   Units switch to the downtime protocol below, so care never waits on the tool.
2. **Assess (first day).** Security determines what data was reachable. The tool keeps no data beyond what the
   EHR already holds, which limits exposure.
3. **Notify.** The privacy officer follows HIPAA breach notification rules: affected patients and regulators
   within 60 days, sooner if state law requires.
4. **Recover.** Rebuild from clean images and the versioned model files, rotate credentials, and run silent
   mode for a week before staff see recommendations again.
5. **Review.** The oversight committee reviews the incident and the vendor's response, and keeps or retires
   the vendor.

### Oversight and contingency plans (rubric 4.3)

- **Before launch:** silent mode on Halvian's own data and the bias test above, which must pass the pilot gate.
- **After launch:** monthly checks against the pause conditions (AUC, calibration drift, miss-rate gaps,
  override rate band, payer gaps, feed outages), owned by the tool owner and reviewed by the oversight
  committee.
- **When to pause or retire:** a payer gap widening past the guardrail for two months, AUC below 0.75, an
  override rate outside 2% to 40%, or a safety event pauses the tool; missing goals for two quarters after a
  recovery plan retires it.
- **Review without deferring:** reasons are shown before the recommendation, overrides need a reason, approvals
  are audited when overrides fall under 2%, and AI-only note findings are marked for checking.
- **Contingency:** if feeds are down for more than 30 minutes, units return to phone calls and the whiteboard
  with a bed huddle every 2 hours. If the language model is down, the note reader falls back to the rules and
  says so. A standby server takes over if the main one fails. Downtime drills run on every unit in Phase 2.
"""


def main() -> str:
    plan = json.loads((ROOT / "models" / "plan.json").read_text())
    scenarios = json.loads((ROOT / "models" / "scenarios.json").read_text())
    metrics = json.loads((ROOT / "models" / "metrics.json").read_text())
    text = render(plan, scenarios, metrics)
    OUT.write_text(text, encoding="utf-8")
    return text


if __name__ == "__main__":
    main()
