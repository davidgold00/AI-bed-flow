"""The configuration must reproduce the case brief exactly."""

from halvian import config as C


def test_payer_mix_matches_brief_and_sums_to_one():
    assert C.PAYER_MIX_BRIEF == {
        C.MEDICAID: 0.35, C.MEDICARE: 0.22, C.COMMERCIAL: 0.33, C.UNINSURED: 0.08
    }
    assert abs(sum(C.PAYER_MIX.values()) - 1.0) < 1e-9
    assert abs(C.PAYER_MIX[C.OTHER] - 0.02) < 1e-9
    assert set(C.PAYER_MIX) == set(C.PAYERS)


def test_volume_and_admissions():
    assert C.ED_VISITS_PER_YEAR == 85_000
    assert C.ADMISSION_RATE == 0.16
    assert C.ED_ADMISSIONS_PER_YEAR == 13_600


def test_ed_spaces_and_beds():
    assert C.ED_SPACES == {"main": 32, "fast_track": 8, "resus": 4, "behavioral": 4}
    assert C.WAITING_ROOM_SEATS == 40
    assert sum(C.UNITS.values()) == C.INPATIENT_BEDS == 320
    assert C.UNITS["ICU"] == C.ICU_BEDS == 24
    assert sum(v for k, v in C.UNITS.items() if k != "ICU") == 296


def test_staffing_matches_brief():
    assert C.STAFFING == {
        "physicians": (4, 4, 2),
        "apps": (3, 3, 1),
        "nurses": (14, 14, 9),
        "techs_registration": (8, 7, 4),
    }
    assert C.PROVIDERS == (7, 7, 3)
    for role_counts, total in (
        (C.REGISTRATION_CLERKS, C.STAFFING["techs_registration"]),
        (C.TRIAGE_NURSES, C.STAFFING["nurses"]),
    ):
        assert all(r <= t for r, t in zip(role_counts, total, strict=True))


def test_costs_match_brief():
    assert (C.COST_NURSE_PER_H, C.COST_PHYSICIAN_PER_H, C.COST_APP_PER_H, C.COST_ADMIN_PER_H) == (
        65, 200, 100, 35
    )
    assert C.OVERTIME_MULTIPLIER == 1.5
    assert C.NET_REVENUE_PER_VISIT == 1_500
    assert C.BOARDING_COST_PER_BED_HOUR == 350


def test_outcome_targets_match_brief():
    assert C.MEDIAN_DOOR_TO_PROVIDER_MIN == 55
    assert C.DOOR_TO_PROVIDER_BY_PAYER_MIN == {C.COMMERCIAL: 48, C.MEDICAID: 58, C.UNINSURED: 64}
    assert C.LWBS_RATE == 0.04
    assert C.LWBS_BY_PAYER == {C.COMMERCIAL: 0.03, C.MEDICAID: 0.046, C.UNINSURED: 0.058}
    assert C.MEDIAN_BOARDING_H == 3.5
    assert C.TARGET_OCCUPANCY == 0.88


def test_impact_defaults_use_observable_timing_and_documented_assumptions():
    assert C.IMPACT_DEFAULTS == {
        "adoption": 0.5,
        "staff_response_delay_h": 1.0,
        "threshold": 0.7,
        "discharge_hours_saved": 1.0,
    }
    assert C.IMPACT_RANGES["discharge_hours_saved"] == (0.0, 4.0)
    assert set(C.IMPACT_DEFAULT_SOURCES) == set(C.IMPACT_DEFAULTS) == set(C.IMPACT_RANGES)


def test_payer_barrier_mechanism_is_explicit_and_adjustable():
    """PLAN.md decision 6: Medicaid/CHIP and Uninsured have more non-medical barriers by
    default, as documented parameters that can be neutralised for sensitivity runs."""
    import dataclasses

    p = C.DEFAULT_PARAMS
    assert p.barrier_payer_logodds[C.COMMERCIAL] == 0.0
    assert p.barrier_payer_logodds[C.MEDICAID] > 0 and p.barrier_payer_logodds[C.UNINSURED] > 0
    assert p.barrier_type_payer_tilt[C.COMMERCIAL] == 1.0
    neutral = dataclasses.replace(p, barrier_payer_logodds=dict.fromkeys(C.PAYERS, 0.0),
                                  barrier_type_payer_tilt=dict.fromkeys(C.PAYERS, 1.0))
    assert set(neutral.barrier_payer_logodds.values()) == {0.0}


def test_params_distributions_are_normalised():
    p = C.DEFAULT_PARAMS
    assert abs(sum(p.hourly_weekday) - 1) < 1e-9
    assert abs(sum(p.hourly_weekend) - 1) < 1e-9
    assert abs(sum(p.esi_mix) - 1) < 1e-9
    assert abs(sum(p.dow_multiplier) - 7) < 1e-9
    assert abs(sum(C.BARRIER_BASE_MIX.values()) - 1) < 1e-9
    assert abs(sum(C.NON_ED_PAYER_MIX.values()) - 1) < 1e-9
    assert abs(sum(C.DIRECT_UNIT_MIX.values()) - 1) < 1e-9
    assert abs(sum(C.ELECTIVE_UNIT_MIX.values()) - 1) < 1e-9
