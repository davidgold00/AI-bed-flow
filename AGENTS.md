# Halvian Bed Flow: agent guide

This file is mirrored in `AGENTS.md`. Keep the two identical: edit one, then copy it over the other.

## Purpose

A working prototype for the Michigan Ross AI Forum "Hack the Case" healthcare AI competition. Halvian Medical Center is a fictional 320-bed hospital. Our focus area is **Patient Flow and Boarding** and the demo is the brief's **Option B, a staff-facing AI dashboard**. It predicts which ED patients will be admitted and which inpatients will go home soon, flags what is holding discharges up, rolls this into a bed forecast, and lets staff approve or override every recommendation.

Audience: two non-technical teammates (MBA students) judging the idea, then competition judges. Faithfulness to the case, plain-language explanations and polish matter more than speed.

Use the source tags in `halvian/config.py` and the methodology in `docs/DATA.md` to trace numerical assumptions. The build plan is `PLAN.md`.

## Commands

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/generate_data.py     # synthetic year, baseline simulation, notes, validation
python scripts/train_models.py      # note reader, models, scores, impact sweeps (about 3 min)
python scripts/train_models.py --skip-scenarios   # models only, about 25 s
python scripts/validate.py          # calibration table: Target | Simulated | Tolerance | Pass
ollama serve & ollama pull llama3.2:3b   # local model for the AI note reader (optional: the app falls back)
python scripts/run_llm_reader.py    # AI note reader: demo days, stress set, sealed sample B (about 30 min)
python scripts/make_stress_notes.py # the new-phrasing stress set (fixed; committed before any reader ran on it)
python scripts/build_plan.py        # budget, value, ROI, goals, gates -> models/plan.json, and the results
                                    # as rounded ranges -> models/impact_ranges.json (the UI's results contract)
python scripts/export_strategy.py   # slide-ready docs/STRATEGY.md from plan.json and the saved results
python scripts/export_numbers.py    # docs/NUMBERS.md (python scripts/export_slide_assets.py also renders exports/)
streamlit run app.py --server.port 8502           # the dashboard (data and models are committed)
streamlit run results_app.py --server.port 8511   # results companion: impact, simulator, requirements check
pytest                              # all tests, including AppTest page smoke tests and the numbers on every page
python scripts/qa_browser.py        # Playwright: every page and the demo path at 1440x900 and 1920x1080 (qa_screens/)
ruff check .                        # lint, must be clean
python scripts/check_identity.py    # both pre-push identity checks; must exit 0
```

Python 3.11 to 3.13. Dependencies are pinned in `requirements.txt`.

## Layout

```
app.py                  Streamlit entry point: grouped top navigation (Start here, Dashboard, Safeguards,
                        Results), product frame and the replay bar (not on Results pages)
results_app.py          the Results pages on their own: downstream impact, impact simulator,
                        requirements check, data and methods (pages in results/)
pages/                  overview, guided_demo, bed_board, admission_flags, discharge_readiness,
                        bed_forecast, oversight (menu titles and order in halvian/ui/navigation.py)
halvian/config.py       EVERY number, tagged [brief], [assumption], [calibrated] or [equity param]
halvian/data/           cohort.py (pre-drawn patients), simulate.py (custom DES), notes.py, generate.py,
                        gaps.py (payer gaps, guardrail), live.py (views at a replay time for pages 1 to 6)
halvian/models/         admission, discharge, thresholds, forecast, explain, fairness
halvian/notes/          reader.py (NoteReader, RuleBasedNoteReader, LLMNoteReader, guard g2), prompt.py (the one
                        versioned prompt), ollama.py (loopback-only client), live.py (analyze_note and
                        reader_status, the UI contract), evaluate.py (samples A and B, stress set, scoring),
                        stress.py (new-phrasing stress set)
halvian/impact.py       paired baseline vs tool runs (3 synthetic years, Oct to Dec test quarter)
halvian/equity.py       payer gaps and the equity guardrail
halvian/roi.py          bed-hours, capacity value, pitch 15/30/60 table; budget by phase, traditional approach,
                        value of gains, ROI and payback (assumptions B1 to B20 in config)
halvian/ranges.py       results as rounded ranges: break-even, Cautious/Expected/Full rollout, parts, equity
                        verdicts, staffing options, tool cost, references -> models/impact_ranges.json
halvian/roadmap.py      Month 18 goals, milestones, pilot gates (checked against saved results), Phase 2
                        threshold decision, KPIs
halvian/validation.py   calibration checks shared by scripts/validate.py and tests
halvian/requirements.py every brief and rubric requirement, where it is met, and an automated check
halvian/ui/             shared Streamlit helpers: navigation (menu), session (replay bar, tour, decision log),
                        components (page header and the design-system helpers), design (the helpers pages import,
                        plus kpi_row and capped_table), story (problem, user, downstream effect per page), theme
scripts/                generate_data.py, train_models.py, validate.py, calibrate.py
data/  models/          generated artifacts (committed while under 25 MB)
docs/                   DATA.md, MODELS.md, NUMBERS.md, STRATEGY.md (generated, slide-ready roadmap, budget,
                        ROI and risk), PRESENTER_GUIDE.md, DEMO_SCRIPT.md
```

## Conventions

- Every number lives in `halvian/config.py` with a tag citing its source. Never scatter magic numbers.
- **Results are ranges, never single numbers** (user's direction, Nov 23). Show the tool's effect only as the
  spread across the three synthetic years widened outward (minutes to 5, dollars to $0.1M, waits to 1 minute,
  walkouts to 0.1 points), introduced by the break-even point (about 6 minutes saved per admission) and with the
  caveat in `halvian/ranges.py`. The case brief's own numbers (3.5 h, 55 min, 4%, $350) stay exact. The UI reads
  results from `models/impact_ranges.json` only. Goals and ROI use the Cautious scenario (today's defaults).
- Deterministic: one global seed (`config.SEED`), named random streams per component. Same seed, same output.
- Models are **payer-blind**: payer is never a model feature. It is used only for fairness auditing and the with-payer comparison on the Fairness page.
- Every model's feature list must contain only information available at prediction time. `tests/test_leakage.py` enforces this.
- Operational screens (bed board, flags, rounds, forecast) do not display payer.
- **Product first, results in their own menu group.** At the user's request (Nov 23), the Overview leads with a
  concise strip of estimated impact (from `models/impact_ranges.json`), and the four results
  pages (Downstream impact, Impact simulator, Requirements check, Data and methods) sit in the main app's
  "Results" menu group; `results_app.py` still serves the same pages on its own. The staff pages (bed board,
  flags, rounds, forecast) show no evaluation results: no model scorecards, backtests or simulated
  with-and-without impact. The brief's required fairness check by patient group stays on Fairness and
  Oversight. Every estimate is labelled as simulated on synthetic patients; capacity and cash are never added.
- **Every part says what problem it solves.** Each dashboard page opens with its `Story` strip from
  `halvian/ui/story.py` (problem from the brief, what it does, downstream impact chain) and shows a live
  `impact_now()` note. The Overview lists the same strips. Change the wording in one place: `story.py`.
- `halvian/requirements.py` must keep passing (`tests/test_requirements.py`). Add a row when the brief or
  rubric asks for something new; never make a check pass by hard-coding its answer. Rows that belong on the
  slides stay "Cover on slides" even when `models/plan.json` backs them; their checks fail if the content is
  missing or over budget.
- Budget, goals and gates are computed, never typed: change an assumption in `config.py` (tag B<n>), then run
  `build_plan.py`, `export_strategy.py` and `export_numbers.py`. Tests fail if `plan.json`, `STRATEGY.md` or
  `NUMBERS.md` is stale.
- Every page is in the grouped top navigation (`halvian/ui/navigation.py`). `app.py` renders the product frame
  (`halvian/ui/chrome.py`: synthetic-data tag and footer) and the replay bar once; pages read the clock with
  `page_header()` or `current_clock()`. Fonts and icons are bundled in `static/` so the app runs offline.
- UI copy: each page opens with its problem strip, has a "How it works" expander, puts headline numbers before charts, and uses chart titles that state the finding.
- One color-blind-safe palette from `halvian/ui/theme.py`; amber and vermillion are reserved for warnings.
- Plotly for all charts.

## Hard rules

- **Synthetic data only.** No real patient data, no real person names, no downloading of real datasets. IDs look like `ED-000123` and `IP-004512`.
- **No API keys, no paid services, no calls off this machine at runtime.** The app runs fully offline. The AI
  note reader talks only to a local Ollama server on 127.0.0.1 (`halvian/notes/ollama.py` refuses any other
  host), and the app keeps working with Ollama off.
- **Every AI output is a recommendation** with a visible reason and an approve or override control. Nothing executes automatically.
- **Label estimates as estimates.** Never present simulated results as real-world evidence.
- **Do not rig results.** Never hard-code an outcome. If the simulation shows an equity gap does not narrow, the app must show that and the user must be told.
- **No em-dashes** in any user-facing text, README or docs. Use commas, periods or "to" for ranges.
- The note reader is the **AI note reader (local language model) with a rule-based fallback**. It keeps a finding
  only if its evidence appears verbatim in the note, and every barrier it finds is a recommendation a person
  acts on. The rule-based reader stays the full-year feature source for the discharge model (107,000 notes is
  too many for a laptop model); the local model reads a stratified evaluation sample and every demo-day note.
  Never tune the prompt or the checks on an evaluation sample; change the prompt only by bumping
  `PROMPT_VERSION` and the checks only by bumping `GUARD_VERSION`. Sample A scored v1+g1 and its errors were
  studied, so the current reader is scored on the sealed sample B and the stress set; guard g2 was designed on
  training-month notes only.

## Git and identity

- Repo: private GitHub repo `Hack-the-case`. Work on `main`.
- **Never touch `codex/*` branches** (a parallel Codex session works on `codex/refine` in its own worktree). Never rewrite history on `main` (no force-push, no rebase of pushed commits). The user merges Codex work.
- The repo-local git identity uses the GitHub noreply address. Never use or write the user's personal email in any file, config or commit.
- Before every push, both checks must pass:

  ```bash
  git log --format='%ae%n%ce' | sort -u          # only noreply addresses
  git grep -nE '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'   # no real email addresses
  ```

- Before every commit run `pytest` and `ruff check .`. Commit in small logical steps.
- `scripts/check_identity.py` runs both checks; compressed binary files can contain byte runs that fit
  the email pattern, so it decodes binary matches and scans their real content. Push only if it exits 0.

## Two workstreams (file ownership)

From the final quality pass (Nov 23, 2026, the user's latest split):

- **Codex owns** the visual system: `.streamlit/config.toml`, `static/*`, `halvian/ui/theme.py`,
  `halvian/ui/chrome.py`, `halvian/ui/components.py`, `pages/overview.py` and `docs/DESIGN.md`.
- **Claude Code owns** everything else: `app.py`, every other page in `pages/`, `results/*`, `results_app.py`,
  the other `halvian/ui/` modules (`session.py`, `navigation.py`, `story.py`, `note_reader.py`,
  `discharge_actions.py`, `results.py`, `design.py`), all data, models, scripts, docs and tests.

Do not edit the other workstream's files. If the UI needs a change, write it in `HANDOFF.md` under
"For Codex". When the user says Codex is done, Claude Code merges `codex/refine` into `main` (Codex's version
wins in UI files, Claude Code's everywhere else), runs the full suite, regenerates `docs/NUMBERS.md` and
`exports/`, and pushes.
