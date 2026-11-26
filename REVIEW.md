# Halvian Bed Flow Dashboard review

**Audit baseline** `main` at `7383a6a` (Nov 21, 2026). This revision contains the build plan and case materials. It has no `AGENTS.md`, `docs/`, synthetic outputs, application, models, or tests. Running `python3 scripts/validate.py` returned `[Errno 2] No such file or directory`. The findings below identify defects and gaps in the planned design. Empirical validation requires a later build.

I reviewed the organizer’s brief and scoring criteria alongside the team’s planning documents.

## Findings in severity order

| Rank | Severity | File | Problem | Why it matters | Fix |
| --- | --- | --- | --- | --- | --- |
| 1 | High, correctness | [PLAN.md §6](PLAN.md#6-impact-simulator-how-the-tool-is-modelled) | The request clock uses `admit decision - lead time`. The decision timestamp is unavailable when the simulator is deciding whether to act. An eventual admission may also be needed to calculate that timestamp. | This can target preparation and reservations just before they become useful, distort false-positive costs, and manufacture a lead-time benefit. | Schedule at an hourly batch from observed triage, simulated staff response delay, and current ED state. Process candidates while undetermined, including those later discharged or leaving unseen. Measure lead time from the resulting events. |
| 2 | High, correctness | [PLAN.md §§5.1, 5.2, 5.5](PLAN.md#5-models) | The date split specifies months but omits label availability at cutoffs. A feature-name allowlist cannot prove that notes, diagnoses or synthetic mobility/lab trends contain only information available at prediction time. The common lead-time definition also refers only to admission. | September outcomes can inform an earlier model selection even when they resolve in October. Future-conditioned features or post-decision flags can inflate accuracy and lead time. | Split by snapshot time, fit preprocessing and calibration on eligible prior rows, and require labels to be observable by each fit cutoff. Audit source timestamps and synthetic feature construction. Report admission and discharge lead times on their own clocks, with event definitions and denominators. |
| 3 | High, correctness | [PLAN.md §6](PLAN.md#6-impact-simulator-how-the-tool-is-modelled) | Reusing baseline discharge snapshots can action a stay absent from the scenario at that hour, or use a note or stay duration the scenario never observed. A medical-readiness floor alone also allows an unresolved barrier to be bypassed. | This can give the intervention credit for beds that could not have been released. | Evaluate rounds on each scenario's current inpatients using features available at rounds. Require a staffed action and a release time after medical readiness and all unresolved constraints. Log which component was shortened. |
| 4 | High, correctness | [PLAN.md §5.4](PLAN.md#54-bed-forecast) | “Open now” needs to distinguish ready from dirty or reserved beds. The ED probability sum needs to distinguish undecided patients from patients already admitted and waiting. A fixed daily discharge curve also needs conditioning on patients still present at the forecast origin. | Double-counted demand or unavailable beds can make the forecast unsafe to interpret. Unvalidated intervals can look more informative than they are. | Decompose supply and demand into mutually exclusive states. Use a clock- and horizon-specific discharge profile for eligible inpatients, add existing boarders once and include cleaning and reservation constraints in a forecast labelled usable beds. Check each horizon against a persistence baseline and report empirical interval coverage. |
| 5 | High, correctness | [PLAN.md §§2.7, 6](PLAN.md#6-impact-simulator-how-the-tool-is-modelled) | “Annualized per admission” leaves the numerator and reference cohort unspecified. The headline outcome is a difference in medians, while capacity value is a difference in total hours. Tool runs can also change who is seen and eventually admitted. | Multiplying a median difference by volume can misstate value, especially when the longest waits or the number treated change. Annualizing a winter-heavy quarter also embeds a seasonality assumption. | Subtract total boarded ED room-hours over the same window, including room-hours from visits crossing its edges. If annualizing, apply the same baseline admission denominator and 13,600 reference volume to the paired difference and label the result a test-quarter run rate. Report signed effects, admission counts and reserved time alongside it. |
| 6 | Medium, case faithfulness | [PLAN.md §§0, 2.1, 2.7](PLAN.md#21-calibration-targets-all-go-in-configpy-with-a-brief-citation) | Average hospital-wide occupancy does not establish whether a staffed, clean, appropriate bed exists when one is needed. The plan's additional target for 36 to 44 open beds imposes a tighter, partly asymmetric condition on the same 320-bed average. | The demo could overstate how much of boarding is coordination and make one data fit look like two independent checks. | Treat open beds as the complement of occupancy. Show occupied, clean available, dirty and reserved counts by unit and hour. Decompose time spent securing a bed, preparing it and transferring the patient. |
| 7 | Medium, case faithfulness | [PLAN.md §§2.4, 5.1, 5.7](PLAN.md#57-fairness-by-payer-group) | Payer exclusion is left open in the admission plan, and a moving operational threshold needs a separate evaluation from a fixed reference threshold. The admission training cohort excludes people who left unseen, even though triaged patients in that cohort may enter the live workflow. | Direct use of payer contradicts the review scope. Availability of a known outcome varies with waiting, and fixed-threshold parity can miss unequal errors under the actual policy. | Keep payer out of both feature schemas and production decisions. Keep it on evaluation joins. Report the fixed and deployed policy with their own labels, outcome coverage, missing labels, support and positive denominators by group. Use the synthetic latent admission label only in a clearly identified simulator diagnostic. |
| 8 | Medium, case faithfulness | [PLAN.md §§2.4, 2.6, 6](PLAN.md#26-equity-mechanisms-gaps-should-come-mostly-from-mechanism) | The pitch anticipates an equity improvement, but the assumed group-level urgency, arrival and patience profiles can dominate the result. Median wait among patients seen can worsen when the intervention helps previously unseen patients reach care. | Improvements in averages and changes in the observed cohort can conceal harm to a group. Payer-blind features can still proxy for payer. | Show signed wait and walkout gaps, group outcomes, counts, changes in who was seen and paired seed differences. Run a sensitivity check with direct payer-specific patience or registration adjustments disabled. Keep the same draws and mechanisms in both arms, and mark unfavorable results explicitly. |
| 9 | Medium, case faithfulness | [PLAN.md §6](PLAN.md#6-impact-simulator-how-the-tool-is-modelled) | “Conservative” is unverified for one hour of lead and two hours of discharge work reduction. Full-hospital scope previews expansion while the proposed pilot covers one general medicine unit. Sensitivities cover policy sliders but may miss the share of boarding time that staff can actually reduce. | Default ROI can look like an empirical estimate or a pilot result. The largest uncertain input can be omitted from the sensitivity view. | Identify assumptions in the interface, include zero-effect controls and a labelled Medicine A pilot, and sweep the recoverable process share along with adoption, response time, threshold and discharge prep. |
| 10 | Medium, case faithfulness | [PLAN.md §§5.3, 6, 7](PLAN.md#7-app-pages) | The plan mentions a limit on early reservations but specifies an expiry only in the impact flow. It leaves the handling of new staffed-room demand, incorrect units, duplicate approvals and fallback handoff underdefined. | A missed admission or an idle held bed can harm flow without appearing in ED boarding alone. A rehearsed demo can hide whether an override actually changes the workflow. | Exercise an override end to end and record who approved or overrode, why and what changed. Compare unused reserved bed-hours and delays to competing admissions. Give current priority requests precedence under the chosen safety rule and rehearse the phone and whiteboard fallback. |
| 11 | Medium, explainability | [PLAN.md §§5.5, 5.6, 7](PLAN.md#56-explainability) | Acronyms, band semantics, model scores and reasons can be accurate while still being difficult to interpret in one minute. Three highlighted patients can also be mistaken for a guaranteed bed match. | A judge should see the staff decision and the consequence before interpreting model diagnostics. | Use the page checks below. Show short definitions at first use, timestamp all estimates, and say what changed after a user action. Show feature reasons as contributions to an estimate and distinguish predicted unit availability from a confirmed assignment. |
| 12 | Low, polish and quality | [PLAN.md §§7, 9](PLAN.md#9-testing-and-definition-of-done) | AppTest coverage, plotting conventions and caching are planned. No timings, cold-start budget, contrast measurements or keyboard checks exist. | Slow initial loads and color-only state markers can weaken the demo even if formulas pass. | Add smoke coverage for every page and time cold loads and representative warm reruns separately. Check the browser as well as AppTest, including keyboard controls, labels, contrast and non-color state cues. |

## Calibration re-derived from the case

| Reference | Target | Independent calculation or check |
| --- | --- | --- |
| Brief p. 1, scale and patients | About 85,000 ED visits and 16% admitted | Count arrivals in the reporting year, including walkouts. Divide realized admissions by all arrivals. At target levels this is 13,600 realized admissions, about 37.3 per day. Compare latent intent to actual disposition separately. |
| Brief p. 1, insurance | 35% Medicaid/CHIP, 22% Medicare, 33% commercial, 8% uninsured | At 85,000 arrivals these are 29,750, 18,700, 28,050 and 6,800. They sum to 98%. A 2% residual (1,700 visits) is a modelling assumption. Use “Other” unless coverage is defined further. |
| Brief p. 1, demand | Monday busiest, weekday morning and evening peaks, about 20% winter uplift | Compare mean volume per calendar day by weekday and by winter/non-winter, including every date. Check the weekday hourly profile. With a Dec to Feb winter assumption, a 365-day year gives about 222 non-winter and 266 winter visits per day. |
| Brief pp. 2 to 3, first contact | 55 min overall, 48 commercial, 58 Medicaid, 64 uninsured | Median of first-provider timestamp minus arrival among visits with a first provider contact. Medicaid/CHIP is an explicit operational proxy for the brief's Medicaid outcomes. No Medicare or Other median is supplied. Compute the overall median on pooled visits. |
| Brief pp. 2 to 3, leave before seen | 4.0% overall, 3.0% commercial, 4.6% Medicaid, 5.8% uninsured | Walkouts divided by all arrivals, overall and inside each group. At exact target shares and rates, Medicare plus Other would have a combined 3.9% walkout rate to reconcile the overall 4.0%. The separate rates are unspecified. |
| Brief p. 3, equity | Commercial as comparator | Medicaid minus commercial is +10 min and +1.6 percentage points. Uninsured minus commercial is +16 min and +2.8 points. Report signed gap changes and outcomes for both groups. |
| Brief pp. 2, 4, boarding | Median 3.5 h (210 min) | Calculate admit decision to departure from ED for inpatient transfer, using realized admissions. Count duration over the reporting window separately for capacity value. |
| Brief p. 1, hospital space | 320 beds including 24 ICU, about 88% occupied and 40 open | Integrate occupied inpatient bed-time divided by 320 and observation time. At 88%, 281.6 are occupied on average and 38.4 unoccupied. Validate the bed inventory and census states separately, and distinguish unoccupied from clean, staffed and available. |
| Brief pp. 1 to 2, ED space and staffing | 32 treatment, 8 fast-track, 4 resuscitation/trauma, 4 behavioral health, 40 waiting seats. Day/evening/night: 4/4/2 physicians, 3/3/1 APPs, 14/14/9 nurses, 8/7/4 techs/registration. | Verify queue and resource capacities and shift changes at 07:00, 15:00 and 23:00. A configured headcount is not evidence of an actual simulation constraint. Document allocations, resource pooling and hallway overflow. |
| Brief pp. 3 to 4, workflow | Registration 5 to 10 min, triage 5 to 15 min, evaluation/treatment 2 to 3 h, ED discharge 20 to 40 min, 2+ h for lower urgency on surge days | Measure step durations from events and show queue time separately. “Median among acuity levels 4 to 5 on the busiest 10% of days” is a reproducible definition proposed by the plan. The brief supplies neither that percentile nor a median for the subgroup. |
| Brief p. 2, reference comparisons | Typical 30 to 40 min to provider, 2 to 3% leave unseen, 2 to 2.5 h boarding. Follow-up 40% at Halvian vs about 40 to 50% typical. | Use as case context. Follow-up within 14 days belongs outside the chosen simulation scope. |
| Brief p. 6, cost drivers | Nurse $65/h, physician $200/h, advanced practice provider $100/h, admin $35/h, overtime 1.5×, net revenue $1,500 per visit, about $350 per boarded ED bed-hour | Verify units, rate application and consistent horizons. The 15/30/60-minute pitch examples imply 3,400 / 6,800 / 13,600 ED bed-hours and $1.19M / $2.38M / $4.76M in annual capacity value if these are **mean** reductions at 13,600 admissions. |

**Inpatient reconciliation.** The plan's hypothetical mix yields `(13,600 × 4.8 + 4,400 × 3.0 + 5,400 × 4.5) / 365 = 281.59` occupied beds, or 88.0%. At 281.6 occupied beds and those length-of-stay assumptions the implied direct admission count is about 5,401 per year. The planned arithmetic is consistent. The brief supplies neither inpatient length of stay nor non-ED admissions. In the build, compare integrated census bed-days with the independent sum of stay intervals clipped to the same half-open year window. Include warm-up stays that cross Jan 1 and stays still admitted at Dec 31. Then compare steady-state admissions/day times **mean** stay by unit and source, disclosing boundary effects and queues. Using the same full-stay arithmetic for both sides alone cannot validate the census.

**Mechanism checks for the next revision.** Counts and payer shares can be explicit generator parameters. Boarding, crowding, wait and walkout outcomes should come from recorded events and independently reproduce when recalculated from the raw timestamps. Perturb demand, room processing, and patience with fixed draws to check that outputs respond. Inspect for post-generation overwrites, outcome clipping, forced payer-level medians or forced walkout counts. The plan explicitly proposes tuning latent admission noise toward about 0.85 AUC, which makes that synthetic AUC a generator assumption. Discharge barrier prevalence, unit size allocations, discharge timing and inpatient length of stay are also assumptions. No implementation was available to establish if any outcome is hard-coded.

## Model, fairness and impact verification

| Test area | Evidence required |
| --- | --- |
| Information available at scoring | Admission inputs must be available by end of triage and discharge inputs by 07:00 rounds. As-of joins must use the note and diagnosis available at that time. Changing a later note, disposition, or discharge timestamp must leave earlier features and scores unchanged for an otherwise identical observed history. Use positive allowlists per model. Unit can be an observed discharge feature, while eventual admitting unit cannot enter the triage model. |
| Temporal split | Select the algorithm on September predictions from a model fit before September, then refit before October using only outcomes observable by each cutoff. Separate scoring and outcome timestamps. For the 24-hour discharge label, require the full outcome window or other confirmed outcome by the cutoff. Keep October to December labels for evaluation. State how late-December outcomes mature and how repeat snapshots from the same stay affect uncertainty. |
| Metrics | Recompute ROC AUC, average precision, mean squared probability error (Brier), reliability bins with counts, and confusion counts from saved holdout labels and probabilities. For admission, report time from first eligible flag to decision and from approved hourly batch to decision, separately. For discharge, report time from first eligible flag and from staff action to actual departure. Count late and missed signals explicitly and state the true-positive denominator for lead summaries. |
| Fairness | At the specified threshold, false negative rate is false negatives divided by all actual positives. Flag rate is flags divided by eligible predictions. Calibration difference is mean predicted risk minus observed event rate in the same eligible labelled cohort. Undefined AUC and rates for groups without the needed classes or denominator should read “insufficient data.” Show support by payer and use stay- or day-level resampling when repeated rows share outcomes. |
| Impact | Compare identical cohorts with zero adoption against baseline, and test each intervention on its own. Use paired random draws by person, separate seeds for variation, and report counts, group differences and signed effects. A simple min-to-max spread across three seeds describes simulation variability. It does not establish a confidence interval. Track false-positive reservations, competing admission delays and distinct patients affected. |
| Defaults and sensitivity | Fifty percent adoption and one hour are planning assumptions. A 70% threshold is a candidate from a retrospective simulation in a preprint. Hopkins observed shorter stays on two of four units, which supports testing a rounds workflow. The two-hour recoverable delay is a scenario assumption. A multicenter study found no significant association of morning discharge volume with hospital length of stay or ED length of stay. Keep the sensitivity comparison on matching capacity units, and use zero and adverse cases. Higher adoption or a lower alert threshold can worsen results when reservations consume supply. [Schiff et al. preprint](https://assets-eu.researchsquare.com/files/rs-8563126/v1/7454df18b3d3665a3e387e35.pdf), [Levin et al. rounds study](https://innovations.bmj.com/content/7/2/414), [Kirubarajan et al. study](https://pubmed.ncbi.nlm.nih.gov/34129483/). |
| Capacity vs financial return | Label `net ED boarding bed-hours freed × $350` as estimated freed capacity. If showing a financial return, use independently justified cash savings and incremental costs over the same period. Show reserved inpatient time and possible walkout recapture separately. A patient who stays cannot automatically be valued as $1,500 of incremental revenue. |

## One-minute page checks

| Planned page | What the viewer should understand first | Specific review check for the build |
| --- | --- | --- |
| Overview | Why boarded patients hold ED rooms and where staff can act | Define boarding and “left before being seen.” Mark case numbers as case baseline and distinguish simulation results from them. |
| Live Bed Board | How many ED rooms are held and which inpatient beds can receive a patient now | Label clean, needs cleaning, reserved and occupied in text. Display the replay time. Lead with the count of ED rooms held. |
| ED Admission Flags | Who looks likely to need an inpatient bed, why, and what staff can do | Expand the urgency score, translate `P(admit)`, explain the threshold, and show a draft request change after an approval or override. |
| Discharge Readiness | Which specific task the rounds team can start today and who owns it | Quote the note evidence, name the person responsible and distinguish forecast likelihood from checkable medical readiness. Label the rule-based reader directly. |
| Bed Forecast | Which unit may have a usable bed by a stated time | Say what the range represents and show actual forecast error. Use a finding title driven by the selected time and unit. |
| Impact Simulator | Whether the scenario frees room time, who benefits and whether there is a trade-off | Lead with a signed change and units, show baseline beside scenario, and place the formula and default assumptions close to the dollar estimate. |
| Fairness and Oversight | Whether any group waits longer or misses more alerts, and what would trigger review | Spell out false negative rate in context. Show denominators, outcome vs model measures, and text warning states. |
| Data and Methods | Which inputs come from the brief, and whether the simulation met them | Show target, simulated value, tolerance and evidence path. Label model accuracy as synthetic and keep detailed pipeline notes behind progressive disclosure. |

**Performance and accessibility acceptance.** All eight pages need actual browser smoke and keyboard tests, including one approval and one override. Time each page against the requested three-second target using ready-to-interact cold and warm loads, and record scenario execution time separately. Test warning and chart contrast on the rendered background, verify labels and focus states, and use text or markers alongside color. Inspect startup and page reruns for artifact reloads, excessive chart payloads and runtime network calls. No test coverage or performance result can be inferred at this revision.

## Rubric coverage

Workbook `Sheet1` rows 2 to 16 total **37 points**. Rows 2 to 14 cover the four strategy sections (31 points). The demo row is **1 or 3 points** for the performance levels shown in the rubric, with no 2-point level. There is no functional MVP evidence at the audited revision. The middle column records plan coverage. Each remaining gap describes evidence the team needs to earn full credit.

| Row | Criterion and points | Available plan evidence | Gap |
| --- | --- | --- | --- |
| 2 | Focus area and rationale (2) | Overview frames boarding with the case wait, walkout and bed baselines. | Show who is affected and how held rooms propagate to waits. Avoid attributing the full delay to hospital-wide bed timing. |
| 3 | Automation vs human oversight (2) | Bed manager approval and attending discharge authority are planned. | Show the named role accountable for wrong output, a consequential override and the action log. |
| 4 | Tool selection and justification (2) | Python, Streamlit and scikit-learn support an offline prototype. | Explain the feasible operating stack for a small ED team, the costs to maintain it and why the tools fit. |
| 5 | Technical design (3) | Synthetic data, models and staff views make the prototype flow clear on paper. | Show data-to-staff and EHR handoffs for deployment, hosting and privacy controls, reliability, scaling, costs and maintenance. |
| 6 | Measurable goals (3) | Pitch proposes 3.5→2.5 h boarding, 55→45 min provider wait, 4%→3% walkouts and a 16→8 min uninsured wait gap. | Choose and label Month 18 targets, name the measurement cadence and owners, and state actions if targets are missed. |
| 7 | Phase 1 pilot (3) | Medicine A scope and supervision are proposed. | Month 1 to 6 milestone dates, operational and equity gates, clinician and patient adoption, plus patient experience and safety measures. |
| 8 | Phase 2 scale (2) | Full-hospital scope is planned as a scenario. | Month 7 to 18 milestones, criteria for using pilot results, training and ownership, maintenance funding and cost-to-serve. |
| 9 | Financial assumptions (3) | Case drivers and rough 18-month pitch range are available. | Phase-level cost estimates including licensing, integration, monitoring, clinician time and security review. Reconcile both budget time bases and quantify a lower-cost option. |
| 10 | Value versus traditional approach (2) | Planned room-hours calculation and sensitivity against 15/30/60-minute examples. | Quantify an overtime, staffing or contractor comparator from case rates, separate capacity from cash, and show uncertainty and calculation inputs. |
| 11 | KPIs and ROI (2) | Planned boarding, wait time, walkouts and payer gaps. | Demonstrate the baseline-to-scenario gap and its denominator, choose measurable targets, and give a time-aligned ROI definition with honest limits. |
| 12 | Risk identification (2) | Potential bias, false positives and model drift are planned for discussion. | Give concrete risks and mitigations for privacy, over-reliance and loss of human connection, alongside bias. |
| 13 | Data security (2) | Offline synthetic demo avoids real patient data exposure. | Explain protection and a specific compromised hospital or vendor response for deployment, with owners and manual fallback. |
| 14 | Oversight and contingency plans (3) | Planned fairness checks, override logs, pause triggers and phone/whiteboard fallback. | Show a pre-launch check, how an override changes the workflow, incident and pause ownership, monitoring and retirement criteria, and an actual fallback walkthrough. |
| 15 | Working MVP demo (3) | Proposed Option B dashboard with prediction, reasoning, override and payer fairness. | Run the app with synthetic inputs and show a complete staff action linked to the forecast. A static or planned demo cannot establish functionality or polish. |
| 16 | Overall presentation (3) | Pitch has a proposed patient-to-bed story and a two-minute demo segment. | Verify video timing within 5 to 8 minutes, the required slide sequence, engagement, clear transitions and at least three checked sources. |
| 17 | Total (37) | Spreadsheet sum of rows 2 to 16. | Score after watching the complete submission and using the working MVP. |

Prioritize the timing and accounting defects before producing pitch screenshots. Once the app is runnable, the shortest useful demo proof is a real prediction that produces a staff-approved action, a visible forecast consequence, an override and a signed payer-gap check.

## Scaffold follow-up

At `dbc631b` the scaffold added `AGENTS.md`, `halvian/config.py` and eight configuration tests. The published case targets for volume, payer mix, admission rate, provider waits, walkouts, boarding, occupancy and resource totals match the brief. The simulated year and calibrator are still needed to test whether the generator meets them.

The scaffold used “lead time” as an impact input and said its default was below a measured value before an evaluation existed. The refined configuration uses staff response delay and preserves the scaffold's one-hour recoverable discharge task assumption. The scaffold also gave Medicaid/CHIP and uninsured inpatients higher default odds of a barrier and a different barrier mix. Direct payer tilt is now neutral by default, consistent with the planned age and mobility mechanism. The settings remain available for explicit sensitivity runs.

The light theme's primary blue and normal text have contrast of 5.49:1 and 15.11:1 on white. The proposed orange and vermillion warning fills are 2.25:1 and 3.87:1 against white. Use dark text and visible state labels rather than warning-colored small text on white. Confirm contrast on the rendered pages when available.

## Preliminary data run during the build

I copied the uncommitted data engine and its matching configuration into a disposable directory and ran the default synthetic year. This was a point-in-time check while calibration was underway. The results can change as the builder tunes the model. `scripts/validate.py` was still absent.

| Measure | Case target | Preliminary result |
| --- | --- | --- |
| Annual ED visits | About 85,000 | 84,808 |
| Payer mix | 35% Medicaid/CHIP, 22% Medicare, 33% commercial, 8% uninsured | 35.16%, 22.04%, 32.97%, 7.81%, plus 2.02% Other |
| Realized admission rate | 16% | 14.36% |
| Median arrival to provider | 55 min overall, 48 commercial, 58 Medicaid, 64 uninsured | 43.3, 43.9, 45.5 and 45.3 min |
| Leave before being seen | 4.0% overall, 3.0% commercial, 4.6% Medicaid, 5.8% uninsured | 13.27%, 13.11%, 14.79% and 13.75% |
| Median boarding | 3.5 h | 1.55 h |
| Time-weighted inpatient occupancy | About 88% | 85.26%, or 272.83 occupied and 47.17 unoccupied on average |
| Monday and winter | Monday highest and about 20% winter uplift | Monday highest at 257.5 arrivals/day, winter uplift 19.86% |
| Little's law | Mean occupancy near admissions/day × mean LOS | 272.83 occupied from clipped stay intervals vs 273.02 from full lengths of stay for admissions inside the year |

Three high-severity findings apply to that snapshot.

| File | Problem | Why it matters | Fix |
| --- | --- | --- | --- |
| `halvian/data/cohort.py`, `build_cohort` | ED rates are normalized over whichever simulation dates fall inside the case year. The Aug 1 to Jan 1 request produced 84,846 visits vs 35,212 over the same dates in the full-year cohort. A one-week request produced 85,080 vs 1,511. | Every partial window is exposed to nearly a full year of ED demand while direct and elective rates continue at their normal scale. This can invalidate quarter impacts and short-run tests. | Normalize the rate over the entire case calendar, then sample only the requested exposure. The one-line change in the disposable copy produced 35,297 and 1,594 visits for the same partial windows. Recheck this on the committed generator. |
| `halvian/data/simulate.py`, hourly batch | The usual batch path reads the pre-drawn remaining workup time to determine when to act. | The engine has a future event time the staff at that batch cannot observe, confirming the plan's first finding in code. | Use observed triage time, current status, threshold and staff response delay. Change future workup duration in a paired test and check that earlier batch decisions remain identical while eligibility is unchanged. |
| `halvian/data/simulate.py`, inpatient bed arrival | A baseline-derived discharge flag can accelerate the simulated departure when the patient first arrives on the inpatient unit. The flag carries no achieved rounds timestamp. The start gate checks the later baseline departure time. | Work can appear to start before it was flagged, including for a stay admitted before the tool was switched on. The same mechanism can undermine equivalent warm-up between arms. | Schedule a rounds event from the scenario clock. Check the current stay and observed note, constrain the effect to actionable work, and test equivalent pre-intervention timelines. |

## Committed data follow-up

At `44a60b5`, `python scripts/validate.py` passed **29 of 29** checks.
The committed year has 85,082 ED visits, 13,609 admissions, a 55.2-minute
median provider wait, a 4.00% walkout rate and 3.52 hours of median boarding.
Integrating stay intervals independently gives 281.77 occupied beds (88.05%),
close to the validator's steady-state flow estimate of 282.0 beds. November 1
to 8 has 1,555 arrivals in the saved year and 1,552 when generated on its own.
This confirms the partial-window defect is fixed.

Volume and payer shares set Poisson rates. The five fitted inputs for clinical
flow change admission propensity, patience, nurse assessment time, inpatient bed
processing and length of stay. Wait, walkout and boarding outputs are computed
from events. Baseline payer gaps depend on adjustable arrival, urgency and
patience inputs. Direct payer-related barrier settings are enabled under the
team's approved assumption, and their effect should be checked by sensitivity
runs. The earlier scaffold note reflects the settings before that approval
was reconciled on main.

The merged simulator schedules admission requests by observed triage plus
staff response delay. Two issues remain. First, the discharge effect is still
scheduled at inpatient arrival using a baseline rounds flag. Second, the note
text, mobility and lab trend in `halvian/data/generate.py::inpatient_days` use
a progress ratio with future medical readiness in its denominator, and some
note timing depends on future barrier resolution. Changing a future timestamp
can alter features at the same nominal prediction time. Move the logic to
scenario rounds and build observed features forward in time before interpreting
the model and impact metrics as evidence of the proposed workflow.

The rule-based reader found 12,435 of 13,353 labelled barriers in 107,215
synthetic notes, with 139 false positives. Pooled precision was 98.9%,
recall was 93.1%, and F1 was 95.9%. The test measures extraction from the
repo's note templates and includes notes without active barriers.

## Model phase follow-up

At `e57950f`, I recomputed held-out logistic AUC and Brier scores from the
prediction files and the saved labels. Admission AUC = 0.8567, Brier = 0.1018
on 20,686 labelled visits. Discharge AUC = 0.8873, Brier = 0.1080 on 27,279
rounds snapshots. Both reproduced the model report. The deployed feature
lists exclude payer. The selection split uses outcomes known before its
September and October cutoffs. The note flags come from the rule reader's
findings. The data-generator concern about future-derived recovery proxies
still applies, even though rewrites of raw labels do not change saved scores.

| Severity | File | Problem | Why it matters | Fix |
| --- | --- | --- | --- | --- |
| High, correctness | `halvian/models/forecast.py::fit_tables` | The cleaning lag and ED request-delay distributions use the full data passed to the function, including 3,492 ED admissions first scored in the test quarter. Demand windows can also reach across the training cutoff. | The reported October to December error and interval coverage do not give an independent check of the fitted forecast. | Limit fitting inputs to matured training events and use only full training exposure for each rate window. Perturb test outcomes and verify fitted tables stay unchanged. |
| Medium, correctness | `halvian/models/discharge.py::first_flag_lead`, `scripts/train_models.py` | The earliest flagged round is chosen regardless of its 24-hour label. Of 3,600 flagged stays, 1,191 first flagged more than 24 hours before leaving and 18 left after December. | The current label says stays discharged in the test months. The cohort instead includes stays with flagged rounds in the test months, and the number does not describe lead time for correct next-day flags. | Keep the all-flags time as a named diagnostic. For true positives use the first flagged round with a positive 24-hour label, and show eligible counts and missed positives. |

The admission batch flags reached 730 of 3,492 observed test admissions
(20.9%) before the clinical decision. The median 1.92 hours applies to those
730 visits. Show volume and lead together. In the current forecast backtest,
coverage at 4, 8 and 24 hours is 80.2%, 77.1% and 73.3%, respectively.
Recheck those rates after removing the holdout contribution from fitting.
