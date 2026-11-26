"""Single source of truth for every number in the Halvian prototype.

Every constant carries a tag saying where it comes from:

  [brief: <section>]   taken directly from the case brief
  [assumption A<n>]    our assumption where the brief is silent; each is listed in
                       docs/DATA.md
  [calibrated]         tuned with scripts/calibrate.py so the simulation reproduces a
                       brief target; the target it serves is named in the comment
  [equity param]       an explicit, adjustable payer-specific mechanism (never hidden)
  [pitch] / [strategy] from the team's planning documents

All data are synthetic. Nothing here describes a real hospital or a real patient.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------
SEED = 20_261_124  # one global seed; every random stream is spawned from it
IMPACT_REPLICATION_SEEDS = (SEED, SEED + 1, SEED + 2)  # synthetic years for the impact sim

# ---------------------------------------------------------------------------
# Calendar  [assumption A19]
# ---------------------------------------------------------------------------
WARMUP_START = date(2024, 11, 1)  # two months simulated and discarded so the census is steady
YEAR_START = date(2025, 1, 1)  # fictional hospital year on the 2025 calendar
YEAR_END = date(2026, 1, 1)  # exclusive
WINTER_MONTHS = (12, 1, 2)  # winter respiratory season  [assumption A8]
TRAIN_MONTHS = tuple(range(1, 10))  # Jan to Sep: model training
VALID_MONTH = 9  # model selection month inside training
TEST_MONTHS = (10, 11, 12)  # Oct to Dec: held-out test period and impact simulation
IMPACT_WARMUP_START = date(2025, 8, 1)  # impact runs start here with the tool off

DEMO_DAYS = {
    "busy": date(2025, 12, 8),  # Monday, winter, busiest weekday, test period
    "typical": date(2025, 10, 15),  # Wednesday in fall, test period
}
DEMO_START_HOUR = 10  # replay clock starts at 10:00 on the demo day
DEMO_DAY_LABELS = {
    "busy": "Busy winter Monday (Mon Dec 8, 2025)",
    "typical": "Typical mid-week fall day (Wed Oct 15, 2025)",
}

# ---------------------------------------------------------------------------
# Patients and payers  [brief: Halvian at a Glance, Patients]
# ---------------------------------------------------------------------------
ED_VISITS_PER_YEAR = 85_000  # [brief: Company and Case Overview]
ADMISSION_RATE = 0.16  # [brief: Patients] about 13,600 admissions a year

MEDICAID = "Medicaid/CHIP"
MEDICARE = "Medicare"
COMMERCIAL = "Commercial"
UNINSURED = "Uninsured"
OTHER = "Other (VA, workers' comp, auto)"
PAYERS = (MEDICAID, MEDICARE, COMMERCIAL, UNINSURED, OTHER)

PAYER_MIX_BRIEF = {MEDICAID: 0.35, MEDICARE: 0.22, COMMERCIAL: 0.33, UNINSURED: 0.08}  # [brief]
# The brief's mix sums to 98%. The remaining 2% is assigned to "Other".  [assumption A1]
# Self-pay patients belong with Uninsured, so "Other" means VA/TRICARE, workers'
# compensation and auto insurance.
PAYER_MIX = {**PAYER_MIX_BRIEF, OTHER: round(1.0 - sum(PAYER_MIX_BRIEF.values()), 4)}
# Fixed color per payer (Okabe-Ito). Validated with the dataviz palette checker in the
# order Commercial, Medicare, Uninsured, Medicaid/CHIP; sky and purple need direct labels
# or a table beside them (contrast below 3:1 on white). "Other" is a labelled neutral.
PAYER_COLORS = {COMMERCIAL: "#0072B2", MEDICARE: "#009E73", UNINSURED: "#56B4E9",
                MEDICAID: "#CC79A7", OTHER: "#4D5C6A"}

# ---------------------------------------------------------------------------
# Performance today and national levels  [brief: Where Halvian stands today]
# ---------------------------------------------------------------------------
MEDIAN_DOOR_TO_PROVIDER_MIN = 55
LWBS_RATE = 0.040
MEDIAN_BOARDING_H = 3.5
FOLLOW_UP_COMPLETION = 0.40
NATIONAL = {
    "door_to_provider_min": (30, 40),
    "lwbs": (0.02, 0.03),
    "boarding_h": (2.0, 2.5),
    "follow_up": (0.40, 0.50),
}

# Outcome gaps  [brief: Outcome gaps table]
DOOR_TO_PROVIDER_BY_PAYER_MIN = {COMMERCIAL: 48, MEDICAID: 58, UNINSURED: 64}
LWBS_BY_PAYER = {COMMERCIAL: 0.030, MEDICAID: 0.046, UNINSURED: 0.058}

# Lower-urgency waits on surge days  [brief: How an Emergency Visit Works, step 3]
SURGE_LOW_ACUITY_WAIT_MIN = 120  # "2+ hrs on surge days for lower-urgency patients"
SURGE_DAY_QUANTILE = 0.90  # our operational definition: busiest 10% of days

# Volume pattern  [brief: Patients]
BUSIEST_WEEKDAY = "Monday"
WINTER_UPLIFT = 0.20  # "winter respiratory season adds about 20% to volume"

# Process times, minutes  [brief: How an Emergency Visit Works]
REGISTRATION_RANGE_MIN = (5, 10)
TRIAGE_RANGE_MIN = (5, 15)
EVAL_TREAT_RANGE_H = (2, 3)
ED_DISCHARGE_RANGE_MIN = (20, 40)

# ---------------------------------------------------------------------------
# Capacity  [brief: Hospital Space Types]
# ---------------------------------------------------------------------------
ED_SPACES = {"main": 32, "fast_track": 8, "resus": 4, "behavioral": 4}
ED_SPACE_LABELS = {
    "main": "Treatment rooms",
    "fast_track": "Fast-track rooms",
    "resus": "Resuscitation and trauma bays",
    "behavioral": "Behavioral health rooms",
}
ED_TOTAL_SPACES = sum(ED_SPACES.values())  # 48
WAITING_ROOM_SEATS = 40

INPATIENT_BEDS = 320  # [brief] includes 24 ICU
ICU_BEDS = 24  # [brief]
TARGET_OCCUPANCY = 0.88  # [brief] "typically about 88% occupied, leaving an average of 40 open"
TYPICAL_OPEN_BEDS = 40  # [brief]

# Named units  [assumption A5]: the brief names no units, only 320 beds including 24 ICU.
# Non-ICU unit sizes are set so each unit carries a similar share of demand (sized from
# expected bed-days, Little's law), keeping the 296 non-ICU beds the brief implies.
UNITS = {
    "Medicine A": 80,
    "Medicine B": 76,
    "Telemetry": 52,
    "Surgery": 64,
    "Step-down": 24,
    "ICU": ICU_BEDS,
}
UNIT_NAMES = tuple(UNITS)
UNIT_DESCRIPTIONS = {
    "Medicine A": "General medicine: GI, renal, endocrine, behavioral-medical",
    "Medicine B": "General medicine: respiratory, infection, neuro; small pediatric section",
    "Telemetry": "Cardiac monitoring: chest pain, syncope, arrhythmia",
    "Surgery": "Elective surgery, trauma, surgical abdomen",
    "Step-down": "Higher acuity: respiratory failure, sepsis, stroke",
    "ICU": "Critical care",
}

# ---------------------------------------------------------------------------
# Staffing per shift  [brief: Typical staff per shift]
# Shifts: day 7a to 3p, evening 3p to 11p, night 11p to 7a
# ---------------------------------------------------------------------------
SHIFT_START_HOURS = (7, 15, 23)
SHIFTS = ("day", "evening", "night")
STAFFING = {
    "physicians": (4, 4, 2),
    "apps": (3, 3, 1),
    "nurses": (14, 14, 9),
    "techs_registration": (8, 7, 4),
}
# How we read those totals into roles  [assumption A11]
REGISTRATION_CLERKS = (2, 2, 1)  # out of techs and registration staff
TRIAGE_NURSES = (3, 3, 2)  # out of triage and bedside nurses
PROVIDERS = tuple(p + a for p, a in zip(STAFFING["physicians"], STAFFING["apps"], strict=True))
# Staffed ED spaces per shift, boarders included. Day and evening staff all 48 spaces.
# At night 9 nurses (7 at the bedside at about 1:5 to 1:6, plus triage) staff the 40 spaces
# outside fast-track, which is closed. ESI 1 patients are always roomed.  [assumption A11]
STAFFED_SPACES = (48, 48, 40)

FAST_TRACK_HOURS = (9, 23)  # open 9:00 to 23:00, ESI 4 and 5 only  [assumption A12]

# ---------------------------------------------------------------------------
# Costs (fictional)  [brief: 3. Budget & ROI]
# ---------------------------------------------------------------------------
COST_NURSE_PER_H = 65
COST_PHYSICIAN_PER_H = 200
COST_APP_PER_H = 100
COST_ADMIN_PER_H = 35
OVERTIME_MULTIPLIER = 1.5
NET_REVENUE_PER_VISIT = 1_500
BOARDING_COST_PER_BED_HOUR = 350  # "lost capacity", not cash
ANNUAL_BUDGET = 500_000  # [brief: Scenario]
BUDGET_18_MONTHS = 750_000  # [brief: Scenario]
ED_ADMISSIONS_PER_YEAR = round(ED_VISITS_PER_YEAR * ADMISSION_RATE)  # 13,600
PITCH_BOARDING_CUTS_MIN = (15, 30, 60)  # [pitch: Rough numbers] conservative, lead, optimistic

# ---------------------------------------------------------------------------
# Tool settings
# ---------------------------------------------------------------------------
ALERT_THRESHOLD = 0.70  # [strategy] 70% confidence policy (Early Prediction paper)
MOVING_THRESHOLD_ON = True  # [strategy] threshold depends on ED census (Operations Research)
MOVING_THRESHOLD_SLOPE = 0.40  # threshold change per unit of crowding above typical
MOVING_THRESHOLD_FLOOR = 0.55
MOVING_THRESHOLD_CEILING = 0.85
DISCHARGE_LIST_THRESHOLD = 0.50  # rounds list cut-off  [assumption]
BATCH_INTERVAL_MIN = 60  # bed requests batched hourly per unit  [strategy, arXiv 2026]
RESERVATION_EXPIRY_H = 4  # a reserved bed unused after 4 h is released  [assumption]
RESERVED_BED_HANDOFF_MIN = 10  # handoff when a pre-prepared bed is claimed  [assumption]
SCORE_REFRESH_MIN = 15  # [pitch] "runs in the background every 15 minutes or so"
# Placeholder note reader settings (halvian/notes/reader.py)
READER_CONTEXT_WORDS = 6
READER_CONFIDENCE = {"explicit": 0.90, "contextual": 0.75}

# Impact simulator defaults, each with its source (shown next to the slider)
IMPACT_DEFAULTS = {
    "adoption": 0.50,
    "staff_response_delay_h": 1.0,
    "threshold": ALERT_THRESHOLD,
    "discharge_hours_saved": 1.0,
}
IMPACT_RANGES = {
    "adoption": (0.0, 1.0),
    "staff_response_delay_h": (0.0, 3.0),
    "threshold": (0.50, 0.90),
    "discharge_hours_saved": (0.0, 4.0),
}
# Live Bed Board lever, tool run only  [assumption A22]: a shared electronic bed board (beds marked
# dirty the moment a patient leaves, requests visible to housekeeping and the bed manager) cuts the
# housekeeping notification delay and bed request processing by this share. Our assumption: we found
# vendor and hospital case reports but no controlled study, so none is cited. Applies after go-live,
# on the units in scope, in the tool arm only.
BED_BOARD_DELAY_CUT = 0.25
BED_BOARD_SOURCE = ("Our assumption: the bed board cuts the housekeeping notification delay and bed "
                    "request processing by 25%. We found no controlled study to cite.")

# Results shown as rounded ranges (models/impact_ranges.json, halvian/ranges.py)
# Full rollout scenario  [team scenario, Nov 23]: staff act on 75% of flags, base threshold 60% with
# the moving threshold, discharges 2 hours earlier, bed board on. Cautious = today's defaults;
# Expected = today's defaults plus the bed board.
FULL_ROLLOUT = {"adoption": 0.75, "threshold": 0.60, "discharge_hours_saved": 2.0}
# Rounding of simulated outcomes: ranges come from the spread across the synthetic years, widened
# outward to these steps. Never a single point estimate.  [our rule]
RANGE_STEP = {"minutes": 5, "usd_m": 0.1, "wait_min": 1, "walkout_pts": 0.1}
# Traditional staffing options, costed per year with the brief's rates only  [assumption B20]. Cost
# only: we do not estimate how much each would cut boarding.
SURGE_DAYS_PER_YEAR = 37  # the busiest 10% of 365 days (SURGE_DAY_QUANTILE), rounded up
STAFFING_OPTIONS = (
    ("Bed coordinator around the clock", COST_ADMIN_PER_H, 24 * 365, 1.0,
     "One clerical bed coordinator on every shift, 24 hours a day all year (8,760 hours), at the brief's "
     "$35 an hour administrative rate."),
    ("Extra day-shift case manager", COST_NURSE_PER_H, 8 * 365, 1.0,
     "One more case manager on the 8-hour day shift every day of the year (2,920 hours), at the brief's "
     "$65 an hour nurse rate."),
    ("Surge-day nurse overtime", COST_NURSE_PER_H, 2 * 16 * SURGE_DAYS_PER_YEAR, OVERTIME_MULTIPLIER,
     "Two extra ED nurses on overtime for the day and evening shifts (16 hours each) on the busiest 10% of "
     "days (37 a year), at the brief's $65 an hour times 1.5."),
)
# The team's ballpark tool cost over 18 months  [pitch: "$550K to $650K over 18 months"]; the itemized
# budget in models/plan.json sits inside it.
TOOL_COST_18_MONTHS = (550_000, 650_000)

IMPACT_DEFAULT_SOURCES = {
    "adoption": "Our assumption. The brief says many clinicians are skeptical, so a pilot "
    "should not assume full uptake.",
    "staff_response_delay_h": "Illustrative staff response time after a flag. The next hourly "
    "batch determines when the request is sent. Lead time is measured from the resulting events.",
    "threshold": "Early Prediction of Hospital Admission and Specialty (preprint, not "
    "peer-reviewed): a 70% confidence policy.",
    "discharge_hours_saved": "Scenario assumption for recoverable discharge work. The Johns "
    "Hopkins study supports testing discharge-focused rounds. The local benefit is uncertain.",
}

# ---------------------------------------------------------------------------
# Fairness tolerances (model metrics by payer)  [our rule, see docs/MODELS.md]
# ---------------------------------------------------------------------------
FAIRNESS_TOLERANCES = {
    "auc_below_overall": {"amber": 0.03, "red": 0.05},
    "calibration_gap_pts": {"amber": 2.0, "red": 4.0},
    "fnr_above_overall_pts": {"amber": 5.0, "red": 10.0},
}

# Base thresholds compared for the deployed policy (a Phase 2 decision), payer-blind  [our rule]
POLICY_BASE_THRESHOLDS = (0.5, 0.6, 0.7)

# Pre-launch bias test (halvian.models.fairness.case_mix_check): a payer group's admission
# miss rate minus the rate expected from its triage levels and ages.  [our rule]
CASE_MIX_UNEXPLAINED_PTS = {"amber": 3.0, "red": 5.0}

# Equity guardrail: review or pause if a payer gap widens beyond these amounts versus
# baseline for two consecutive simulated months.  [our rule]
EQUITY_GUARDRAIL = {
    "door_to_provider_gap_min": 2.0,
    "lwbs_gap_pts": 0.3,
    "consecutive_months": 2,
}

# Oversight pause conditions  [our rule]
PAUSE_CONDITIONS = {
    "min_auc": 0.75,
    "max_override_rate": 0.40,
    "min_override_rate": 0.02,
    "max_calibration_drift_pts": 5.0,
    "max_fnr_gap_pts": 10.0,
    "max_feed_outage_min": 30,
}

# ---------------------------------------------------------------------------
# Validation tolerances  [your spec]
# ---------------------------------------------------------------------------
TOL_VISITS_REL = 0.01
TOL_PAYER_SHARE_PTS = 1.0
TOL_ADMISSION_PTS = 1.0
TOL_MEDIAN_REL = 0.05
TOL_LWBS_PTS = 0.4
TOL_OCCUPANCY_PTS = 2.0
WINTER_UPLIFT_RANGE = (0.15, 0.25)
BARRIER_SHARE_RANGE = (0.17, 0.23)
OPEN_BEDS_RANGE = (36, 44)
LITTLES_LAW_TOL_REL = 0.03


# ---------------------------------------------------------------------------
# Simulation mechanism parameters
# ---------------------------------------------------------------------------
def _hourly(values: list[float]) -> tuple[float, ...]:
    total = sum(values)
    return tuple(v / total for v in values)


@dataclass(frozen=True)
class SimParams:
    """Every tunable mechanism parameter. Defaults are the calibrated values.

    Override with dataclasses.replace(params, name=value) for experiments.
    """

    # --- Arrivals [assumption A8, calibrated to T4 to T6] ---
    hourly_weekday: tuple[float, ...] = _hourly(
        [2.9, 2.4, 2.0, 1.8, 1.6, 1.6, 2.0, 2.9, 4.0, 5.0, 5.6, 5.8,
         5.6, 5.3, 5.1, 5.0, 5.1, 5.3, 5.6, 5.7, 5.4, 4.9, 4.2, 3.4]
    )
    hourly_weekend: tuple[float, ...] = _hourly(
        [3.2, 2.7, 2.3, 2.0, 1.8, 1.7, 2.0, 2.6, 3.4, 4.3, 4.9, 5.2,
         5.3, 5.3, 5.2, 5.1, 5.1, 5.2, 5.4, 5.5, 5.3, 4.9, 4.3, 3.6]
    )
    dow_multiplier: tuple[float, ...] = (1.12, 1.03, 1.00, 0.98, 0.97, 0.95, 0.95)  # Mon..Sun
    winter_multiplier: float = 1.0 + WINTER_UPLIFT
    seasonal_severity_drop: float = 1.3  # extra winter visits are mostly lower acuity
    # Payer arrival-timing tilt  [equity param]: extra share of visits in the evening and
    # overnight (17:00 to 07:00) and at weekends, when clinics are closed.
    payer_evening_tilt: dict = field(
        default_factory=lambda: {MEDICAID: 0.15, UNINSURED: 0.45, COMMERCIAL: -0.40,
                                 MEDICARE: 0.0, OTHER: 0.0}
    )
    payer_weekend_tilt: dict = field(
        default_factory=lambda: {MEDICAID: 0.10, UNINSURED: 0.10, COMMERCIAL: 0.0,
                                 MEDICARE: -0.05, OTHER: 0.0}
    )

    # --- Acuity [assumption A3, A4] ---
    esi_mix: tuple[float, ...] = (0.01, 0.17, 0.45, 0.29, 0.08)  # ESI 1..5 overall
    # Lower average severity of visits (more primary-care-type visits)  [equity param]
    payer_low_acuity_shift: dict = field(
        default_factory=lambda: {MEDICAID: -0.10, UNINSURED: 0.25, COMMERCIAL: 0.0,
                                 MEDICARE: 0.80, OTHER: 0.0}
    )
    # Extra low-acuity shift for visits at peak hours (10-13 and 17-22)  [equity param]
    payer_peak_low_acuity_extra: dict = field(
        default_factory=lambda: {MEDICAID: 0.15, UNINSURED: 0.20, COMMERCIAL: 0.0,
                                 MEDICARE: 0.0, OTHER: 0.0}
    )

    # --- Admission (latent) [calibrated to T3; noise sets achievable AUC, A15] ---
    admit_intercept: float = -2.6773
    admit_severity_coef: float = 1.55
    admit_age_coef: float = 0.018  # per year above 50
    admit_comorbidity_coef: float = 0.35
    admit_noise_sd: float = 1.05  # information not known at triage (labs, imaging, exam)

    # --- ED service times, minutes ---
    registration_tri: tuple[float, float, float] = (5.0, 7.0, 10.0)  # [brief range]
    triage_tri: tuple[float, float, float] = (5.0, 9.0, 15.0)  # [brief range]
    # Extra registration minutes by payer (eligibility checks, financial screening)
    registration_extra_by_payer: dict = field(  # [equity param]
        default_factory=lambda: {MEDICAID: 0.0, UNINSURED: 0.0, COMMERCIAL: 0.0,
                                 MEDICARE: 0.0, OTHER: 0.0}
    )
    nurse_assess_median: float = 7.02  # bedside nurse assessment before provider pickup
    provider_eval_median: float = 15.0  # first assessment incl. documentation [calibrated T7]
    provider_eval_sigma: float = 0.40
    workup_median_by_esi: tuple[float, ...] = (150.0, 165.0, 150.0, 65.0, 45.0)  # [calibrated T22]
    workup_sigma: float = 0.50
    dispo_task_median: float = 8.0
    low_acuity_promote_after_min: float = 90.0  # ESI 4-5 then get ESI 3 priority  [assumption]
    ed_discharge_range: tuple[float, float] = (20.0, 40.0)  # [brief range]

    # --- Leaving without being seen [calibrated to T12 to T15, A14] ---
    patience_median_by_esi: tuple[float, ...] = (1e9, 1200.0, 420.0, 300.0, 260.0)
    patience_sigma: float = 0.60
    patience_scale: float = 1.7973
    patience_mult_by_payer: dict = field(  # [equity param]
        default_factory=lambda: {MEDICAID: 0.95, UNINSURED: 0.90, COMMERCIAL: 1.0,
                                 MEDICARE: 1.0, OTHER: 1.0}
    )

    # --- Bed process under the whiteboard and phone workflow [assumption A13, calibrated T16] ---
    admit_acceptance_median: float = 45.0  # admitting physician reviews and accepts
    bed_request_median: float = 35.0
    bed_readiness_median: float = 40.0
    transport_median: float = 20.0
    clean_median: float = 50.0
    clean_notify_median: float = 35.0
    process_sigma: float = 0.50
    bed_process_scale: float = 1.2942  # multiplies acceptance, request and readiness  [calibrated T16]
    overflow_after_h: float = 8.0  # then any compatible unit's clean bed  [assumption A13]

    # --- Inpatient flow [assumption A6, A7, calibrated to T18, T29] ---
    los_median_h_by_unit: dict = field(
        default_factory=lambda: {"Medicine A": 80.0, "Medicine B": 80.0, "Telemetry": 58.0,
                                 "Surgery": 66.0, "Step-down": 84.0, "ICU": 60.0}
    )
    los_sigma: float = 0.62
    los_scale: float = 0.931
    elective_per_year: float = 4_400.0
    elective_los_median_h: float = 50.0
    elective_winter_factor: float = 0.60  # electives postponed in respiratory season
    direct_per_year: float = 5_400.0
    discharge_clock_mean_h: float = 13.75  # early to mid afternoon  [assumption A9]
    discharge_clock_sd_h: float = 1.6
    discharge_same_day_cutoff_h: float = 12.0
    weekend_hold_prob: float = 0.30  # share of weekend-ready patients who wait to Monday

    # --- Non-medical discharge barriers [assumption A10, calibrated to T27] ---
    barrier_intercept: float = -1.20
    barrier_age_coef: float = 0.025  # per year above 65
    barrier_mobility_coef: float = -0.12  # per mobility point above 15
    # More non-medical discharge barriers for Medicaid/CHIP and Uninsured patients, as
    # approved in PLAN.md decision 6. Documented, adjustable assumptions, never hidden:
    # set to 0.0 and 1.0 respectively for the neutral sensitivity run.  [equity param]
    barrier_payer_logodds: dict[str, float] = field(
        default_factory=lambda: {MEDICAID: 0.65, UNINSURED: 0.75, COMMERCIAL: 0.0,
                                 MEDICARE: 0.0, OTHER: 0.0}
    )
    # Tilt toward transport, home care and insurance-authorization barriers  [equity param]
    barrier_type_payer_tilt: dict[str, float] = field(
        default_factory=lambda: {MEDICAID: 1.6, UNINSURED: 1.8, COMMERCIAL: 1.0,
                                 MEDICARE: 1.0, OTHER: 1.0}
    )


BARRIER_TYPES = (
    "placement",
    "home_care",
    "insurance_auth",
    "family_pickup",
    "transport",
    "meds_equipment",
)
BARRIER_LABELS = {
    "placement": "Rehab or nursing-facility placement",
    "home_care": "Home care set-up",
    "insurance_auth": "Insurance authorization",
    "family_pickup": "Family pickup",
    "transport": "Transport",
    "meds_equipment": "Pending medications or equipment",
}
BARRIER_BASE_MIX = {  # share of barriers by type  [assumption A10]
    "placement": 0.30,
    "home_care": 0.20,
    "insurance_auth": 0.13,
    "family_pickup": 0.12,
    "transport": 0.15,
    "meds_equipment": 0.10,
}
BARRIER_EQUITY_TYPES = ("transport", "home_care", "insurance_auth")  # tilted by payer
BARRIER_DELAY_MEDIAN_H = {  # typical extra delay  [assumption A10]
    "placement": 36.0,
    "home_care": 24.0,
    "insurance_auth": 24.0,
    "family_pickup": 18.0,
    "transport": 12.0,
    "meds_equipment": 10.0,
}
BARRIER_DELAY_SIGMA = 0.5
BARRIER_OWNER = {  # suggested owner on the rounds view
    "placement": "Case manager",
    "home_care": "Case manager",
    "insurance_auth": "Case manager",
    "transport": "Case manager",
    "family_pickup": "Nurse",
    "meds_equipment": "Nurse",
}

# AI note reader: a local language model via Ollama on this machine, never a cloud API.  [assumption]
# The Mac has 8 GB of RAM, so per the team plan the 3B instruct model is used (16 GB+ would compare
# llama3.1:8b and qwen2.5:7b). Deterministic decoding: temperature 0 and a fixed seed.
LLM_MODEL = "llama3.2:3b"
LLM_DISPLAY_NAME = "Llama 3.2 3B, running locally"
OLLAMA_URL = "http://127.0.0.1:11434"  # loopback only; the client refuses any other host
LLM_SEED = 20261124
LLM_TEMPERATURE = 0.0
LLM_MAX_TOKENS = 200
LLM_TIMEOUT_S = 20.0
LLM_CONFIDENCE_AGREE = 0.90  # match strength, not a probability: the rules found the same barrier
LLM_CONFIDENCE_ALONE = 0.70  # the model alone found it (evidence still verified verbatim)
LLM_EVAL_BUDGET_MIN = 60  # the whole precompute (sample + demo days) must finish within this
LLM_EVAL_PER_CELL = 35  # target notes per barrier type x payer group in the evaluation sample
LLM_EVAL_NO_BARRIER = 700  # notes with no labelled barrier (half contain barrier words)

# Payer mix for direct and elective admissions (not ED)  [assumption A6]
NON_ED_PAYER_MIX = {MEDICARE: 0.40, COMMERCIAL: 0.34, MEDICAID: 0.20, UNINSURED: 0.04, OTHER: 0.02}
DIRECT_UNIT_MIX = {"Medicine A": 0.36, "Medicine B": 0.22, "Telemetry": 0.23,
                   "Step-down": 0.05, "ICU": 0.07, "Surgery": 0.07}
ELECTIVE_UNIT_MIX = {"Surgery": 0.80, "Telemetry": 0.10, "Step-down": 0.05, "ICU": 0.05}

DEFAULT_PARAMS = SimParams()

# ---------------------------------------------------------------------------
# Budget, value and roadmap  [assumption B<n>]  (each listed in docs/STRATEGY.md)
# Staff time uses the brief's hourly rates; rates the brief does not give are assumptions.
# Computed in halvian/roi.py (budget, value, ROI) and halvian/roadmap.py (goals, gates).
# ---------------------------------------------------------------------------
PLAN_PHASES = {"pilot": (1, 6), "scale": (7, 18)}  # months, inclusive  [brief: 2. Roadmap]
PLAN_MONTHS = 18  # [brief: Scenario]
HOURS_PER_FTE_YEAR = 2_080  # [assumption B1] 40 hours x 52 weeks
HOURS_PER_SEAT_YEAR = 24 * 365  # one post staffed around the clock
COST_DATA_SCIENTIST_PER_H = 90  # [assumption B2] loaded hourly cost, hospital analytics
COST_INTEGRATION_ENGINEER_PER_H = 150  # [assumption B3] contracted EHR interface engineer
COST_PROJECT_MANAGER_PER_H = 55  # [assumption B4]
COST_SECURITY_ANALYST_PER_H = 75  # [assumption B5]
AGENCY_MULTIPLIER = 2.0  # [assumption B6] agency or contract staff versus the employed rate (least certain)
TRAINING_RATE_MULTIPLIER = OVERTIME_MULTIPLIER  # [assumption B7] training happens off-shift, paid as overtime
BUDGET_CONTINGENCY = 0.10  # [assumption B8] reserve added to every phase

# People trained, by role: (hourly rate [brief], (pilot, scale) headcount, hours each)  [assumption B9]
TRAINED_ROLES = {
    "ED charge and triage nurses": (COST_NURSE_PER_H, (20, 0), 2.0),
    "Bed managers and house supervisors": (COST_NURSE_PER_H, (6, 0), 2.0),
    "Inpatient charge nurses": (COST_NURSE_PER_H, (8, 40), 2.0),
    "Case managers": (COST_NURSE_PER_H, (4, 16), 2.0),
    "Hospitalists and attendings (rounds list)": (COST_PHYSICIAN_PER_H, (8, 32), 1.0),
    "ED physicians (awareness briefing)": (COST_PHYSICIAN_PER_H, (14, 0), 0.5),
    "Advanced practice providers (awareness briefing)": (COST_APP_PER_H, (10, 0), 0.5),
    "Super-users, one per unit and shift (extra hours)": (COST_NURSE_PER_H, (6, 15), 8.0),
}
ANNUAL_TRAINING_TURNOVER = 0.20  # [assumption B10] share of trained users replaced each year (full training)
REFRESHER_HOURS = 0.5  # [assumption B10] yearly refresher for every trained user

# Budget lines: (phase, category, item, quantity, unit, rate in $, hidden cost?)  [assumption B11]
# Phases: "pilot" = Months 1 to 6, "scale" = Months 7 to 18, "run" = each year after Month 18.
BUDGET_LINES = (
    ("pilot", "Licensing", "Open-source stack: Python, scikit-learn, Streamlit, Ollama and Llama 3.2 3B "
     "open weights", 1, "stack", 0, False),
    ("pilot", "Integration", "Read-only EHR feeds: bed status and ADT events, triage, notes (contract engineer)",
     300, "h", COST_INTEGRATION_ENGINEER_PER_H, False),
    ("pilot", "Integration", "EHR vendor interface activation fee (least certain: needs a quote)", 1, "fee",
     20_000, True),
    ("pilot", "Infrastructure", "Hospital-hosted server with a small GPU for the models and the local "
     "language model", 1, "server", 12_000, False),
    ("pilot", "Build and validation", "Data scientist, 1.0 FTE for 6 months (production build, silent-mode "
     "validation)", 1_040, "h", COST_DATA_SCIENTIST_PER_H, False),
    ("pilot", "Build and validation", "Tool owner: clinical informatics nurse, 0.5 FTE", 520, "h",
     COST_NURSE_PER_H, False),
    ("pilot", "Build and validation", "Project manager, 0.5 FTE", 520, "h", COST_PROJECT_MANAGER_PER_H, False),
    ("pilot", "Security review", "Third-party security assessment and penetration test before go-live", 1,
     "review", 25_000, True),
    ("pilot", "Security review", "HIPAA security risk analysis update (privacy and security office)", 60, "h",
     COST_SECURITY_ANALYST_PER_H, True),
    ("pilot", "Adoption and trust", "Patient and family advisory sessions, plain-language materials", 1,
     "program", 3_000, False),
    ("scale", "Integration", "Extend feeds to five more units; decision log to the quality data warehouse",
     120, "h", COST_INTEGRATION_ENGINEER_PER_H, False),
    ("scale", "Integration", "EHR vendor interface maintenance, 12 months", 1, "year", 10_000, True),
    ("scale", "Infrastructure", "Standby server for failover", 1, "server", 12_000, False),
    ("scale", "Infrastructure", "Hardware support and backups, 12 months", 1, "year", 3_000, False),
    ("scale", "Build and validation", "Data scientist, 0.5 FTE for 12 months (monitoring, retraining)", 1_040,
     "h", COST_DATA_SCIENTIST_PER_H, False),
    ("scale", "Build and validation", "Tool owner: clinical informatics nurse, 0.5 FTE for 12 months", 1_040,
     "h", COST_NURSE_PER_H, False),
    ("scale", "Build and validation", "Project manager, 0.25 FTE for the 6-month rollout", 260, "h",
     COST_PROJECT_MANAGER_PER_H, False),
    ("scale", "Security review", "Security re-test after expansion", 1, "review", 10_000, True),
    ("scale", "Adoption and trust", "Unit champion huddles and patient materials", 1, "program", 2_000, False),
    ("run", "Integration", "EHR vendor interface maintenance", 1, "year", 10_000, True),
    ("run", "Infrastructure", "Hardware support, backups and a replacement reserve (2 servers over 5 years)",
     1, "year", 3_000 + 2 * 12_000 / 5, False),
    ("run", "Build and validation", "Data scientist, 0.5 FTE (monitoring, retraining)", 1_040, "h",
     COST_DATA_SCIENTIST_PER_H, False),
    ("run", "Build and validation", "Tool owner: clinical informatics nurse, 0.25 FTE", 520, "h",
     COST_NURSE_PER_H, False),
    ("run", "Security review", "Annual security assessment", 1, "review", 15_000, True),
)
# Monthly AI oversight committee for 1.5 h: physician chair, nursing director, case management lead and
# a patient and equity advocate. The tool owner and data scientist attend within their FTE.  [assumption B12]
OVERSIGHT_MEETING_H = 1.5
OVERSIGHT_MEMBER_RATES = (COST_PHYSICIAN_PER_H, COST_NURSE_PER_H, COST_NURSE_PER_H, COST_ADMIN_PER_H)

# Lower-cost and higher-cost alternatives named on the budget slide  [assumption B13]
BUDGET_ALTERNATIVES = (
    ("Rules-only note reader (no language model, no GPU server)", -12_000,
     "Saves the GPU server. The rules match these synthetic notes well but are brittle on new phrasing."),
    ("Train-the-trainer: super-users train their own units", None,
     "Cuts classroom hours; the training line already assumes it for scale."),
    ("Commercial patient-flow platform instead of an in-house build", None,
     "Vendor pricing is not public; we would get quotes in Month 1 and compare against this budget."),
    ("Cloud language model API instead of a local model", None,
     "Rejected: notes would leave Halvian's network and add per-call fees."),
)

# The traditional approach: staff time to give the same coverage by hand  [assumption B14, least certain]
TRADITIONAL_WORK = (
    ("Flow nurse screening each triaged ED patient for likely admission and calling bed requests, around the "
     "clock", COST_NURSE_PER_H, HOURS_PER_SEAT_YEAR),
    ("Case manager time to screen every occupied inpatient chart for discharge barriers each morning, 3 min each",
     COST_NURSE_PER_H, 3 / 60 * round(INPATIENT_BEDS * TARGET_OCCUPANCY) * 365),
    ("Bed manager time to build unit-by-unit bed forecasts by phone, 4 times a day for 45 min",
     COST_NURSE_PER_H, 4 * 0.75 * 365),
)

# Value of the gains
ED_NURSE_H_PER_BOARDER_H = 0.25  # [assumption B15] a boarded patient needs a quarter of an ED nurse (1:4)
BOARDER_NURSING_ON_OVERTIME = 0.25  # [assumption B16] share of that nursing covered by overtime (least certain)
WALKOUT_RECOVERED_SHARE = 0.5  # [assumption B17] share of avoided walkouts that are revenue Halvian keeps;
# the rest would have returned later (least certain)
# Value ramp over the 18 months: no live tool (setup, training, silent mode), the pilot unit only,
# rollout at half of the full value, then all units  [assumption B18]
VALUE_RAMP = {"setup": (1, 3), "pilot": (4, 6), "rollout": (7, 9), "full": (10, 18)}
ROLLOUT_VALUE_SHARE = 0.5  # [assumption B18]

# Month 18 goals: each target banks this share of the simulated improvement  [assumption B19]
GOAL_TARGET_SHARE = 0.75

# Criteria to move from Phase 1 (pilot) to Phase 2 (scale)  [our rule]
PILOT_GATES = {
    "min_admission_precision": 0.60,
    "min_discharge_precision": 0.55,
    "min_barrier_precision": 0.90,
    "max_unexplained_miss_pts": CASE_MIX_UNEXPLAINED_PTS["red"],
    "min_adoption": 0.40,
    "min_override_reason_share": 0.90,
    "min_staff_useful_share": 0.60,
}

# Roadmap milestones: (first month, last month, phase, milestone, owner, done when)  [our plan]
ROADMAP_MILESTONES = (
    (1, 2, "pilot", "Set up: governance charter, read-only EHR feeds, security review, data quality checks",
     "Tool owner (clinical informatics) with IT security",
     "Feeds pass daily data-quality checks for 14 days; the security assessment has no open high findings"),
    (2, 3, "pilot", "Silent mode: the tool scores every patient on Halvian's own data and shows nothing",
     "Data scientist", "Precision, calibration and the bias test meet the pilot gates on Halvian's data"),
    (3, 3, "pilot", "Training: 2-hour sessions for pilot users, super-users on every shift, a patient advisory "
     "session", "Nurse educator with the tool owner", "At least 90% of pilot users trained"),
    (4, 4, "pilot", "Supervised go-live on Medicine A: ED bed requests for the unit and its rounds list; every "
     "recommendation needs a person to approve or override it", "Bed manager and Medicine A nurse manager",
     "30 days live with no safety event linked to the tool"),
    (4, 6, "pilot", "Weekly huddles with users; monthly oversight committee reviews adoption, overrides and "
     "equity", "AI oversight committee", "Every override reason reviewed; issues logged and closed"),
    (6, 6, "pilot", "Pilot review: go or no-go for Phase 2 against the pilot gates",
     "Chief medical and nursing officers with the oversight committee", "Every pilot gate met"),
    (7, 9, "scale", "Adjust from pilot results (alert threshold, workflow, the note reader's role), then add "
     "Medicine B and Telemetry", "Tool owner", "Gates still met on the new units after 30 days"),
    (10, 12, "scale", "Add Surgery, Step-down and ICU; standby server and a downtime drill on every unit",
     "IT and nursing operations", "Failover and the phone-and-whiteboard downtime drill pass"),
    (12, 12, "scale", "Year 1 review: goals against targets, budget, retrain or retire decision",
     "Oversight committee with finance", "Decision recorded; budget for the next year approved"),
    (13, 18, "scale", "Optimize: quarterly retraining check, annual bias audit, refresher training; move the "
     "tool into the operating budget", "Tool owner", "Ownership and the yearly run cost in the operating plan"),
    (18, 18, "scale", "Month 18 review against the four goals: continue, extend to another area, or retire",
     "Executive board", "Goals met or a written recovery plan"),
)
