# Presentation numbers

Regenerate with `python scripts/export_numbers.py`. This table reads the saved simulation,
model, and calibration outputs and the case values in the app configuration.

Halvian's case baselines describe the fictional hospital and are exact. Simulated results
are never single numbers: each is the spread across three synthetic years (paired runs on
the same synthetic patients, Oct to Dec test quarter), widened outward to round numbers
(minutes to the nearest 5, dollars to $0.1M, waits to the nearest minute, walkouts to 0.1
points), introduced by the break-even point. Freed capacity is the minute range at the
brief's $350 per boarded ED room-hour and 13,600 admissions a year; it is capacity, not
cash. Payer gap verdicts compare the pooled gap against Commercial with the saved flat
tolerance. Goals and ROI use the Cautious scenario (today's defaults). `pp` means
percentage points.

Model estimate from a synthetic Halvian calibrated to the case brief. It shows which levers
matter and how large the payoff could be under stated assumptions. It is not evidence from
a real hospital.

| Number | Plain-English meaning | Rubric section | Source file and key |
| --- | --- | --- | --- |
| 85,000 | Annual ED visits in the brief | AI Tool Architecture | `halvian/config.py` · `ED_VISITS_PER_YEAR` |
| 16.0% | Share of ED visits resulting in an admission in the brief | AI Tool Architecture | `halvian/config.py` · `ADMISSION_RATE` |
| 13,600 | Annual ED admissions used to annualize capacity | Budget and ROI | `halvian/config.py` · `ED_ADMISSIONS_PER_YEAR` |
| 48 | ED treatment spaces in the brief, including fast-track and specialty rooms | AI Tool Architecture | `halvian/config.py` · `ED_TOTAL_SPACES` |
| 320 | Inpatient beds in the brief | AI Tool Architecture | `halvian/config.py` · `INPATIENT_BEDS` |
| 24 | ICU beds included in the inpatient bed count | AI Tool Architecture | `halvian/config.py` · `ICU_BEDS` |
| 88.0% | Typical inpatient occupancy in the brief | AI Tool Architecture | `halvian/config.py` · `TARGET_OCCUPANCY` |
| 40 | Typical open inpatient beds in the brief | AI Tool Architecture | `halvian/config.py` · `TYPICAL_OPEN_BEDS` |
| 20.0% | Additional visit volume in winter in the brief | AI Tool Architecture | `halvian/config.py` · `WINTER_UPLIFT` |
| 3.5 h | Case median boarding after the admit decision | AI Tool Architecture | `halvian/config.py` · `MEDIAN_BOARDING_H` |
| 55 min | Case median arrival-to-provider wait | AI Tool Architecture | `halvian/config.py` · `MEDIAN_DOOR_TO_PROVIDER_MIN` |
| 4.0% | Case share leaving the ED before seeing a provider | AI Tool Architecture | `halvian/config.py` · `LWBS_RATE` |
| 40.0% | Case follow-up visit completion, outside this prototype's scope | AI Tool Architecture | `halvian/config.py` · `FOLLOW_UP_COMPLETION` |
| 2.0 h to 2.5 h | National benchmark in the brief for median boarding | AI Tool Architecture | `halvian/config.py` · `NATIONAL['boarding_h']` |
| 30 min to 40 min | National benchmark in the brief for median arrival-to-provider wait | AI Tool Architecture | `halvian/config.py` · `NATIONAL['door_to_provider_min']` |
| 2.0% to 3.0% | National benchmark in the brief for share leaving before seeing a provider | AI Tool Architecture | `halvian/config.py` · `NATIONAL['lwbs']` |
| 40.0% to 50.0% | National benchmark in the brief for follow-up completion | AI Tool Architecture | `halvian/config.py` · `NATIONAL['follow_up']` |
| 35.0% | Case ED payer mix for Medicaid/CHIP | AI Tool Architecture | `halvian/config.py` · `PAYER_MIX_BRIEF['Medicaid/CHIP']` |
| 22.0% | Case ED payer mix for Medicare | AI Tool Architecture | `halvian/config.py` · `PAYER_MIX_BRIEF['Medicare']` |
| 33.0% | Case ED payer mix for Commercial | AI Tool Architecture | `halvian/config.py` · `PAYER_MIX_BRIEF['Commercial']` |
| 8.0% | Case ED payer mix for Uninsured | AI Tool Architecture | `halvian/config.py` · `PAYER_MIX_BRIEF['Uninsured']` |
| 48 min | Case median arrival-to-provider wait for Commercial | Risk Assessment and Mitigation | `halvian/config.py` · `DOOR_TO_PROVIDER_BY_PAYER_MIN['Commercial']` |
| 58 min | Case median arrival-to-provider wait for Medicaid/CHIP | Risk Assessment and Mitigation | `halvian/config.py` · `DOOR_TO_PROVIDER_BY_PAYER_MIN['Medicaid/CHIP']` |
| 64 min | Case median arrival-to-provider wait for Uninsured | Risk Assessment and Mitigation | `halvian/config.py` · `DOOR_TO_PROVIDER_BY_PAYER_MIN['Uninsured']` |
| 3.0% | Case share leaving before seeing a provider for Commercial | Risk Assessment and Mitigation | `halvian/config.py` · `LWBS_BY_PAYER['Commercial']` |
| 4.6% | Case share leaving before seeing a provider for Medicaid/CHIP | Risk Assessment and Mitigation | `halvian/config.py` · `LWBS_BY_PAYER['Medicaid/CHIP']` |
| 5.8% | Case share leaving before seeing a provider for Uninsured | Risk Assessment and Mitigation | `halvian/config.py` · `LWBS_BY_PAYER['Uninsured']` |
| $500,000 | Annual innovation budget cap in the brief | Budget and ROI | `halvian/config.py` · `ANNUAL_BUDGET` |
| $750,000 | Total innovation budget cap for the case rollout | Budget and ROI | `halvian/config.py` · `BUDGET_18_MONTHS` |
| $350 | Case capacity value of a boarded ED room-hour | Budget and ROI | `halvian/config.py` · `BOARDING_COST_PER_BED_HOUR` |
| $65 | Case hourly cost of an ED nurse | Budget and ROI | `halvian/config.py` · `COST_NURSE_PER_H` |
| $200 | Case hourly cost of an ED physician | Budget and ROI | `halvian/config.py` · `COST_PHYSICIAN_PER_H` |
| $100 | Case hourly cost of an advanced practice provider | Budget and ROI | `halvian/config.py` · `COST_APP_PER_H` |
| $35 | Case hourly cost of a registration or administrative worker | Budget and ROI | `halvian/config.py` · `COST_ADMIN_PER_H` |
| $1,500 | Case average net revenue per ED visit | Budget and ROI | `halvian/config.py` · `NET_REVENUE_PER_VISIT` |
| 1.5× | Case overtime multiplier | Budget and ROI | `halvian/config.py` · `OVERTIME_MULTIPLIER` |
| 29 of 29 | Calibration checks passed in the main synthetic year | AI Tool Architecture | `data/validation.json` · `passed, total` |
| 25 of 29 | Checks passed in replication with seed 20261125 | AI Tool Architecture | `data/validation.json` · `replication_years[0].passed, .total, .seed` |
| 29 of 29 | Checks passed in replication with seed 20261126 | AI Tool Architecture | `data/validation.json` · `replication_years[1].passed, .total, .seed` |
| Oct 1 to Dec 31, 2025 (test quarter) | Comparison window for each paired run | Budget and ROI | `models/scenarios.json` · `window` |
| 3 | Synthetic runs in the paired scenario comparison | Budget and ROI | `models/scenarios.json` · `seeds (entry count)` |
| 6 min | Break-even: minutes saved per admission at which freed capacity ($350 x 13,600 admissions) equals the $500,000 yearly budget | Budget and ROI | `models/impact_ranges.json` · `break_even.minutes_per_admission` |
| 10 min to 20 min | Cautious scenario: minutes of boarding saved per admission | Budget and ROI | `models/impact_ranges.json` · `scenarios[0].minutes_saved_per_admission` |
| $0.8M to $1.6M | Cautious scenario: freed capacity a year, not cash | Budget and ROI | `models/impact_ranges.json` · `scenarios[0].freed_capacity_per_year_usd_m` |
| -5 min to -2 min | Cautious scenario: change in median wait to see a provider, simulated winter quarter | Budget and ROI | `models/impact_ranges.json` · `scenarios[0].provider_wait_change_min` |
| -0.9 pp to -0.4 pp | Cautious scenario: change in the share leaving before being seen, simulated winter quarter | Budget and ROI | `models/impact_ranges.json` · `scenarios[0].walkout_change_pts` |
| 20 min to 30 min | Expected scenario: minutes of boarding saved per admission | Budget and ROI | `models/impact_ranges.json` · `scenarios[1].minutes_saved_per_admission` |
| $1.6M to $2.4M | Expected scenario: freed capacity a year, not cash | Budget and ROI | `models/impact_ranges.json` · `scenarios[1].freed_capacity_per_year_usd_m` |
| -10 min to -5 min | Expected scenario: change in median wait to see a provider, simulated winter quarter | Budget and ROI | `models/impact_ranges.json` · `scenarios[1].provider_wait_change_min` |
| -1.0 pp to -0.6 pp | Expected scenario: change in the share leaving before being seen, simulated winter quarter | Budget and ROI | `models/impact_ranges.json` · `scenarios[1].walkout_change_pts` |
| 35 min to 50 min | Full rollout scenario: minutes of boarding saved per admission | Budget and ROI | `models/impact_ranges.json` · `scenarios[2].minutes_saved_per_admission` |
| $2.8M to $4.0M | Full rollout scenario: freed capacity a year, not cash | Budget and ROI | `models/impact_ranges.json` · `scenarios[2].freed_capacity_per_year_usd_m` |
| -17 min to -8 min | Full rollout scenario: change in median wait to see a provider, simulated winter quarter | Budget and ROI | `models/impact_ranges.json` · `scenarios[2].provider_wait_change_min` |
| -1.6 pp to -0.8 pp | Full rollout scenario: change in the share leaving before being seen, simulated winter quarter | Budget and ROI | `models/impact_ranges.json` · `scenarios[2].walkout_change_pts` |
| 10 min to 15 min | Admission flags alone (Cautious settings): minutes saved per admission | Budget and ROI | `models/impact_ranges.json` · `parts[0].minutes_saved_per_admission` |
| -5 min to 10 min | Discharge readiness alone (Cautious settings): minutes saved per admission | Budget and ROI | `models/impact_ranges.json` · `parts[1].minutes_saved_per_admission` |
| 10 min to 15 min | Bed board alone (Cautious settings): minutes saved per admission | Budget and ROI | `models/impact_ranges.json` · `parts[2].minutes_saved_per_admission` |
| Narrowed | Payer gap in the Expected scenario: Medicaid/CHIP vs Commercial, wait to see a provider | Risk Assessment and Mitigation | `models/impact_ranges.json` · `equity[0].verdict` |
| Narrowed | Payer gap in the Expected scenario: Medicaid/CHIP vs Commercial, leaving before being seen | Risk Assessment and Mitigation | `models/impact_ranges.json` · `equity[1].verdict` |
| Narrowed | Payer gap in the Expected scenario: Medicare vs Commercial, wait to see a provider | Risk Assessment and Mitigation | `models/impact_ranges.json` · `equity[2].verdict` |
| Flat | Payer gap in the Expected scenario: Medicare vs Commercial, leaving before being seen | Risk Assessment and Mitigation | `models/impact_ranges.json` · `equity[3].verdict` |
| Narrowed | Payer gap in the Expected scenario: Uninsured vs Commercial, wait to see a provider | Risk Assessment and Mitigation | `models/impact_ranges.json` · `equity[4].verdict` |
| Narrowed | Payer gap in the Expected scenario: Uninsured vs Commercial, leaving before being seen | Risk Assessment and Mitigation | `models/impact_ranges.json` · `equity[5].verdict` |
| Flat | Payer gap in the Expected scenario: Other (VA, workers' comp, auto) vs Commercial, wait to see a provider | Risk Assessment and Mitigation | `models/impact_ranges.json` · `equity[6].verdict` |
| Flat | Payer gap in the Expected scenario: Other (VA, workers' comp, auto) vs Commercial, leaving before being seen | Risk Assessment and Mitigation | `models/impact_ranges.json` · `equity[7].verdict` |
| $310,000 | Traditional option, cost a year: Bed coordinator around the clock | Budget and ROI | `models/impact_ranges.json` · `staffing_alternative[0].annual_cost_usd` |
| $190,000 | Traditional option, cost a year: Extra day-shift case manager | Budget and ROI | `models/impact_ranges.json` · `staffing_alternative[1].annual_cost_usd` |
| $120,000 | Traditional option, cost a year: Surge-day nurse overtime | Budget and ROI | `models/impact_ranges.json` · `staffing_alternative[2].annual_cost_usd` |
| $370,000 to $430,000 | Tool cost a year (our $550K to $650K 18-month ballpark, per year) | Budget and ROI | `models/impact_ranges.json` · `tool_cost.per_year_usd` |
| 700 to 1,000 | Trade-off: inpatient bed-hours held idle by reservations, simulated winter quarter (Cautious) | Budget and ROI | `models/scenarios.json` · `results.default.summary.idle_reserved_bed_hours.{min, max}` |
| OK | Equity guardrail (Cautious), Uninsured vs Commercial Door-to-provider | Risk Assessment and Mitigation | `models/scenarios.json` · `results.default.guardrail[0].Status` |
| OK | Equity guardrail (Cautious), Uninsured vs Commercial LWBS | Risk Assessment and Mitigation | `models/scenarios.json` · `results.default.guardrail[1].Status` |
| OK | Equity guardrail (Cautious), Medicaid/CHIP vs Commercial Door-to-provider | Risk Assessment and Mitigation | `models/scenarios.json` · `results.default.guardrail[2].Status` |
| OK | Equity guardrail (Cautious), Medicaid/CHIP vs Commercial LWBS | Risk Assessment and Mitigation | `models/scenarios.json` · `results.default.guardrail[3].Status` |
| 2 min | Wait gap widening tolerance for the equity guardrail | Risk Assessment and Mitigation | `halvian/config.py` · `EQUITY_GUARDRAIL['door_to_provider_gap_min']` |
| 0.3 pp | Walkout gap widening tolerance for the equity guardrail | Risk Assessment and Mitigation | `halvian/config.py` · `EQUITY_GUARDRAIL['lwbs_gap_pts']` |
| 2 | Consecutive months of widening that trigger the equity guardrail | Risk Assessment and Mitigation | `halvian/config.py` · `EQUITY_GUARDRAIL['consecutive_months']` |
| 0.857 | ED admission model test AUC, ability to rank outcomes | Working MVP Demo | `models/metrics.json` · `admission.test.logistic.auc` |
| 67.9% | ED admission flag precision, share of flags that were correct | Working MVP Demo | `models/metrics.json` · `admission.deployed_policy.precision` |
| 20.9% | ED admission flag recall, share of eventual outcomes caught | Working MVP Demo | `models/metrics.json` · `admission.deployed_policy.recall` |
| 0.853 | Discharge model test AUC, ability to rank outcomes | Working MVP Demo | `models/metrics.json` · `discharge.test.boosting.auc` |
| 63.1% | Discharge flag precision, share of flags that were correct | Working MVP Demo | `models/metrics.json` · `discharge.at_threshold.precision` |
| 41.0% | Discharge flag recall, share of eventual outcomes caught | Working MVP Demo | `models/metrics.json` · `discharge.at_threshold.recall` |
| 1.9 h | Median lead from first batch flag to admission decision for correct flags | Working MVP Demo | `models/metrics.json` · `admission.lead_time.median_h` |
| 11.7 | ED admission flags per day in the test quarter | Working MVP Demo | `models/metrics.json` · `admission.lead_time.alerts_per_day` |
| 6.8 h | Median time from correctly flagged rounds to discharge | Working MVP Demo | `models/metrics.json` · `discharge.lead_time.median_h_true_positive` |
| 98.9% | Rule-based note reader precision on all synthetic notes (the discharge model's feature source) | Working MVP Demo | `models/metrics.json` · `note_reader.overall.precision` |
| 93.1% | Rule-based note reader recall on all synthetic notes (the discharge model's feature source) | Working MVP Demo | `models/metrics.json` · `note_reader.overall.recall` |
| 1,319 | Notes in the sealed evaluation sample B read by the local model | Working MVP Demo | `models/metrics.json` · `note_reader.llm.sample_n` |
| 99.3% | AI note reader (local model) precision on the evaluation sample | Working MVP Demo | `models/metrics.json` · `note_reader.llm.overall.precision` |
| 93.7% | AI note reader (local model) recall on the evaluation sample | Working MVP Demo | `models/metrics.json` · `note_reader.llm.overall.recall` |
| 96.4% | AI note reader (local model) F1 on the evaluation sample | Working MVP Demo | `models/metrics.json` · `note_reader.llm.overall.f1` |
| 100.0% | Rule-based reader precision on the evaluation sample | Working MVP Demo | `models/metrics.json` · `note_reader.rules.overall.precision` |
| 94.7% | Rule-based reader recall on the evaluation sample | Working MVP Demo | `models/metrics.json` · `note_reader.rules.overall.recall` |
| 97.3% | Rule-based reader F1 on the evaluation sample | Working MVP Demo | `models/metrics.json` · `note_reader.rules.overall.f1` |
| 99.3% | AI reader and rules combined precision on the evaluation sample | Working MVP Demo | `models/metrics.json` · `note_reader.combined.overall.precision` |
| 96.8% | AI reader and rules combined recall on the evaluation sample | Working MVP Demo | `models/metrics.json` · `note_reader.combined.overall.recall` |
| 98.0% | AI reader and rules combined F1 on the evaluation sample | Working MVP Demo | `models/metrics.json` · `note_reader.combined.overall.f1` |
| 74.5% | The same model answers under the first reader's checks (g1): precision on sample B | Working MVP Demo | `models/metrics.json` · `note_reader.llm_checks_g1.overall.precision` |
| 54.9% recall, 97.5% precision | AI note reader on the new-phrasing stress set (wording neither reader was built on) | Working MVP Demo | `models/metrics.json` · `note_reader.stress.llm.overall.{recall, precision}` |
| 6.2% recall, 100.0% precision | Rule-based reader on the new-phrasing stress set (wording neither reader was built on) | Working MVP Demo | `models/metrics.json` · `note_reader.stress.rules.overall.{recall, precision}` |
| 78.3% precision, F1 0.84 | First AI reader (v1-2241325901+g1) on sample A, kept for comparison | Working MVP Demo | `models/metrics.json` · `note_reader.history[0].llm.overall.{precision, f1}` |
| 39.3 min | Time for the local model to read the evaluation sample, the stress set and every demo-day note | AI Tool Architecture | `models/metrics.json` · `note_reader.llm_run.wall_minutes` |
| 79.1% | Missed share of eventual admissions for All patients | Risk Assessment and Mitigation | `models/metrics.json` · `admission.fairness_deployed[0].fnr` |
| 88.4% | Missed share of eventual admissions for Medicaid/CHIP | Risk Assessment and Mitigation | `models/metrics.json` · `admission.fairness_deployed[1].fnr` |
| 68.7% | Missed share of eventual admissions for Medicare | Risk Assessment and Mitigation | `models/metrics.json` · `admission.fairness_deployed[2].fnr` |
| 82.8% | Missed share of eventual admissions for Commercial | Risk Assessment and Mitigation | `models/metrics.json` · `admission.fairness_deployed[3].fnr` |
| 91.8% | Missed share of eventual admissions for Uninsured | Risk Assessment and Mitigation | `models/metrics.json` · `admission.fairness_deployed[4].fnr` |
| 71.3% | Missed share of eventual admissions for Other (VA, workers' comp, auto) | Risk Assessment and Mitigation | `models/metrics.json` · `admission.fairness_deployed[5].fnr` |
| AUC 0.857, calibration +0.2 pts, missed 79.1%, flagged 5.2% | ED admission flags as deployed, All patients | Risk Assessment and Mitigation | `models/metrics.json` · `admission.fairness_deployed[0].{auc, calibration_gap_pts, fnr, flag_rate}` |
| AUC 0.869, calibration +0.5 pts, missed 88.4%, flagged 1.7% | ED admission flags as deployed, Medicaid/CHIP | Risk Assessment and Mitigation | `models/metrics.json` · `admission.fairness_deployed[1].{auc, calibration_gap_pts, fnr, flag_rate}` |
| AUC 0.803, calibration +0.1 pts, missed 68.7%, flagged 13.5% | ED admission flags as deployed, Medicare | Risk Assessment and Mitigation | `models/metrics.json` · `admission.fairness_deployed[2].{auc, calibration_gap_pts, fnr, flag_rate}` |
| AUC 0.851, calibration +0.1 pts, missed 82.8%, flagged 4.0% | ED admission flags as deployed, Commercial | Risk Assessment and Mitigation | `models/metrics.json` · `admission.fairness_deployed[3].{auc, calibration_gap_pts, fnr, flag_rate}` |
| AUC 0.870, calibration +0.1 pts, missed 91.8%, flagged 1.2% | ED admission flags as deployed, Uninsured | Risk Assessment and Mitigation | `models/metrics.json` · `admission.fairness_deployed[4].{auc, calibration_gap_pts, fnr, flag_rate}` |
| AUC 0.835, calibration -0.4 pts, missed 71.3%, flagged 8.1% | ED admission flags as deployed, Other (VA, workers' comp, auto) | Risk Assessment and Mitigation | `models/metrics.json` · `admission.fairness_deployed[5].{auc, calibration_gap_pts, fnr, flag_rate}` |
| AUC 0.857, calibration +0.2 pts, missed 89.5%, flagged 2.3% | ED admission flags at a fixed 70% threshold, All patients | Risk Assessment and Mitigation | `models/metrics.json` · `admission.fairness_fixed[0].{auc, calibration_gap_pts, fnr, flag_rate}` |
| AUC 0.869, calibration +0.5 pts, missed 92.5%, flagged 1.0% | ED admission flags at a fixed 70% threshold, Medicaid/CHIP | Risk Assessment and Mitigation | `models/metrics.json` · `admission.fairness_fixed[1].{auc, calibration_gap_pts, fnr, flag_rate}` |
| AUC 0.803, calibration +0.1 pts, missed 84.9%, flagged 5.6% | ED admission flags at a fixed 70% threshold, Medicare | Risk Assessment and Mitigation | `models/metrics.json` · `admission.fairness_fixed[2].{auc, calibration_gap_pts, fnr, flag_rate}` |
| AUC 0.851, calibration +0.1 pts, missed 91.9%, flagged 1.7% | ED admission flags at a fixed 70% threshold, Commercial | Risk Assessment and Mitigation | `models/metrics.json` · `admission.fairness_fixed[3].{auc, calibration_gap_pts, fnr, flag_rate}` |
| AUC 0.870, calibration +0.1 pts, missed 95.9%, flagged 0.6% | ED admission flags at a fixed 70% threshold, Uninsured | Risk Assessment and Mitigation | `models/metrics.json` · `admission.fairness_fixed[4].{auc, calibration_gap_pts, fnr, flag_rate}` |
| AUC 0.835, calibration -0.4 pts, missed 83.0%, flagged 4.1% | ED admission flags at a fixed 70% threshold, Other (VA, workers' comp, auto) | Risk Assessment and Mitigation | `models/metrics.json` · `admission.fairness_fixed[5].{auc, calibration_gap_pts, fnr, flag_rate}` |
| AUC 0.857, calibration +0.2 pts, missed 89.6%, flagged 2.3% | comparison model that sees insurance (not used), All patients | Risk Assessment and Mitigation | `models/metrics.json` · `admission.fairness_with_payer[0].{auc, calibration_gap_pts, fnr, flag_rate}` |
| AUC 0.870, calibration +0.4 pts, missed 92.3%, flagged 1.1% | comparison model that sees insurance (not used), Medicaid/CHIP | Risk Assessment and Mitigation | `models/metrics.json` · `admission.fairness_with_payer[1].{auc, calibration_gap_pts, fnr, flag_rate}` |
| AUC 0.803, calibration -0.6 pts, missed 86.8%, flagged 4.8% | comparison model that sees insurance (not used), Medicare | Risk Assessment and Mitigation | `models/metrics.json` · `admission.fairness_with_payer[2].{auc, calibration_gap_pts, fnr, flag_rate}` |
| AUC 0.851, calibration +0.4 pts, missed 91.0%, flagged 1.9% | comparison model that sees insurance (not used), Commercial | Risk Assessment and Mitigation | `models/metrics.json` · `admission.fairness_with_payer[3].{auc, calibration_gap_pts, fnr, flag_rate}` |
| AUC 0.870, calibration +0.1 pts, missed 95.4%, flagged 0.6% | comparison model that sees insurance (not used), Uninsured | Risk Assessment and Mitigation | `models/metrics.json` · `admission.fairness_with_payer[4].{auc, calibration_gap_pts, fnr, flag_rate}` |
| AUC 0.836, calibration +2.2 pts, missed 77.7%, flagged 6.1% | comparison model that sees insurance (not used), Other (VA, workers' comp, auto) | Risk Assessment and Mitigation | `models/metrics.json` · `admission.fairness_with_payer[5].{auc, calibration_gap_pts, fnr, flag_rate}` |
| AUC 0.853, calibration -0.4 pts, missed 59.0%, flagged 14.2% | Discharge list, All patients | Risk Assessment and Mitigation | `models/metrics.json` · `discharge.fairness[0].{auc, calibration_gap_pts, fnr, flag_rate}` |
| AUC 0.848, calibration +0.7 pts, missed 57.0%, flagged 15.7% | Discharge list, Medicaid/CHIP | Risk Assessment and Mitigation | `models/metrics.json` · `discharge.fairness[1].{auc, calibration_gap_pts, fnr, flag_rate}` |
| AUC 0.862, calibration -2.1 pts, missed 62.5%, flagged 12.4% | Discharge list, Medicare | Risk Assessment and Mitigation | `models/metrics.json` · `discharge.fairness[2].{auc, calibration_gap_pts, fnr, flag_rate}` |
| AUC 0.846, calibration +0.7 pts, missed 56.4%, flagged 15.4% | Discharge list, Commercial | Risk Assessment and Mitigation | `models/metrics.json` · `discharge.fairness[3].{auc, calibration_gap_pts, fnr, flag_rate}` |
| AUC 0.854, calibration +0.7 pts, missed 57.4%, flagged 15.0% | Discharge list, Uninsured | Risk Assessment and Mitigation | `models/metrics.json` · `discharge.fairness[4].{auc, calibration_gap_pts, fnr, flag_rate}` |
| AUC 0.860, calibration -0.1 pts, missed 62.0%, flagged 12.1% | Discharge list, Other (VA, workers' comp, auto) | Risk Assessment and Mitigation | `models/metrics.json` · `discharge.fairness[5].{auc, calibration_gap_pts, fnr, flag_rate}` |
| 50% | Share of flags acted on in the default simulated scenario | Roadmap and Milestones | `models/scenarios.json` · `results.default.scenario.adoption` |
| 1 h | Minimum staff response delay after triage in the default simulated scenario | Roadmap and Milestones | `models/scenarios.json` · `results.default.scenario.staff_response_delay_h` |
| 70% | Base admission alert threshold in the default simulated scenario | Roadmap and Milestones | `models/scenarios.json` · `results.default.scenario.threshold` |
| 1 h | Time a discharge task can recover in the default simulated scenario | Roadmap and Milestones | `models/scenarios.json` · `results.default.scenario.discharge_hours_saved` |
| On | Default use of the crowding-adjusted admission threshold | Roadmap and Milestones | `models/scenarios.json` · `results.default.scenario.moving` |
| All units | Default scenario scope | Roadmap and Milestones | `models/scenarios.json` · `results.default.scenario.scope` |
| On | Early admission preparation in the default scenario | Roadmap and Milestones | `models/scenarios.json` · `results.default.scenario.admission_side` |
| On | Discharge work in the default scenario | Roadmap and Milestones | `models/scenarios.json` · `results.default.scenario.discharge_side` |
| 25% | Our assumption: cut in housekeeping notification and bed request processing with the bed board (Expected and Full rollout only) | Roadmap and Milestones | `halvian/config.py` · `BED_BOARD_DELAY_CUT` |
| 75% | Share of flags acted on in the Full rollout scenario | Roadmap and Milestones | `halvian/config.py` · `FULL_ROLLOUT['adoption']` |
| 60% | Base admission alert threshold in the Full rollout scenario | Roadmap and Milestones | `halvian/config.py` · `FULL_ROLLOUT['threshold']` |
| 2 h | Time a discharge task can recover in the Full rollout scenario | Roadmap and Milestones | `halvian/config.py` · `FULL_ROLLOUT['discharge_hours_saved']` |
| 55.0% | Floor for the crowding-adjusted admission threshold | Roadmap and Milestones | `halvian/config.py` · `MOVING_THRESHOLD_FLOOR` |
| 85.0% | Ceiling for the crowding-adjusted admission threshold | Roadmap and Milestones | `halvian/config.py` · `MOVING_THRESHOLD_CEILING` |
| 50.0% | Threshold for a discharge-probability flag at rounds | Working MVP Demo | `halvian/config.py` · `DISCHARGE_LIST_THRESHOLD` |
| 60 min | Interval for batching bed requests | AI Tool Architecture | `halvian/config.py` · `BATCH_INTERVAL_MIN` |
| 4 h | Time after which an unused reservation is released | Risk Assessment and Mitigation | `halvian/config.py` · `RESERVATION_EXPIRY_H` |
| 0 min to 5 min | Minutes saved per admission (range), adoption 50%, response 1 h, threshold 70%, discharge 1 h, pilot (Pilot: Medicine A only) | Budget and ROI | `models/scenarios.json` · `results['pilot'].summary.mean_minutes_saved_per_admission.{min, max}` |
| 10 min to 15 min | Minutes saved per admission (range), adoption 50%, response 1 h, threshold 70%, discharge 1 h, admission side only | Budget and ROI | `models/scenarios.json` · `results['admission_only'].summary.mean_minutes_saved_per_admission.{min, max}` |
| -5 min to 10 min | Minutes saved per admission (range), adoption 50%, response 1 h, threshold 70%, discharge 1 h, discharge side only | Budget and ROI | `models/scenarios.json` · `results['discharge_only'].summary.mean_minutes_saved_per_admission.{min, max}` |
| 10 min to 15 min | Minutes saved per admission (range), bed board only | Budget and ROI | `models/scenarios.json` · `results['bed_board_only'].summary.mean_minutes_saved_per_admission.{min, max}` |
| 20 min to 30 min | Minutes saved per admission (range), adoption 50%, response 1 h, threshold 70%, discharge 1 h, bed board on | Budget and ROI | `models/scenarios.json` · `results['expected'].summary.mean_minutes_saved_per_admission.{min, max}` |
| 35 min to 50 min | Minutes saved per admission (range), adoption 75%, response 1 h, threshold 60%, discharge 2 h, bed board on | Budget and ROI | `models/scenarios.json` · `results['full_rollout'].summary.mean_minutes_saved_per_admission.{min, max}` |
| 5 min to 15 min | Minutes saved per admission (range), adoption 25%, response 1 h, threshold 70%, discharge 1 h | Budget and ROI | `models/scenarios.json` · `results['adoption=0.25'].summary.mean_minutes_saved_per_admission.{min, max}` |
| 15 min to 30 min | Minutes saved per admission (range), adoption 75%, response 1 h, threshold 70%, discharge 1 h | Budget and ROI | `models/scenarios.json` · `results['adoption=0.75'].summary.mean_minutes_saved_per_admission.{min, max}` |
| 20 min to 35 min | Minutes saved per admission (range), adoption 100%, response 1 h, threshold 70%, discharge 1 h | Budget and ROI | `models/scenarios.json` · `results['adoption=1'].summary.mean_minutes_saved_per_admission.{min, max}` |
| 10 min to 25 min | Minutes saved per admission (range), adoption 50%, response 0 h, threshold 70%, discharge 1 h | Budget and ROI | `models/scenarios.json` · `results['staff_response_delay_h=0'].summary.mean_minutes_saved_per_admission.{min, max}` |
| 15 min to 25 min | Minutes saved per admission (range), adoption 50%, response 0.5 h, threshold 70%, discharge 1 h | Budget and ROI | `models/scenarios.json` · `results['staff_response_delay_h=0.5'].summary.mean_minutes_saved_per_admission.{min, max}` |
| 5 min to 15 min | Minutes saved per admission (range), adoption 50%, response 2 h, threshold 70%, discharge 1 h | Budget and ROI | `models/scenarios.json` · `results['staff_response_delay_h=2'].summary.mean_minutes_saved_per_admission.{min, max}` |
| 5 min to 15 min | Minutes saved per admission (range), adoption 50%, response 3 h, threshold 70%, discharge 1 h | Budget and ROI | `models/scenarios.json` · `results['staff_response_delay_h=3'].summary.mean_minutes_saved_per_admission.{min, max}` |
| 20 min to 30 min | Minutes saved per admission (range), adoption 50%, response 1 h, threshold 50%, discharge 1 h | Budget and ROI | `models/scenarios.json` · `results['threshold=0.5'].summary.mean_minutes_saved_per_admission.{min, max}` |
| 15 min to 25 min | Minutes saved per admission (range), adoption 50%, response 1 h, threshold 60%, discharge 1 h | Budget and ROI | `models/scenarios.json` · `results['threshold=0.6'].summary.mean_minutes_saved_per_admission.{min, max}` |
| 5 min to 20 min | Minutes saved per admission (range), adoption 50%, response 1 h, threshold 80%, discharge 1 h | Budget and ROI | `models/scenarios.json` · `results['threshold=0.8'].summary.mean_minutes_saved_per_admission.{min, max}` |
| 0 min to 15 min | Minutes saved per admission (range), adoption 50%, response 1 h, threshold 90%, discharge 1 h | Budget and ROI | `models/scenarios.json` · `results['threshold=0.9'].summary.mean_minutes_saved_per_admission.{min, max}` |
| 10 min to 15 min | Minutes saved per admission (range), adoption 50%, response 1 h, threshold 70%, discharge 0 h | Budget and ROI | `models/scenarios.json` · `results['discharge_hours_saved=0'].summary.mean_minutes_saved_per_admission.{min, max}` |
| 10 min to 25 min | Minutes saved per admission (range), adoption 50%, response 1 h, threshold 70%, discharge 2 h | Budget and ROI | `models/scenarios.json` · `results['discharge_hours_saved=2'].summary.mean_minutes_saved_per_admission.{min, max}` |
| 15 min to 30 min | Minutes saved per admission (range), adoption 50%, response 1 h, threshold 70%, discharge 3 h | Budget and ROI | `models/scenarios.json` · `results['discharge_hours_saved=3'].summary.mean_minutes_saved_per_admission.{min, max}` |
| 15 min to 35 min | Minutes saved per admission (range), adoption 50%, response 1 h, threshold 70%, discharge 4 h | Budget and ROI | `models/scenarios.json` · `results['discharge_hours_saved=4'].summary.mean_minutes_saved_per_admission.{min, max}` |
| 15 min, 30 min, 60 min | Pitch assumptions for minutes saved per admission | Budget and ROI | `halvian/config.py` · `PITCH_BOARDING_CUTS_MIN` |
| $314,738 | Budget for Phase 1, the pilot (Months 1 to 6) | Budget and ROI | `models/plan.json` · `budget.by_phase.pilot` |
| $66,840 | Hidden costs in that budget (clinician training time, security review, vendor fees): pilot | Budget and ROI | `models/plan.json` · `budget.hidden_by_phase.pilot` |
| $296,219 | Budget for Phase 2, scale (Months 7 to 18) | Budget and ROI | `models/plan.json` · `budget.by_phase.scale` |
| $52,220 | Hidden costs in that budget (clinician training time, security review, vendor fees): scale | Budget and ROI | `models/plan.json` · `budget.hidden_by_phase.scale` |
| $210,252 | Yearly running cost after Month 18 | Budget and ROI | `models/plan.json` · `budget.by_phase.run` |
| $49,368 | Hidden costs in that budget (clinician training time, security review, vendor fees): run | Budget and ROI | `models/plan.json` · `budget.hidden_by_phase.run` |
| $610,956 | Total cost over the 18 months, against the $750,000 cap | Budget and ROI | `models/plan.json` · `budget.total_18_months` |
| $462,847 | Year 1 spend (Months 1 to 12), against the $500,000 a year cap | Budget and ROI | `models/plan.json` · `budget.year_1` |
| $139,044 | Budget left over the 18 months | Budget and ROI | `models/plan.json` · `budget.headroom_18_months` |
| 7.2 FTE | Staff needed to give the same coverage by hand | Budget and ROI | `models/plan.json` · `traditional.total.fte` |
| $975,098, $1.46M, $1.95M | Yearly cost of that coverage hired, on overtime, or through an agency | Budget and ROI | `models/plan.json` · `traditional.total.{hired, overtime, agency}` |
| 300 to 500 | Walkouts avoided per year (relative drop applied to the brief's baseline) (Cautious) | Budget and ROI | `models/plan.json` · `value.walkouts_avoided.{min, max}` |
| $0.2M to $0.4M | Cash from recovered visits per year (50% of avoided walkouts at $1,500) (Cautious) | Budget and ROI | `models/plan.json` · `value.walkout_revenue.{min, max}` |
| $10K to $30K | Nurse overtime avoided per year (Cautious) | Budget and ROI | `models/plan.json` · `value.overtime_avoided.{min, max}` |
| $0.2M to $0.4M | Total cash value per year (recovered visits plus overtime) (Cautious) | Budget and ROI | `models/plan.json` · `value.cash_value.{min, max}` |
| 200% to 700% | Yearly ROI on freed capacity (Cautious freed capacity against the yearly running cost) | Budget and ROI | `models/impact_ranges.json` · `scenarios[0].freed_capacity_per_year_usd_m` |
| 10% to 80% | Yearly cash ROI (recovered visits and overtime only, Cautious) | Budget and ROI | `models/plan.json` · `roi.cash.roi_per_year.{min, max}` |
| month 11 to 13 (capacity), month 38 to after month 60 (cash) | Payback counted from the start of the pilot (Cautious) | Budget and ROI | `models/plan.json` · `roi.capacity.payback_month_range, roi.cash.payback_month_range` |
| $40 to $100 | Yearly cost per ED room-hour freed (Cautious) | Budget and ROI | `models/impact_ranges.json` · `scenarios[0].minutes_saved_per_admission` |
| 3.5 h to 3.4 h | Month 18 goal G1: Median boarding, admit decision to leaving the ED | Roadmap and Milestones | `models/plan.json` · `goals[0].{baseline, target}` |
| 4.0% to 3.6% | Month 18 goal G2: Share of arrivals who leave before a provider sees them | Roadmap and Milestones | `models/plan.json` · `goals[1].{baseline, target}` |
| 10 to 9 min | Month 18 equity goal: Medicaid/CHIP minus Commercial, median minutes to a provider | Roadmap and Milestones | `models/plan.json` · `goals[2].parts[0].{baseline, target}` |
| 2.8 to 2.6 pp | Month 18 equity goal: Uninsured minus Commercial, share leaving before being seen | Roadmap and Milestones | `models/plan.json` · `goals[2].parts[1].{baseline, target}` |
| 5 of 9 | Pilot gates met in the synthetic test (the rest need pilot data or are not met) | Roadmap and Milestones | `models/plan.json` · `pilot_gates (entry count)` |
| 91.8% missed, 89.2% expected, +2.6 pts unexplained | Uninsured admissions missed by the flags, the rate expected from triage level and age, and the part they do not explain (pre-launch bias test) | Risk Assessment and Mitigation | `models/metrics.json` · `admission.fairness_case_mix.rows[3].{observed_miss_rate, expected_from_case_mix, unexplained_pts}` |
| 20 min to 30 min, 63.5%, 3 of 4 gaps narrowed | Phase 2 option, base threshold 50%: minutes saved, flag precision, case gaps | Roadmap and Milestones | `models/plan.json` · `phase2.options[0].{minutes_saved.min, minutes_saved.max, precision, case_gaps_narrowed}` |
| 15 min to 25 min, 66.1%, 4 of 4 gaps narrowed | Phase 2 option, base threshold 60%: minutes saved, flag precision, case gaps | Roadmap and Milestones | `models/plan.json` · `phase2.options[1].{minutes_saved.min, minutes_saved.max, precision, case_gaps_narrowed}` |
