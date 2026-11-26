# Final quality pass: report

Main is pushed and the app is running on <http://127.0.0.1:8502>. All tests pass, ruff is clean and both identity checks pass. The last full browser pass found no problems: every page plus the demo path, at 1440x900 and 1920x1080, with Ollama on and with it off.

## Bugs fixed

- **Replay bar cut off.** It is now two rows. Row one holds a plain sentence ("You are viewing Monday, Dec 8, 2025 at 10:00, the busy demo day...") with the date, **Demo days** and **Reset**. Row two holds **Earlier**, the time slider and **Later**, then the three story jumps, **Highlight demo patients** and the decision-log link. Every feature is kept, and nothing truncates or wraps at either size.
- **/overview showed "Page not found".** A hidden alias page now serves the Overview at both `/` and `/overview`; the results companion gets the same fix for `/impact`. In-app links are unchanged.
- **Walkouts mixed periods.** Every quarterly change now says "simulated winter quarter". The only yearly figure is `plan.json` `value.walkouts_avoided` (300 to 500 a year, Cautious).
- **Handoff items.** Codex asked for a checkbox for **Highlight demo patients** and for Bed Board tiles that use only the design classes; both are done. The older items (the stay ID in the guided demo, the forecast change shown beside the confirmation, the requirements wording, the presenter guide) were already resolved on main.
- **Found during the pass:**
  - The note reader stacked three status captions, including an outdated "Placeholder" line. It now shows one line: which reader answered, why, the model and the time taken. It also says "match strength" instead of "confidence", since the score is not a probability.
  - Model chances in tables showed two decimals ("81.48%"). They now show whole percents.
  - Results ranges lost a decimal ("$4 million", "-1 to -0.6"). They now read "$4.0 million" and "-1.0 to -0.6".
  - Results cost cards wrapped over three lines. They now read "$370K to $430K".
  - Bed Forecast said the same sentence twice; the duplicate is replaced with the action it implies.
  - The "At this replay time" note sat flush against the next heading; it now has space below it.

## Design, clarity and numbers (steps 2 to 4)

- **Design system:** every page I own uses Codex's helpers (`kpi`, `card`, `section_heading`, `status_tag`, `callout`) through `halvian/ui/design.py`. No inline CSS, border-radius or hard-coded colors remain, and every chart uses the theme's Plotly template. The Bed Board's room tiles use the `hv-tile` classes.
- **Page headers:** each page opens with who uses it, a distinct problem from the case brief, and a distinct downstream effect, all from `story.py`. A test fails if two pages claim the same problem or effect.
- **Page layout:** after the header come the headline numbers, then the main table or chart, then the actions, with one primary button per screen.
  - Text is about a third shorter, and jargon lives in "How it works".
  - Tables are capped with "Show all N rows", and empty states explain themselves.
- **Number checks:** `tests/test_numbers_on_pages.py` renders every page and fails in three cases:
  - a simulated outcome is shown as a single number;
  - a number next to a model score or case benchmark isn't in `docs/NUMBERS.md`;
  - an insurance group appears on an operational screen.

  A built-in self-test proves the first two rules fire. NUMBERS.md now lists every per-group fairness score the Fairness page shows.

## The merge

**Merged on your confirmation, not on Codex's marker.** The line `CODEX STATUS: DONE` never appeared in codex/refine's HANDOFF.md. You told me Codex was done, so I merged the pushed tip **`9488f52`** without waiting. Its worktree was clean and matched that commit.

- Merge commit: **`f700bf7`**. It was clean, with no conflicts, and pytest passed before and after.
- No change to Codex's files was needed to make the merged app work.

## Still imperfect

All screenshots are in `qa_screens/` (git-ignored). `qa_screens/report.json` lists them with their load times.

1. **The first live note read is slow.** After the model has sat idle, the first **Read this note** takes about 10 to 15 seconds while Ollama loads it; later reads take about 3 to 4. Do one practice read before recording. See `qa_screens/1440x900_demo_04_note.png`.
2. **One slow load.** Once in about eight runs the Overview took 4.5 seconds at 1920x1080. Every other run, every page loaded in under 2 seconds (the guided demo is the slowest at 1.3 to 1.8). Probably the machine was busy with the model at that moment.
3. **Text cut off in tables.** On Discharge Readiness and ED Admission Flags, the long "Reasons" column is cut at the table edge; the full text shows on hover. See `qa_screens/1440x900_discharge_readiness.png` and `qa_screens/1440x900_admission_flags.png`.
4. **Uneven cards and tiles.** A headline card is taller when its label wraps (the first Bed Board card), and Bed Board tiles vary in height with their detail text. See `qa_screens/1440x900_bed_board.png`.
5. **Equity colors.** "Flat" equity verdicts use the amber **Watch** tag. That is a design choice: flat is not a failure, but it is worth watching. See `qa_screens/1440x900_impact.png`.
6. **The number test is keyword-based.** It checks sentences about simulated outcomes, model scores and benchmarks. Live replay counts, such as patients waiting, are not claims and are not checked.
7. **Ollama off works.** The reader says "Rule-based backup: Rule-based reader (fallback: local model not running)", and the demo continues. See `qa_screens/ollama_off_1440x900_note.png`. Ollama is running again now.
8. **My process slip.** One commit (`7cf5caf`) went in with a failing test: piping pytest into `tail` hid its exit code. It was fixed in the next commit (`d76f7f0`), and every later commit checked pytest's exit code first.

## The 2-minute demo click path

Open <http://127.0.0.1:8502/> in a fresh tab at least 1440 pixels wide. First run `ollama serve` and do one practice **Read this note**.

1. **Overview** (0:00 to 0:15). Point to 3.5 hours to a bed against 2 to 2.5 nationally, then select **Start the guided demo**.
2. **Step 1, bed request** (0:15 to 0:35). Point to ED-078643, the 65% chance of admission and the three reasons, then select **Approve request**.
3. **Next: discharge task** (0:35 to 1:00).
   - Point to IP-021972, a different patient on Medicine B.
   - Select **Read this note** and show the highlighted "needs wheelchair van" and its owner.
   - Select **Record transport as arranged**. The chance of going home rises from 9% to 33%.
4. **Next: bed forecast** (1:00 to 1:15). Show the before and after ranges for Medicine B, then select **Approve forecast**.
5. **Finish: see the decisions in the log** (1:15 to 1:30). Show the three decisions with their roles, then open **Fairness check** and point to the Uninsured finding.
6. **Results → Downstream impact** (1:30 to 2:00). Read "Pays for itself if it saves about 6 minutes per admitted patient", then the ranges: Cautious 10 to 20 minutes, Expected 20 to 30, Full rollout 35 to 50. Say it is a model estimate on a synthetic hospital.

The full script with lines to say is in `docs/DEMO_SCRIPT.md`.

## If the app isn't running when you're back

```sh
cd ~/Documents/HackTheCase
source .venv/bin/activate
streamlit run app.py --server.address 127.0.0.1 --server.port 8502
```

Then open <http://127.0.0.1:8502>. For the live AI note reader, also run `ollama serve` in another terminal; without it the app uses the rule-based backup and says so. To recheck everything in a browser, run `python scripts/qa_browser.py` (it starts its own copy on a spare port and writes screenshots to `qa_screens/`).
