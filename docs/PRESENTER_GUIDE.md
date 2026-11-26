# Halvian Bed Flow presenter guide

The point values are rubric maxima. The rubric also awards 3 points for Overall Presentation across the video.

Simulated results are never single numbers: say the break-even first (about 6 minutes saved per admission), then the ranges across three synthetic years, rounded outward. Say the caveat once: "This is a model estimate from a synthetic Halvian calibrated to the case brief. It shows which levers matter and how large the payoff could be under stated assumptions. It is not evidence from a real hospital." The brief's own numbers (3.5 h, 55 min, 4%, $350 per bed-hour) are exact. Goals and ROI use the Cautious scenario (today's defaults). Read individual synthetic patient estimates from the screen during the demo. [Presentation numbers](NUMBERS.md) · [Strategy numbers for the slides](STRATEGY.md) (goals, milestones, gates, budget by phase, ROI, risk and response plans, all generated from the saved results)

## AI Tool Architecture

**Rubric.** Focus Area & Rationale (2 points), Automation vs Human Oversight (2), Tool Selection & Justification (2), and Technical Design (3).

**Show.** Start with the [problem-to-feature map](../exports/problem_to_feature.png) and follow with the [architecture](../exports/architecture.png). Name the local Streamlit dashboard, admission logistic regression, discharge gradient boosting, the AI note reader (Llama 3.2 3B running on the laptop through Ollama, with a rule-based fallback) and statistical bed forecast. For a hospital pilot, describe the proposed read-only feeds from the EHR and registration system to an approved hospital-hosted service.

**Numbers to say.** The case hospital has 320 beds, usually 88.0% occupied, and about 85,000 ED visits a year. The median wait to see a provider is 55 min, compared to 30 min to 40 min nationally. Median boarding is 3.5 h, compared to 2.0 h to 2.5 h nationally. The main synthetic year passed 29 of 29 calibration checks. [Presentation numbers](NUMBERS.md)

**Say.** “Admitted patients hold ED rooms while they wait, so we give bed managers and unit teams an earlier chance to prepare while clinicians retain control of admission and discharge.”

## Roadmap and Milestones

**Rubric.** Measurable Goals (3 points), Phase 1 Pilot (3), and Phase 2 Scale (2).

**Show.** The [roadmap](../exports/roadmap.png) (milestones and the Month 6 go or no-go), then the goals table and the pilot gates from [STRATEGY.md](STRATEGY.md) section 2. Keep the [sensitivity plot](../exports/sensitivity.png) for "what if staff do not use it".

**Numbers to say.** Month 18 goals tied to the brief: median boarding 3.5 h to 3.4 h, walkouts 4.0% to 3.6%, the Medicaid/CHIP wait gap 10 to 9 min and the Uninsured walkout gap 2.8 to 2.6 points, plus a use goal (half of flags acted on, overrides between 2% and 40% with reasons). Each target banks 75% of what the simulation shows, rounded to the brief's precision. Of 9 gates to Phase 2, 5 are already met on the synthetic data and 4 need the pilot's own data (staff use, override reasons, usefulness, safety); a gate the data does not meet would be listed as not met. The Medicine A pilot alone saves 0 to 5 minutes per admission, too little to judge on outcomes, so the pilot is judged on process measures. For Phase 2, the pilot decides the alert threshold: at 60% the simulation saves 15 to 25 minutes per admission and narrows all four Medicaid/CHIP and Uninsured gaps, at 66.1% flag precision. [Strategy numbers](STRATEGY.md)

**Say.** "We start supervised on one unit, prove it on Halvian's own data in silent mode, and only scale when the gates are met, including an equity gate."

## Budget and ROI

**Rubric.** Financial Assumptions (3 points), Value vs Traditional Approach (2), and KPIs & ROI (2).

**Show.** The [budget by phase](../exports/budget_by_phase.png), then the [scenarios against the break-even](../exports/ranges_vs_break_even.png), the [staffing options against the tool](../exports/value_vs_traditional.png) and the [downstream chain](../exports/downstream_chain.png). The line-by-line budget, the alternatives and the KPI table are in [STRATEGY.md](STRATEGY.md) section 3. Explain the break-even formula once: freed capacity is minutes saved x 13,600 admissions a year at the brief's $350 per room-hour. Keep the [sensitivity plot](../exports/sensitivity.png) available for questions.

**Numbers to say.** The case cap is $500,000 a year and $750,000 for the rollout. Break-even: $500,000 / ($350 x 13,600 admissions) = about 6 minutes saved per admission. Cautious (today's defaults): 10 to 20 minutes, $0.8M to $1.6M of freed capacity a year. Expected (plus the bed board): 20 to 30 minutes, $1.6M to $2.4M. Full rollout (75% of flags acted on, 60% threshold, discharges 2 hours earlier, bed board): 35 to 50 minutes, $2.8M to $4.0M. All capacity, not cash. Each part alone: admission flags 10 to 15 minutes, the bed board 10 to 15, discharge readiness -5 to 10 (no reliable effect on its own). The trade-off: inpatient reservations hold beds idle 700 to 1,000 hours a quarter in Cautious. [Presentation numbers](NUMBERS.md)

**Budget to say.** $611K over 18 months (pilot $315K, scale $296K), inside the $750K cap, then $210K a year: about $370K to $430K a year on our $550K to $650K ballpark. Hidden costs are counted: clinician training time at the brief's rates paid as overtime, security review and vendor fees. Licensing is $0 (open-source tools, an open-weight local model). Traditional staffing, cost only at the brief's rates: a bed coordinator around the clock $310K a year, an extra day-shift case manager $190K, surge-day nurse overtime $120K; we do not estimate how much boarding each would cut. Doing all the same work by hand is 7.2 FTE, $975K a year hired. Cautious value a year: $0.8M to $1.6M of freed capacity (not cash) and $0.2M to $0.4M of cash (recovered walkout visits and overtime). ROI a year: 200% to 700% on freed capacity, 10% to 80% on cash alone; payback month 11 to 13 on capacity, month 38 or later on cash. Least certain: the bed board's 25% cut (no study behind it), staff adoption, the vendor interface fee, and how many walkouts are revenue Halvian keeps.

**Say.** "The tool pays for itself at about 6 minutes saved per admission. Even our cautious case, with today's settings and no credit for the bed board, saves 10 to 20. That is a model estimate on a synthetic hospital, so the pilot has to prove it. On cash alone it pays back slowly, and we say so; on the brief's own capacity measure it pays back within the first year."

## Risk Assessment and Mitigation

**Rubric.** Risk Identification (2 points), Data Security (2), and Oversight and Contingency Plans (3).

**Show.** Use the [payer gap chart](../exports/payer_gaps.png): no gap widens in any scenario. Point out that the Uninsured wait gap is the least stable one. The risk table, the five-step response plan if Halvian's or a vendor's systems are compromised, and the contingency plan are in [STRATEGY.md](STRATEGY.md) section 4. Use the [architecture](../exports/architecture.png) to show review and the decision log. Keep Fairness and Oversight available for the subgroup audit and pause rules.

**Numbers to say.** Payer gaps against Commercial: in the Expected scenario all four Medicaid/CHIP and Uninsured wait and walkout gaps narrow and none widens. In the Cautious scenario the Uninsured wait gap is flat, and year by year it widened in one of the three synthetic years in both Cautious and Expected, so it is the gap to watch. The admission policy missed 91.8% of eventual admissions for Uninsured patients and 79.1% overall. [Presentation numbers](NUMBERS.md)

**Bias test to say.** The flags miss 91.8% of Uninsured admissions against 79.1% overall, but matched on triage level and age the unexplained gap is 2.6 points: it comes from who arrives (younger, fewer at triage levels 1 and 2), not from the model treating similar patients differently. A missed flag means the usual process, never a lower priority. The pilot reruns the test on Halvian's own records, because triage levels can carry bias in real data.

**Say.** "The unstable Uninsured wait gap and higher missed-admission rate justify a pre-launch review, with named staff accountable for overrides and for pausing the tool when needed."

## Working MVP Demo

**Rubric.** MVP Demo (3 points). Recording polish also contributes to Overall Presentation.

**Show.** Follow [the demo script](DEMO_SCRIPT.md). Open **Overview** and select **Start the guided demo**. Read the flag reasons and select **Approve request**. Select **Next: discharge task**, point to the second patient's stay ID, select **Read this note**, show the wheelchair van evidence and the reader's source line, then select **Record transport as arranged** and read the before-and-after estimate. Select **Next: bed forecast** and show the small before-and-after change and range for the same unit. Finish with **Finish: see the decisions in the log**, then open **Fairness check** and point to the Uninsured admission finding. The simulated results are on the Overview strip and under **Results**, **Downstream impact**; the staff pages show none.

**Numbers to say.** From the Overview strip (or **Results**, **Downstream impact**), say the break-even, then the Expected range: 20 to 30 minutes of boarding saved per admission. Keep the precision, recall and lead time below for questions. In the walkthrough, read the patient estimates displayed on screen. [Presentation numbers](NUMBERS.md)

**Say.** “I’ll approve preparation for an ED admission, record a separate inpatient’s transport task, then check how that task changes the unit’s bed estimate.”

## Eight-minute recording plan

| Elapsed | Section | Cue |
| --- | --- | --- |
| 0:00 to 1:25 | AI Tool Architecture | Move from the blocked ED room to the roles that can act. |
| 1:25 to 2:45 | Roadmap and Milestones | Show pilot milestones, measures, scale criteria and ownership. |
| 2:45 to 4:35 | Budget and ROI | Show the budget, the break-even, the three ranges and the reservation trade-off. |
| 4:35 to 6:00 | Risk Assessment and Mitigation | Show gap verdicts, oversight and downtime response. |
| 6:00 to 6:20 | Working MVP Demo | Start from Overview and show the admission flag reason. |
| 6:20 to 7:05 | Working MVP Demo | Approve the request and record transport for the other patient on the unit. |
| 7:05 to 8:00 | Working MVP Demo | Check the forecast, then finish in the decision log and the fairness check. |

## Slide by slide

Fifteen slides in the brief's order. Each title states the finding; the visual and the numbers come from `exports/` and [STRATEGY.md](STRATEGY.md). Synthetic data and simulated results are estimates: say so once at the start of the results.

| # | Slide title (the finding) | Visual | Say (numbers) |
| --- | --- | --- | --- |
| 1 | Admitted patients wait 3.5 hours for a bed, and everyone behind them waits too | [problem_to_feature](../exports/problem_to_feature.png) | Boarding 3.5 h against 2 to 2.5 nationally; 55 min to a provider; 4% leave unseen, 5.8% of uninsured patients. We chose Patient Flow and Boarding because it is the cause upstream of the waits. |
| 2 | AI prepares the bed early; people make every decision | [architecture](../exports/architecture.png) | AI: admission flags, the rounds list, barriers read from notes, the bed forecast. Human: the bed manager approves the request, the attending owns discharge, the case manager works the barrier, the charge nurse confirms the forecast. Who is accountable when the AI is wrong: the table under When to pause in the app. |
| 3 | Real, low-cost tools that run inside Halvian | STRATEGY.md tools table | Read-only EHR feeds, two small explainable models, Llama 3.2 3B running locally (no patient text leaves), Streamlit on the intranet. Licensing $0. On wording the rules never saw, the rules found 6% of barriers and the AI reader 55%. |
| 4 | How information moves, where it runs, what keeps it safe | STRATEGY.md technical design | Triage to flag every 15 min, hourly bed requests, 07:00 rounds, hourly forecast; one hospital server plus a standby; phone-and-whiteboard fallback after 30 min of feed outage. |
| 5 | Four goals for Month 18, one of them equity | STRATEGY.md goals table | Boarding 3.5 to 3.4 h; walkouts 4.0% to 3.6%; Medicaid/CHIP wait gap 10 to 9 min and Uninsured walkout gap 2.8 to 2.6 pp; half of flags acted on, overrides 2% to 40% with reasons. Each target banks 75% of the simulated change, rounded. |
| 6 | A supervised pilot on one unit, then scale if the gates are met | [roadmap](../exports/roadmap.png) | Silent mode first, go-live on Medicine A in Month 4, go or no-go at Month 6 on 9 gates: 5 already met on synthetic data, 4 need the pilot's own data. Adoption plan: clinicians design it, overrides welcome, super-users on every shift. |
| 7 | Pilot results decide what changes before scaling | STRATEGY.md Phase 2 table, [sensitivity](../exports/sensitivity.png) | At a 60% alert threshold the simulation saves 15 to 25 minutes per admission and narrows all four Medicaid/CHIP and Uninsured gaps, at 66.1% precision. Ownership after Month 18: clinical informatics, $210K a year. |
| 8 | $611K over 18 months, inside the $750K budget | [budget_by_phase](../exports/budget_by_phase.png) | Pilot $315K, scale $296K, then $210K a year. Hidden costs counted: clinician training time at the brief's rates paid as overtime, security review, vendor fees. Lower-cost options named. |
| 9 | Staffing options cost less, with no estimate of effect | [value_vs_traditional](../exports/value_vs_traditional.png) | Bed coordinator around the clock $310K a year, extra day-shift case manager $190K, surge-day nurse overtime $120K (brief rates, cost only); the tool $370K to $430K a year over 18 months, then $210K. All the same work by hand: 7.2 FTE, $975K a year hired. |
| 10 | Every scenario clears the 6-minute break-even | [ranges_vs_break_even](../exports/ranges_vs_break_even.png), [downstream_chain](../exports/downstream_chain.png) | Break-even $500K / ($350 x 13,600) = 6 min. Cautious 10 to 20 min ($0.8M to $1.6M a year), Expected 20 to 30 ($1.6M to $2.4M), Full rollout 35 to 50 ($2.8M to $4.0M). Capacity, not cash; cash is $0.2M to $0.4M a year. Say the caveat. |
| 11 | KPIs and ROI, including an equity KPI | STRATEGY.md KPI table | ROI a year 200% to 700% on freed capacity, 10% to 80% on cash alone; payback month 11 to 13 on capacity, month 38 or later on cash; $40 to $100 per ED room-hour freed against the $350 value. |
| 12 | Four risks, each with a control you can see | STRATEGY.md risk table | Bias, privacy, over-reliance, loss of human connection. The bias test: Uninsured admissions are missed 91.8% of the time against 89.2% expected from triage level and age, so the gap is case mix, and the pilot retests it on real data. |
| 13 | If systems are compromised, care continues | STRATEGY.md response plan | Contain in the first hour (cut the feeds, downtime protocol), assess, notify under HIPAA, rebuild from clean images, review the vendor. |
| 14 | A small team keeps it accurate and fair | [payer_gaps](../exports/payer_gaps.png); When to pause in the app | Monthly checks, pause triggers, override band, AI-only findings marked for checking. Honest: no gap widens, but the Uninsured wait gap is flat in the Cautious case and widened in one of three synthetic years. |
| 15 | Demo: approve a bed, clear a barrier, see the forecast move | The app (guided demo) | Follow [the demo script](DEMO_SCRIPT.md); end in the decision log and the fairness check. |

## Eight likely judge questions

1. **Why tackle boarding?** The case median is 3.5 h. Each boarded patient keeps an ED room occupied. In the paired simulation the wait to see a provider falls by 2 to 5 minutes in the Cautious case and 5 to 10 in the Expected case.
2. **Who is accountable if the model is wrong?** The bed manager can override bed preparation, the case manager verifies the discharge task, and clinicians retain admission and discharge authority. The charge nurse uses the forecast to plan and confirms actual bed status.
3. **How many admissions does the dashboard catch and how early?** The deployed policy had 67.9% precision and 20.9% recall, with 11.7 alerts per day. Correct flags led the admit decision by a median 1.9 h. The admission model's test AUC was 0.857.
4. **How credible is the discharge or note result?** The discharge model's synthetic test AUC was 0.853. Its flags had 63.1% precision and 41.0% recall, with correct flags a median 6.8 h before departure. The AI note reader (Llama 3.2 3B, local) is checked on a sealed sample of 1,319 test notes: 99.3% precision and 93.7% recall on its own, and 99.3% precision with 96.8% recall together with the rules, which is what the app shows (the rules alone: 100.0% and 94.7%). On 304 notes in wording neither reader was written for, the rules found 6% of barriers and the AI reader 55% at 98% precision: that is why there is a language model at all. Say plainly that the rules do well on the templated notes because they were written for the same templates. The first version of the reader had 78% precision; its false alarms on clinical shorthand ("holding meds", "NPO") are now filtered because a finding must name an open discharge task. The rules read every note and feed the discharge model.
5. **Does the tool help the groups that wait the longest?** No payer gap widens in any scenario. In the Expected case all four Medicaid/CHIP and Uninsured gaps narrow; in the Cautious case the Uninsured wait gap is flat, and it widened in one of three synthetic years. The admission policy missed 91.8% of eventual Uninsured admissions. Payer is excluded from predictions and used for auditing.
6. **Why show ranges instead of one number?** The results come from a synthetic Halvian, not real patients, and they move from one synthetic year to the next. A single number would claim a precision we do not have, so we report the spread across three years rounded outward, and compare it with the 6-minute break-even. (The test quarter includes the winter surge, so its simulated levels run above the brief's annual baselines; that is why we report changes, not levels.)
7. **Does the capacity estimate translate into savings?** In the Cautious case it is $0.8M to $1.6M a year of freed capacity, not cash: minutes saved x 13,600 admissions at the brief's $350 per room-hour. The cash we can see is smaller, $0.2M to $0.4M a year from recovered walkout visits and overtime, so cash alone pays back in month 38 or later, while the capacity value pays back in month 11 to 13. The two are never added.
8. **How sensitive are the results to what staff do?** Very. With staff acting on 25% of flags the tool saves 5 to 15 minutes per admission (straddling the break-even); at 100% it saves 20 to 35. A 50% alert threshold gives 20 to 30. The bed board alone adds 10 to 15, and its 25% cut in bed turnover delays is our least certain assumption: no study we found backs it, which is why the Cautious case leaves it out. Each sweep changes one setting at a time.

## What the slides still need

Everything below now has generated content in [STRATEGY.md](STRATEGY.md); the slides need to present it.

| Rubric criterion | Where the content is | What the team still adds |
| --- | --- | --- |
| Technical Design and Tool Selection | [Architecture](../exports/architecture.png), STRATEGY.md budget lines (servers, feeds, local model) | The production picture in one slide: read-only EHR feeds into a hospital-hosted server, staff in the loop, nothing leaves the network. |
| Measurable Goals, Phase 1 Pilot, Phase 2 Scale | STRATEGY.md section 2, [roadmap](../exports/roadmap.png) | Pick the 3 or 4 goals to say aloud; the gates slide. |
| Financial Assumptions, Value vs Traditional, KPIs and ROI | STRATEGY.md section 3, [budget](../exports/budget_by_phase.png), [value](../exports/value_vs_traditional.png) | One budget slide, one value slide, one KPI and ROI slide. |
| Risk, Data Security, Oversight and Contingency | STRATEGY.md section 4 and the bias test in section 2 | The risk table and the response plan as two slides; show When to pause in the app. |
| Overall Presentation | This guide and [the demo script](DEMO_SCRIPT.md) | Record the full sequence and check the edit, audio and pacing. |

[Source figures](NUMBERS.md) · [Slide asset index](../exports/README.md)
