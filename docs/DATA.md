# Synthetic data: how the Halvian year is made

**Everything here is synthetic.** No real patients, notes or datasets were used. Halvian is a fictional hospital and its numbers come from the case brief. Patients have IDs like `ED-000123` and `IP-004512`. Results from this simulation are estimates for discussion, not evidence about a real hospital.

Regenerate everything with `python scripts/generate_data.py` (about 10 seconds, deterministic) and check it with `python scripts/validate.py`.

## 1. The idea in plain language

We did not invent a spreadsheet of numbers. We built a small working model of the hospital and let it run for one fictional year (2025 on the calendar):

1. Patients arrive at the ED in the pattern the brief describes: more on weekday mornings and evenings, most on Mondays, about 20% more in winter.
2. They register, are triaged, wait for a room, see a provider, get tests and treatment, and are either sent home or admitted.
3. **An admitted patient keeps the ED room until an inpatient bed is ready.** While they wait (boarding), the room is unavailable to the next patient in the waiting room. That is the mechanism the whole project is about.
4. Upstairs, inpatients go home once they are medically ready and any non-medical barrier (a ride, home care, a rehab bed) is sorted out. Discharges cluster in the early afternoon, then housekeeping cleans the bed.
5. Some waiting patients give up and leave without being seen. The longer the wait, the more likely that is.

Waits, walkouts, boarding and occupancy are **outputs** of that process. We tuned a short list of inputs (section 4) until the outputs matched the brief. No outcome is written in directly.

## 2. The simulation engine

`halvian/data/cohort.py` draws everything a patient brings with them **before** the simulation runs: arrival time, payer, age, complaint, acuity (ESI), vitals, whether they would be admitted and to which unit, every service time, how long they would wait before leaving, and their inpatient stay if admitted. `halvian/data/simulate.py` is a compact discrete-event simulation: a calendar of upcoming events processed in time order. It resolves only the queues.

Because the patients are fixed before the run, a baseline run and a run with the AI tool switched on see exactly the same people with the same draws ("common random numbers"). Any difference is caused by the tool.

**Why a custom engine rather than SimPy:** a full year (about 85,000 visits, 23,700 stays, roughly a million events) runs in about 1.3 seconds, which makes calibration and the live impact simulator practical. Shift changes, ESI priority, priority aging, leaving while waiting, bed reservations and cleaning are explicit and testable.

**Determinism:** one global seed (`config.SEED`) with a separate random stream per component. Ties are broken by a sequence counter. A guard raises an error if any event is ever scheduled in the past.

**Tests** (`tests/test_simulation.py`): every patient leaves exactly once; timestamps are ordered; no ED room or inpatient bed is ever double-booked or over capacity; boarders leave their ED room exactly when they arrive in the bed; ICU patients are never placed off-service outside the ICU or step-down; nobody is discharged before medical readiness; identical seeds give identical output; short windows get the same daily volume as a full year; and a **causal mechanism test**: slowing only the inpatient bed process raises boarding, ED waits and LWBS.

### ED rules

| Step | Rule |
|---|---|
| Registration | Walk-ins only; 2/2/1 clerks per shift (day/evening/night); 5 to 10 min |
| Triage | 3/3/2 triage nurses; ambulance arrivals first; 5 to 15 min. ESI 1 goes straight to a resuscitation bay |
| Rooming | Order: ESI, then arrival time. ESI 1 to the 4 resuscitation bays, behavioral health to the 4 behavioral rooms, ESI 4 and 5 to the 8 fast-track rooms while open (9:00 to 23:00), everyone else to the 32 treatment rooms. Anyone can overflow into a free treatment room |
| Staffed spaces | All 48 spaces by day and evening; 40 at night (fast-track closed). Boarders count against these |
| Priority aging | ESI 4 and 5 patients who have waited 90 minutes get ESI 3 priority, so nobody waits indefinitely |
| Provider | Short bedside nurse assessment (about 7 min), then one of the pooled physicians and APPs (7/7/3) sees the patient in ESI order. That first contact ends door-to-provider |
| Treatment | Tests and treatment, then a provider disposition task (done first, to free rooms) |
| Discharge | 20 to 40 min in the room, then the patient leaves |
| Admission | Admitting physician accepts the patient, bed manager processes the request, the request waits for a clean bed on the right unit (first come, first served), the unit gets ready, then transport. **The ED room is held the whole time.** After 8 hours without a bed the patient can be placed off-service on another unit (ICU patients only in the ICU or step-down) |
| Leaving unseen | Each patient has a patience time; if it runs out before provider contact they leave and free any room they held |

### Inpatient rules

| Item | Rule |
|---|---|
| Length of stay | Time to medical readiness (lognormal by unit, longer for sicker patients), plus any barrier delay, plus the discharge clock |
| Discharge clock | Patients ready before noon leave that afternoon (centered around 13:45); later, the next day. 30% of patients ready on a weekend wait until Monday |
| Cleaning | Housekeeping notification (about 35 min under the whiteboard workflow) plus cleaning (about 50 min) |
| Non-ED admissions | Direct admissions (about 5,400 a year, weekdays heavier) and elective surgery (about 4,400 a year, weekdays only, 40% fewer in winter as surgeries are postponed) |

## 3. Calibration results (main synthetic year)

All 29 checks pass. Produced by `scripts/validate.py` from the committed files.

| Target | Simulated | Tolerance | Pass |
|---|---|---|---|
| ED visits per year: 85,000 | 85,082 | ±1% | Yes |
| Payer share Medicaid/CHIP: 35% | 35.0% | ±1 pt | Yes |
| Payer share Medicare: 22% | 22.0% | ±1 pt | Yes |
| Payer share Commercial: 33% | 32.9% | ±1 pt | Yes |
| Payer share Uninsured: 8% | 8.0% | ±1 pt | Yes |
| Payer share Other (VA, workers' comp, auto): 2% (assumption A1) | 2.1% | ±1 pt | Yes |
| Admission rate: 16% | 16.0% | ±1 pt | Yes |
| Busiest day: Monday | Monday | Monday highest | Yes |
| Winter respiratory season adds about 20% | 19.6% | 15 to 25% | Yes |
| Weekday arrivals peak in the morning and evening | 14.3 and 13.1 per hour vs 12.5 mid-afternoon | Both peaks present | Yes |
| Median door-to-provider, all: 55 min | 55.2 min | ±5% | Yes |
| Median door-to-provider, Commercial: 48 min | 49.3 min | ±5% | Yes |
| Median door-to-provider, Medicaid/CHIP: 58 min | 59.3 min | ±5% | Yes |
| Median door-to-provider, Uninsured: 64 min | 63.3 min | ±5% | Yes |
| LWBS, all: 4.0% | 4.00% | ±0.4 pt | Yes |
| LWBS, Commercial: 3.0% | 3.27% | ±0.4 pt | Yes |
| LWBS, Medicaid/CHIP: 4.6% | 4.55% | ±0.4 pt | Yes |
| LWBS, Uninsured: 5.8% | 5.69% | ±0.4 pt | Yes |
| Median boarding: 3.5 h | 3.52 h | ±5% | Yes |
| Lower-urgency (ESI 4 and 5) waits on surge days: 2+ h | 215 min median on the busiest 10% of days | at least 120 min | Yes |
| Inpatient occupancy: about 88% | 88.1% | ±2 pt | Yes |
| Open inpatient beds: about 40 | 38.2 | 36 to 44 | Yes |
| Registration: 5 to 10 min | 7.3 min median | inside range | Yes |
| Triage: 5 to 15 min | 9.5 min median | inside range | Yes |
| Evaluation and treatment: 2 to 3 h | 2.36 h median | inside range | Yes |
| ED discharge: 20 to 40 min | 30.0 min median | inside range | Yes |
| Stays with a non-medical discharge barrier: about 1 in 5 (assumption A10) | 19.0% | 17 to 23% | Yes |
| Discharges cluster before ED admission requests (assumption A9) | discharges 13.8h vs ED admit decisions 14.2h (median hour) | discharges earlier | Yes |
| Little's law: occupied beds = admissions/day × average stay | 281.8 occupied vs 64.2/day × 4.39 d = 282.0 | within 3% | Yes |

Reported, not pass/fail: Medicare median door-to-provider **56.3 min** (emerges near the overall median, as expected); Medicare LWBS 3.7%; mean boarding 4.9 h (a realistic long tail); 13,609 ED admissions among 2025 ED arrivals; 64 inpatient admissions a day, 58% from the ED; average stay 4.4 days; unit occupancy Medicine A 91%, Medicine B 89%, Telemetry 88%, Surgery 89%, Step-down 84%, ICU 75%; 7% of stays placed off-service.

**Other synthetic years.** Only the main year is calibrated. The impact simulator also uses two other synthetic years (seeds +1 and +2) to show run-to-run noise. Seed +2 passes all 29 checks. Seed +1 passes 25: all four LWBS rates run 0.4 to 0.9 points high (4.5% overall). This is ordinary year-to-year variation and it is recorded in `data/validation.json`. It is also a warning: equity changes smaller than about half a point of LWBS are inside the noise.

### Little's law, worked through

Target occupied beds = 0.88 × 320 = 281.6. Simulated: 64.2 admissions a day × 4.39 days average stay = 282.0 beds, against 281.8 measured directly from the census. ED-sourced stays starting in 2025 (13,615, slightly more than the 13,609 admissions among 2025 arrivals because late-December 2024 arrivals reach a bed in January; average stay 4.75 days) fill about 177 beds; direct admissions (5,398, 4.52 days) about 67; elective surgery (4,417, 3.13 days) about 38.

## 4. What was calibrated

Five global inputs were tuned by `scripts/calibrate.py` (secant search per input, with a joint step for the two that interact). Final values are in `config.SimParams`, marked `[calibrated]`.

| Input | Value | Target it serves |
|---|---|---|
| Admission intercept | -2.68 | Admission rate 16% |
| Patience scale | 1.80 | LWBS 4.0% |
| Nurse assessment median | 7.0 min | Median door-to-provider 55 min |
| Bed process scale | 1.29 | Median boarding 3.5 h |
| Length-of-stay scale | 0.93 | Occupancy 88% |

**Honest log of structural changes made during calibration.** The first runs gridlocked, which taught us where the realism was missing. Each change below is documented as an assumption:

- Unit sizes were re-allocated to demand (the plan's sizes overloaded Medicine and Step-down).
- Triage staffing rose from 2/2/1 to 3/3/2 nurses (one night triage nurse could not keep up).
- Off-service placement after 8 hours was added (without it one full unit gridlocked the ED).
- Night staffing became 40 spaces; a 1:4 nurse ratio cap all day made staffing, not boarding, the binding constraint, which is a different focus area.
- Winter electives were reduced and the extra winter visits made mostly lower acuity (otherwise winter demand exceeded bed capacity and the census climbed for weeks).
- A bedside nurse assessment step and priority aging were added (without them waits were either near zero or hours long, never the brief's shape).
- A bug was found and fixed where short simulation windows received a full year of arrivals.

## 5. Equity: where the payer gaps come from

The brief's gaps should arise mostly from plausible mechanisms. Every payer-specific setting is a named, adjustable parameter (`[equity param]` in `config.py`):

| Type | Setting | Medicaid/CHIP | Medicare | Commercial | Uninsured | Other |
|---|---|---|---|---|---|---|
| Mechanism | Extra share of visits 17:00 to 07:00 | +15% | 0 | -40% | +45% | 0 |
| Mechanism | Extra share of weekend visits | +10% | -5% | 0 | +10% | 0 |
| Mechanism | Lower average visit severity (shift) | -0.10 | +0.80 | 0 | +0.25 | 0 |
| Mechanism | Extra low-acuity visits at peak hours (shift) | +0.15 | 0 | 0 | +0.20 | 0 |
| Mechanism | More non-medical discharge barriers (log-odds) | +0.65 | 0 | 0 | +0.75 | 0 |
| Mechanism | Tilt toward transport, home care, insurance barriers | ×1.6 | ×1 | ×1 | ×1.8 | ×1 |
| Explicit adjustment | Patience before leaving unseen | ×0.95 | ×1 | ×1 | ×0.90 | ×1 |
| Explicit adjustment | Extra registration minutes | 0 | 0 | 0 | 0 | 0 |

Resulting acuity mix (share ESI 4 and 5): Medicaid/CHIP 41%, Medicare 32%, Commercial 34%, Uninsured 46%. Barrier share of stays: Medicaid/CHIP 16%, Medicare 26% (older patients), Commercial 13%, Uninsured 19%.

**Decomposition** (`data/equity_decomposition.json`, three full-year runs):

| Scenario | Medicaid/CHIP vs Commercial, wait | Uninsured vs Commercial, wait | Medicaid/CHIP vs Commercial, LWBS | Uninsured vs Commercial, LWBS |
|---|---|---|---|---|
| No payer-specific terms | +5.7 min | +1.3 min | +0.8 pts | +0.3 pts |
| Mechanisms only | +10.2 min | +16.3 min | +0.9 pts | +1.5 pts |
| Calibrated (mechanisms plus explicit adjustments) | +10.0 min | +14.0 min | +1.3 pts | +2.4 pts |
| Case brief target | +10 min | +16 min | +1.6 pts | +2.8 pts |

What this means: the **waiting-time gaps come entirely from mechanisms**, mainly after-hours arrivals (fast-track closes at 23:00 and only 3 providers work nights), plus age and acuity mix. Even with every payer term off, CHIP children and complaint mix leave a 5.7-minute Medicaid gap. About half of the **walkout gaps** come from those waits; the other half needs one explicit assumption, that Medicaid/CHIP and Uninsured patients leave somewhat sooner at the same wait (for example cost worries or work and childcare pressures).

## 6. Assumptions where the brief is silent

| ID | Assumption | Value | Why |
|---|---|---|---|
| A1 | Payer mix sums to 98% | Remaining 2% is "Other (VA, workers' comp, auto)" | Self-pay belongs with Uninsured |
| A2 | Medicare door-to-provider | Emerges: 56.3 min | Not in the brief |
| A3 | ESI mix | 1/17/45/29/8% for ESI 1 to 5 | Typical US distribution |
| A4 | Acuity and timing by payer | Section 5 | Main equity mechanisms |
| A5 | Inpatient units | Medicine A 80, Medicine B 76, Telemetry 52, Surgery 64, Step-down 24, ICU 24 (brief) | Brief names no units; sized to demand |
| A6 | Non-ED admissions | About 4,400 elective, 5,400 direct a year | Needed for Little's law at 88% |
| A7 | Length of stay | Average 4.75 d (ED), 4.52 d (direct), 3.13 d (elective) | Typical US ranges |
| A8 | Winter season | Dec, Jan, Feb at 1.2×; extra visits mostly lower-acuity respiratory; electives 40% lower | Brief: winter adds about 20% |
| A9 | Discharge timing | Centered around 13:45; ready after noon leaves next day; 30% weekend hold | Produces the afternoon and evening mismatch |
| A10 | Non-medical barriers | About 19% of stays. Mix: placement 28%, home care 22%, transport 16%, insurance 14%, family pickup 11%, meds or equipment 10%. Typical delays 10 to 36 h | Hopkins one-fifth finding; delays are assumptions |
| A11 | Staff roles | Registration 2/2/1, triage nurses 3/3/2, providers 7/7/3 pooled; 48/48/40 staffed spaces; nurse assessment about 7 min | Brief gives totals, not roles |
| A12 | Fast-track hours | 9:00 to 23:00, ESI 4 and 5 | Common practice |
| A13 | Bed process (whiteboard and phone era) | Acceptance about 58 min, request processing about 45, unit readiness about 52 (medians after scaling), transport 20, cleaning 50 plus 35 notification; off-service after 8 h | Calibrated to the 3.5 h median; the most influential assumption |
| A14 | Leaving unseen | Lognormal patience by ESI, scaled, with payer multipliers (section 5) | Calibrated to 4.0% |
| A15 | Admission noise | Information not known at triage (labs, imaging, exam) adds noise to the true admission chance | Sets achievable model accuracy; a property of the generator |
| A16 | Simplifications | No transfers between units except off-service placement, no transfers out, no hallway beds, sex has no effect | Scope |
| A17 | Impact simulator flags | Computed only from information known at each hour or rounds (REVIEW findings 1 and 3) | Causal timing |
| A21 | Inpatient observations | Mobility and lab trend follow hidden recovery progress plus per-patient random-walk noise; barriers are identified 6 to 48 h into the stay regardless of when they resolve | Informative but not a clean readout of the future; tested |
| A18 | Definitions | Door-to-provider over patients seen; LWBS over all arrivals; boarding from admit decision to leaving the ED room; occupancy time-weighted | Brief is silent |
| A19 | Calendar | Fictional year on the 2025 calendar; two months of warm-up discarded; demo days Mon Dec 8 and Wed Oct 15 | Real weekdays, test period |
| A20 | Priority aging | ESI 4 and 5 get ESI 3 priority after 90 min waiting | Prevents unrealistic starvation |
| A22 | Bed board lever (impact runs only) | With the Live Bed Board on, the housekeeping notification delay and bed request processing are 25% shorter after go-live, in the tool arm only (`config.BED_BOARD_DELAY_CUT`) | Our assumption: we found vendor and hospital case reports but no controlled study; it separates the Cautious and Expected scenarios |

## 7. Synthetic notes

One short typed note per inpatient per day (about 107,000), for example `pt VSS, steady w/ 1 assist, SNF placement pending` or `pt transport to CT done, VSS, ambulating independently, transport home not arranged`. Built from templates in `halvian/data/notes.py` with abbreviations, about 4% typos, weekday references ("dtr can't pick up until Thurs"), clinical distractors, negations ("no barriers to dc") and resolved barriers ("ride confirmed for 2pm") that must not count as active. A barrier is documented only after case management identifies it (6 to 48 hours into the stay) and then in about 85% of notes. **Ground truth** (barrier types each note asserts as active) is in `note_labels.parquet` and is never a model feature.

## 8. Data dictionary

Times are minutes from midnight on 2024-11-01 (`config.WARMUP_START`); `halvian.data.cohort.minutes_from_start(date)` converts dates.

**`ed_visits.parquet`**, one row per 2025 ED visit (85,082 rows)

| Column | Meaning |
|---|---|
| `visit_id` | `ED-000001` upward, arrival order |
| `cohort_row` | Row in the pre-drawn cohort (links to impact runs) |
| `arrival_min` | Arrival time |
| `payer` | Medicaid/CHIP, Medicare, Commercial, Uninsured, Other (VA, workers' comp, auto) |
| `age`, `sex`, `arrival_mode` | Ambulance or Walk-in |
| `chief_complaint` | One of 14 categories |
| `esi` | Triage acuity 1 (most urgent) to 5 |
| `heart_rate`, `systolic_bp`, `resp_rate`, `spo2`, `temp_c` | Triage vitals |
| `recent_ed_visits_12m` | ED visits in the past year |
| `arrival_hour`, `arrival_dow` (0 = Monday), `arrival_month`, `winter` | Calendar features |
| `t_registration`, `t_triage` | Service times (excluding queue) |
| `reg_start_min`, `reg_end_min`, `triage_end_min`, `roomed_min`, `provider_min`, `decision_min`, `departure_min` | Event times |
| `room_type`, `room_label` | `main`, `fast_track`, `resus`, `behavioral`; labels like `T12`, `FT3`, `R1`, `BH2` |
| `door_to_provider_min` | Provider minus arrival (missing for LWBS) |
| `disposition` | Discharged, Admitted, Left without being seen |
| `lwbs`, `admitted` | Flags |
| `admit_unit`, `dx_group` | Intended unit and diagnosis group, admitted patients only |
| `bed_request_min`, `bed_assigned_min` | Request entered the unit queue; bed assigned |
| `boarding_min` | Admit decision to leaving the ED room |

**`inpatient_stays.parquet`**, one row per stay in house at any time in 2025 (23,701 rows): `stay_id` (`IP-`), `kind`/`source` (ED, Direct, Elective), `ed_visit_id`, `unit` (where the bed is), `intended_unit`, `bed_number`, `request_min`, `queue_entry_min`, `bed_assigned_min`, `bed_arrival_min`, `ready_min` (medically ready), `discharge_min`, `discharge_base_min`, `clean_min`, `accelerated`, `has_barrier`, `barrier`, `barrier_delay_h`, `payer`, `age`, `dx_group`, `ip_los_ready_h`, `ip_mobility0`, `los_h`.

**`inpatient_days.parquet`**, one row per inpatient per 07:00 rounds (107,215 rows): `note_id`, `stay_id`, `rounds_min`, `rounds_dow`, `unit`, `dx_group`, `source`, `payer`, `age`, `los_so_far_h`, `mobility_score` (6 to 24), `lab_trend` (-2 worsening to +2 improving), `discharge_min`, `hours_to_discharge`, `discharged_24h` (label), `true_barrier`, `barrier_active` (simulator truth, never a feature).

**`notes.parquet`**: `note_id`, `stay_id`, `written_min` (06:00), `text`. **`note_labels.parquet`**: `note_id`, `barrier_type`.

**`stress_notes.parquet`** (`note_id` such as `ST-0001`, `text`) and **`stress_labels.parquet`** (`note_id`, `barrier_type`): the new-phrasing stress test for the note readers, 304 notes in wording the templates never use (`halvian/notes/stress.py`, `python scripts/make_stress_notes.py`). They belong to no patient and never enter the simulation or any model; labels come from how each note was built.

**`census_hourly.parquet`**: `hour_min`, then per unit `occupied`, `cleaning`, `assigned` (bed assigned, patient not yet arrived), `open`; per ED space type `in_use`; `ED|boarders`; `ED|not_yet_roomed`.

**`validation.json`**: the calibration table, reported measures, replication years and open misses. **`equity_decomposition.json`**, **`payer_parameters.json`**: section 5.

## 9. Limitations

- Every behavioral input (patience, process times, barrier delays) is an assumption calibrated to the brief's averages; the simulation reproduces the brief, it does not validate it.
- The split between boarding that is process time and boarding that is waiting for a bed (A13) drives how much the tool can help. The app shows it rather than hiding it.
- Model accuracy on this data reflects how the generator was built (A15), not real-world performance.
- Medicare and Other outcomes are emergent and untargeted.
