"""Does the prototype meet the case? Every requirement in the brief and rubric, where it is met, and a check.

`REQUIREMENTS` records the prototype checklist derived from the case brief, rubric and team decisions.
Items the dashboard can meet have an automated
`check` that reads the committed data, models and code. Items that belong in the slides say what the app and
the repository already give the team for that slide. `tests/test_requirements.py` fails if any check fails.
Nothing here is hard-coded to pass: each check computes its answer.
"""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from functools import cache
from pathlib import Path

from halvian import config as C

ROOT = Path(__file__).resolve().parents[1]
APP_CODE = [ROOT / "app.py", ROOT / "results_app.py", *sorted((ROOT / "pages").glob("*.py")),
            *sorted((ROOT / "results").glob("*.py")), *sorted((ROOT / "halvian").rglob("*.py"))]
USER_TEXT = [*sorted((ROOT / "pages").glob("*.py")), *sorted((ROOT / "results").glob("*.py")),
             *sorted((ROOT / "halvian" / "ui").glob("*.py")), ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]
RECOMMENDING_PAGES = ["pages/admission_flags.py", "pages/discharge_readiness.py", "pages/bed_forecast.py",
                      "pages/guided_demo.py"]
NETWORK_MODULES = {"requests", "httpx", "aiohttp", "urllib.request", "http.client", "socket", "openai",
                   "anthropic", "boto3", "websockets"}

PASS, PARTLY, FAIL = "Pass", "Partly", "Fail"
SLIDES = "Cover on slides"
JUDGMENT = "Judgment call"


@dataclass(frozen=True)
class Result:
    status: str
    detail: str


@dataclass(frozen=True)
class Requirement:
    id: str
    section: str
    requirement: str
    source: str
    where: str
    check: Callable[[], Result] | None = None
    team_status: str = SLIDES  # used when there is no automated check
    rubric: tuple[str, ...] = ()  # rubric lines this row answers, for example ("5.1",)

    def evaluate(self) -> Result:
        if self.check is None:
            return Result(self.team_status, "")
        try:
            return self.check()
        except FileNotFoundError as exc:
            return Result(FAIL, f"Missing artifact: {Path(str(exc.filename or exc)).name}. Run the data and "
                                "model scripts.")


# --------------------------------------------------------------------------- helpers
@cache
def _metrics() -> dict:
    return json.loads((ROOT / "models" / "metrics.json").read_text())


@cache
def _scenarios() -> dict:
    return json.loads((ROOT / "models" / "scenarios.json").read_text())


@cache
def _ranges() -> dict:
    return json.loads((ROOT / "models" / "impact_ranges.json").read_text())


def _source(rel: str) -> str:
    return (ROOT / rel).read_text()


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
            found |= {f"{node.module}.{alias.name}" for alias in node.names}
    return found


# --------------------------------------------------------------------------- checks
def ranks_flags_forecasts() -> Result:
    from halvian.data import live as L

    adm, dis, fc = L.admission_scores(), L.discharge_scores(), L.forecast_tables()
    t = L.day_start(C.DEMO_DAYS["busy"]) + 11 * 60
    forecast = L.forecast_at(t)
    ok = len(adm) > 0 and len(dis) > 0 and fc is not None and set(forecast.unit) == set(C.UNIT_NAMES)
    return Result(PASS if ok else FAIL,
                  f"Flags: admission chances for {len(adm):,} ED visits. Ranks: discharge chances for "
                  f"{len(dis):,} rounds entries. Forecasts: usable beds for all {len(C.UNIT_NAMES)} units at "
                  f"{', '.join(str(h) for h in sorted(forecast.horizon_h.unique()))} hours.")


def shows_reasoning() -> Result:
    from halvian.data import live as L

    day = C.DEMO_DAYS["busy"]
    tour = L.tour_patients(day)
    t = L.day_start(day) + tour["ed_patient"]["hour"] * 60
    q = L.ed_queue(t)
    flagged = q[q.flagged]
    rounds = L.rounds_list(day)
    with_reasons = int(flagged.reasons.map(bool).sum())
    rounds_ok = int(rounds.reasons.map(bool).sum())
    ok = len(flagged) > 0 and with_reasons == len(flagged) and rounds_ok == len(rounds)
    return Result(PASS if ok else FAIL,
                  f"At {tour['ed_patient']['hour']:02d}:00 on the busy Monday, {with_reasons} of {len(flagged)} "
                  f"flagged ED patients show their top reasons; {rounds_ok} of {len(rounds)} patients at rounds "
                  "show reasons, and notes highlight the barrier. The forecast lists what frees up and what is "
                  "needed.")


def staff_can_override() -> Result:
    missing = []
    for rel in RECOMMENDING_PAGES:
        src = _source(rel)
        if "record_action(" not in src or '"approve"' not in src or '"override"' not in src:
            missing.append(rel)
    from halvian.ui import session

    reason_rule = "An override requires a reason" in Path(session.__file__).read_text()
    ok = not missing and reason_rule
    pages = ", ".join(Path(p).stem.replace("_", " ") for p in RECOMMENDING_PAGES)
    return Result(PASS if ok else FAIL,
                  (f"Approve and override on: {pages}. An override needs a reason, and every decision goes to the "
                   "decision log with the role that made it.") if ok else f"No override path on: {', '.join(missing)}")


def fairness_by_group() -> Result:
    m = _metrics()
    tables = {"admission flags": m["admission"]["fairness_deployed"], "discharge list": m["discharge"]["fairness"]}
    expected = set(C.PAYERS)
    gaps = {name: expected - {row["group"] for row in rows} for name, rows in tables.items()}
    ok = not any(gaps.values()) and "pages/oversight.py" in {s.path for s in _menu()}
    return Result(PASS if ok else FAIL,
                  f"Fairness and Oversight checks both models for all {len(expected)} insurance groups (AUC, "
                  "calibration, missed cases, flag rate) with a fixed amber and red rule, and tracks waits and "
                  "walkouts by group." if ok else f"Groups missing: {gaps}")


def _menu():
    from halvian.ui import navigation as NAV

    return NAV.ALL_PAGES


def fairness_result() -> Result:
    m = _metrics()
    flagged = [(part, row["group"], row["worst_level"])
               for part, rows in (("admission flags", m["admission"]["fairness_deployed"]),
                                  ("discharge list", m["discharge"]["fairness"]))
               for row in rows if row["group"] != "All patients" and row["worst_level"] in ("amber", "red")]
    if not flagged:
        return Result(PASS, "Every insurance group is within tolerance for both models.")
    names = "; ".join(f"{g} on the {p} ({lvl})" for p, g, lvl in flagged)
    rows = [r for r in m["admission"].get("fairness_case_mix", {}).get("rows", []) if "unexplained_pts" in r]
    explained = ""
    if rows:
        worst = max(abs(r["unexplained_pts"]) for r in rows)
        explained = (f" The pre-launch bias test (K5) finds the missed-admission gaps come from case mix: after "
                     f"matching triage level and age, no group is missed more than {worst:.1f} points beyond "
                     "expectation. A missed flag means the usual process, never a lower priority.")
    return Result(PARTLY, f"The check works and flags: {names}. Red means review before launch.{explained} Say "
                          "so on the risk slide; the Phase 2 threshold review (docs/STRATEGY.md) is the fix to test.")


def payer_blind() -> Result:
    m = _metrics()
    feats = {part: [f for f in m[part]["features"] if re.search(r"payer|coverage|medicaid|medicare|uninsured", f, re.I)]
             for part in ("admission", "discharge")}
    ok = not any(feats.values())
    return Result(PASS if ok else FAIL,
                  "Neither model uses the patient's insurance group. It is used only for the fairness check. (The "
                  "discharge model does see 'waiting on insurance approval' when a note says so: that is a task "
                  "to clear, not the patient's coverage.)" if ok else f"Insurance group used as a feature: {feats}")


def synthetic_only() -> Result:
    import pandas as pd

    ed = pd.read_parquet(ROOT / "data" / "ed_visits.parquet", columns=["visit_id"])
    ip = pd.read_parquet(ROOT / "data" / "inpatient_stays.parquet", columns=["stay_id"])
    bad_ed = int((~ed.visit_id.str.fullmatch(r"ED-\d{6}")).sum())
    bad_ip = int((~ip.stay_id.str.fullmatch(r"IP-\d{6}")).sum())
    cols = set(pd.read_parquet(ROOT / "data" / "ed_visits.parquet").columns)
    named = {c for c in cols if re.search(r"name|address|phone|mrn|ssn", c, re.I)}
    ok = not (bad_ed or bad_ip or named)
    return Result(PASS if ok else FAIL,
                  f"All {len(ed):,} ED visits and {len(ip):,} inpatient stays are generated by "
                  "scripts/generate_data.py with IDs like ED-000123 and IP-004512. No names, addresses or record "
                  "numbers." if ok else f"Unexpected IDs or identifying columns: {bad_ed}, {bad_ip}, {named}")


LOCAL_MODEL_CLIENT = "halvian/notes/ollama.py"  # the one file allowed to open a connection, to localhost only


def offline() -> Result:
    from urllib.parse import urlparse

    from halvian.notes import ollama

    hits = {str(p.relative_to(ROOT)): sorted(_imports(p) & NETWORK_MODULES) for p in APP_CODE if p.is_file()}
    hits = {k: v for k, v in hits.items() if v and k != LOCAL_MODEL_CLIENT}
    loopback = urlparse(C.OLLAMA_URL).hostname in ollama.LOOPBACK
    try:
        ollama._url("/api/tags", "http://example.com")
        refuses_other_hosts = False
    except ValueError:
        refuses_other_hosts = True
    ok = not hits and loopback and refuses_other_hosts
    return Result(PASS if ok else FAIL,
                  f"No app or library file imports a network library except {LOCAL_MODEL_CLIENT}, which talks only "
                  f"to the local Ollama server at {C.OLLAMA_URL} and refuses any other host. No API keys, no paid "
                  "services, nothing leaves the machine." if ok else
                  f"Network imports: {hits}; loopback URL: {loopback}; refuses other hosts: {refuses_other_hosts}")


def human_accountable() -> Result:
    src = _source("pages/oversight.py")
    ok = "Who acts, and who is accountable" in src and "Accountable when wrong" in src
    return Result(PASS if ok else FAIL,
                  "Fairness and Oversight names who acts on each recommendation and who is accountable when it is "
                  "wrong. Admission and discharge decisions stay with clinicians; nothing executes automatically."
                  if ok else "The accountability table is missing.")


def pause_rules() -> Result:
    src = _source("pages/oversight.py")
    pc = C.PAUSE_CONDITIONS
    ok = "When the tool is reviewed or paused" in src and "Fallback" in src and pc
    return Result(PASS if ok else FAIL,
                  f"When to pause lists {len(pc)} numeric triggers (accuracy, missed cases by group, calibration "
                  "drift, override rate too high or too low, data feed outage) and the manual fallback: phone, "
                  "whiteboard and a bed huddle every 2 hours." if ok else "Pause rules or fallback missing.")


def calibrated() -> Result:
    v = json.loads((ROOT / "data" / "validation.json").read_text())["checks"]
    passed = sum(bool(c["Pass"]) for c in v)
    return Result(PASS if passed == len(v) else PARTLY,
                  f"{passed} of {len(v)} calibration targets from the brief are within tolerance (volumes, waits, "
                  "walkouts, boarding, occupancy, payer gaps). Table in docs/DATA.md.")


def equity_never_widens() -> Result:
    rows = [r for r in _scenarios()["results"]["default"]["gap_table"]
            if r["Gap"].startswith((C.MEDICAID, C.UNINSURED))]
    verdicts = {f"{r['Gap'].split(' vs ')[0]} {r['Measure'].split(' (')[0].lower()}": r["Verdict"] for r in rows}
    widened = [k for k, v in verdicts.items() if v == "Widened"]
    flat = [k for k, v in verdicts.items() if v == "Flat"]
    status = FAIL if widened else (PARTLY if flat else PASS)
    text = "; ".join(f"{k}: {v.lower()}" for k, v in verdicts.items())
    option = ""
    for name, result in _scenarios()["results"].items():
        if not name.startswith("threshold="):
            continue
        case = [r for r in result["gap_table"] if r["Gap"].startswith((C.MEDICAID, C.UNINSURED))]
        if case and all(r["Verdict"] == "Narrowed" for r in case):
            option = (f" Tested Phase 2 option: at a {float(name.split('=')[1]):.0%} base threshold all "
                      f"{len(case)} Medicaid/CHIP and Uninsured gaps narrow (docs/STRATEGY.md).")
            break
    expected = [e for e in _ranges()["equity"] if e["gap"].startswith((C.MEDICAID, C.UNINSURED))]
    exp_text = (f" Expected scenario (bed board on): {sum(e['verdict'] == 'Narrowed' for e in expected)} of "
                f"{len(expected)} narrow, {sum(e['verdict'] == 'Widened' for e in expected)} widen.")
    return Result(status, f"Simulated, Cautious (today's default) settings: {text}." + (
        " Nothing widens, but not every gap narrows yet; treat the flat one as the equity goal to prove in the "
        "pilot." if flat and not widened else "") + exp_text + option)


def clickable_app() -> Result:
    pages = _menu()
    missing = [s.path for s in pages if not (ROOT / s.path).is_file()]
    for spec in pages:
        if spec.path not in missing:
            ast.parse((ROOT / spec.path).read_text())
    return Result(PASS if not missing else FAIL,
                  f"{len(pages)} pages in the grouped top navigation, all present. tests/test_app_smoke.py opens each one, "
                  "approves and overrides recommendations, and clicks through the guided demo."
                  if not missing else f"Missing pages: {missing}")


def every_page_explains() -> Result:
    from halvian.ui.story import ORDER, STORIES

    missing = [s.title for s in ORDER if not (STORIES.get(s.url) and STORIES[s.url].chain)]
    return Result(PASS if not missing else FAIL,
                  "Every dashboard page opens with the problem it solves (from the brief), what it does and its "
                  "downstream impact, plus a live note on what the numbers mean right now."
                  if not missing else f"No story for: {missing}")


def estimates_labelled() -> Result:
    from halvian.ui import chrome

    frame_src = Path(chrome.__file__).read_text()
    entries = {name: "product_frame(" in (ROOT / name).read_text() for name in ("app.py", "results_app.py")}
    tagged = "Synthetic demo data" in frame_src and "hv-footer" in frame_src
    ok = all(entries.values()) and tagged
    return Result(PASS if ok else FAIL,
                  "Every page of the dashboard and the results companion sits inside one product frame: a "
                  f"'Synthetic demo data' tag in the header and the footer '{chrome.SYNTHETIC_BANNER}'. Simulated "
                  "results are labelled as estimates." if ok else
                  f"Product frame missing: {[k for k, v in entries.items() if not v]}; tag and footer: {tagged}")


def no_em_dashes() -> Result:
    dashes = re.compile("[\\u2013\\u2014]")
    hits = [p.relative_to(ROOT).as_posix() for p in USER_TEXT if p.is_file() and dashes.search(p.read_text())]
    return Result(PASS if not hits else FAIL,
                  "No em or en dashes in pages, README or docs." if not hits else f"Dashes in: {hits}")


# --------------------------------------------------------------------------- the rubric itself
RUBRIC_FILE = ROOT / "context" / "2026_Case_Rubric.xlsx"


@cache
def rubric_lines() -> list[dict]:
    """Every scored line of the case rubric, read from the spreadsheet (no extra packages).

    Returns dicts with ``id`` ("1.1", "1.2", ...), ``section``, ``criterion`` (its name where the
    sheet gives one), ``points`` and ``full_marks`` (the top-scoring description).
    """
    import html
    import zipfile

    with zipfile.ZipFile(RUBRIC_FILE) as z:
        shared = [html.unescape("".join(re.findall(r"<t[^>]*>(.*?)</t>", si, re.S)))
                  for si in re.findall(r"<si>(.*?)</si>", z.read("xl/sharedStrings.xml").decode(), re.S)]
        sheet = z.read("xl/worksheets/sheet1.xml").decode()
    rows = []
    for row in re.findall(r"<row[^>]*>(.*?)</row>", sheet, re.S):
        cells = {}
        for attrs, body in re.findall(r"<c ([^>]*?)(?:/>|>(.*?)</c>)", row, re.S):  # empty cells self-close
            col = re.search(r'r="([A-Z]+)', attrs).group(1)
            v = re.search(r"<v>(.*?)</v>", body, re.S)
            if v:
                cells[col] = shared[int(v.group(1))] if 't="s"' in attrs else v.group(1)
        rows.append(cells)
    out, section, k = [], None, 0
    for cells in rows[1:]:
        points = cells.get("C")
        try:
            pts = float(points)
        except (TypeError, ValueError):
            continue
        name = cells.get("A", "")
        if re.match(r"^\d+\.\s", name):
            section, k = name.strip(), 0
        if section is None:
            continue
        k += 1
        best = [cells.get(c, "").strip() for c in ("F", "E", "D") if cells.get(c, "").strip()
                and not cells.get(c, "").startswith("NA")]
        if not best:  # the total row
            continue
        crit = cells.get("B", "").strip()
        out.append({"id": f"{section.split('.')[0]}.{k}", "section": section, "criterion": "" if crit.isdigit() else crit,
                    "points": pts, "full_marks": best[0] if best else ""})
    return out


def rubric_coverage() -> dict[str, list[str]]:
    """Rubric line id to the requirement rows that answer it."""
    cover = {line["id"]: [] for line in rubric_lines()}
    for req in REQUIREMENTS:
        for rid in req.rubric:
            cover.setdefault(rid, []).append(req.id)
    return cover


# --------------------------------------------------------------------------- strategy content (plan.json)
@cache
def _plan() -> dict:
    return json.loads((ROOT / "models" / "plan.json").read_text())


def _strategy_text() -> str:
    return (ROOT / "docs" / "STRATEGY.md").read_text(encoding="utf-8")


def _ready(detail: str) -> Result:
    """Computed and checked, but it belongs on the slides: the status stays "Cover on slides"."""
    return Result(SLIDES, "Ready for the slides (docs/STRATEGY.md): " + detail)


def _money(v: float) -> str:
    return f"${v:,.0f}"


def plan_budget() -> Result:
    b = _plan()["budget"]
    cats = set(b["by_category"]["pilot"]) | set(b["by_category"]["scale"])
    need = {"Licensing", "Integration", "Training (clinician time)", "Monitoring and oversight", "Security review"}
    if need - cats:
        return Result(FAIL, f"Budget categories missing: {', '.join(sorted(need - cats))}.")
    if not all(b["within_caps"].values()):
        over = [k for k, ok in b["within_caps"].items() if not ok]
        return Result(FAIL, f"The budget is over the brief's cap: {', '.join(over)}.")
    hidden = b["hidden_by_phase"]["pilot"] + b["hidden_by_phase"]["scale"]
    return _ready(f"pilot {_money(b['by_phase']['pilot'])}, scale {_money(b['by_phase']['scale'])}, 18 months "
                  f"{_money(b['total_18_months'])} of {_money(b['caps']['18_months'])}, then "
                  f"{_money(b['run_per_year'])} a year; hidden costs (clinician training time at the brief's rates, "
                  f"security review, vendor fees) {_money(hidden)} over 18 months; {len(b['alternatives'])} "
                  "alternatives named. Open-source tools and an open-weight local model: no licence fees.")


def _span(r: list, fmt: str = "{:g}") -> str:
    return f"{fmt.format(r[0])} to {fmt.format(r[1])}"


def plan_value() -> Result:
    p, rg = _plan(), _ranges()
    t, v = p["traditional"], p["value"]
    staff = rg["staffing_alternative"]
    ranges_ok = all(lo < hi for sc in rg["scenarios"] for key in ("minutes_saved_per_admission",
                                                                 "freed_capacity_per_year_usd_m")
                    for lo, hi in [sc[key]])
    if len(t["rows"]) < 2 or len(v["least_certain"]) < 3 or not 2 <= len(staff) <= 3 or not ranges_ok:
        return Result(FAIL, "The traditional comparison, the staffing options, the ranges or the least certain "
                            "assumptions are missing.")
    sc = {x["name"]: x for x in rg["scenarios"]}
    be = rg["break_even"]["minutes_per_admission"]
    below = [n for n, x in sc.items() if x["minutes_saved_per_admission"][0] < be]
    return _ready(f"break-even {be} minutes saved per admission ($500,000 / ($350 x 13,600)); simulated ranges: "
                  + "; ".join(f"{n} {_span(x['minutes_saved_per_admission'])} min "
                              f"({_span(x['freed_capacity_per_year_usd_m'], '${:.1f}M')} freed capacity, not cash)"
                              for n, x in sc.items())
                  + (f"; below break-even: {', '.join(below)}" if below else "; every range above break-even")
                  + ". Staffing options, cost only at the brief's rates: "
                  + ", ".join(f"{x['option'].lower()} {_money(x['annual_cost_usd'])}" for x in staff)
                  + f", against the tool's {_span(rg['tool_cost']['per_year_usd'], '${:,.0f}')} a year. Same coverage "
                  f"by hand is {t['total']['fte']:.1f} FTE ({_money(t['total']['hired'])} a year hired). Each with "
                  f"its method; {len(v['least_certain'])} least certain assumptions named.")


def plan_kpis() -> Result:
    p = _plan()
    equity = [k for k in p["kpis"] if k["kind"] == "equity"]
    shrinking = [k for k in equity if k["target"] < k["baseline"]]
    sim = {k["kpi"]: k["simulated"] for k in p["kpis"]}
    roi_cap = next(v for k, v in sim.items() if k.startswith("Yearly ROI on freed capacity"))
    roi_cash = next(v for k, v in sim.items() if k.startswith("Yearly cash ROI"))
    serve = next(v for k, v in sim.items() if k.startswith("Cost per ED room-hour"))
    detail = (f"{len(p['kpis'])} KPIs with targets, {len(shrinking)} of {len(equity)} equity KPIs set to shrink a "
              f"gap; ROI a year {roi_cap} on freed capacity and {roi_cash} cash only (Cautious ranges); cost to serve "
              f"{serve} per ED room-hour freed.")
    if not shrinking:
        return Result(PARTLY, detail + " No equity KPI narrows a gap in the simulation.")
    return _ready(detail)


def plan_goals() -> Result:
    goals = _plan()["goals"]
    equity = [g for g in goals if g["kind"] == "equity"]
    tracked = all(g["track"] and g["if_off_track"] for g in goals)
    if not (3 <= len(goals) <= 4 and equity and tracked):
        return Result(FAIL, "Need three or four tracked goals with actions, including an equity goal.")
    narrows = [part for g in equity for part in g["parts"] if part["target"] < part["baseline"]]
    detail = (f"{len(goals)} Month 18 goals tied to the brief's baselines, each with how it is tracked and what "
              f"happens if it slips; the equity goal narrows {len(narrows)} gaps (Medicaid/CHIP wait, Uninsured "
              "walkouts) with a guardrail that pauses the tool if a gap widens.")
    return _ready(detail) if narrows else Result(PARTLY, detail)


def plan_pilot() -> Result:
    p = _plan()
    pilot = [m for m in p["milestones"] if m["phase"] == "pilot"]
    gates = p["pilot_gates"]
    text = _strategy_text()
    has_parts = all(h in text for h in ("Pilot success metrics", "Adoption plan", "Pre-launch bias test"))
    if len(pilot) < 4 or len(gates) < 5 or not has_parts:
        return Result(FAIL, "The pilot needs milestones, gates, success metrics and an adoption plan.")
    met = [g for g in gates if g["status"].startswith("Met")]
    unmet = [g["gate"] for g in gates if g["status"].startswith("Not met")]
    return _ready(f"{len(pilot)} pilot milestones with owners and exit criteria; {len(gates)} gates to Phase 2: "
                  f"{len(met)} met in the synthetic test, {len(unmet)} not met"
                  + (f" ({'; '.join(unmet)})" if unmet else "")
                  + ", the rest need pilot data. Success metrics cover operations, adoption, patient experience, "
                    "equity and safety; the adoption plan covers skeptical clinicians and patients.")


def plan_scale() -> Result:
    p = _plan()
    scale = [m for m in p["milestones"] if m["phase"] == "scale"]
    text = _strategy_text()
    if len(scale) < 3 or len(p["phase2"]["options"]) < 2 or "Long-term ownership" not in text:
        return Result(FAIL, "Phase 2 needs milestones, a pilot-based adjustment and long-term ownership.")
    return _ready(f"{len(scale)} scale milestones; the pilot decides the alert threshold from "
                  f"{len(p['phase2']['options'])} tested options; metrics as we scale; ownership, the yearly run "
                  f"cost ({_money(p['budget']['run_per_year'])}) and when to retire.")


def bias_test_before_launch() -> Result:
    rows = [r for r in _metrics()["admission"].get("fairness_case_mix", {}).get("rows", []) if "unexplained_pts" in r]
    if not rows:
        return Result(FAIL, "Run scripts/train_models.py: the pre-launch bias test is missing.")
    worst = max(rows, key=lambda r: abs(r["unexplained_pts"]))
    ok = abs(worst["unexplained_pts"]) <= C.CASE_MIX_UNEXPLAINED_PTS["red"]
    uninsured = next((r for r in rows if r["group"] == C.UNINSURED), None)
    detail = (f"Missed admissions by payer, standardized by triage level and age: the largest unexplained gap is "
              f"{worst['unexplained_pts']:+.1f} points ({worst['group']})")
    if uninsured:
        detail += (f"; Uninsured admissions are missed {uninsured['observed_miss_rate']:.1%} of the time against "
                   f"{uninsured['expected_from_case_mix']:.1%} expected from case mix")
    return Result(PASS if ok else PARTLY, detail + ". Rerun on Halvian's data in silent mode before go-live.")


def risk_plan_written() -> Result:
    text = _strategy_text()
    need = ("Loss of human connection", "If Halvian's or a vendor's systems are compromised", "Contingency")
    missing = [n for n in need if n not in text]
    if missing:
        return Result(FAIL, f"docs/STRATEGY.md is missing: {', '.join(missing)}.")
    return _ready("the risk table (bias, privacy, over-reliance, loss of human connection), the five-step response "
                  "plan if Halvian's or a vendor's systems are compromised, and the contingency plan.")


# --------------------------------------------------------------------------- AI note reader checks
def _note_reader_metrics() -> dict:
    return _metrics().get("note_reader", {})


def reader_runs_locally() -> Result:
    from halvian.notes import ollama
    from halvian.notes.prompt import PROMPT_ID

    run = _note_reader_metrics().get("llm_run")
    local = urlparse_host(C.OLLAMA_URL) in ollama.LOOPBACK
    if not run:
        return Result(FAIL, "The local model has not been run. Run scripts/run_llm_reader.py.")
    ok = local and run["model"] == C.LLM_MODEL and run["prompt_version"] == PROMPT_ID
    return Result(PASS if ok else FAIL,
                  f"{run['display_name']} reads notes through Ollama at {C.OLLAMA_URL} (this machine only), at "
                  f"temperature {run['temperature']:g} with a fixed seed and one versioned prompt ({PROMPT_ID}). "
                  f"{run['why_this_model']}" if ok else
                  f"Cached results are for {run['model']} / {run['prompt_version']}, not {C.LLM_MODEL} / {PROMPT_ID}.")


def urlparse_host(url: str) -> str | None:
    from urllib.parse import urlparse

    return urlparse(url).hostname


def _f1(block: dict) -> float:
    return block["overall"]["f1"] or 0.0


def reader_evaluated() -> Result:
    nr = _note_reader_metrics()
    if not all(k in nr for k in ("llm", "rules", "combined")):
        return Result(FAIL, "No evaluation of the AI reader. Run scripts/run_llm_reader.py.")
    n = nr["llm"]["sample_n"]
    parts = "; ".join(f"{who} precision {nr[who]['overall']['precision']:.2f}, recall "
                      f"{nr[who]['overall']['recall']:.2f}, F1 {_f1(nr[who]):.2f}"
                      for who in ("llm", "rules", "combined"))
    return Result(PASS, f"Scored against the note labels on sealed sample B, {n:,} test-quarter notes sharing "
                        "no note or text with the sample whose errors were studied (balanced by barrier type and "
                        f"payer group, plus notes with no barrier): {parts}. "
                        "Also by barrier type and by payer group in models/metrics.json.")


def reader_vs_rules() -> Result:
    nr = _note_reader_metrics()
    if "llm" not in nr:
        return Result(FAIL, "No evaluation of the AI reader.")
    worse = [b for b in C.BARRIER_TYPES
             if (nr["llm"]["by_barrier"][b]["f1"] or 0) < (nr["rules"]["by_barrier"][b]["f1"] or 0) - 0.005]
    overall = _f1(nr["llm"]) >= _f1(nr["rules"]) - 0.005
    if overall and not worse:
        return Result(PASS, "The AI reader matches or beats the rules overall and on every barrier type.")
    names = ", ".join(C.BARRIER_LABELS[b].lower() for b in worse)
    st = nr.get("stress", {})
    stress = ""
    if "llm" in st and "rules" in st:
        stress = (f" On new wording (the stress set), the rules found {st['rules']['overall']['recall']:.0%} of "
                  f"barriers and the AI reader {st['llm']['overall']['recall']:.0%} at "
                  f"{st['llm']['overall']['precision']:.0%} precision.")
    return Result(PARTLY, f"The AI reader (F1 {_f1(nr['llm']):.2f}) is {'below' if not overall else 'level with'} "
                          f"the rules (F1 {_f1(nr['rules']):.2f}) on these synthetic, templated notes"
                          + (f", and below them on: {names}" if worse else "") + ". The rules were written for "
                          "these templates; the model was not tuned on them." + stress + " Say so, and present the "
                          "model as the reader for real, free-text notes, with the rules as the safety net.")


def reader_shown_beats_rules() -> Result:
    nr = _note_reader_metrics()
    st = nr.get("stress", {})
    if not all(k in nr for k in ("combined", "rules")) or not all(k in st for k in ("llm", "rules")):
        return Result(FAIL, "Run scripts/run_llm_reader.py: the sealed sample or the stress set is missing.")
    shown, rules = nr["combined"]["overall"], nr["rules"]["overall"]
    new_ai, new_rules = st["llm"]["overall"], st["rules"]["overall"]
    ok = shown["f1"] >= rules["f1"] - 0.005 and new_ai["f1"] > new_rules["f1"]
    return Result(PASS if ok else PARTLY,
                  f"What the app shows (AI reader plus rules) on the sealed sample: precision {shown['precision']:.2f}, "
                  f"recall {shown['recall']:.2f}, F1 {shown['f1']:.2f}, against the rules alone at F1 {rules['f1']:.2f}. "
                  f"On new wording: AI reader F1 {new_ai['f1']:.2f} (recall {new_ai['recall']:.2f}), rules F1 "
                  f"{new_rules['f1']:.2f} (recall {new_rules['recall']:.2f}).")


def reader_falls_back() -> Result:
    from halvian.notes.reader import LLMNoteReader

    findings, status, detail = LLMNoteReader(model="halvian-missing-model:0", timeout_s=3).read_detailed(
        "pt has no ride home")
    ok = status == "fallback" and [f["type"] for f in findings] == ["transport"]
    return Result(PASS if ok else FAIL,
                  f"With the model unavailable, the reader answers with the rules and reports status 'fallback' "
                  f"({detail}). The app keeps working with Ollama off." if ok else f"No fallback: {status}, {findings}")


def reader_fair_by_payer() -> Result:
    nr = _note_reader_metrics()
    if "llm" not in nr:
        return Result(FAIL, "No evaluation of the AI reader.")
    rec = {g: v["recall"] for g, v in nr["llm"]["by_payer"].items() if v["recall"] is not None}
    overall = nr["llm"]["overall"]["recall"]
    worst = min(rec, key=rec.get)
    gap = (overall - rec[worst]) * 100
    text = ", ".join(f"{g} {v:.0%}" for g, v in rec.items())
    status = PASS if gap <= 5 else PARTLY
    return Result(status, f"Recall by payer group on the sample: {text} (overall {overall:.0%}). Worst group "
                          f"{worst}, {gap:.1f} points below overall" + (
                              "; within the 5-point amber rule." if status == PASS else
                              "; beyond the 5-point amber rule, so review before launch."))


def reader_evidence_verbatim() -> Result:
    import pandas as pd

    path = ROOT / "models" / "llm_note_findings.parquet"
    if not path.is_file():
        return Result(FAIL, "No cached AI reader results.")
    from halvian.notes.evaluate import load_stress

    cache = pd.read_parquet(path)
    text = pd.read_parquet(ROOT / "data" / "notes.parquet", columns=["note_id", "text"]).set_index("note_id").text
    stress = load_stress()
    if stress is not None:
        text = pd.concat([text, stress[0].set_index("note_id").text])
    hits = cache[cache.barrier_type.notna()]
    bad = sum(text[r.note_id][int(r.start):int(r.end)] != r.evidence for r in hits.itertuples())
    guard = _note_reader_metrics().get("llm_run", {}).get("guard_counts", {})
    return Result(PASS if not bad else FAIL,
                  f"All {len(hits):,} cached findings quote the note word for word, with offsets taken from the "
                  f"note. Dropped by the checks during the run: {guard.get('evidence_not_in_note', 0)} with "
                  f"evidence not in the note, {guard.get('negated_or_resolved', 0)} negated or resolved, "
                  f"{guard.get('no_open_task_named', 0)} whose clause named no open discharge task; "
                  f"{guard.get('relabelled', 0)} given the type their words name."
                  if not bad else f"{bad} findings do not match their note.")


def reader_scale_documented() -> Result:
    import pandas as pd

    from halvian.notes.evaluate import demo_note_ids

    path = ROOT / "models" / "llm_note_findings.parquet"
    if not path.is_file():
        return Result(FAIL, "No cached AI reader results.")
    cache = pd.read_parquet(path)
    days = pd.read_parquet(ROOT / "data" / "inpatient_days.parquet", columns=["note_id", "rounds_min"])
    demo = set(demo_note_ids(days))
    covered = demo <= set(cache.note_id)
    doc = (ROOT / "docs" / "MODELS.md").read_text()
    documented = "evaluation sample" in doc and "full-year" in doc
    run = _note_reader_metrics().get("llm_run", {})
    ok = covered and documented
    return Result(PASS if ok else FAIL,
                  f"The local model read {run.get('evaluation_notes', 0):,} sealed evaluation notes, "
                  f"{run.get('stress_notes', 0)} stress notes and all {len(demo)} demo-day notes in "
                  f"{run.get('wall_minutes', 0):.0f} minutes; the rules read all 107,215 notes "
                  "and feed the discharge model. The split is documented in docs/MODELS.md."
                  if ok else f"Demo notes covered: {covered}; documented in MODELS.md: {documented}")


# --------------------------------------------------------------------------- the list
A, R, B, K, D, S, T = ("1. AI tool architecture", "2. Roadmap and milestones", "3. Budget and ROI",
                       "4. Risk assessment and mitigation", "5. Working MVP demo", "Case scenario",
                       "Team rules")
N, P = "AI note reader", "6. Overall presentation"

REQUIREMENTS: list[Requirement] = [
    # 5. demo: the part the app must carry on its own (3 points, all or nothing)
    Requirement("D1", D, "A working prototype someone can click through, not slides or mockups.", "Brief 5",
                "The whole app. pytest opens every menu page and clicks through the guided demo.",
                clickable_app),
    Requirement("D2", D, "Option B: ranks, flags or forecasts from a synthetic dataset.", "Brief 5, Option B",
                "ED Admission Flags (flags), Discharge Readiness (ranks), Bed Forecast (forecasts)",
                ranks_flags_forecasts),
    Requirement("D3", D, "Shows its reasoning.", "Brief 5, Option B",
                "Top reasons on every flag and rounds card, highlighted note barriers, forecast breakdown",
                shows_reasoning),
    Requirement("D4", D, "Lets staff override it.", "Brief 5, Option B",
                "Approve and override on Flags, Discharge, Forecast and the Guided demo; decision log",
                staff_can_override),
    Requirement("D5", D, "Includes a fairness check by patient group.", "Brief 5, Option B",
                "Fairness and Oversight: Fairness check and Waits and walkouts tabs", fairness_by_group),
    Requirement("D6", D, "Uses only synthetic or fictional data, no real patient information.",
                "Brief 5; rubric 5", "data/ is generated by scripts/generate_data.py", synthetic_only),
    Requirement("D7", D, "Uses AI in a clear and meaningful way and supports the chosen focus area.", "Rubric 5",
                "Two prediction models, a note reader and a forecast, each tied to a cause of boarding on its page",
                every_page_explains),
    Requirement("D8", D, "Looks polished enough to represent a real product component.", "Rubric 5",
                "One palette, consistent page layout, plain-language copy. Judge it in a full run-through.",
                team_status=JUDGMENT),
    Requirement("D9", D, "The demo is the tool the strategy is built around.", "Brief 5",
                "Slides must describe this same dashboard: the four parts and their safeguards.",
                team_status=SLIDES),
    # scenario-level musts
    Requirement("S1", S, "Every tool keeps a qualified human accountable for clinical decisions.", "Brief, Scenario",
                "Fairness and Oversight, When to pause tab: who acts and who is accountable", human_accountable),
    Requirement("S2", S, "Narrow outcome gaps and never widen them.", "Brief, Outcome gaps",
                "Downstream impact page (simulated); live gaps on Fairness and Oversight", equity_never_widens),
    Requirement("S3", S, "Use readily available AI and automation platforms within $500K a year (about $750K over "
                "18 months).", "Brief, Scenario",
                "docs/STRATEGY.md section 3 (models/plan.json). The prototype uses free open-source tools only.",
                plan_budget),
    # 1. architecture
    Requirement("A1", A, "State the focus area and why, tied to baseline measures and who is affected.",
                "Brief 1; rubric 1 (2 pts)",
                "Overview: 3.5 h boarding (national 2 to 2.5), 55 min to a provider, 4% walkouts, the gaps by "
                "insurance. Pitch doc: Why boarding. Chart: exports/problem_to_feature.png.", team_status=SLIDES),
    Requirement("A2", A, "Where AI is used, what stays human-led, and who is accountable when the AI is wrong.",
                "Brief 1; rubric 1 (2 pts)",
                "Screenshot the accountability table on Fairness and Oversight; every page shows who uses it.",
                human_accountable),
    Requirement("A3", A, "Tools you will use and why they fit an ED and a small team (real, cost-aware).",
                "Brief 1; rubric 1 (2 pts)", "Pitch doc: How it works. Not shown in the app.", team_status=SLIDES),
    Requirement("A4", A, "Technical design: data used, how information moves between tool, staff and the EHR, "
                "where it runs, cost, scalability, reliability, maintenance, privacy and clinical risk.",
                "Brief 1; rubric 1 (3 pts)",
                "Start from exports/architecture.png (data in, AI steps, forecast, staff review, oversight). "
                "docs/DATA.md and docs/MODELS.md list the data and models; models use only triage-time fields "
                "(tests/test_leakage.py). Add cost, scaling, reliability, maintenance and privacy to the slide.",
                team_status=SLIDES),
    # 2. roadmap
    Requirement("R1", R, "Three or four Month-18 goals from the baselines, including one equity goal that narrows a "
                "gap, with a tracking plan and actions if missed.", "Brief 2; rubric 2 (3 pts)",
                "docs/STRATEGY.md section 2 (goals table); the equity guardrail on Fairness and Oversight is the "
                "tracking rule and the action.", plan_goals),
    Requirement("R2", R, "Phase 1 pilot (months 1 to 6): milestones, criteria to move to Phase 2, success metrics "
                "(operations, adoption, patient experience, equity) and an adoption plan for skeptical clinicians "
                "and patients.", "Brief 2; rubric 2 (3 pts)",
                "docs/STRATEGY.md section 2: milestones, gates, success metrics, adoption plan. The Medicine A "
                "pilot scenario is on the Downstream impact page; the Guided demo is the training script.", plan_pilot),
    Requirement("R3", R, "Phase 2 (months 7 to 18): use pilot results, rollout milestones, metrics (efficiency, "
                "outcomes, override rates, cost-to-serve), long-term ownership, funding and retirement.",
                "Brief 2; rubric 2 (2 pts)",
                "docs/STRATEGY.md section 2 (Phase 2); pause rules on Fairness and Oversight name the tool owner and "
                "when to retire.", plan_scale),
    # 3. budget
    Requirement("B1", B, "Costs by phase (licensing, integration, training, monitoring), hidden costs such as "
                "clinician training time and security review, and lower-cost alternatives.",
                "Brief 3; rubric 3 (3 pts)", "docs/STRATEGY.md section 3; chart exports/budget_by_phase.png.",
                plan_budget),
    Requirement("B2", B, "Value against the traditional approach (staffing, overtime, contractors): freed ED beds, "
                "fewer boarding hours, reduced overtime, how each number was reached, least certain assumptions.",
                "Brief 3; rubric 3 (2 pts)",
                "Break-even and the three scenarios as rounded ranges in models/impact_ranges.json (shown on the "
                "Overview and Downstream impact; the Impact simulator compares the saved scenarios). "
                "Charts: exports/ranges_vs_break_even.png, exports/value_vs_traditional.png and "
                "exports/sensitivity.png; every number and its source in docs/NUMBERS.md; the traditional "
                "comparison is in docs/STRATEGY.md section 3.", plan_value),
    Requirement("B3", B, "KPIs and ROI, including an equity KPI that shows gaps shrinking, not only averages.",
                "Brief 3; rubric 3 (2 pts)",
                "Fairness and Oversight, Waits and walkouts by group: the gap versus Commercial is the equity KPI. "
                "Chart: exports/payer_gaps.png. KPI table and ROI in docs/STRATEGY.md section 3.", plan_kpis),
    # 4. risk
    Requirement("K1", K, "Clinical and ethical risks: algorithmic bias, patient privacy, over-reliance on AI, loss "
                "of human connection.", "Brief 4; rubric 4 (2 pts)",
                "Bias: the fairness check. Privacy: insurance never used, runs offline. Over-reliance: overrides "
                "need a reason and a too-low override rate triggers review. Human connection: docs/STRATEGY.md "
                "section 4.",
                fairness_result),
    Requirement("K2", K, "Data security: how patient data is protected and the response if Halvian's or a vendor's "
                "systems are compromised.", "Brief 4; rubric 4 (2 pts)",
                "The prototype has no patient data and no network calls. The response plan if systems are "
                "compromised: docs/STRATEGY.md section 4.", offline),
    Requirement("K3", K, "Oversight: bias testing before launch, monitoring after, when to pause or retire, and how "
                "clinicians review and override without simply deferring.", "Brief 4; rubric 4 (3 pts)",
                "Fairness and Oversight: fairness check, When to pause, override-rate band", pause_rules),
    Requirement("K4", K, "Contingency plans: backup systems, manual protocols or hybrid workflows if a tool fails.",
                "Brief 4; rubric 4 (3 pts, shared)", "When to pause: phone, whiteboard and a bed huddle every 2 hours",
                pause_rules),
    Requirement("K5", K, "Bias testing before launch separates who arrives (case mix) from how the model treats "
                "similar patients.", "Brief 4 (oversight)", "models/metrics.json admission.fairness_case_mix; "
                "docs/STRATEGY.md section 2", bias_test_before_launch),
    Requirement("K6", K, "A written risk table, a response plan if systems are compromised, and contingency "
                "plans.", "Brief 4; rubric 4", "docs/STRATEGY.md section 4", risk_plan_written),
    # team rules
    Requirement("T1", T, "Models never use insurance.", "Team plan", "metrics.json feature lists", payer_blind),
    Requirement("T2", T, "No API keys, paid services or network calls at runtime.", "Team plan", "All app code",
                offline),
    Requirement("T3", T, "Estimates are labelled as estimates; simulated results are never shown as real evidence.",
                "Team plan", "Product frame header tag and footer (halvian/ui/chrome.py); Downstream impact page",
                estimates_labelled),
    Requirement("T4", T, "The synthetic hospital matches the brief's numbers.", "Team plan", "docs/DATA.md",
                calibrated),
    Requirement("T5", T, "No em dashes in user-facing text, README or docs.", "Team plan", "pages, README, docs",
                no_em_dashes),
]


REQUIREMENTS += [
    # the AI note reader
    Requirement("N1", N, "The note reader is a real language model that runs on this machine, with no cloud API "
                "and no keys.", "Team plan, Phase 2", "halvian/notes/reader.py (LLMNoteReader), prompt.py, ollama.py",
                reader_runs_locally),
    Requirement("N2", N, "The AI reader, the rules and their union are scored against the note labels: precision, "
                "recall and F1 overall, by barrier type and by payer group.", "Team plan, Phase 2",
                "models/metrics.json note_reader.llm, .rules, .combined; docs/MODELS.md", reader_evaluated),
    Requirement("N3", N, "The AI reader is at least as accurate as the rules it replaces.", "Team plan, Phase 2",
                "Same sample, same labels", reader_vs_rules),
    Requirement("N8", N, "What the app shows (AI reader plus rules) is at least as accurate as the rules alone, "
                "and the AI reader holds up on wording the rules were not written for.", "Brief 5 (meaningful AI)",
                "Sealed sample B and the new-phrasing stress set (models/metrics.json note_reader.combined, .stress)",
                reader_shown_beats_rules),
    Requirement("N4", N, "If the local model is off or times out, the rules answer and the result says so.",
                "Team plan, Phase 2", "halvian.notes.live.analyze_note; LLMNoteReader.read_detailed",
                reader_falls_back),
    Requirement("N5", N, "The AI reader works as well for every payer group.", "Brief 4 (bias); team plan",
                "note_reader.llm.by_payer", reader_fair_by_payer),
    Requirement("N6", N, "No invented evidence: a finding is kept only if its quote appears in the note, and "
                "negated or resolved barriers are dropped.", "Team plan, Phase 2",
                "halvian/notes/reader.py locate_evidence and span_is_inactive", reader_evidence_verbatim),
    Requirement("N7", N, "Honest about scale: which notes the model reads and which the rules read.",
                "Team plan, Phase 2", "docs/MODELS.md; models/llm_note_findings.parquet", reader_scale_documented),
    # 6. presentation
    Requirement("P1", P, "Very clear, well organized and engaging, with creativity, smooth flow and professional "
                "polish throughout.", "Rubric 6 (3 pts)",
                "The video. The guided demo gives a two-minute click path; docs/DEMO_SCRIPT.md times it.",
                team_status=SLIDES),
]

_RUBRIC_MAP: dict[str, tuple[str, ...]] = {
    **{f"D{k}": ("5.1",) for k in range(1, 10)},
    "S1": ("1.2",), "S2": ("2.1", "3.3"), "S3": ("1.3", "3.1"),
    "A1": ("1.1",), "A2": ("1.2",), "A3": ("1.3",), "A4": ("1.4",),
    "R1": ("2.1",), "R2": ("2.2",), "R3": ("2.3",),
    "B1": ("3.1",), "B2": ("3.2",), "B3": ("3.3",),
    "K1": ("4.1",), "K2": ("4.2",), "K3": ("4.3",), "K4": ("4.3",), "K5": ("4.3",),
    "K6": ("4.1", "4.2", "4.3"),
    "T1": ("4.1",), "T2": ("4.2",), "T3": ("6.1",), "T4": ("1.1",), "T5": ("6.1",),
    "N1": ("1.3", "4.2"), "N2": ("5.1",), "N3": ("5.1",), "N4": ("4.3",), "N5": ("4.1", "4.3"),
    "N6": ("4.1",), "N7": ("1.4",), "N8": ("5.1", "1.3"), "P1": ("6.1",),
}
REQUIREMENTS = [replace(req, rubric=_RUBRIC_MAP.get(req.id, ())) for req in REQUIREMENTS]


def evaluate_all() -> list[tuple[Requirement, Result]]:
    return [(req, req.evaluate()) for req in REQUIREMENTS]
