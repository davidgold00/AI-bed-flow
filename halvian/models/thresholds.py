"""Alert thresholds and hourly batched bed requests.

Two ideas from the team's research:

* **Moving threshold** (Operations Research, "Using Hospital Admission Predictions at
  Triage"): request beds at a lower probability when the ED is packed, and only at a
  higher probability when it is quiet.
* **Batched requests** (arXiv 2026, "Proactive Inpatient Bed Requests"): each hour, ask
  each unit for the *expected number* of beds (the sum of admission probabilities of
  flagged patients), instead of one request per patient, so one wrong call costs little.
"""

from __future__ import annotations

from collections.abc import Iterable

from halvian import config as C


def moving_threshold(
    crowding: float,
    typical_crowding: float,
    base: float = C.ALERT_THRESHOLD,
    slope: float = C.MOVING_THRESHOLD_SLOPE,
    floor: float = C.MOVING_THRESHOLD_FLOOR,
    ceiling: float = C.MOVING_THRESHOLD_CEILING,
    enabled: bool = C.MOVING_THRESHOLD_ON,
) -> float:
    """Alert threshold given current ED crowding.

    crowding = (patients in ED spaces + patients not yet roomed) / 48 ED spaces.
    Above the typical level the threshold drops; below it, the threshold rises.
    The result never leaves [floor, ceiling], and the floor/ceiling are widened if needed
    so a user-chosen base threshold is always reachable.
    """
    if not enabled:
        return base
    lo, hi = min(floor, base), max(ceiling, base)
    return float(min(hi, max(lo, base - slope * (crowding - typical_crowding))))


def threshold_reason(crowding: float, typical_crowding: float, threshold: float,
                     base: float = C.ALERT_THRESHOLD) -> str:
    """Plain-English explanation of the current threshold."""
    pct = f"{threshold:.0%}"
    if abs(threshold - base) < 0.005:
        return f"ED crowding is about typical, so the alert threshold stays at {pct}."
    if threshold < base:
        return (f"The ED is more crowded than usual, so the threshold is lowered from "
                f"{base:.0%} to {pct} to request beds earlier.")
    return (f"The ED is quieter than usual, so the threshold is raised from {base:.0%} to "
            f"{pct} to avoid unnecessary requests.")


def batch_request(probabilities: Iterable[float], already_reserved: int = 0) -> dict:
    """Beds to request from one unit in this hour's batch.

    The request is the rounded sum of admission probabilities (an expected count), minus
    beds already reserved for the ED on that unit, and never negative.
    """
    probs = [float(p) for p in probabilities]
    expected = sum(probs)
    beds = max(0, round(expected) - int(already_reserved))
    return {"patients": len(probs), "expected_admissions": expected, "beds_to_request": beds}
