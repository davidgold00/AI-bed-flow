"""Source assumptions and validation for the synthetic Halvian replay."""

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from halvian import config as C
from halvian.notes.reader import PLACEHOLDER_LABEL
from halvian.ui.components import PROJECT_ROOT, number_column, page_header, percent_column
from halvian.ui.design import callout, capped_table, kpi, section_heading

DATA = PROJECT_ROOT / "data"
MODEL_METRICS = PROJECT_ROOT / "models" / "metrics.json"


@st.cache_data(show_spinner=False)
def read_json(path: Path, modified_ns: int):
    return json.loads(path.read_text())


def artifact(path: Path):
    return read_json(path, path.stat().st_mtime_ns) if path.is_file() else None


def scores_table(title: str, scores: dict, label_map: dict | None = None) -> None:
    label_map = label_map or {}
    table = pd.DataFrame([{"Group": label_map.get(group, group), **values}
                          for group, values in scores.items()])
    if table.empty:
        st.caption(f"{title} is unavailable.")
        return
    st.markdown(f"**{title}**")
    st.dataframe(
        table[["Group", "notes", "support", "precision", "recall", "f1"]],
        width="stretch",
        hide_index=True,
        column_config={
            "notes": number_column("Notes"),
            "support": number_column("Labelled barriers"),
            "precision": percent_column("Precision"),
            "recall": percent_column("Recall"),
            "f1": percent_column("F1"),
        },
    )


def planned_assumptions() -> pd.DataFrame:
    p = C.DEFAULT_PARAMS
    rows = [
        ("A1", "Unspecified payer share", f"{C.PAYER_MIX[C.OTHER]:.0%} grouped as {C.OTHER}."),
        ("A2", "Medicare wait", "Calculated from the replay. The brief gives no Medicare target."),
        ("A3", "Triage urgency", f"Starting mix for urgency levels 1 to 5: {', '.join(f'{v:.0%}' for v in p.esi_mix)}."),
        ("A4", "Demand differs by payer group", "Synthetic arrival timing and urgency differ by group. See the fitted settings below."),
        ("A5", "Inpatient units", ", ".join(f"{unit} {beds}" for unit, beds in C.UNITS.items()) + " beds."),
        ("A6", "Other ways patients enter the hospital", f"Starting yearly rates are {p.elective_per_year:,.0f} scheduled admissions and "
         f"{p.direct_per_year:,.0f} direct admissions. The ED is another source."),
        ("A7", "Length of stay", "Varies by unit and source. The simulation estimates the average from bed arrivals and departures."),
        ("A8", "Winter demand", f"December through February use a {p.winter_multiplier:g}× seasonal demand multiplier."),
        ("A9", "Discharge timing", f"Departures cluster in the afternoon. Late readiness can shift discharge to the next day. "
         f"About {p.weekend_hold_prob:.0%} of affected weekend departures can wait until Monday."),
        ("A10", "Discharge barriers", "Six synthetic barrier types. Barriers depend on age, mobility and documented payer adjustments."),
        ("A11", "Shift staffing", "The simulation pools physicians and advanced practice providers and allocates staff to registration, triage and bedside care."),
        ("A12", "Fast track", f"Open from {C.FAST_TRACK_HOURS[0]:02d}:00 to {C.FAST_TRACK_HOURS[1]:02d}:00 for less urgent visits."),
        ("A13", "Bed processing", "Acceptance, requests, unit preparation, transport and cleaning use assumed task times. "
         "The calibration adjusts the process as a whole to match median boarding."),
        ("A14", "Leaving before care", "Patients can leave if they wait past their drawn patience time, which varies with urgency and documented payer settings."),
        ("A15", "Uncertainty at triage", "The generator includes information that a triage score cannot see. Reported accuracy measures how well predictions work on synthetic data."),
        ("A16", "Scope", "The replay excludes transfers out and hallway treatment beds. Initial assignment can overflow to compatible units."),
        ("A17", "Impact scenario", "Staff response and recoverable task time are assumptions. Compare them with the logged action timing."),
        ("A18", "Metric denominators", "Median time to provider uses visits with a provider contact. The fraction who left unseen uses all arrivals."),
        ("A19", "Replay calendar", f"Fictional year {C.YEAR_START.year}. Default replay is {C.DEMO_DAY_LABELS['busy']}."),
        ("A20", "Priority after long waits", f"Patients at urgency levels 4 and 5 receive level 3 "
         f"queue priority after {p.low_acuity_promote_after_min:g} minutes."),
        ("A21", "Inpatient observations", "Mobility and lab trend follow recovery with day-to-day noise; a barrier "
         "is documented 6 to 48 hours into the stay."),
        ("A22", "Bed board effect", f"Our assumption: the Live Bed Board cuts housekeeping notification and bed "
         f"request processing by {C.BED_BOARD_DELAY_CUT:.0%} (Expected and Full rollout only). No study backs it."),
        ("Models", "Prediction inputs", "Both models exclude payer. Payer is used to audit whether errors and outcomes differ across groups."),
    ]
    return pd.DataFrame(rows, columns=["ID", "Assumption", "How it is used"])


page_header(
    "How we tested the dashboard",
    "How closely the synthetic year matches the case, the assumptions behind it, and how well the models and the "
    "note reader score. Every score is measured on synthetic data.",
    "We generated an artificial year of arrivals, queues, inpatient stays and typed notes, calibrated to the case "
    "brief. Models were trained on January to September and scored on October to December.",
)

section_heading("The synthetic year matches the case brief")
validation = artifact(DATA / "validation.json")
if validation:
    checks = pd.DataFrame(validation["checks"])
    passed = int(checks["Pass"].sum())
    kpi("Case targets within tolerance", f"{passed} of {len(checks)}", "Main synthetic year")
    if passed < len(checks):
        callout("Some checks are outside tolerance. Review them before using scenario results.")
    checks["Result"] = checks["Pass"].map({True: "Pass", False: "Outside tolerance"})
    capped_table(checks[["Target", "Tolerance", "Result"]], key="calibration",
                 column_config={"Target": "Case target", "Tolerance": "Tolerance", "Result": "Status"})
else:
    callout("No saved calibration results yet. Run scripts/generate_data.py.")

section_heading("Assumptions where the brief is silent")
capped_table(planned_assumptions(), key="assumptions", column_config={
    "ID": "Reference", "Assumption": "Assumption", "How it is used": st.column_config.TextColumn(width="large"),
})
metrics = artifact(MODEL_METRICS) or {}
section_heading("How well the models score on synthetic data")
with st.expander("Model scores", expanded=True):
    if metrics:
        st.caption("Measured on synthetic October to December data. AUC: how well the model ranks cases (0.5 is "
                   "chance, 1.0 is perfect). Precision: the share of flags that were correct.")
        policies = [
            ("Flags for ED admission", metrics["admission"]["deployed_policy"]),
            ("Flags for discharge within 24 hours", metrics["discharge"]["at_threshold"]),
        ]
        st.table([{"Prediction": name, "AUC": f"{scores['auc']:.2f}", "Precision": f"{scores['precision']:.2f}"}
                  for name, scores in policies], hide_index=True)
        st.table([{"Hours ahead": row["horizon_h"], "Mean error (beds)": f"{row['mae']:.2f}",
                   "Mean error if we forecast no change (beds)": f"{row['mae_persistence']:.2f}"}
                  for row in metrics["forecast"]["backtest"]], hide_index=True)
    st.markdown("Insurance is used to audit model errors and outcome gaps. Both models exclude it from predictions.")
    records = artifact(DATA / "payer_parameters.json")
    if records:
        st.dataframe(pd.DataFrame(records), hide_index=True, width="stretch")

section_heading("The note reader finds documented barriers")
with st.expander("Note reader scores"):
    st.caption(PLACEHOLDER_LABEL)
    st.markdown("**Precision** is the share of flags that are correct. "
                "**Recall** is the share of labelled barriers the reader finds. **F1** balances the two.")
    scores = metrics.get("note_reader")
    if scores:
        scores_table("All notes", {"All notes": scores["overall"]})
        scores_table("By barrier type", scores["by_barrier"], C.BARRIER_LABELS)
        scores_table("By insurance group", scores["by_payer"])
        st.caption("Measured on templated synthetic notes.")
    else:
        callout("No saved note reader scores yet. Run scripts/train_models.py.")

section_heading("Sources behind the design")
st.markdown(
    """
- Case baseline and costing assumptions. Healthcare AI Case Competition Brief. See the simulation assumptions above.
- Context on emergency department boarding and crowding. [American College of Emergency Physicians](https://www.acep.org/administration/crowding--boarding)
- Discharge prediction and multidisciplinary rounds. [Johns Hopkins study](https://pure.johnshopkins.edu/en/publications/machine-learning-based-hospital-discharge-predictions-can-support/)
- Admission prediction at triage. [Operations Research](https://pubsonline.informs.org/doi/10.1287/opre.2022.2405)
- Preprint on hourly requests for inpatient beds. [Proactive Inpatient Bed Requests for ED Admissions](https://arxiv.org/abs/2607.15432)
- Triage-only prediction in prior work. [PLOS ONE](https://pmc.ncbi.nlm.nih.gov/articles/PMC6054406/)
- Evidence on morning discharge timing. [Journal of Hospital Medicine](https://pubmed.ncbi.nlm.nih.gov/34328839/)
"""
)
