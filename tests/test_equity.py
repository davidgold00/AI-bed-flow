import pandas as pd
import pytest

from halvian import config as C
from halvian.equity import gap_table, payer_outcomes, verdict


def visits(commercial_wait, uninsured_wait):
    return pd.DataFrame({
        "payer": [C.COMMERCIAL] * 2 + [C.UNINSURED] * 2,
        "door_to_provider_min": [commercial_wait, commercial_wait + 4, uninsured_wait, None],
        "provider_min": [commercial_wait, commercial_wait + 4, uninsured_wait, None],
        "lwbs": [False, False, False, True],
    })


def test_payer_metrics_use_all_arrivals_for_walkouts_and_seen_patients_for_waits():
    result = payer_outcomes(visits(40, 58))
    assert result.loc[C.COMMERCIAL, "d2p_median"] == 42
    assert result.loc[C.UNINSURED, "d2p_median"] == 58
    assert result.loc[C.UNINSURED, "lwbs_pct"] == 50
    assert result.loc[C.UNINSURED, "visits"] == 2


def test_gap_table_retains_sign_and_evaluates_absolute_gap_after_crossing_zero():
    results = gap_table(visits(40, 47), visits(40, 30))
    uninsured = results[results["Gap"] == f"{C.UNINSURED} vs {C.COMMERCIAL}"]
    wait, walkouts = uninsured.iloc[0], uninsured.iloc[1]
    assert wait["Baseline"] == 5
    assert wait["With tool"] == -12
    assert wait["Change"] == -17
    assert wait["Absolute gap change"] == 7
    assert wait["Verdict"] == "Widened"
    assert walkouts["Verdict"] == "Flat"
    assert walkouts["Flat tolerance"] == C.EQUITY_GUARDRAIL["lwbs_gap_pts"] / 2
    assert set(results["Gap"]) == {f"{payer} vs {C.COMMERCIAL}" for payer in C.PAYERS if payer != C.COMMERCIAL}
    assert set(results.loc[~results.index.isin(uninsured.index), "Verdict"]) == {"Insufficient data"}


@pytest.mark.parametrize(
    ("change", "label"), [(-2.0, "Narrowed"), (-1.0, "Flat"), (0, "Flat"), (1.0, "Flat"), (2.0, "Widened")]
)
def test_verdict_uses_stated_tolerance(change, label):
    assert verdict(change, 1.0) == label
