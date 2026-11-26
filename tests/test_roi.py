from datetime import datetime, timedelta

import pytest

from halvian.roi import PitchCapacityExample, estimate_capacity, pitch_capacity_examples

WINDOW_START = datetime(2025, 10, 1)
WINDOW_END = WINDOW_START + timedelta(hours=12)


def interval(start_hour, end_hour):
    return WINDOW_START + timedelta(hours=start_hour), WINDOW_START + timedelta(hours=end_hour)


def test_capacity_clips_both_arms_and_counts_different_admission_cohorts():
    baseline = [interval(-4, 2), interval(4, 8), interval(11, 14), interval(12, 16)]
    scenario = [interval(-4, 1), interval(5, 7), interval(11, 13), interval(8, 9)]
    impact = estimate_capacity(
        baseline, scenario, window_start=WINDOW_START, window_end=WINDOW_END, baseline_admissions=2
    )
    assert impact.baseline_boarded_hours == 7
    assert impact.scenario_boarded_hours == 5
    assert impact.bed_hours_freed == 2
    assert impact.capacity_value == 700
    assert impact.annualized_bed_hours_freed == 13_600
    assert impact.annualized_capacity_value == 4_760_000


def test_capacity_retains_negative_impact():
    impact = estimate_capacity(
        [interval(1, 2)],
        [interval(1, 5)],
        window_start=WINDOW_START,
        window_end=WINDOW_END,
        baseline_admissions=1,
    )
    assert impact.bed_hours_freed == -3
    assert impact.capacity_value == -1_050


def test_no_baseline_admissions_leaves_the_annual_estimate_undefined():
    impact = estimate_capacity(
        [], [], window_start=WINDOW_START, window_end=WINDOW_END, baseline_admissions=0
    )
    assert impact.capacity_value == 0
    assert impact.annualized_bed_hours_freed is None
    assert impact.annualized_capacity_value is None


def test_reversed_interval_fails_instead_of_hiding_bad_timestamps():
    with pytest.raises(ValueError, match="ED departure precedes"):
        estimate_capacity(
            [interval(4, 2)],
            [],
            window_start=WINDOW_START,
            window_end=WINDOW_END,
            baseline_admissions=1,
        )


def test_pitch_examples_reproduce_mean_reductions_at_case_volume():
    assert pitch_capacity_examples() == (
        PitchCapacityExample(15, 3_400, 1_190_000),
        PitchCapacityExample(30, 6_800, 2_380_000),
        PitchCapacityExample(60, 13_600, 4_760_000),
    )
