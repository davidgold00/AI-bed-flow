"""Compare simulated patient outcomes with the commercially insured group.

Use `gap_table(baseline_ed, scenario_ed)` for a signed group comparison.
Each input must have one row per ED arrival in the same reporting window.
Use `monthly_gaps` and `guardrail` for the monitored Medicaid/CHIP and uninsured
gaps series. The underlying denominators come from halvian.data.gaps.
"""

import math

import pandas as pd

from halvian import config as C
from halvian.data.gaps import guardrail, monthly_gaps, payer_outcomes

__all__ = ["gap_table", "guardrail", "monthly_gaps", "payer_outcomes", "verdict"]

_MEASURES = (
    ("d2p_median", "Door-to-provider (median)", "min", "door_to_provider_gap_min"),
    ("lwbs_pct", "Left without being seen", "pts", "lwbs_gap_pts"),
)


def verdict(change: float, tolerance: float) -> str:
    """Describe a change in gap magnitude within an inclusive flat threshold."""
    if not math.isfinite(change):
        return "Insufficient data"
    if abs(change) <= tolerance or math.isclose(abs(change), tolerance):
        return "Flat"
    return "Narrowed" if change < 0 else "Widened"


def gap_table(baseline_ed: pd.DataFrame, scenario_ed: pd.DataFrame) -> pd.DataFrame:
    """Compare each payer with Commercial without losing the direction of a gap.

    Baseline and With tool are signed group-minus-Commercial differences.
    Change is the signed difference between scenarios. Verdict uses the change
    in absolute gap size. The flat range is half the configured review
    tolerance, consistent with the baseline gap display.
    """
    baseline = payer_outcomes(baseline_ed)
    scenario = payer_outcomes(scenario_ed)
    rows = []
    for payer in C.PAYERS:
        if payer == C.COMMERCIAL:
            continue
        for column, label, unit, config_key in _MEASURES:
            base = baseline.loc[payer, column] - baseline.loc[C.COMMERCIAL, column]
            current = scenario.loc[payer, column] - scenario.loc[C.COMMERCIAL, column]
            magnitude_change = abs(current) - abs(base)
            tolerance = C.EQUITY_GUARDRAIL[config_key] / 2
            rows.append({
                "Gap": f"{payer} vs {C.COMMERCIAL}",
                "Measure": label,
                "Unit": unit,
                "Baseline": base,
                "With tool": current,
                "Change": current - base,
                "Absolute gap change": magnitude_change,
                "Flat tolerance": tolerance,
                "Verdict": verdict(magnitude_change, tolerance),
            })
    return pd.DataFrame(rows)
