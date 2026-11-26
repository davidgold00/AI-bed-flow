"""Build models/plan.json (budget, value, ROI, goals, gates, KPIs) and models/impact_ranges.json.

    python scripts/build_plan.py

models/impact_ranges.json is the results contract the UI reads: the tool's effect as rounded
ranges introduced by a break-even point (halvian/ranges.py).

Reads the assumptions in halvian/config.py ([assumption B<n>]), the saved impact simulation
(models/scenarios.json) and the model metrics (models/metrics.json). Nothing is typed in by
hand: change an assumption in config and rerun. scripts/export_numbers.py and
scripts/export_strategy.py read the result.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from halvian import ranges, roi  # noqa: E402
from halvian import roadmap as R  # noqa: E402

PLAN = ROOT / "models" / "plan.json"
RANGES = ROOT / "models" / "impact_ranges.json"


def note_precision(metrics: dict) -> float | None:
    """Precision of the findings the app shows: the AI reader plus the rules, else the rules."""
    nr = metrics.get("note_reader", {})
    shown = nr.get("combined") or nr
    return shown.get("overall", {}).get("precision")


def build(scenarios: dict, metrics: dict) -> dict:
    b = roi.budget()
    r = roi.roi(scenarios)
    goals = R.goals(scenarios)
    return {
        "budget": b,
        "traditional": roi.traditional_approach(b["run_per_year"]),
        "value": roi.value_of_gains(scenarios),
        "roi": r,
        "goals": goals,
        "milestones": R.milestones(),
        "pilot_gates": R.pilot_gates(metrics, scenarios, note_precision(metrics)),
        "phase2": R.phase2_adjustment(metrics, scenarios),
        "kpis": R.kpis(scenarios, r, goals),
    }


def main() -> dict:
    scenarios = json.loads((ROOT / "models" / "scenarios.json").read_text())
    metrics = json.loads((ROOT / "models" / "metrics.json").read_text())
    plan = build(scenarios, metrics)
    PLAN.write_text(json.dumps(plan, indent=1))
    RANGES.write_text(json.dumps(ranges.build(scenarios, plan), indent=1) + "\n")
    b = plan["budget"]
    print(f"Budget: pilot ${b['by_phase']['pilot']:,.0f}, scale ${b['by_phase']['scale']:,.0f}, "
          f"18 months ${b['total_18_months']:,.0f} (cap ${b['caps']['18_months']:,.0f}), "
          f"then ${b['run_per_year']:,.0f} a year")
    return plan


if __name__ == "__main__":
    main()
