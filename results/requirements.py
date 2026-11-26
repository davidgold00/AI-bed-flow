"""Requirements check: every item in the case brief and rubric, where it is met, and a live check."""

import pandas as pd
import streamlit as st

from halvian.requirements import FAIL, JUDGMENT, PARTLY, PASS, REQUIREMENTS, SLIDES, Result
from halvian.ui.components import page_header
from halvian.ui.design import kpi_row, status_tag
from halvian.ui.results import EMPTY_RESULTS, load_impact_ranges

page_header(
    "What the case asks us to show",
    "Every requirement in the case brief and rubric, where the prototype meets it, and a live check where one "
    "is possible.",
    "Each check reads the committed data, models and code and computes its answer; nothing is hard-coded to "
    "pass. The same checks run in `pytest` (`tests/test_requirements.py`), so a change that breaks a "
    "requirement fails the tests.\n\n"
    "- **Pass**: met in the app, checked automatically.\n"
    "- **Partly**: the app does what is asked, but the result needs a decision or a caveat (shown in the detail).\n"
    "- **Fail**: not met. Fix before recording the video.\n"
    "- **Team: slides** or **Team: judgment**: belongs in the presentation or needs a person to judge it.",
)

# Keep the live checklist statuses and use the published ranges for impact claims.
financial_checks = {
    "B1": "See the phase budgets and assumptions in the strategy brief.",
    "B2": "See Downstream impact for the estimated capacity and staffing comparison.",
    "B3": "See Downstream impact for the break-even estimate and equity verdicts.",
    "S3": "See the budget caps and the phase budgets in the strategy brief.",
    "R3": "See the scale milestones and operating assumptions in the strategy brief.",
}
def impact_equity_check() -> Result:
    impact = load_impact_ranges()
    if impact is None:
        return Result(JUDGMENT, EMPTY_RESULTS)
    verdicts = {row["verdict"] for row in impact["equity"]}
    if "Widened" in verdicts:
        return Result(FAIL, "At least one gap widened in the Expected scenario. See the verdicts in Downstream impact.")
    if "Flat" in verdicts:
        return Result(PARTLY, "Some gaps stayed flat in the Expected scenario. See the verdicts in Downstream impact.")
    return Result(PASS, "The tracked gaps narrowed in the Expected scenario. See the verdicts in Downstream impact.")


checks = [(req, impact_equity_check() if req.id == "S2" else req.evaluate()) for req in REQUIREMENTS]
rows = [{"ID": req.id, "Section": req.section, "Requirement": req.requirement, "Source": req.source,
         "Status": res.status, "Where it is met": financial_checks.get(req.id, req.where),
         "Check result": res.detail if req.id not in financial_checks or res.status == FAIL else ""}
        for req, res in checks]
df = pd.DataFrame(rows)
counts = df.Status.value_counts()
app_rows = df[~df.Status.isin([SLIDES, JUDGMENT])]

kpi_row([("App checks passing", f"{counts.get(PASS, 0)} of {len(app_rows)}", "Checked live"),
         ("Partly met", f"{counts.get(PARTLY, 0)}", "Met, with a caveat for the slides"),
         ("Failing", f"{counts.get(FAIL, 0)}", "Fix before recording"),
         ("For the slides", f"{counts.get(SLIDES, 0) + counts.get(JUDGMENT, 0)}", "Or a judgment call")])
if counts.get(FAIL, 0):
    status_tag("act", "Review failing requirements before recording.")
demo = df[df.ID.str.startswith("D")]
demo_ok = demo[~demo.Status.isin([SLIDES, JUDGMENT])].Status.eq(PASS).all()
st.markdown(
    ("**The demo requirements (rubric section 5, 3 points, all or nothing) pass.** " if demo_ok else
     "**Some demo requirements (rubric section 5) do not pass yet.** ")
    + "Sections 1 to 4 carry 31 of the 37 points and live in the slides; the rows below say what the app gives "
    "you for each one.")
partly = df[df.Status == PARTLY]
if len(partly):
    with st.expander("Some checks need more evidence"):
        for _, row in partly.iterrows():
            st.markdown(f"**{row.ID}. {row.Requirement}** {row['Check result']}")


BADGE = {PASS: "green", PARTLY: "orange", FAIL: "red", SLIDES: "blue", JUDGMENT: "blue"}
view = st.segmented_control("Show", ["All", "Checked in the app", "For the slides"], default="All",
                            selection_mode="single") or "All"
for section in df.Section.unique():
    part = df[df.Section == section]
    if view == "Checked in the app":
        part = part[~part.Status.isin([SLIDES, JUDGMENT])]
    elif view == "For the slides":
        part = part[part.Status.isin([SLIDES, JUDGMENT])]
    if part.empty:
        continue
    with st.expander(section, expanded=section.startswith("5.")):
        for _, r in part.iterrows():
            left, right = st.columns([2.2, 3])
            left.markdown(f":{BADGE[r.Status]}-badge[{r.Status}] **{r.ID}. {r.Requirement}**")
            left.caption(f"Source: {r.Source}")
            right.markdown(f"**Where it is met:** {r['Where it is met']}")
            if r["Check result"]:
                right.markdown(f"**Check:** {r['Check result']}")
st.download_button("Download the checklist (CSV)", df.to_csv(index=False), "halvian-requirements.csv",
                   mime="text/csv", icon=":material/download:", on_click="ignore")
