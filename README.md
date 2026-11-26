# Halvian Bed Flow

Halvian Bed Flow is a staff dashboard prototype for the Michigan Ross AI Forum healthcare case competition. It helps emergency department and inpatient staff anticipate bed demand, prepare transfers, and review the equity of their decisions.

**Synthetic data only. Prototype for discussion, not clinical use.** Every patient, note and event is generated. The app runs fully offline with no API keys or external services.

## The 30-second version

At Halvian, a fictional 320-bed hospital, a patient who needs to be admitted waits a median of **3.5 hours** in the ED for an inpatient bed (national: 2 to 2.5). The bed search starts late, bed status lives on phone calls and a whiteboard, and discharges stall on rides, home care and insurance approvals. While admitted patients hold ED rooms, new arrivals wait longer and some leave without being seen, more often if they are uninsured or on Medicaid/CHIP.

Halvian Bed Flow gives staff a head start. Each part fixes one cause of boarding:

| Problem (from the brief) | What the dashboard does | Downstream impact | Page |
| --- | --- | --- | --- |
| Beds are requested too late | Predicts at triage who will likely be admitted and to which unit, and drafts an hourly bed request per unit | Bed work starts before the admit decision, so the patient boards for less time | ED Admission Flags |
| Discharges stall on paperwork and coordination | Lists who can likely go home within 24 hours at 07:00 rounds, highlights the blocking task in the note and names its owner | The bed opens before the afternoon ED rush | Discharge Readiness |
| Bed openings come as a surprise | Forecasts usable beds per unit 4, 8 and 24 hours ahead; the charge nurse confirms or corrects it | A shortfall is handled hours ahead instead of when the ED calls | Bed Forecast |
| Nobody can see the whole hospital | Shows every ED space and inpatient bed in one view | A clean bed is assigned without a round of phone calls | Live Bed Board |
| Crowding hurts some patients more | Never uses insurance to predict, checks each model by insurance group, tracks waits and walkouts by group | A gap is caught and acted on before it widens | Fairness and Oversight |
| Clinicians are skeptical of AI | Every recommendation shows its reasons and needs a person to approve or override it; every decision is logged | Staff stay in charge, so they can trust and use it | Every page, logged in Fairness and Oversight |

Together they get an inpatient bed ready when the ED patient needs it. Downstream: shorter boarding, ED rooms free up sooner, patients are seen sooner, fewer leave without being seen, and the gaps for Medicaid/CHIP and uninsured patients shrink.

**What it could change (a model estimate from a synthetic Halvian calibrated to the case brief, not evidence from a real hospital).** The tool pays for itself if it saves about **6 minutes of boarding per admission**: $500,000 a year / ($350 per bed-hour x 13,600 admissions a year). Across three synthetic years the simulation gives **Cautious** (today's default settings) 10 to 20 minutes per admission, about $0.8M to $1.6M of freed capacity a year (capacity, not cash); **Expected** (plus the bed board) 20 to 30 minutes, $1.6M to $2.4M; and **Full rollout** 35 to 50 minutes, $2.8M to $4.0M. In Cautious and Expected the wait to see a provider falls by 2 to 10 minutes and the share leaving unseen by 0.4 to 1.0 points in the simulated winter quarter (about 300 to 500 fewer walkouts a year in Cautious, from `plan.json`); no payer gap widens. Results are always ranges, rounded outward; the brief's own numbers are exact. It costs $611K over 18 months, inside the $750K budget. Every figure and its source: [docs/NUMBERS.md](docs/NUMBERS.md).

## Run it

Use Python 3.11 to 3.13 from the repository root. The synthetic data and trained models are checked in, so this is all you need:

```sh
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py --server.port 8502            # the dashboard: http://127.0.0.1:8502
```

The Overview opens with the problem (3.5 hours to a bed against 2 to 2.5 nationally), the case benchmarks, how the parts work together and the break-even point, and the **Results** menu holds the evidence behind it: downstream impact, the impact simulator, the requirements check and data and methods. The same Results pages also run on their own if you want them in a second window:

```sh
streamlit run results_app.py --server.port 8511    # Results only: http://127.0.0.1:8511
```

Everything runs offline. Fonts and icons are bundled in `static/`. If the app is not running, start it again with the `streamlit run app.py` line above (from the repository root, with the virtual environment active).

To check the app in a real browser (every page and the demo path at 1440x900 and 1920x1080; screenshots go to the git-ignored `qa_screens/`):

```sh
pip install -r scripts/requirements-qa.txt   # Playwright; it drives the Chrome already installed
python scripts/qa_browser.py
```

### The AI note reader (optional, runs on this machine)

Discharge Readiness reads each morning note with a small language model running locally through [Ollama](https://ollama.com). Nothing leaves the machine and there is no API key. The saved results for both demo days are committed, so the pages show the model's findings even with Ollama off. Ollama is needed only for **Read this note** (reading a note live) and to rerun the evaluation. Without it, the reader falls back to the rules and says **Rule-based backup**.

```sh
brew install ollama          # once, if it is not installed
ollama serve                 # leave running in its own terminal
ollama pull llama3.2:3b      # about 2 GB, once
python scripts/run_llm_reader.py   # about 40 minutes: demo-day notes, the stress set and the sealed sample
```

The model is Llama 3.2 3B because this Mac has 8 GB of memory. The script times a small batch first and sizes the evaluation sample to finish within an hour.

To rebuild everything from scratch (about 4 minutes): `python scripts/generate_data.py`, `python scripts/validate.py`, then `python scripts/train_models.py`. Run `pytest` and `ruff check .` before committing changes. The first live read after the model has been idle takes about 15 seconds while it loads; later reads take about 4.

## Tour of the dashboard

The pages sit in the top navigation under **Start here**, **Dashboard**, **Safeguards** and **Results**. Under it, the **replay bar** sets the moment being replayed: any day of the synthetic year, with the two featured demo days (a busy winter Monday, Dec 8, and a typical Wednesday, Oct 15) one click away, at any time of day, with **Earlier** and **Later**, quick jumps to rounds, the bed request and the forecast, and **Reset**. Every page shows that same moment. **Highlight demo patients** surfaces the guided-demo records on each page. The header and footer mark every page as synthetic demo data.

Each dashboard page opens with who uses it, the problem it solves (from the case brief) and what changes downstream, then its headline numbers, its main table or chart, and its actions. No two pages claim the same problem or effect.

| Page | Who uses it | What to do there |
| --- | --- | --- |
| **Overview** | Everyone | The problem and the case benchmarks, how the parts work together, the break-even point and the three scenario ranges, and what the tool never does. Start the guided demo here, or jump straight to the AI note reader. |
| **Guided demo** | Presenters | One patient's bed request, a discharge task for another patient on the same unit (with **Read this note**), and the bed forecast, in three steps. The replay bar follows each step, and the last step opens the decision log. |
| **Live Bed Board** | Bed manager, ED charge nurse | Every ED space and inpatient bed: who is boarding, which beds are clean, being cleaned or about to open, and how the day builds. |
| **ED Admission Flags** | Bed manager | Likely admissions with their top three reasons, the hourly bed request per unit, and approve or override (an override needs a reason). |
| **Discharge Readiness** | Rounds team, case manager | The 07:00 rounds list with the AI note reader's highlighted barriers, which reader found each one, and its owner. Recording an action re-scores the patient and feeds the forecast and bed board. **Try the AI note reader** reads any synthetic or pasted fictional note live. |
| **Bed Forecast** | Charge nurses, house supervisor | Usable beds per unit 4, 8 and 24 hours ahead with an 80% range, and what is freeing up versus what is needed. The charge nurse confirms the forecast or overrides it with a corrected estimate and a reason. |
| **Fairness and Oversight** | Tool owner, AI oversight committee | The decision log (with CSV download), the fairness check by insurance group, waits and walkouts by group over the last 90 days, and the rules for pausing the tool. |
| **Results** (four pages) | Judges, the team | Downstream impact (break-even, the three scenarios, where the minutes come from, waits and walkouts, payer gap verdicts, staffing costs, sources), the impact simulator, the requirements check against the brief and rubric, and data and methods. Every simulated result is a rounded range. |

See the [two-minute demo script](docs/DEMO_SCRIPT.md) and the [presenter guide](docs/PRESENTER_GUIDE.md).

## Key assumptions

- **Synthetic hospital.** A fictional year on the 2025 calendar, generated by a discrete-event simulation of the ED and six inpatient units and calibrated to the brief's volumes, waits, walkout rates, boarding time and occupancy (`python scripts/validate.py` checks 29 targets). The brief names no units, so the unit names and sizes are ours: Medicine A 80, Medicine B 76, Telemetry 52, Surgery 64, Step-down 24, ICU 24 beds.
- **Admission flags** use only what is known at the end of triage. A patient is flagged at a 70% chance of admission. The threshold moves with crowding between 55% and 85%, from a published preprint policy. Flagged patients join an hourly bed request per unit at least an hour after triage.
- **Discharge list.** Scored at 07:00 rounds; it shows patients with at least a 50% chance of leaving within 24 hours, plus anyone whose note flags a barrier.
- **Note reader.** An AI note reader (Llama 3.2 3B, running locally) with a rule-based fallback. It keeps a barrier only if the quoted evidence appears word for word in the note and its clause names a discharge task that is still open. A laptop model cannot read all 107,000 notes of the synthetic year, so it reads a sealed evaluation sample of about 1,300 notes, a 304-note stress set in new wording, and every note shown on the two demo days; the rule-based reader is the full-year input to the discharge model. Together the two readers reach 99% precision and 97% recall on the sample; on new wording the rules find 6% of barriers and the AI reader 55%. Details in [docs/MODELS.md](docs/MODELS.md).
- **Insurance is never a model input.** It is used only for the fairness check and the waits and walkouts by group.
- **Insurance groups.** The brief's payer mix sums to 98%. The remaining 2% is "Other (VA, workers' comp, auto)", and self-pay patients count as Uninsured.
- **Equity mechanisms** (adjustable, documented in `docs/DATA.md`): Medicaid/CHIP and uninsured patients make more lower-acuity visits at peak times and face more non-medical discharge barriers.
- **Fairness rule.** A group is amber or red when its AUC trails the overall figure by 0.03 or 0.05, its calibration is off by 2 or 4 points, or it misses 5 or 10 points more true cases. The equity guardrail sends the tool for review if a tracked gap widens by more than 2 minutes or 0.3 points for 2 months in a row.

The full assumption list (A1 to A21) is in the [data documentation](docs/DATA.md).

## Results and the requirements check

The staff pages show the product only. The evidence behind it is in the **Results** menu group (also available on its own with `streamlit run results_app.py --server.port 8511`), and the Overview opens with a short summary of it:

- **Downstream impact.** The break-even first (about 6 minutes saved per admission), then the three scenarios (Cautious, Expected, Full rollout) as ranges against it, where the time comes from (admission flags, discharge readiness, the bed board), the change in waits and walkouts, the payer gap verdicts, traditional staffing costs against the tool's cost, and the published sources. All read from `models/impact_ranges.json`.
- **Impact simulator.** Pick a saved scenario and see its settings, its range against the break-even, and its waits, walkouts and freed capacity.
- **Requirements check.** Every item in the case brief and rubric, where the prototype meets it, and a live automated check. The same checks run in `pytest`, so a change that breaks a requirement fails the tests. Items that belong in the slides say what the app already gives you for that slide.
- **Data and methods.** Calibration against the brief, the assumptions, and the AI note reader's scores against the rules.

Slide-ready charts are in `exports/` (`python scripts/export_slide_assets.py`), and every presentation number with its source file is in [docs/NUMBERS.md](docs/NUMBERS.md).

All results come from a synthetic hospital. They are estimates, not evidence from a real one. The written detail is in [docs/DATA.md](docs/DATA.md) and [docs/MODELS.md](docs/MODELS.md).

## Strategy: roadmap, budget, ROI and risk

The parts of the video the app cannot show (the brief's sections 2 to 4) are computed too, so every slide number traces to a file:

- [docs/STRATEGY.md](docs/STRATEGY.md) is generated from `models/plan.json` and the saved results: Month 18 goals tied to the brief's baselines with an equity goal, pilot and scale milestones with owners, the gates to move from the pilot to Phase 2 checked against the synthetic evidence, the alert threshold decision for Phase 2, the budget by phase with hidden costs, the traditional approach (the same work by hand, hired, on overtime or through an agency), the value of the gains, KPIs, ROI and payback, the risk table, the response plan if systems are compromised and the contingency plan.
- Every budget and plan assumption is in `halvian/config.py` (tags B1 to B20). Change one, then run `python scripts/build_plan.py` (writes `models/plan.json` and `models/impact_ranges.json`, the results the app shows), `python scripts/export_strategy.py` and `python scripts/export_numbers.py`. Tests fail if any of these outputs is stale.
- Charts for these slides: `exports/ranges_vs_break_even.png` (the three scenarios and each part against the break-even), `exports/budget_by_phase.png`, `exports/value_vs_traditional.png` (staffing options against the tool, cost only) and `exports/roadmap.png`.
- The pre-launch bias test (missed admissions by insurance group, matched on triage level and age) is in `models/metrics.json` and in the strategy page.

## Sources

- The competition brief supplied the fictional baseline. [Data and simulation methodology](docs/DATA.md) documents the assumptions used in this prototype.
- [American College of Emergency Physicians on boarding and crowding](https://www.acep.org/administration/crowding--boarding)
- [Using Hospital Admission Predictions at Triage](https://pubsonline.informs.org/doi/10.1287/opre.2022.2405)
- [Johns Hopkins study of discharge predictions in multidisciplinary rounds](https://pure.johnshopkins.edu/en/publications/machine-learning-based-hospital-discharge-predictions-can-support/)
- [Preprint on proactive inpatient bed requests](https://arxiv.org/abs/2607.15432)
