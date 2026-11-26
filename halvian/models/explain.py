"""Turn feature contributions into short plain-English reasons.

Example: ``["Age 78 raises the chance", "Chest pain raises it", "ESI 2 raises it"]``.
Reasons describe what pushed this estimate up or down compared with a typical patient.
They are explanations of the model, not clinical causes.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from halvian import config as C
from halvian.data.cohort import COMPLAINT_LABELS

WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

FEATURE_LABELS = {
    "age": "Age",
    "heart_rate": "Heart rate",
    "systolic_bp": "Blood pressure",
    "resp_rate": "Breathing rate",
    "spo2": "Oxygen level",
    "temp_c": "Temperature",
    "recent_ed_visits_12m": "ED visits in past year",
    "chief_complaint": "Main complaint",
    "esi": "Triage level (ESI)",
    "arrival_mode": "Arrival mode",
    "arrival_period": "Time of arrival",
    "weekend": "Weekend",
    "winter": "Winter season",
    "payer": "Insurance (comparison model only)",
    "los_so_far_h": "Time in hospital so far",
    "unit": "Unit",
    "dx_group": "Diagnosis group",
    "source": "Admission source",
    "mobility_score": "Mobility score",
    "lab_trend": "Lab trend",
    "rounds_dow": "Day of the week",
    **{f"note_{b}": f"Note: {C.BARRIER_LABELS[b].lower()}" for b in C.BARRIER_TYPES},
}


def phrase(feature: str, value) -> str:
    """How a single feature value reads in a sentence."""
    if feature == "age":
        return f"Age {float(value):.0f}"
    if feature == "heart_rate":
        return f"Heart rate {float(value):.0f}"
    if feature == "systolic_bp":
        return f"Blood pressure {float(value):.0f}"
    if feature == "resp_rate":
        return f"Breathing rate {float(value):.0f}"
    if feature == "spo2":
        return f"Oxygen level {float(value):.0f}%"
    if feature == "temp_c":
        return f"Temperature {float(value):.1f} C"
    if feature == "recent_ed_visits_12m":
        v = int(float(value))
        return "No ED visits in the past year" if v == 0 else f"{v} ED visit{'s' if v != 1 else ''} in the past year"
    if feature == "chief_complaint":
        return COMPLAINT_LABELS.get(str(value), str(value))
    if feature == "esi":
        return f"ESI {value}"
    if feature == "arrival_mode":
        return "Arrived by ambulance" if str(value) == "Ambulance" else "Walked in"
    if feature == "arrival_period":
        return f"Arrival in the {value}"
    if feature == "weekend":
        return "Weekend arrival" if str(value) in ("True", "1") else "Weekday arrival"
    if feature == "winter":
        return "Winter season" if str(value) in ("True", "1") else "Outside winter"
    if feature == "payer":
        return f"Insurance: {value}"
    if feature == "los_so_far_h":
        return f"{float(value) / 24:.1f} days in hospital so far"
    if feature == "unit":
        return f"On {value}"
    if feature == "dx_group":
        return f"{value} diagnosis"
    if feature == "source":
        return f"{value} admission"
    if feature == "mobility_score":
        return f"Mobility score {float(value):.0f} of 24"
    if feature == "lab_trend":
        v = float(value)
        return "Labs improving" if v > 0.4 else ("Labs worsening" if v < -0.4 else "Labs stable")
    if feature == "rounds_dow":
        try:
            return f"{WEEKDAY_NAMES[int(float(value))]} rounds"
        except (ValueError, IndexError):
            return f"{value} rounds"
    if feature.startswith("note_"):
        label = C.BARRIER_LABELS[feature[5:]].lower()
        return f"Note flags {label}" if float(value) >= 0.5 else f"No {label} flagged in note"
    return f"{FEATURE_LABELS.get(feature, feature)} {value}"


def top_reasons(contrib: pd.DataFrame, values: pd.DataFrame, k: int = 3,
                exclude: tuple[str, ...] = ()) -> list[list[str]]:
    """Top-k reasons per row, largest absolute contribution first."""
    out = []
    cols = [c for c in contrib.columns if c not in exclude]
    arr = contrib[cols].to_numpy()
    for r in range(len(contrib)):
        order = np.argsort(-np.abs(arr[r]))[:k]
        reasons = []
        for j, col_idx in enumerate(order):
            feat = cols[col_idx]
            c = arr[r, col_idx]
            verb = "raises" if c > 0 else "lowers"
            tail = "the chance" if j == 0 else "it"
            reasons.append(f"{phrase(feat, values.iloc[r][feat])} {verb} {tail}")
        out.append(reasons)
    return out


def importance_labels(imp: pd.DataFrame) -> pd.DataFrame:
    imp = imp.copy()
    imp["label"] = imp.feature.map(lambda f: FEATURE_LABELS.get(f, f))
    return imp
