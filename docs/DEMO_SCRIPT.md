# Two-minute dashboard demo

Open [Halvian Bed Flow on port 8502](http://127.0.0.1:8502/) in a browser window at least 1440 pixels wide. Use a fresh session so the decision log starts empty (reload the page, or select **Reset** and open a new tab). The header and footer say the data are synthetic.

**Before recording:** start Ollama (`ollama serve`) and read one note once, so the local model is loaded. The first read after the model has been idle takes about 15 seconds; later reads take about 4. With Ollama off, the app says **Rule-based backup** and the demo still works.

| Time | Click | Say |
| --- | --- | --- |
| 0:00 to 0:15 | **Overview.** Point to the case baseline (3.5 hours to a bed, against 2 to 2.5 nationally), then select **Start the guided demo**. | "Admitted patients wait 3.5 hours for a bed and hold emergency rooms while they wait. The dashboard helps staff start bed work and discharge work earlier." |
| 0:15 to 0:35 | **Step 1, bed request.** Read the visit ID, the 65% chance of admission and the three reasons. Select **Approve request**. | "The bed manager sees a likely admission, checks why, and approves preparing a bed. The clinician still decides whether to admit." |
| 0:35 to 1:00 | **Next: discharge task.** Point to the second patient's stay ID (IP-021972). Select **Read this note**, show the highlighted wheelchair van and its owner, then select **Record transport as arranged**. Read the change in the chance of going home. | "This is a different patient on the same unit. The AI reader, running on this computer, highlights the transport problem and quotes it word for word. The case manager records the ride as arranged; the attending makes the discharge decision." |
| 1:00 to 1:15 | **Next: bed forecast.** Show the before and after ranges for Medicine B and select **Approve forecast**. | "Clearing one task makes a small change to the forecast. The charge nurse uses the range to plan and confirms each bed before assigning it." |
| 1:15 to 1:30 | **Finish: see the decisions in the log.** Show the three decisions with their roles. Open **Fairness check** and point to the Uninsured finding. | "Every decision is logged with who made it. The tool also checks itself by insurance group: uninsured admissions are missed more often, so that needs review before launch." |
| 1:30 to 2:00 | **Results → Downstream impact.** Read the break-even headline, then the Cautious, Expected and Full rollout ranges. | "It pays for itself if it saves about 6 minutes per admitted patient. On a synthetic hospital calibrated to the case, the cautious estimate is 10 to 20 minutes. This is a model estimate, not evidence from a real hospital." |

Read the source line after the note is analyzed. **Read locally with Ollama** names the model and how long it took. **Rule-based backup** says why the local model was not used; describe the backup and carry on. The percentage beside a finding is a match strength, not a probability.

## Questions and alternate views

- **Can I see the staff pages?** Use **Dashboard** in the top menu. The replay bar keeps the day and time; tick **Highlight demo patients** to bring the demo patients to the top.
- **Can I change the replay?** Pick any date, or **Demo days** for the two featured days. Step with **Earlier** and **Later** or the slider; the shortcuts jump to 07:00 rounds, the 11:00 bed request and the 14:00 forecast. **Reset** restores the start and keeps the decision log.
- **Can staff disagree?** Every recommendation has **Override** with a reason. On Bed Forecast the charge nurse can enter a corrected number of beds.
- **Can I try another note?** On Overview select **Try the Ollama note reader**, or open it at the bottom of Discharge Readiness. Pick a synthetic stay or paste fictional text and select **Read this note**.
- **What about the simulated impact?** **Results → Downstream impact** shows where the minutes come from, the change in waits and walkouts, the payer gap verdicts and staffing costs. **Impact simulator** compares the three scenarios.
- **Who is accountable?** **Safeguards → Fairness and Oversight → When to pause.**
