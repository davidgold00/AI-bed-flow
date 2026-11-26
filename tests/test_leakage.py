"""No model may see information that is not available when it makes its prediction."""

from __future__ import annotations

import re
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

from halvian.models import admission as A
from halvian.models import discharge as D

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = re.compile(
    r"disposition|admitted|admit_unit|boarding|decision|departure|discharge_min|hours_to|"
    r"los_h$|ready|barrier_active|true_barrier|would_admit|lwbs|provider|roomed|bed_|"
    r"severity_latent|comorbidity_latent|patience|label|payer"
)


@pytest.mark.parametrize("module", [A, D])
def test_features_are_on_the_prediction_time_allowlist(module):
    assert set(module.FEATURES) <= module.AVAILABLE_AT_PREDICTION, module.PREDICTION_TIME
    assert len(module.FEATURES) == len(set(module.FEATURES))


@pytest.mark.parametrize("module", [A, D])
def test_no_forbidden_or_outcome_features(module):
    bad = [f for f in module.FEATURES if FORBIDDEN.search(f)]
    assert not bad, f"{module.__name__} uses post-prediction or payer features: {bad}"


@pytest.mark.parametrize("module", [A, D])
def test_default_models_are_payer_blind(module):
    assert "payer" not in module.new_model("logistic").features
    assert "payer" not in module.new_model("boosting").features
    assert "payer" in module.new_model("logistic", with_payer=True).features


def test_discharge_barrier_features_come_from_the_reader_not_ground_truth():
    assert all(f.startswith("note_") for f in D.BARRIER_FEATURES)
    days = pd.DataFrame({"note_id": ["a", "b"], "true_barrier": ["transport", None]})
    found = pd.DataFrame({"note_id": ["b"], "barrier_type": ["transport"], "start": [0], "end": [3],
                          "confidence": [0.9]})
    out = D.add_barrier_flags(days, found)
    assert out.note_transport.tolist() == [0.0, 1.0]  # follows the reader, not the truth


DATA = ROOT / "data"
MODELS = ROOT / "models"
needs_artifacts = pytest.mark.skipif(
    not (MODELS / "admission.joblib").exists() or not (DATA / "ed_visits.parquet").exists(),
    reason="run scripts/generate_data.py and scripts/train_models.py first")


@needs_artifacts
def test_admission_scores_unchanged_when_future_columns_change():
    """As-of property: rewriting what happens after triage must not move the score."""
    model = joblib.load(MODELS / "admission.joblib")["model"]
    ed = pd.read_parquet(DATA / "ed_visits.parquet").sample(500, random_state=1)
    X = A.prepare(ed)
    p0 = model.predict_proba(X)
    X2 = X.copy()
    X2["decision_min"] = X2.decision_min + 999
    X2["departure_min"] = X2.departure_min + 999
    X2["disposition"] = "Discharged"
    X2["admitted"] = ~X2.admitted
    X2["admit_unit"] = "ICU"
    X2["boarding_min"] = 0.0
    X2["payer"] = "Commercial"
    assert np.allclose(p0, model.predict_proba(X2))


@needs_artifacts
def test_discharge_scores_unchanged_when_future_columns_change():
    model = joblib.load(MODELS / "discharge.joblib")["model"]
    days = pd.read_parquet(DATA / "inpatient_days.parquet").sample(500, random_state=2)
    found = pd.read_parquet(MODELS / "note_findings.parquet")
    X = D.add_barrier_flags(days, found)
    p0 = model.predict_proba(X)
    X2 = X.copy()
    for col, val in (("discharge_min", 0.0), ("hours_to_discharge", 1.0), ("discharged_24h", True),
                     ("true_barrier", "placement"), ("barrier_active", True), ("payer", "Uninsured")):
        X2[col] = val
    assert np.allclose(p0, model.predict_proba(X2))


def test_temporal_split_requires_outcomes_known_before_cutoff():
    from halvian.models.common import month_start, split_labels

    score = pd.Series([month_start(8) + 10, month_start(9) - 60, month_start(9) + 10, month_start(10) + 10])
    outcome = pd.Series([month_start(8) + 100, month_start(9) + 30, month_start(9) + 100, month_start(10) + 50])
    assert split_labels(score, outcome).tolist() == ["fit", "", "valid", "test"]
