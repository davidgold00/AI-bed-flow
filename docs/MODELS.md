# Models: what the AI does and how well it does it

**All results are on synthetic data.** Accuracy here reflects how the synthetic year was built (see `docs/DATA.md`, assumption A15). It is not evidence of how these models would perform at a real hospital. Every number below is produced by `python scripts/train_models.py` and saved in `models/metrics.json`.

## 1. The pieces

| Piece | Question it answers | When it runs | Who acts on it |
|---|---|---|---|
| Admission predictor | How likely is this ED patient to be admitted? | End of triage, refreshed for hourly bed-request batches | Bed manager approves or overrides an early bed request |
| Discharge predictor | How likely is this inpatient to leave within 24 hours? | 07:00 rounds | Unit team and case manager start discharge work |
| AI note reader (local language model, rule-based fallback) | What non-medical barrier is holding this discharge? | On each morning note | Case manager or nurse clears the barrier |
| Bed forecast | How many usable beds will each unit have in 4, 8 and 24 hours? | Any time | Charge nurse lines up cleaning and transport |

Nothing executes automatically. Every output is a recommendation with its reasons and an approve or override control.

## 2. Shared design rules

- **Payer-blind.** Insurance is never a model feature (PLAN.md decision 1). It is used only to audit fairness. A comparison model that does see insurance is trained and shown on the Fairness page, never deployed.
- **Only information available at prediction time.** Each model declares its prediction time and a feature allowlist. `tests/test_leakage.py` checks the allowlist, a list of forbidden outcome columns, and an "as-of" property: rewriting anything that happens later (disposition, departure, discharge time, ground-truth barriers, payer) leaves the scores unchanged.
- **Temporal split with label availability** (REVIEW finding 2). Algorithm choice: fit on January to August rows whose outcome was known before September 1, score September. Final model: refit on January to September rows whose outcome was known before October 1. Test: October to December, never used for fitting or choice.
- **Algorithm choice rule.** Logistic regression is the default because its reasons are exact and add up to the estimate. Gradient boosting (scikit-learn HistGradientBoosting) is chosen only if it beats logistic regression by at least 0.02 AUC on September with no worse Brier score.
- **Explanations.** For logistic regression, each patient's top 3 reasons are exact contributions to the log-odds compared with a typical training patient ("Age 78 raises the chance", "Chest pain raises it", "ESI 2 raises it"). For gradient boosting they come from occlusion (reset one feature to typical and measure the change). Global importance is reported as mean absolute contribution and permutation importance (drop in AUC when a feature is shuffled). Reasons explain the model, not clinical causes.

## 3. Admission predictor

**Features (end of triage):** age, heart rate, blood pressure, breathing rate, oxygen level, temperature, ED visits in the past year, main complaint (14 categories), ESI, arrival mode, time of day of arrival, weekend, winter.

**Cohort:** patients who were seen (they have a disposition). 93.4% of triaged test-period patients have a known outcome; the rest left without being seen. Training rows: 60,916. Test rows: 20,686 (3,492 admissions).

| Algorithm | September AUC | September Brier | Test AUC | Test average precision | Test Brier | Calibration gap |
|---|---|---|---|---|---|---|
| Logistic regression (chosen) | 0.847 | 0.105 | **0.857** | 0.557 | 0.102 | +0.2 pts |
| Gradient boosting | 0.845 | 0.105 | 0.856 | 0.553 | 0.102 | +0.2 pts |

Boosting did not beat logistic regression, so the transparent model is used. Test AUC 0.857 is close to the 0.87 the PLOS ONE triage study reports, by design of the generator.

**Most influential inputs** (permutation AUC drop): ESI 0.170, age 0.044, main complaint 0.034, then oxygen level and breathing rate. The model leans heavily on the triage nurse's ESI.

**Two policies, reported separately** (test months):

| Policy | Flags | Precision | Admissions caught (recall) | False positive rate |
|---|---|---|---|---|
| Fixed 70% threshold at triage | 2.3% of patients | 0.78 | 10.5% | 0.6% |
| **Deployed**: moving threshold (base 70%), hourly batch, 1 h staff response delay | 5.2% of patients | 0.68 | **20.9%** | 2.0% |

The moving threshold drops when the ED is crowded (typical crowding is 1.08 patients per space, because waiting patients count too), so the deployed policy flags more than the fixed rule.

**Lead time** (deployed policy): of 3,492 test admissions, 730 were flagged before the admit decision, a median of **1.9 hours** ahead (middle half 1.1 to 3.2 hours). 2,762 were not flagged in time. About 11.7 alerts a day.

**Honest reading:** at a 70% threshold the tool catches about one admission in five, but those it catches come with about two hours of warning and two in three flags are right. Lowering the threshold catches more admissions at the cost of more unused bed preparations; the Impact Simulator shows that trade-off.

**Likely unit:** a lookup of the most common admitting unit for the same complaint, ESI and age band (training data, smoothed). It picks the right unit for 69% of test admissions, which is why bed requests are batched per unit as expected counts rather than promised to individuals.

## 4. Discharge predictor

**Features (07:00 rounds):** time in hospital so far, mobility score, lab trend, unit, diagnosis group, admission source, day of the week, and the six barrier flags the note reader found in that morning's note.

**Cohort:** every inpatient at every 07:00 rounds. Label: leaves within 24 hours. A row's label counts as known only after its 24-hour window closes. Training rows: 79,375. Test rows: 27,279 (5,977 discharges within 24 h).

| Algorithm | September AUC | September Brier | Test AUC | Test average precision | Test Brier | Calibration gap |
|---|---|---|---|---|---|---|
| Logistic regression | 0.841 | 0.125 | 0.827 | 0.536 | 0.131 | -0.3 pts |
| Gradient boosting (chosen) | 0.862 | 0.118 | **0.853** | 0.600 | 0.122 | -0.4 pts |

Boosting beat logistic regression by 0.021 AUC on September with a lower Brier score, clearing the 0.02 margin, so it is the default here. Its patient-level reasons come from occlusion.

**At the 50% rounds threshold:** 14.2% of inpatient-days are flagged, precision 0.63, recall 0.41. **Timing, on explicit cohorts** (Codex review): of the 5,977 patients who went home in the test months with a rounds row in their last 24 hours, **2,448 (41%) were flagged on that morning** and 3,529 were missed; for correct flags, departure came a median **6.8 hours** after rounds. The 3,529 missed rounds rows (not flagged, but the patient left within 24 hours) also left a median 6.8 hours after rounds, so a missed patient is not one who left too quickly to act on: that is warning time the list did not give. Each cohort is defined in `halvian/models/discharge.py::LEAD_COHORTS` and saved with the numbers in `models/metrics.json` (`discharge.lead_time.cohorts`). Diagnostic: counting every flag, the first flag came a median 8.0 hours before departure, and 36% of flagged stays were first flagged more than 24 hours ahead. On the rounds page, anyone whose note flags a barrier is also listed, whatever their score.

**Most influential inputs** (permutation AUC drop): lab trend 0.165, mobility 0.032, time in hospital 0.027, day of the week 0.020, then the placement and home care barrier flags.

**Synthetic artifact, reduced but not removed.** Lab trend and mobility are generated from each patient's hidden recovery progress plus day-to-day random-walk noise, in the same way vitals are generated from hidden severity. An earlier version used almost noise-free trends and reached AUC 0.887; adding realistic noise brought it to 0.853 (Codex review). Barrier identification no longer depends on when the barrier will be resolved, and a test checks that changing a barrier's future duration leaves earlier observations unchanged. Treat the remaining accuracy as a property of the generator.

## 5. AI note reader (local language model) with a rule-based fallback

**What it is.** `LLMNoteReader` (`halvian/notes/reader.py`) sends each morning note to **Llama 3.2 3B (instruct)** running through Ollama on this Mac (`http://127.0.0.1:11434`; the client in `halvian/notes/ollama.py` refuses any other host). No cloud API, no key. Decoding is deterministic: temperature 0, a fixed seed, a JSON schema for the answer (`format`), one versioned prompt (`halvian/notes/prompt.py`, `v1-2241325901`) with five hand-written worked examples, and a 20-second timeout. **Why this model:** this Mac has 8 GB of memory, and the team plan uses the 3B model below 16 GB (llama3.1:8b and qwen2.5:7b would be compared on 16 GB or more).

**Checks on every answer (guard `g2`).** The model returns each barrier with a status (active, resolved or negated) and a quoted evidence phrase. A finding is kept only if:

1. it is active, and the quote appears in the note word for word (ignoring letter case; the offsets come from the note, never from the model);
2. the rules' own negation, resolution and imaging checks do not contradict it ("ride confirmed", "no barriers to dc", "transport to MRI");
3. new in `g2`: the quote's own clause names a discharge task (a facility, home care, an approval, a family member, a ride, a prescription or equipment; typo-tolerant) **and** says it is still open (pending, awaiting, needs, until, can't, not yet). "Holding meds", "O2 2L NC", "NPO" and "PT eval pending" fail this. If the clause says "none avail until Sun" and the clause just before it in the same sentence names the task ("needs wheelchair van"), the highlight grows to include it. A finding the model filed under the wrong type is given the one type its words name (an approval pending for any service is an insurance task).

In the run below the model returned 1,737 items: 577 were not active, **65 quoted text that is not in the note**, 46 were negated or resolved by context, **269 named no open discharge task** and were dropped, and 64 were given the type their words name; 730 were kept. Confidence is a match strength, not a probability: 0.90 when the rules found the same barrier, 0.70 when only the model did.

**How `g2` was built without touching the test notes.** The first reader (checks `g1`) was scored on **sample A** (1,561 test-quarter notes) and its false alarms were studied. Those errors told us what to fix, so sample A can no longer judge the fix. `g2` was written on two independent draws of 360 **training-month** notes (January to September): on the first it took the model from precision 0.78 to 1.00 at recall 0.89 to 0.92; on the second, drawn to confirm it, from 0.77 to 0.99 at recall 0.88 to 0.92; its one remaining false alarm ("home meds reconciled, PT eval pending") led to one more rule, that the task and "still open" must sit in the same clause, after which both draws scored precision 1.00. Then the current reader was scored once on **sample B**: the same design as A (up to 35 notes per barrier type × payer group, plus 700 notes with no barrier, half with barrier words), drawn afterwards and sharing **no note and no note text** with A. The cache keeps the model's raw answers, so B also shows the same answers under the old checks.

**Results on sealed sample B (1,319 notes the model read):**

| Reader | Precision | Recall | F1 |
|---|---|---|---|
| AI reader, checks g2 (current) | 0.993 | 0.937 | 0.964 |
| Same model answers, first checks g1 | 0.745 | 0.919 | 0.823 |
| Rule-based reader | 1.000 | 0.947 | 0.973 |
| **AI reader and rules together (what the app shows)** | **0.993** | **0.968** | **0.980** |

| Barrier type | AI reader F1 (precision, recall) | Rules F1 (precision, recall) |
|---|---|---|
| Placement | 0.968 (1.00, 0.94) | 0.953 (1.00, 0.91) |
| Home care | 0.964 (1.00, 0.93) | 0.972 (1.00, 0.95) |
| Insurance authorization | 0.985 (1.00, 0.97) | 0.980 (1.00, 0.96) |
| Family pickup | 0.957 (1.00, 0.92) | 0.986 (1.00, 0.97) |
| Transport | 0.967 (0.99, 0.94) | 0.981 (1.00, 0.96) |
| Medications or equipment | 0.939 (0.97, 0.91) | 0.966 (1.00, 0.93) |

For comparison, the first reader on sample A: precision 0.783, recall 0.909, F1 0.841, with medications or equipment at precision 0.50 (kept in `metrics.json` under `note_reader.history`, its cache in `models/llm_note_findings_v1-2241325901_g1.parquet`).

**On these templated notes the AI reader alone is still slightly below the rules** (F1 0.964 against 0.973), because the rules were written for the same templates that generated the notes. Together they beat the rules alone: the model finds barriers the rules miss (recall 0.968 against 0.947) without adding false alarms.

**New-phrasing stress test (wording neither reader was built on).** `halvian/notes/stress.py` holds 304 notes (144 labelled barriers) in other clinical styles ("PT/OT recommending SAR. Referrals faxed to 3 facilities, no bed offers so far", "Wife works nights, cannot come get him until Saturday morning"), with resolved, negated and distracting phrases. It was committed before either reader ran on it, and nothing was tuned on it.

| Reader | Precision | Recall | F1 |
|---|---|---|---|
| AI reader, checks g2 | 0.975 | 0.549 | 0.702 |
| Same answers, first checks g1 | 0.732 | 0.778 | 0.754 |
| Rule-based reader | 1.000 | **0.062** | 0.118 |

The rules find 6% of barriers once the wording changes; the language model finds most of them. That is the case for the AI reader, and the reason the rules are only the fallback. The stress test also shows the cost of `g2`: its task and open-word vocabulary came from the templates, so on new wording it trades recall (0.78 to 0.55) for precision (0.73 to 0.98). Which trade is right is a pilot question (a missed barrier is worse than a false alarm a case manager dismisses in seconds), and the vocabulary should be rebuilt from real, de-identified notes. The stress set is small and synthetic: robustness to new wording, not real-world accuracy.

**Fallback.** If Ollama is not running, the model is missing, a call times out or the answer is not valid, the rule-based reader answers and the result says `status: "fallback"` with the reason. The app works with Ollama off. In the run, 2 of 2,180 notes fell back (after one retry each) and were left out of the model's scores.

**Scale, honestly.** The synthetic year has 107,215 notes (53,481 distinct texts). At about one second per note that is around 15 hours, too long for a laptop. So the local model reads the evaluation sample B (1,321 notes), the stress set (304) and **every note the app shows on both demo days** (581 notes, Oct 15 and Dec 8), and the **rule-based reader stays the full-year feature source** for the discharge model and the impact simulation. `scripts/run_llm_reader.py` timed 40 training-month notes first (0.57 s each), sized the run to finish within 60 minutes, and finished in **39.3 minutes**. Results are cached in `models/llm_note_findings.parquet` with the model, prompt and guard versions, the raw answer and the time of each read.

**Fairness by payer (sample B).** AI reader recall: Commercial 0.95, Medicare 0.94, Medicaid/CHIP 0.93, **Uninsured 0.92 (1.8 points below overall)**; precision 0.99 to 1.00 for every group. Sample A had taken most of the test quarter's Uninsured barrier notes, so B has only 37 for Uninsured and none for "Other"; sample A's payer results for the first reader are in `note_reader.history`. Rules: recall 0.89 (Uninsured) to 0.96 (Medicare), precision 1.00.

**How the app uses it.** On the demo days, each note shows the model's findings plus any barrier only the rules found, each tagged with which reader found it (`reader`: "llm" or "rules"). The discharge chance always uses the rule findings, the model's feature source, so the score does not change with the reader. `halvian.notes.live.analyze_note` reads a single note live (about one second once the model is loaded) with the same checks. Every barrier is a suggestion a case manager or nurse acts on; the attending makes the discharge decision.

## 6. Bed forecast

**What it forecasts:** net usable beds per unit, meaning clean, empty, unassigned beds minus patients already waiting in that unit's bed queue. Positive means spare beds; negative means patients will keep waiting. Assigning a bed to a waiting patient does not change it; it rises when a bed is cleaned and falls when a new request joins the queue (a test confirms this identity on the simulated data, including off-service moves). So:

> net in h hours = net now + beds made ready − new requests

using only what is known now (the tables are fitted only on events observable before October 1, and every demand window closes before that cutoff): beds being cleaned (typical cleaning time 89 min); inpatients who may leave (latest rounds probability spread over the horizon with the time-of-day discharge profile, then cleaned); ED patients already admitted but not yet queued (counted once); ED patients still undecided (P(admit) × P(unit) × chance the request lands in time); patients not yet arrived and direct or elective admissions (historical rates by hour, weekday or weekend, and season, from January to September). The 80% band treats patients as independent yes/no events and arrivals as Poisson.

**Backtest** (07:00 and 15:00 on every test day, every unit; 1,092 forecasts per horizon):

| Horizon | Mean absolute error (beds) | "No change" baseline error | Share inside the 80% band |
|---|---|---|---|
| 4 h | **1.16** | 2.56 | 81% |
| 8 h | **2.04** | 3.02 | 78% |
| 24 h | **3.41** | 3.64 | 75% |

The forecast clearly beats "no change" at 4 and 8 hours and only slightly at 24 hours. Its 24-hour band is too narrow (75% coverage for an 80% band), because the independence assumption ignores days when everything runs late. The page says so.

## 7. Thresholds and requests

- **Alert threshold** 70% (Early Prediction of Hospital Admission preprint).
- **Moving threshold** (Operations Research): `clip(base - 0.40 × (crowding - typical), 0.55, 0.85)`, where crowding is patients in ED spaces plus patients not yet roomed, divided by 48 spaces. All four numbers are in `config.py`.
- **Hourly batched requests per unit** (arXiv 2026): each hour, the bed request for a unit is the rounded sum of admission probabilities of approved, flagged, still-undecided patients whose likely unit it is, minus beds already reserved. A wrong individual prediction costs little.
- **Rounds list** threshold 50%.

## 8. Fairness by payer

**Rule** (also on the Fairness page). Measured on test months; "insufficient data" if a group has fewer than 30 positives or negatives.

| Check | Amber if more than | Red if more than |
|---|---|---|
| AUC below the overall AUC | 0.03 | 0.05 |
| Calibration gap (mean predicted minus observed), either direction | 2 pts | 4 pts |
| False negative rate (missed true cases ÷ all true cases) above the overall rate | 5 pts | 10 pts |

**Admission predictor, deployed policy:**

| Group | Visits | Admissions | AUC | Calibration gap | Missed admissions (FNR) | Flag rate | Level |
|---|---|---|---|---|---|---|---|
| All patients | 20,686 | 3,492 | 0.857 | +0.2 pts | 79.1% | 5.2% | |
| Medicaid/CHIP | 7,071 | 802 | 0.869 | +0.5 pts | 88.4% | 1.7% | Amber |
| Medicare | 4,578 | 1,284 | 0.803 | +0.1 pts | 68.7% | 13.5% | Red (AUC) |
| Commercial | 6,972 | 1,117 | 0.851 | +0.1 pts | 82.8% | 4.0% | OK |
| Uninsured | 1,622 | 195 | 0.870 | +0.1 pts | 91.8% | 1.2% | **Red (FNR)** |
| Other | 443 | 94 | 0.835 | -0.4 pts | 71.3% | 8.1% | OK |

At the fixed 70% threshold the pattern is the same but smaller: Uninsured is amber (95.9% missed vs 89.5% overall) and Medicare red on AUC.

**What this means.** The model is equally well calibrated for every group (within half a point), so a 70% score means the same thing for everyone. But Uninsured and Medicaid/CHIP patients are younger and less acute on average, so fewer of their eventual admissions reach the threshold, and the early-bed-request benefit flows more to Medicare patients. Medicare discrimination is weaker because, among older patients, age stops separating admissions from discharges. **By our own rule this would trigger a review before launch.** Options to discuss: a lower base threshold for everyone, measuring whether missed Uninsured admissions are simply less urgent, or leaning on the discharge side of the tool, which is fair across groups. Group-specific thresholds would make payer an input to decisions, which the plan rules out.

**Pre-launch bias test: case mix or model?** (`halvian.models.fairness.case_mix_check`, saved in `models/metrics.json` under `admission.fairness_case_mix`.) Among true admissions in the test quarter, each group's miss rate is compared with the rate expected if its patients were missed like everyone else with the same triage level and age band (direct standardization). The unexplained part is observed minus expected:

| Group | Admissions | Missed | Expected from triage level and age | Unexplained |
|---|---|---|---|---|
| Medicaid/CHIP | 802 | 88.4% | 89.3% | -0.9 pts |
| Medicare | 1,284 | 68.7% | 68.8% | -0.1 pts |
| Commercial | 1,117 | 82.8% | 82.3% | +0.5 pts |
| Uninsured | 195 | 91.8% | 89.2% | +2.6 pts |
| Other | 94 | 71.3% | 73.4% | -2.1 pts |

So the red flag is a case-mix effect, not the model scoring similar patients differently: no group is missed more than 2.6 points beyond what its triage levels and ages predict (amber at 3, red at 5, `config.CASE_MIX_UNEXPLAINED_PTS`). Two cautions. On real data, triage levels can themselves carry bias (the brief notes that assignments vary), so the pilot reruns this test on Halvian's records in silent mode. And a missed flag means the usual process, never a lower priority, while the downstream benefit (freed ED rooms) reaches whoever is next in the waiting room.

**The same policy at other base thresholds** (payer-blind; `admission.policy_by_base_threshold`, with the impact runs in `models/scenarios.json`):

| Base threshold | Precision | Recall | Alerts a day | Minutes saved per admission (range) | Medicaid/CHIP and Uninsured gaps narrowed |
|---|---|---|---|---|---|
| 50% | 63.5% | 31.5% | 18.8 | 20 to 30 | 3 of 4 |
| 60% | 66.1% | 25.0% | 14.4 | 15 to 25 | 4 of 4 (the "Other" walkout gap widens slightly) |
| 70% (default) | 67.9% | 20.9% | 11.7 | 10 to 20 | 3 of 4 (Uninsured wait gap flat) |

The roadmap makes this a Phase 2 decision taken on pilot data (`docs/STRATEGY.md`). Lowering the threshold raises recall for every group but does not close the miss-rate gap in points, because that gap comes from case mix.

**Why payer is excluded.** The comparison model that sees insurance has the same overall AUC (0.857) and does not fix the gap (Uninsured FNR 95.4% at the fixed threshold vs 95.9% without insurance). Including insurance would add a proxy for income to clinical decisions for no accuracy gain.

**Discharge predictor:** AUC 0.846 to 0.862 and false negative rates within 4 points of overall for every group. One amber flag: the model over-predicts discharge for Medicare inpatients by 2.1 points (they are older with more placement barriers). The comparison model with insurance has AUC 0.854 vs 0.853.

## 9. Impact simulation (October to December, three synthetic years)

> Model estimate from a synthetic Halvian calibrated to the case brief. It shows which levers matter and how large
> the payoff could be under stated assumptions. It is not evidence from a real hospital.

`halvian/impact.py` runs the baseline and the tool on **the same pre-drawn patients**; the tool switches on October 1, so both arms match before then (tested), and zero adoption reproduces the baseline exactly (tested). Bed requests come from hourly batches of patients flagged at triage after the staff response delay; discharge actions come from 07:00 rounds in scenario time, scoring the inpatients present that morning with that day's note. A discharge is never brought forward before medical readiness, a barrier the reader missed cannot be skipped, and the shift never exceeds the hours-saved setting (all tested). **The bed board lever** (assumption A22, our assumption with no study behind it) cuts the housekeeping notification delay and bed request processing by 25% after go-live, in the tool arm only; it scales each patient's pre-drawn delay, so the arms stay paired (tested). **Minutes saved per admission** is the drop in total boarded ED room-hours in the window (visits crossing its edges included) per baseline admission. **Freed capacity** is that minute range x 13,600 admissions a year / 60 x the brief's $350 per boarded room-hour: capacity, not cash.

**How results are reported.** Never as a single number. Each range is the spread across the three synthetic years, widened outward to round numbers: minutes to the nearest 5, dollars to $0.1M, waits to the nearest minute, walkouts to 0.1 points (`halvian/ranges.py`, written to `models/impact_ranges.json`, the file the app reads). The spread describes simulation variability, not a confidence interval. The case brief's own numbers (3.5 h, 55 min, 4%, $350 per bed-hour) stay exact.

**Break-even first.** The tool pays for itself at about **6 minutes saved per admission**: $500,000 a year / ($350 per bed-hour x 13,600 admissions a year) = 0.105 hours.

| Scenario | Minutes saved per admission | Freed capacity a year (not cash) | Walkout change, simulated winter quarter (pts) | Reserved bed-hours idle, simulated winter quarter |
|---|---|---|---|---|
| **Cautious**: today's defaults (50% of flags acted on, 1 h response, 70% threshold, 1 h discharge), no bed board | 10 to 20 | $0.8M to $1.6M | -0.9 to -0.4 | 700 to 1,000 |
| **Expected**: Cautious plus the bed board | 20 to 30 | $1.6M to $2.4M | -1.0 to -0.6 | 700 to 1,000 |
| **Full rollout**: 75% acted on, 60% threshold, 2 h discharge, bed board | 35 to 50 | $2.8M to $4.0M | -1.6 to -0.8 | 1,400 to 1,700 |
| Admission flags only | 10 to 15 | $0.8M to $1.2M | -0.7 to -0.3 | 700 to 1,000 |
| Discharge work only | -5 to 10 | -$0.4M to $0.8M | -0.3 to 0.0 | 0 to 100 |
| Bed board only | 10 to 15 | $0.8M to $1.2M | -0.5 to -0.3 | 0 to 100 |
| Pilot: Medicine A only | 0 to 5 | $0.0M to $0.4M | -0.2 to -0.1 | 0 to 100 |
| 100% adoption | 20 to 35 | $1.6M to $2.8M | -1.3 to -0.7 | 1,300 to 1,700 |
| 50% threshold | 20 to 30 | $1.6M to $2.4M | -1.0 to -0.5 | 1,400 to 1,500 |
| 4 h discharge time saved | 15 to 35 | $1.2M to $2.8M | -1.4 to -0.6 | 700 to 1,000 |
| 3 h staff response delay | 5 to 15 | $0.4M to $1.2M | -0.7 to -0.2 | 200 to 400 |

**Reading it.** Every scenario's range sits above the 6-minute break-even, including Cautious. The early bed requests from admission flags and the bed board each contribute 10 to 15 minutes on their own. Discharge work alone has no reliable effect (its range straddles zero), so its value is in combination and in the rounds workflow, not as a stand-alone lever. The share of flags staff act on moves the result most (5 to 15 minutes at 25%, 20 to 35 at 100%), and raising it or lowering the threshold roughly doubles the bed-hours held idle by reservations. A Medicine A-only pilot frees too little to measure on outcomes, so the pilot is judged on process measures (lead time, request acceptance, overrides) first. Direct and elective admissions waited about the same or less in every scenario; the largest increase was under 5 minutes in one synthetic year with the admission flags alone.

**Equity** (payer gaps against Commercial, pooled across the three years; payer is never a model input). Cautious: the Medicaid/CHIP wait and walkout gaps and the Uninsured walkout gap narrow; the Uninsured wait gap is flat. Expected: all four Medicaid/CHIP and Uninsured gaps narrow. Full rollout: all four narrow. Nothing widens in any of the three, and the equity guardrail is not triggered. The Uninsured wait gap is the least stable verdict: year by year it widened in one of the three synthetic years in both Cautious and Expected, and narrowed in all three only in Full rollout. With section 8 (the admission flag misses more Uninsured admissions), it is the gap to watch in the pilot.

## 10. Limitations

- Synthetic accuracy is set by the generator; real performance must be measured in a silent pilot.
- The admission model mostly repeats the triage ESI; its value is speed and consistency, not hidden insight.
- On these templated synthetic notes the AI note reader is less precise than the rules (F1 0.84 against 0.96); its value on real free-text notes is untested.
- The forecast's 24-hour band under-covers.
- The admission flag's benefit is unevenly distributed across payer groups at the default threshold (section 8).
- Impact results depend most on how much of boarding is process time the tool can skip (DATA.md A13). The bed board lever (A22) cuts part of it by an assumed 25%, and on its own adds 10 to 15 minutes per admission, which shows how sensitive the results are to that share; no study we found backs the 25%.
