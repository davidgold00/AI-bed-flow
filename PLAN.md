# Halvian Bed Flow MVP: Build Plan

Status: **approved Nov 21, 2026**, with the decisions below. Where this list and the rest of the plan disagree, this list wins.

### Approved decisions

1. **Payer-blind models.** Payer is never a feature of any default model. It is used only for fairness auditing. The Fairness page shows a with-insurance model as a comparison and explains in plain language why it is excluded.
2. **Custom DES engine**: deterministic, documented in `docs/DATA.md`, covered by tests. It must model the real mechanism: boarded patients hold ED rooms until an inpatient bed frees, and that blocking drives waits and LWBS.
3. **The 2% group is "Other (VA, workers' comp, auto)".** Self-pay belongs with Uninsured. Flagged as an assumption, since the brief's mix sums to 98%.
4. **Defaults**: 50% adoption, 1 h lead time, 70% alert threshold with the moving threshold on, **1 h discharge time saved (slider 0 to 4 h)**. Each default shows its source or "our assumption" next to it. Fairness warning thresholds are listed in `docs/MODELS.md` and on the Fairness page.
5. **Demo days**: the guided tour uses the busy winter Monday (Dec 8, 2025). A toggle compares a typical mid-week fall day (Wed Oct 15, 2025, also in the test period). One simulated year everywhere.
6. **Equity additions**:
   - Fairness page: uninsured vs commercial and Medicaid vs commercial gaps for door-to-provider and LWBS, baseline vs scenario, with a plain-language verdict (narrowed, flat, widened).
   - Equity mechanisms are documented, adjustable parameters (`[equity param]` in `config.py`): more low-acuity visits at peak times for Medicaid/CHIP and Uninsured patients, and more non-medical discharge barriers for them (transport, home care, insurance authorization). Nothing is hard-coded; if the gap does not narrow the app shows it.
   - Equity guardrail on the Oversight page: review or pause if any payer gap widens beyond a stated tolerance for two consecutive simulated months.
7. **Coordination**: work on `main` only, never touch `codex/*` branches, never rewrite history on `main`.

## 0. Summary

We build a staff-facing AI dashboard (the brief's demo Option B) for the **Patient Flow and Boarding** focus area. It runs on one fictional year of synthetic data produced by a discrete-event simulation (DES) of Halvian's ED and inpatient units, calibrated to every number in the case brief. Two models (admission at triage, discharge within 24 hours) plus a placeholder note reader feed an hourly, per-unit bed forecast. Staff approve or override every recommendation. An impact simulator reruns the same simulation with the tool switched on, so the before and after comparison comes from one mechanism, not from assumptions typed into a spreadsheet.

The core argument the app makes visible:

1. Admitted patients hold ED rooms for a median of 3.5 hours, so new arrivals wait and some leave unseen.
2. The case implies about 38 unoccupied inpatient beds on average. A bed must also be clean, available and suitable for the patient. The unit-level board shows which of these constraints is holding up a transfer.
3. Earlier predictions let staff start bed requests and discharge work sooner. The simulation shows how much these actions change boarding, waits and payer gaps.
4. A human approves every action.

### What I read and how I resolved conflicts

The case brief supplied the baseline for the simulator. The table records how we reconciled it with the proposed implementation.

| Conflict | Resolution |
|---|---|
| Brief says "Medicaid or CHIP" (35%) but the outcome-gap table says "Medicaid" | Treated as one group, labelled "Medicaid/CHIP", and the Medicaid gap targets apply to it |
| 88% occupancy of 320 beds is 38.4 open beds; brief says "about 40" | 88% is the calibration target; "about 40" is the derived check |
| Pitch suggests logistic regression or XGBoost | Your spec wins: logistic regression vs sklearn HistGradientBoosting (no XGBoost or LightGBM, see section 5) |
| Pitch and strategy brief describe an LLM note reader with an optional Ollama button | Your spec wins: rule-based placeholder plus a no-network `LLMNoteReader` stub |
| Pitch says the dashboard rescores "every 15 minutes or so"; your spec says hourly batched requests | Both: scores refresh every 15 minutes in the data model, bed requests go out hourly per unit |
| Earlier requirements discussed payer as a feature | Both models and operational decisions exclude payer. Retain it for the fairness and outcome audits. |

The demo uses synthetic data to show a complete patient-flow workflow with working AI features and staff review.

## 1. Architecture

### Layout

Your suggested layout, with four additions explained after the tree.

```
app.py                         Streamlit entry point = Overview page
pages/
  1_Live_Bed_Board.py
  2_ED_Admission_Flags.py
  3_Discharge_Readiness.py
  4_Bed_Forecast.py
  5_Impact_Simulator.py
  6_Fairness_and_Oversight.py
  7_Data_and_Methods.py
halvian/
  config.py                    every case number, each citing the brief section; calibrated values marked as such
  data/cohort.py               NEW: pre-draws every patient and every inpatient stay (attributes, latent outcomes, service times)
  data/simulate.py             DES engine: queues, rooms, providers, beds, boarding, LWBS, tool hooks
  data/notes.py                NEW: synthetic clinical notes plus ground-truth barrier labels
  data/generate.py             orchestration: cohort, baseline run, tables, notes
  models/admission.py
  models/discharge.py
  models/thresholds.py         moving threshold and hourly per-unit batching
  models/forecast.py
  models/explain.py            NEW: plain-English top-3 reasons and global importance
  models/fairness.py           model metrics by payer with tolerance flags
  notes/reader.py              NoteReader interface, RuleBasedNoteReader, LLMNoteReader stub
  impact.py                    NEW: baseline vs tool scenario runner (paired runs, replications)
  equity.py                    outcome gaps by payer, before and after
  roi.py                       bed-hours freed, capacity value, pitch 15/30/60 table
  validation.py                calibration checks shared by scripts/validate.py and pytest
  ui/                          shared Streamlit helpers: banner, palette, formatting, glossary, guided tour, session log
scripts/generate_data.py
scripts/train_models.py        trains models, runs the note reader, scores, precomputes impact sweeps
scripts/validate.py
scripts/calibrate.py           dev tool: searches calibrated parameters, writes nothing automatically
data/                          generated parquet (committed, expected well under 25 MB)
models/                        trained artifacts plus metrics JSON (committed)
tests/
docs/DATA.md  docs/MODELS.md  docs/DEMO_SCRIPT.md
.streamlit/config.toml
CLAUDE.md  AGENTS.md  README.md
```

Why the additions:

- **`cohort.py` separate from `simulate.py`.** Every patient's attributes, latent outcome (would be admitted, which unit), service times and patience are drawn *before* the simulation, independent of how crowded the ED is. The DES only resolves queues. This gives "common random numbers": baseline and tool runs see exactly the same patients, so any difference between them is caused by the tool, not by luck. It also lets the real trained model score every patient up front, so the impact simulator uses the actual model, not an assumed accuracy.
- **`notes.py`** keeps the note generator and its ground truth apart from the reader that is scored against it.
- **`impact.py`** keeps scenario logic out of the Streamlit page so it can be tested.
- **`ui/`** because classic Streamlit `pages/` files each need the same banner, sidebar clock, tour and session log.

### Pipeline

```
config.py ──> cohort.py ──> simulate.py (baseline, tool off) ──> data/*.parquet ──> validate.py
                                                         │
                                        notes.py ────────┤
                                                         ▼
                         train_models.py: note reader ─> discharge model; admission model;
                                          test-period scores; impact sweeps (tool on)
                                                         ▼
                                        Streamlit app reads parquet + models (cached)
```

### Why a small custom DES instead of SimPy

I plan a compact event-driven engine (a heap of timed events, about 400 lines) rather than SimPy:

- **Speed.** Calibration needs dozens of full-year runs and the impact simulator reruns on demand. A tight heap engine should do a full year (about 85,000 ED visits and 23,000 inpatient stays) in a few seconds.
- **Exact control.** Shift-based staffing changes at 7a, 3p and 11p, priority by ESI, patients leaving while waiting, beds reserved by batch requests, and cleaning turnaround are all easier to get exactly right, and to unit-test, in explicit code.
- **One fewer dependency.** SimPy would still work if you prefer it for readability; tell me.

Safety nets: tests assert every patient exits exactly once, rooms and beds never exceed capacity, and the same seed gives byte-identical output.

Determinism: one global seed in `config.py`, a separate named random stream per component (arrivals, attributes, service times, notes, adoption draws), so changing one part does not reshuffle the rest.

## 2. Synthetic data design

### 2.1 Calibration targets (all go in `config.py` with a brief citation)

| # | Target | Value (brief section) | How it is measured | Tolerance | Pass/fail |
|---|---|---|---|---|---|
| T1 | ED visits per year | 85,000 (Company overview) | All arrivals Jan 1 to Dec 31, 2025, including LWBS | ±1% | Yes |
| T2 | Payer mix | Medicaid/CHIP 35, Medicare 22, Commercial 33, Uninsured 8 (Patients) | Share of all arrivals | ±1 point each | Yes |
| T2b | Other/self-pay | 2% (assumption A1) | Share of all arrivals | ±1 point | Yes |
| T3 | Admission rate | 16%, about 13,600 a year (Patients) | Admitted / all arrivals | ±1 point | Yes |
| T4 | Busiest day | Monday (Patients) | Mean arrivals by weekday | Monday highest | Yes |
| T5 | Winter uplift | About +20% (Patients) | Mean daily arrivals Dec to Feb vs Mar to Nov | 15 to 25% | Yes |
| T6 | Arrival peaks | Weekday mornings and evenings (Patients) | Weekday hourly profile has a morning and an evening local peak | Both present | Yes |
| T7 | Median door-to-provider, all | 55 min (Where Halvian stands; Outcome gaps) | Arrival to first provider contact, patients who were seen | ±5% | Yes |
| T8 | Median door-to-provider, Commercial | 48 min (Outcome gaps) | Same, by payer | ±5% | Yes |
| T9 | Median door-to-provider, Medicaid/CHIP | 58 min (Outcome gaps) | Same | ±5% | Yes |
| T10 | Median door-to-provider, Uninsured | 64 min (Outcome gaps) | Same | ±5% | Yes |
| T11 | Median door-to-provider, Medicare | Not given (assumption A2) | Same | Reported only | No |
| T12 | LWBS, all | 4.0% (Outcome gaps) | Left before provider contact / arrivals | ±0.4 points | Yes |
| T13 | LWBS, Commercial | 3.0% | Same, by payer | ±0.4 points | Yes |
| T14 | LWBS, Medicaid/CHIP | 4.6% | Same | ±0.4 points | Yes |
| T15 | LWBS, Uninsured | 5.8% | Same | ±0.4 points | Yes |
| T16 | Median boarding | 3.5 h (Where Halvian stands; step 5b) | Admit decision to leaving the ED room for the inpatient bed | ±5% | Yes |
| T17 | Lower-urgency waits on surge days | 2+ h (step 3) | Median door-to-provider for ESI 4 and 5 on the busiest 10% of days | At least 120 min | Yes |
| T18 | Inpatient occupancy | About 88% of 320 (Space table) | Time-weighted occupied beds / 320, full year | ±2 points | Yes |
| T19 | Unoccupied beds | About 40 (Space table) | 320 minus mean occupied (38.4 at 88%) | Derived from T18 | Reported |
| T20 | Registration time | 5 to 10 min (step 1) | Median service time, excluding queue | Inside range | Yes |
| T21 | Triage time | 5 to 15 min (step 2) | Median service time, excluding queue | Inside range | Yes |
| T22 | Evaluation and treatment | 2 to 3 h (step 4) | Median first provider contact to disposition decision | Inside range | Yes |
| T23 | ED discharge process | 20 to 40 min (step 5a) | Median disposition to departure, discharged patients | Inside range | Yes |
| T24 | ED spaces | 32 treatment, 8 fast-track, 4 resuscitation/trauma, 4 behavioral health, 40 waiting seats (Space table) | Simulation capacities | Exact | Yes (test) |
| T25 | Inpatient beds | 320 including 24 ICU (Space table) | Sum of unit sizes | Exact | Yes (test) |
| T26 | Staffing per shift | Physicians 4/4/2, APPs 3/3/1, nurses 14/14/9, techs and registration 8/7/4 (Staff table) | Simulation rosters | Exact | Yes (test) |
| T27 | Non-medical discharge barriers | About 1 in 5 stays (strategy brief, Hopkins) | Share of stays with a barrier | 17 to 23% | Yes |
| T28 | Discharge vs admission timing | Discharges early to mid afternoon, ED admit requests afternoon and evening (assumption A9) | Peak hour of inpatient departures vs peak hour of ED bed requests | Discharge peak earlier | Yes |
| T29 | Inpatient flow reconciliation | Occupied beds ≈ admissions/day × mean length of stay | Compare integrated census with independently aggregated stay intervals over the same window. Report the steady-state check by unit and source with boundary effects. | Within 3% for the steady-state estimate | Yes |
| Cost | Nurse $65/h, physician $200/h, APP $100/h, admin $35/h, overtime 1.5x, $1,500 net revenue per visit, about $350 per boarded ED bed-hour (Budget & ROI) | Used by `roi.py` only | Exact | Yes (test) |
| Context | National levels: door-to-provider 30 to 40 min, LWBS 2 to 3%, boarding 2 to 2.5 h, follow-up 40 to 50%; Halvian follow-up 40% | Overview page comparison only | n/a | No |

`scripts/validate.py` prints Target | Simulated | Tolerance | Pass for every row marked Yes; pytest asserts the same list; the Data and Methods page shows the same table.

### 2.2 The fictional year and calendar

- Calendar year 2025 (fictional hospital, real weekdays). Jan 1, 2025 is a Wednesday. Winter respiratory season = Dec, Jan, Feb (90 days).
- The simulation starts Dec 1, 2024 and discards December 2024 as warm-up, so the inpatient census is in steady state on Jan 1.
- Model split uses the timestamp of each prediction. Fit on January to August and choose the model on September predictions. Refit before the October holdout, using only inputs and outcome labels available at the fitting cutoff. September predictions whose labels are still unresolved at the October cutoff cannot guide pre-October model selection. Use maturing outcomes beyond December to evaluate the October to December holdout.
- **Demo day:** Monday Dec 8, 2025 (test period, winter, busiest weekday). All "live" pages show this day on a sidebar clock.

### 2.3 Arrivals (mechanism)

- Non-homogeneous Poisson process: hour-of-day profile × day-of-week multiplier × season multiplier. Starting values (calibrated later):
  - Hourly profile with a morning peak around 11:00 and an evening peak around 19:00, trough at 04:00 to 05:00. Weekends get a flatter morning.
  - Weekday multipliers: Mon 1.12, Tue 1.03, Wed 1.00, Thu 0.98, Fri 0.97, Sat 0.95, Sun 0.95.
  - Season: 1.20 in Dec to Feb, concentrated in respiratory and fever complaints. Base about 222 a day, winter about 266 a day, average 233.
- Each payer group has its own stream with a timing tilt (see 2.6). Streams are scaled so annual shares hit T2. The overall pattern is checked after summing.

### 2.4 Patient attributes (pre-drawn in `cohort.py`)

| Attribute | How it is generated |
|---|---|
| ID | `ED-000001` upward, in arrival order |
| Payer | Stream membership (T2) |
| Age | By payer: Medicare mostly 65+ with about 10% under 65 (disability); Medicaid/CHIP about 40% children (CHIP) and the rest 18 to 64; Commercial about 20% children; Uninsured almost all 18 to 64 |
| Sex | 50/50, no effect on outcomes |
| Arrival mode | Ambulance or walk-in, depends on age and severity |
| Chief complaint | 14 categories (chest pain, shortness of breath, abdominal pain, fever or infection, minor injury, major trauma or fall, neuro symptoms, syncope or dizziness, behavioral health, back or musculoskeletal pain, nausea/vomiting/diarrhea, skin or wound, ENT/dental/eye, urinary). Mix depends on age and season |
| Latent severity | Continuous score from complaint, age, comorbidity burden, plus noise |
| ESI 1 to 5 | Thresholds on latent severity, tuned so the overall mix is about 1/17/45/29/8% (assumption A3) |
| Vitals | Heart rate, systolic BP, respiratory rate, SpO2, temperature, each shifted by severity and complaint |
| Recent ED visits (12 months) | Count, higher for Medicaid/CHIP and Uninsured (fewer primary-care alternatives) |
| Would be admitted | Logistic function of severity, age, complaint and vitals **plus a noise term standing for information not known at triage** (labs, imaging, exam). Payer has no direct effect. The noise level is set so a triage model can reach about 0.85 AUC, near the published 0.87 (PLOS ONE). That AUC is a property of our generator, not evidence the model works in a real hospital, and the app says so |
| Admitting unit | From complaint and severity (table in 2.7) |
| Service times | Registration, triage, provider first assessment, diagnostics and treatment interval, disposition, ED discharge process |
| Patience | Time a patient will wait for a provider before leaving (LWBS), by ESI, with any payer adjustment shown explicitly (2.6) |
| Adoption draw | One uniform number per patient, used by the impact simulator so a 50% adoption rate always acts on the same half |

### 2.5 ED process in the DES

1. **Registration**: 2/2/1 clerks per shift (day/evening/night), out of the 8/7/4 techs and registration staff (A11). Service 5 to 10 min.
2. **Triage**: 2/2/1 triage nurses, out of the 14/14/9 nurses (A11). Service 5 to 15 min. Assigns ESI (pre-drawn).
3. **Rooming** by priority (ESI, then arrival time):
   - ESI 1 to a resuscitation/trauma bay (4); overflow to a main room.
   - Behavioral health complaints to a behavioral health room (4); overflow to a main room.
   - ESI 4 and 5 to fast-track (8) while it is open, 9:00 to 23:00 (A12); otherwise main rooms, lowest priority.
   - Everyone else to the 32 main treatment rooms.
   - The 40 waiting seats are tracked; the simulation records how often they are exceeded (hallway or standing room) rather than turning people away.
4. **Provider first assessment** (this is door-to-provider): pooled physicians and APPs, 7/7/3 per shift, priority by ESI. About 12 min of provider time.
5. **Diagnostics and treatment** in the room, then a short provider disposition task. Calibrated so first contact to disposition is 2 to 3 h median.
6. **Disposition** (pre-drawn): discharge (20 to 40 min in room, then leaves) or admit (boarding below).
7. **LWBS**: if a patient's patience runs out before provider contact, they leave (and free their room if they had one).
8. **Boarding** (the key mechanism). An admitted patient keeps the ED room until departure. Baseline process, reflecting phone calls and a whiteboard:
   - Bed request processing by the bed manager (median about 30 min).
   - Wait for a clean bed on the right unit (first come, first served per unit).
   - Unit readiness and nurse report (median about 30 min), then transport (about 15 min).
   - Starting values are assumptions (A13) and are calibrated so the median lands at 3.5 h. The split between "process time" and "waiting for a bed" is the most influential assumption in the whole project, so the app shows it as a decomposition chart rather than hiding it.

### 2.6 Equity mechanisms (gaps should come mostly from mechanism)

Mechanisms built in first, with no payer-specific tuning:

1. **Acuity mix.** More ESI 4 and 5 visits among Medicaid/CHIP (about 43%) and Uninsured (about 47%) than Commercial (about 33%), reflecting fewer primary-care alternatives. Lower priority means longer waits.
2. **Arrival timing.** Medicaid/CHIP and Uninsured arrivals tilt toward evenings, nights and weekends (clinics closed, shift work), when fast-track is closed and only 3 providers are on overnight.
3. **Low acuity at peak times.** The evening tilt overlaps the evening arrival peak, so these patients queue behind higher-acuity arrivals.
4. **LWBS from waiting.** The chance of leaving rises with wait time and falls with acuity, so longer waits produce more walkouts without any payer term.

Then calibrate. If mechanisms 1 to 4 do not reach T8 to T10 and T13 to T15, I add the **smallest explicit payer adjustment** needed, from this list only, each a named parameter in `config.py`, documented in `docs/DATA.md` and shown on the Data and Methods page with its value:

- **Registration time by payer** (eligibility checks and financial screening take longer for Uninsured and Medicaid/CHIP patients).
- **Patience multiplier by payer** (for example cost worries, work or childcare pressures lead some patients to leave sooner at the same wait).

The docs will report a decomposition: how much of each gap the mechanisms produce on their own (adjustments set to zero) vs with the adjustments.

### 2.7 Inpatient side

**Units** (A5). 296 non-ICU beds split into five named units plus the ICU:

| Unit | Beds | Main sources |
|---|---|---|
| Medicine A | 68 | GI, renal, endocrine, general medicine from the ED; direct admissions |
| Medicine B | 68 | Respiratory, infection, neuro (non-critical) from the ED; small pediatric section |
| Telemetry | 56 | Chest pain, syncope, cardiac |
| Surgery | 72 | Elective surgical cases, trauma, surgical abdomen |
| Step-down | 32 | Higher-acuity respiratory, sepsis, stroke |
| ICU | 24 | ESI 1 and critical ESI 2, some post-op |
| **Total** | **320** | |

**Little's law** (A6). Occupied beds = admissions per day × average length of stay.

- Target occupied beds = 0.88 × 320 = 281.6 (38.4 open, "about 40").
- ED admissions: 13,600 a year (37.3 a day) × ALOS about 4.8 days = 178.8 beds.
- Elective surgical admissions, weekdays only: about 4,400 a year × ALOS 3.0 days = 36.2 beds.
- Direct admissions and transfers in: the remaining 66.6 beds ÷ ALOS 4.5 days = about 5,400 a year (14.8 a day).
- Total about 23,400 admissions a year, 58% from the ED (US hospitals typically 50 to 70%), overall ALOS 4.39 days.
- These are starting values; calibration adjusts direct-admission volume and LOS scale until T18 and T29 pass. Per-unit occupancy is reported (expected range about 84 to 93%, ICU and Telemetry highest).

**Length of stay**: time to medical readiness (lognormal by unit and diagnosis group), plus a routine discharge process, plus any non-medical barrier delay.

**Discharge timing** (A9). Discharges cluster early to mid afternoon (departures centered around 14:30, mostly 11:00 to 18:00). Patients ready late in the day go the next day. About 30% of patients ready on a Saturday or Sunday wait until Monday (weekend effect), which also helps make Mondays the worst boarding day. ED admission requests peak in the afternoon and evening, so the mismatch is built in.

**After a discharge**: the bed is open but dirty. Cleaning takes about 50 min plus a notification delay of about 25 min under the whiteboard process (A13). "Open beds" in T19 includes dirty beds, which is one reason boarding exists while beds look free.

**Non-medical barriers** (A10). About 20% of stays (Hopkins finding). Type mix and typical extra delay:

| Barrier | Share of barriers | Typical extra delay |
|---|---|---|
| Rehab or nursing-facility placement | 30% | about 36 h |
| Home care set-up | 20% | about 24 h |
| Insurance authorization | 13% | about 24 h |
| Family pickup | 12% | about 18 h |
| Transport | 15% | about 12 h |
| Pending medications or equipment | 10% | about 10 h |

Probability of a barrier rises with age and low mobility (mobility was the top predictor of post-acute need in the Hopkins work). Per decision 6, Medicaid/CHIP and Uninsured stays also have higher barrier odds and more transport, home care and insurance barriers, as documented, adjustable `[equity param]` settings that can be neutralised for sensitivity runs.

**Daily inpatient snapshots**: one row per inpatient per 07:00 rounds, with LOS so far, unit, diagnosis group, mobility score (6 to 24 scale, improves toward readiness), lab trend (worsening, stable, improving as a slope), and that day's note.

**Simplifications** (A16): no transfers between units (for example ICU to step-down), no transfers out to other hospitals (counted as ED discharges), no hallway beds.

### 2.8 Synthetic clinical notes

- One short typed note per inpatient per day (about 100,000 notes), for example `pt ambulating w/ walker, dtr can't pick up until Thurs, PT eval pending`.
- Built from phrase templates for each barrier type, with abbreviations (pt, d/c, dc, SNF, HH, DME, PT/OT, dtr, auth, rx), minor typos (about 5% of words), weekday references, clinical distractors ("afebrile overnight", "tolerating PO", "BP stable"), negations ("no barriers to dc", "lives w/ spouse, ride confirmed"), and resolved barriers ("HH set up for Fri", "auth obtained") that must not count as active.
- A barrier is not always written down on day one: documentation probability rises over the stay, so the reader sometimes cannot see a barrier that exists.
- Ground truth is stored separately in `data/note_labels.parquet`: for each note, which barrier types the text asserts as active. The reader is scored against these labels, and also against the stay-level truth.

### 2.9 Calibration procedure

1. Set mechanism parameters to plausible starting values (sections 2.3 to 2.8).
2. `scripts/calibrate.py` tunes a short list of global parameters, one target family at a time: arrival scale (T1), admission intercept (T3), provider and treatment times (T7, T22), patience scale (T12), bed process times (T16), direct-admission volume and LOS scale (T18).
3. Only then, if needed, the explicit payer adjustments from 2.6.
4. Final values are written into `config.py` by hand, marked `# calibrated`, separate from `# brief` numbers.

## 3. Generated tables (in `data/`)

| File | Grain | Key columns |
|---|---|---|
| `ed_visits.parquet` | One row per ED visit (about 85,000) | IDs, arrival time, payer, age, mode, complaint, ESI, vitals, recent visits, room type and room ID, provider time, door-to-provider, disposition, admit unit, bed request, bed assigned, departure, boarding minutes, LWBS flag |
| `inpatient_stays.parquet` | One row per stay (about 23,400) | `IP-` ID, source (ED, direct, elective), linked ED visit, unit, bed ID, diagnosis group, admit time, ready time, barrier type and delay, discharge time |
| `inpatient_days.parquet` | One row per inpatient per 07:00 rounds (about 100,000) | features for the discharge model, note ID, label (discharged in next 24 h) |
| `notes.parquet` | One row per note | note ID, stay ID, timestamp, text |
| `note_labels.parquet` | Note × active barrier type | ground truth only, never used as a model feature |
| `census_hourly.parquet` | Unit × hour, and ED space type × hour | occupied, open clean, open dirty, boarders |
| `validation.json` | Calibration results | the table in 2.1 |

Model outputs (`models/`): fitted models (joblib), `metrics.json`, `fairness.json`, note reader results, test-period scores, and `scenarios.parquet` (precomputed impact sweeps).

## 4. Note reader (placeholder only)

- `NoteReader` interface: `read(note_text) -> list[{type, evidence_span, confidence}]`, where `evidence_span` is character offsets into the note so the UI can highlight it.
- `RuleBasedNoteReader`: regex and keyword rules per barrier type, a negation and resolution window ("no", "denies", "not needed", "confirmed", "arranged", "set up", "obtained"), and confidence from rule strength.
- `LLMNoteReader` stub: docstring explains how a Claude API call (structured JSON output with the same schema, running inside Halvian's approved environment) or a local Llama model via Ollama would plug in. It raises `NotImplementedError`; no network code.
- Labelled in the UI: "Placeholder: rule-based stand-in for the LLM note reader."
- Data and Methods page reports precision, recall and F1 overall, per barrier type, and by payer group (so the reader's own fairness is visible).
- The discharge model uses the **reader's output**, not the ground truth, as its barrier features, so reader errors flow through honestly.

## 5. Models

Packages: scikit-learn only. LightGBM needs a separate OpenMP install on macOS and SHAP is heavy, so I will use `LogisticRegression` and `HistGradientBoostingClassifier`, with exact additive contributions for logistic regression and permutation importance plus occlusion-based local reasons for gradient boosting.

### 5.1 Admission predictor

- **Prediction time**: end of triage.
- **Features** (all known at triage): age, arrival hour, day of week, winter flag, arrival mode, chief complaint, ESI, five vitals, recent ED visits. Neither model uses payer.
- **Label**: admitted among patients with a known clinical disposition. Patients who left before being seen can still receive a triage flag if they completed triage. Report scoring and outcome coverage by payer and count their reservation costs in the simulation.
- **Default model rule**: logistic regression, unless gradient boosting beats it by at least 0.02 AUC on the validation month with no worse calibration (Brier score). Logistic regression explains itself exactly, which matters for skeptical clinicians and for MBA teammates. The comparison is reported either way.
- **Likely unit**: lookup from (complaint, ESI, age band) to the most common admitting unit in training data, with its accuracy reported. Needed because bed requests go to a unit.

### 5.2 Discharge predictor

- **Prediction time**: 07:00 rounds each day.
- **Features**: LOS so far, current unit, diagnosis group documented by 07:00, mobility score, lab trend, admission source, and barrier flags from notes available at rounds. Build progress features from the observed history through rounds. Keep final length of stay, the simulated future readiness time, and ground-truth barriers outside the feature builder.
- **Label**: leaves the hospital within the next 24 h.
- Same model-selection rule as 5.1.

### 5.3 Thresholds and requests

- **Alert threshold** defaults to 70% (early-prediction paper in the strategy brief).
- **Moving threshold** (Operations Research paper): `threshold = clip(0.70 - 0.40 × (crowding - typical crowding), 0.55, 0.85)`, where crowding = (patients in ED spaces + waiting) ÷ 48 spaces and typical crowding is the training-period median. A packed ED lowers the bar to request beds earlier; a quiet ED raises it. All four numbers are configurable.
- **Hourly batched requests per unit**: on the hour, for each unit, the requested bed count = round(sum of admission probabilities of approved, flagged, still-undecided ED patients whose likely unit is that unit) minus beds already reserved. Using the sum of probabilities makes a batch an expected count, so one wrong prediction costs little.
- **Discharge rounds list** threshold defaults to 50% (configurable).

### 5.4 Bed forecast

- For each unit and horizon (4, 8, 24 h), forecast usable beds from current bed states and expected changes in availability. Include beds that become clean and beds released from reservations. A reserved bed and the admission expected to use it must affect available capacity once.
- Use discharge probabilities for patients present at the forecast origin. Estimate how many of their departures leave a bed ready by the horizon using training-period timing and cleaning data. Scope the backtest to 07:00, when the discharge model scores. Evaluate a separate origin before reporting accuracy for it.
- Count existing unmatched boarders as known demand. Apply P(admit) × P(that unit) to still-undecided ED patients, then add forecast demand from future ED, direct and elective arrivals. Use rates fit on the training period.
- Use a model-based 80% interval with the independent Bernoulli and Poisson approximations. Report its empirical coverage and mean absolute error by horizon on the test period against a same-census baseline. Compare forecast and observed bed counts using the same definition of availability.

### 5.5 Evaluation (test months 10 to 12)

Report AUC, precision-recall curve and average precision, calibration bins with counts, Brier score, confusion matrix at the threshold, and alerts per day for both models and algorithms in `docs/MODELS.md`. For admissions, measure lead from first eligible flag and approved batch time to the admit decision separately. For discharge, measure lead from first eligible rounds flag and staff action to hospital departure separately. State each denominator and count missed or late flags.

**Leakage tests** cover a positive feature allowlist per model, feature timestamps and label cutoff dates. Test that changing later notes, disposition or discharge times leaves earlier features and scores unchanged for otherwise identical observed histories. The current inpatient unit is allowed for the discharge model. The future admitting unit stays outside the triage inputs.

### 5.6 Explainability

- Per patient, top 3 reasons in plain English, for example "Age 78 raises the chance", "Chest pain raises it", "Oxygen level 89% raises it", "No ED visits in the past year lowers it". For logistic regression these are exact contributions relative to a typical patient, grouped by original feature.
- Global importance chart on the flags page and the methods page.

### 5.7 Fairness (by payer group)

For each model, report AUC, calibration (mean predicted vs observed), false negative rate, flag rate, and eligible, labelled and positive counts by payer. A metric with an undefined denominator or class mix is reported as insufficient data. Report a fixed reference threshold and the deployed moving threshold separately where applicable. Proposed tolerances (open question 4):

| Metric | Amber | Red |
|---|---|---|
| AUC below overall | more than 0.03 | more than 0.05 |
| Calibration gap (predicted vs observed) | more than 2 points | more than 4 points |
| False negative rate above overall | more than 5 points | more than 10 points |

Colors: Okabe-Ito orange (#E69F00) for amber and vermillion (#D55E00) for red, always with a text label so color is never the only signal.

## 6. Impact simulator: how the tool is modelled

Paired runs: baseline (tool off) and tool on, same patients, same random draws.

**Period**: the test quarter, Oct to Dec 2025, so every admission prediction is out of sample. The run starts Aug 1 with the tool off (identical to baseline) to warm up. Report results for the quarter. For a case-volume run rate, divide the paired difference in total boarded ED room-hours by baseline admissions in the quarter and multiply by 13,600. Count each run’s room-hour overlap with the same reporting window, including stays crossing the boundaries. Report both admission counts and label the run rate as a seasonal extrapolation.

**Replications**: 3 independent synthetic years (different seeds, same trained model). Show the range of paired changes across seeds. This matters most for the payer gaps, where groups are small.

**What the tool changes**:

1. **Early bed requests.** After observed triage, flag a patient when P(admit) ≥ the current moving threshold. A simulated approval draw represents adoption. An approved flag enters the first hourly batch at or after flag time plus staff response delay, while the patient is still present and undecided. Calculate each batch from these candidates and their predicted units. Reserve available clean beds and start request processing and unit readiness. At an eventual admit decision, skip only work already completed and use an active reservation only if it matches the required unit. Expire unused reservations after four hours and release any reservation after a disposition or departure invalidates it. Count idle reserved bed-hours and any delays to competing admissions. Measure lead time from logged events.
2. **Earlier discharge work.** At 07:00, score the inpatients present in that scenario using the notes and observations available at rounds. A simulated approval draw represents the unit team acting. Reduce the time for the detected, actionable barrier or routine discharge work by up to the slider setting. Record which work changed and when. The inpatient can leave once medically ready and all remaining tasks and barriers are resolved.

**Sliders and illustrative defaults**

| Slider | Default | Source for the default |
|---|---|---|
| Adoption rate | 50% | Assumption: the brief says many clinicians are skeptical; a pilot should not assume full uptake |
| Staff response delay before hourly batching | 1 h | Illustrative workflow assumption. Compare observed lead from flags and approved batches on the holdout. |
| Alert threshold (base of moving threshold) | 70% | Early Prediction of Hospital Admission paper (not peer-reviewed) |
| Maximum discharge task time saved | 1 h | Scenario assumption. Hopkins supports testing discharge-focused rounds. Evidence on discharge timing and ED flow is mixed. |
| Scope | All units, with a "Pilot: Medicine A only" option | Pitch decision 5 (pilot on one medicine unit) |

**Outputs**: median boarding, median door-to-provider, LWBS, each by payer group; the uninsured vs commercial and Medicaid vs commercial gaps in minutes and points (absolute and relative); net ED boarding bed-hours freed from paired total hours, with the median reported separately; estimated freed capacity at $350 per bed-hour, reported as opportunity value of released ED room time; idle reserved inpatient bed-hours; walkouts avoided (and $1,500 per visit shown separately, labelled as resting on our assumption that a walkout is a lost visit).

**Sensitivity view**: one-at-a-time sweeps (precomputed) of each slider and the assumed recoverable share of boarding process time. Include zero-effect controls. Compare the annual run rate with the pitch's 15, 30 and 60 minute mean reduction examples (3,400 / 6,800 / 13,600 bed-hours and $1.19M / $2.38M / $4.76M in capacity value). Show adverse outcomes and the paired spread by seed.

**Speed**: the default scenario and sweeps are precomputed by `train_models.py`, so the page opens instantly. Custom slider settings run live behind a "Run scenario" button, cached by settings. If 3 replications of the quarter take more than about 10 s, the live run drops to 1 replication and says so.

**No rigging**: no outcome is ever written into the code. If the equity gap does not narrow, or widens, the page shows that in the headline, and I will tell you.

## 7. App pages

Shared on every page: a persistent banner ("Synthetic data only. Prototype for discussion, not clinical use."), a one-sentence "What this shows", a "How it works" expander in plain English, headline numbers before charts, chart titles that state the finding, a sidebar clock (demo day plus hour), the Guided tour toggle, and the session action log with CSV export. Payer is **not** shown on operational screens (flags, rounds, board) so staff are not nudged by insurance; it appears only on the fairness, impact and methods pages.

1. **Overview** (`app.py`). The problem in 30 seconds; Halvian vs national table from the brief; the core argument as a simple flow graphic (arrival → boarding holds rooms → waits and walkouts; predictions → earlier requests → beds sooner); how to use the app; glossary (boarding, LWBS, ESI, AUC, calibration, plus door-to-provider and threshold).
2. **Live Bed Board.** Replaces the whiteboard. ED rooms as a grid by type (empty, in treatment, boarding, fast-track closed), waiting-room count against 40 seats, and inpatient units with occupied, open clean, open dirty and expected to open in 4 h. A time slider replays the demo day in 15-minute steps. Headline example: "At 2 PM, 9 of 48 ED spaces hold admitted patients while 31 inpatient beds are open."
3. **ED Admission Flags.** Current ED queue at the clock time: ID, age, ESI, complaint, time in ED, P(admit), flag, top 3 reasons, likely unit. Current moving threshold with its reason ("ED is crowded, threshold lowered from 70% to 64%"). Per-unit batched bed request cards for the next hourly batch. Approve and Override on each flag and each batch; Override requires a reason from a dropdown (not an admission clinically, already arranged, model missing context, transfer or patient preference, other).
4. **Discharge Readiness (rounds view).** Inpatients at 07:00 rounds with P(discharge within 24 h), sorted; note text with barrier evidence highlighted; detected barriers with confidence; suggested owner (case manager for placement, home care, insurance and transport; nurse for family pickup and medications or equipment; attending physician always owns the discharge decision); an action checkbox. Ticking "barrier resolved" re-scores the patient live.
5. **Bed Forecast.** Expected open beds by unit at +4, +8 and +24 h with the 80% band, matched against predicted ED admissions per unit, plus the backtest accuracy.
6. **Impact Simulator.** Section 6.
7. **Fairness and Oversight.** Model metrics by payer with amber and red flags, alert volume per day, override rate from the session log, and the pause conditions: AUC below 0.75 over 4 weeks; any payer group false negative rate more than 10 points above overall for 2 weeks; calibration drift above 5 points; override rate above 40% (mistrust) or below 2% (possible rubber-stamping); any equity gap wider than baseline at the monthly review; data feed outage over 30 min (fall back to the whiteboard and phone protocol).
8. **Data and Methods.** How the data was generated, the calibration table, every assumption (the table in section 8), the explicit payer adjustments and gap decomposition, note reader precision and recall, model cards, and sources with links from the pitch doc.

**Guided tour** (sidebar toggle) walks one synthetic story across pages, moving the clock as it goes:

1. Flags page, about 10:00: an ED patient with chest pain or shortness of breath is flagged as a likely Medicine or Telemetry admission; the bed manager approves the early bed request.
2. Rounds page: a Medicine A patient's note says "no ride until Thurs"; the case manager ticks "arrange transport"; the patient's discharge probability rises.
3. Forecast page: that bed now shows as expected to open by about 2 PM on Medicine A, matched to the flagged ED patient.

Tour patients are picked from the generated data by a documented search rule (right unit, right barrier, right timing on the demo day), not edited into the data.

**Polish**: `.streamlit/config.toml` theme; one color-blind-safe palette based on Okabe-Ito, with amber and vermillion reserved for warnings; Plotly for all charts; wide layout; formatted `st.dataframe` columns (percent, hours, currency); `st.cache_data` for tables and `st.cache_resource` for models so each page loads in under 3 s.

`docs/DEMO_SCRIPT.md`: the 2-minute click path following the tour, with talking points per step.

## 8. Assumptions where the brief is silent

All of these go in `docs/DATA.md` and on the Data and Methods page.

| ID | Assumption | Value | Why |
|---|---|---|---|
| A1 | Payer mix sums to 98% | Remaining 2% = "Other/self-pay" | Brief is silent; flagged. Note "self-pay" usually means uninsured, see open question 3 |
| A2 | Medicare door-to-provider | Emerges from the simulation | Not in the brief |
| A3 | ESI mix | About 1/17/45/29/8% for ESI 1 to 5 overall | Typical US distribution; not in the brief |
| A4 | Acuity mix by payer | ESI 4 to 5 share: Commercial 33%, Medicaid/CHIP 43%, Uninsured 47%, Medicare 24% | Fewer primary-care alternatives; main equity mechanism |
| A5 | Inpatient units | Medicine A 68, Medicine B 68, Telemetry 56, Surgery 72, Step-down 32, ICU 24 | Brief names no units |
| A6 | Non-ED admissions | About 4,400 elective (weekdays) and 5,400 direct a year | Needed for Little's law at 88% occupancy |
| A7 | Length of stay | ALOS about 4.8 d (ED), 3.0 d (elective), 4.5 d (direct); overall 4.4 d | Typical US ranges; calibrated |
| A8 | Winter season | Dec, Jan, Feb at 1.2×, mostly respiratory and fever | "Winter respiratory season adds about 20%" |
| A9 | Discharge timing | Departures centered around 14:30; ready late, leave next day; 30% of weekend-ready wait to Monday | Realistic pattern that produces the afternoon and evening mismatch |
| A10 | Barriers | 20% of stays; six types with the mix and delays in 2.7 | Hopkins one-fifth finding; delays are assumptions |
| A11 | Staff roles | Registration 2/2/1 of the techs and registration staff; triage nurses 2/2/1 of the nurses; physicians and APPs pooled as 7/7/3 providers | Brief gives totals, not roles |
| A12 | Fast-track hours | 9:00 to 23:00, ESI 4 and 5 only | Common practice; brief is silent |
| A13 | Bed process times (whiteboard era) | Request processing about 30 min, readiness and report about 30 min, transport about 15 min, cleaning about 50 min plus 25 min notification delay | Starting values, calibrated to the 3.5 h median; most influential assumption |
| A14 | LWBS behavior | Patience by ESI, with explicit payer multipliers only if needed | 2.6 |
| A15 | Admission latent noise | Set so a triage-only model reaches about 0.85 AUC | Matches published triage models; not evidence of real-world performance |
| A16 | Simplifications | No inter-unit transfers, no transfers out, no hallway beds, sex has no effect | Scope |
| A17 | Impact sim actions | Current scenario snapshots and hourly request events | Staff response delay and recoverable task time are scenario inputs. Estimate lead and impact from logged events. |
| A18 | Door-to-provider and LWBS definitions | Door-to-provider over patients who were seen; LWBS over all arrivals | Standard practice; brief is silent |
| A19 | Calendar | Fictional year on the 2025 calendar; demo day Monday Dec 8, 2025 | Real weekdays, test period, winter Monday |

## 9. Testing and definition of done

- `pytest`: config integrity (shares, capacities, staffing, costs); simulation invariants on a short run (each patient exits once, capacities never exceeded, determinism by hash); every validation check on the committed data; leakage allowlist; note reader cases including negation and resolved barriers; moving threshold bounds and direction; hourly batching and cancellation; admission batch timing invariant to future outcome changes while the patient is eligible; discharge actions require a current stay and cannot bypass readiness or unresolved barriers; zero-adoption effects are exactly zero; forecast band arithmetic and capacity-state accounting; ROI uses paired total room-hours and reproduces the pitch's 15/30/60 table exactly; `AppTest` smoke test that every page loads without exceptions.
- `ruff check .` clean.
- From a fresh clone: venv, `pip install -r requirements.txt`, `generate_data.py`, `train_models.py`, `streamlit run app.py`. Data and models are committed, so `streamlit run app.py` alone also works.
- Python: built with 3.12 (Homebrew), kept compatible with 3.11 to 3.13; requirements pinned to versions with macOS arm64 wheels.

## 10. Build phases (each ends with tests, ruff, commit, push and a 3-line update)

1. **Scaffold**: venv, pinned requirements, `.gitignore`, package skeleton, `config.py` with every brief number and citation, theme, `CLAUDE.md` and identical `AGENTS.md`, test harness.
2. **Data generation and validation**: cohort, DES, notes, calibration, `validate.py` passing, `docs/DATA.md`.
3. **Models**: admission, discharge, thresholds, forecast, explanations, fairness, leakage test, `docs/MODELS.md`.
4. **Note reader placeholder**: interface, rule-based reader, LLM stub, scoring (needed before the discharge model's final features, so phases 3 and 4 interleave: reader first, then discharge model).
5. **App pages**: Overview, Bed Board, Flags, Rounds, Forecast, Fairness, Methods, guided tour, session log.
6. **Impact simulator**: tool hooks in the DES, paired runs, sweeps, page.
7. **Polish and docs**: README, `DEMO_SCRIPT.md`, AppTest smoke tests, load-time checks, final review.

## 11. Risks and where results may disappoint

- **Calibrating all group medians and LWBS rates at once may be tight.** Seven group targets with ±5% and ±0.4 points tolerances interact. If a target cannot be hit without an unreasonable payer adjustment, I will stop and show you the trade-off rather than force it.
- **The equity gap may not narrow much.** Boarding relief mainly helps admitted patients, who skew older (Medicare). The gap could narrow in minutes but stay similar in relative terms, or barely move. The app will show what the simulation shows.
- **The size of the benefit hinges on A13** (how much of boarding is process time vs truly waiting for a bed). The decomposition chart and the sensitivity view make this visible.
- **Deadline.** Submission is Nov 24, 2026, 11:59 PM, three days from now. I will build in the phase order above so a working core (data, models, flags, rounds, forecast) exists early, with the impact simulator and polish after.

## 12. Decisions and open questions

1. **Payer use.** Keep payer available for calibration, fairness metrics and outcome audits. Audit observed features for proxy effects. Both operational models are payer-blind.
2. **Custom DES vs SimPy.** I recommend the custom engine for speed and exact control (section 1). OK, or do you want SimPy for readability?
3. **Name of the 2% group.** "Other/self-pay" as you specified, or "Other (VA, workers' comp, auto)" to avoid overlap with uninsured, who are usually self-pay?
4. **Fairness tolerances** in 5.7 and **impact defaults** in section 6 (50% adoption, 1 h staff response delay, 70% threshold, 1 h discharge task time saved). OK as starting points?
5. **Demo day**: Monday Dec 8, 2025 (busy winter Monday in the test period). OK, or would you prefer a more typical day so the board looks less extreme?
