"""Synthetic note generation and its ground truth."""

from __future__ import annotations

import numpy as np

from halvian.data.notes import ACTIVE, RESOLVED, make_note


def _note(seed, t, barrier, identified=0.0, resolved=10_000.0):
    rng = np.random.default_rng(seed)
    return make_note(rng, t, 0.5, 15.0, barrier, identified, resolved, base_weekday=0, typo_rate=0.0)


def test_deterministic_for_same_seed():
    assert _note(1, 100.0, "transport") == _note(1, 100.0, "transport")


def test_active_barrier_is_labelled_only_while_active():
    labelled_active = sum("transport" in _note(s, 100.0, "transport")[1] for s in range(300))
    labelled_after = sum(bool(_note(s, 20_000.0, "transport")[1]) for s in range(300))
    labelled_before = sum(bool(_note(s, 100.0, "transport", identified=500.0)[1]) for s in range(300))
    assert 200 < labelled_active < 300  # usually documented, not always
    assert labelled_after == 0  # resolved barriers never count as active
    assert labelled_before == 0  # not yet identified


def test_no_barrier_means_no_label():
    assert all(_note(s, 100.0, None)[1] == [] for s in range(200))


def test_templates_cover_all_types():
    assert set(ACTIVE) == set(RESOLVED)


def test_barrier_documentation_does_not_depend_on_future_resolution():
    """Changing how long a barrier lasts must not change anything observed before it ends."""
    import pandas as pd

    from halvian.data.generate import inpatient_days

    base = pd.DataFrame({
        "stay_id": ["IP-000001"], "bed_arrival_min": [100_000.0], "ready_min": [100_000.0 + 72 * 60],
        "discharge_min": [100_000.0 + 140 * 60], "barrier": ["transport"], "barrier_delay_h": [30.0],
        "ip_note_seed": [12345], "ip_mobility0": [14.0], "unit": ["Medicine A"], "dx_group": ["Digestive"],
        "source": ["ED"], "payer": ["Medicaid/CHIP"], "age": [70],
    })
    longer = base.assign(barrier_delay_h=60.0, discharge_min=100_000.0 + 170 * 60)
    from datetime import date
    window = (date(2024, 11, 1), date(2026, 1, 1))
    d1, _, _ = inpatient_days(base, seed=1, start=window[0], end=window[1])
    d2, _, _ = inpatient_days(longer, seed=1, start=window[0], end=window[1])
    cutoff = 100_000.0 + (72 + 30) * 60  # before the shorter barrier resolves
    cols = ["rounds_min", "mobility_score", "lab_trend", "barrier_active", "los_so_far_h"]
    a1 = d1.loc[d1.rounds_min < cutoff, cols].reset_index(drop=True)
    a2 = d2.loc[d2.rounds_min < cutoff, cols].reset_index(drop=True)
    assert len(a1) >= 3
    pd.testing.assert_frame_equal(a1, a2)
