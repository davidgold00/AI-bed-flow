"""Fairness and Oversight: the staff decision log, the fairness check by patient group, waits and
walkouts by insurance group, and the rules for reviewing or pausing the tool."""

from datetime import timedelta

import pandas as pd
import streamlit as st

from halvian import config as C
from halvian.data import live as L
from halvian.data.cohort import MIN_PER_DAY
from halvian.data.gaps import payer_outcomes
from halvian.models.fairness import tolerance_rows
from halvian.ui import navigation as NAV
from halvian.ui.components import number_column, page_header, percent_column
from halvian.ui.design import callout, capped_table, kpi_row, section_heading, status_tag
from halvian.ui.session import action_log
from halvian.ui.story import impact_now

WINDOW_DAYS = 90  # about three months: shorter windows swing widely on a few hundred visits
LEVEL_TEXT = {"ok": "On track", "amber": "Watch: review", "red": "Act: review before launch",
              "insufficient data": "Insufficient data"}

clock = page_header(
    NAV.OVERSIGHT,
    how="The decision log lists every approval and override with its role and reason. The fairness check compares "
        "each model's accuracy and misses across insurance groups, using insurance only to audit, never to predict. "
        "Waits and walkouts by group come from the replay. The tool owner applies the pause rules.",
)
m = L.metrics()


def fairness_frame(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["status"] = df.worst_level.map(LEVEL_TEXT)
    df.loc[df.group == "All patients", "status"] = "Reference"
    return df


def show_fairness(df: pd.DataFrame, positive: str) -> None:
    cols = ["group", "n", "positives", "auc", "calibration_gap_pts", "fnr", "flag_rate", "status"]
    st.dataframe(df[cols], hide_index=True, width="stretch", column_config={
        "group": "Group", "n": number_column("Cases"), "positives": number_column(positive),
        "auc": number_column("AUC", decimals=2), "calibration_gap_pts": number_column("Calibration gap (pts)", decimals=1),
        "fnr": percent_column("Missed true cases"), "flag_rate": percent_column("Flag rate"), "status": "Status"})


def explain(df: pd.DataFrame, noun: str) -> str:
    flagged = df[(df.group != "All patients") & (df.worst_level.isin(["amber", "red"]))]
    if flagged.empty:
        return f"Every group is within tolerance for the {noun}."
    overall = df[df.group == "All patients"].iloc[0]
    parts = []
    for r in flagged.itertuples():
        why = []
        if r.fnr_level in ("amber", "red"):
            why.append(f"misses {r.fnr:.0%} of true cases vs {overall.fnr:.0%} overall")
        if r.auc_level in ("amber", "red"):
            why.append(f"ranks patients less well (AUC {r.auc:.2f} vs {overall.auc:.2f})")
        if r.calibration_level in ("amber", "red"):
            why.append(f"is off by {r.calibration_gap_pts:+.1f} points on average")
        parts.append(f"**{r.group}** ({LEVEL_TEXT[r.worst_level].split(':')[0].lower()}): {' and '.join(why)}")
    return f"For the {noun}: " + "; ".join(parts) + "."


log = action_log()
adm = fairness_frame(m["admission"]["fairness_deployed"])
dis = fairness_frame(m["discharge"]["fairness"])
n_decisions = len(log)
n_overrides = int((log.decision == "override").sum()) if n_decisions else 0
review = [f"{r.group} ({part}, {LEVEL_TEXT[r.worst_level].split(':')[0].lower()})"
          for part, df in (("admission flags", adm), ("discharge list", dis))
          for r in df[(df.group != "All patients") & df.worst_level.isin(["amber", "red"])].itertuples()]
note = ((f"**{n_decisions} staff decision{'s' if n_decisions != 1 else ''}** this session, {n_overrides} "
         f"override{'s' if n_overrides != 1 else ''}, each with a role and a reason. ") if n_decisions else
        "No staff decisions yet this session. ")
note += (("Fairness check: **" + "; ".join(review) + "** need review before launch.") if review else
         "Fairness check: every group is within tolerance for both models.")
impact_now(note)
if review:
    status_tag("act" if any("act)" in item for item in review) else "watch",
               "At least one insurance group needs review before launch.")
TAB_KEY = NAV.OVERSIGHT_TAB_KEY
LOG_TAB = NAV.DECISION_LOG_TITLE


def _update_log_link() -> None:
    if st.session_state[TAB_KEY] != LOG_TAB and st.query_params.get("view") == NAV.DECISION_LOG_PARAMS["view"]:
        del st.query_params["view"]


if st.query_params.get("view") == NAV.DECISION_LOG_PARAMS["view"]:
    st.session_state[TAB_KEY] = LOG_TAB
tab_log, tab_fair, tab_waits, tab_pause = st.tabs(
    [LOG_TAB, "Fairness check", "Waits and walkouts by group", "When to pause"],
    key=TAB_KEY, on_change=_update_log_link,
)

# ------------------------------------------------------------------ decision log
with tab_log:
    n = len(log)
    overrides = int((log.decision == "override").sum()) if n else 0
    kpi_row([("Staff decisions", f"{n}", "This browser session"), ("Approved", f"{n - overrides}", ""),
             ("Overridden", f"{overrides}", "Each with a reason"),
             ("Override rate", f"{overrides / n:.0%}" if n else "None yet",
              f"Healthy: {C.PAUSE_CONDITIONS['min_override_rate']:.0%} to {C.PAUSE_CONDITIONS['max_override_rate']:.0%}")])
    if not n:
        callout("No decisions yet. Approvals and overrides from any page appear here.")
        links = st.container(horizontal=True)
        for spec in (NAV.ADMISSION_FLAGS, NAV.DISCHARGE, NAV.GUIDED_DEMO):
            links.page_link(spec.path, label=spec.title, icon=spec.icon)
    else:
        shown = log.iloc[::-1].assign(
            decision=log.decision.iloc[::-1].str.capitalize(),
            replay_time=log.replay_time.iloc[::-1].str.replace("T", " "))
        capped_table(shown[["replay_time", "role", "decision", "reason", "recommendation_id", "page"]],
                     key="decision_log", rows=10, column_config={
                         "replay_time": "Replay time", "role": "Role", "decision": "Decision",
                         "reason": "Reason", "recommendation_id": "Recommendation", "page": "Made on"})
        st.download_button("Download the decision log (CSV)", log.to_csv(index=False), "halvian-actions.csv",
                           mime="text/csv", icon=":material/download:", on_click="ignore")
    st.caption("Kept for this browser session only. In a deployment they go to an audit table the tool owner reviews.")

# ------------------------------------------------------------------ fairness check
with tab_fair:
    st.caption("Measured on synthetic visits from October to December 2025, months the models never saw in training.")
    section_heading("ED Admission Flags by insurance group")
    policy = st.radio("Alert rule", ["As deployed (moving threshold, hourly batch)", "Fixed 70% threshold"],
                      horizontal=True)
    shown_adm = adm if policy.startswith("As deployed") else fairness_frame(m["admission"]["fairness_fixed"])
    show_fairness(shown_adm, "Admissions")
    st.markdown(explain(shown_adm, "admission flags"))
    needs_review = shown_adm[(shown_adm.group != "All patients") & shown_adm.worst_level.isin(["amber", "red"])]
    if len(needs_review):
        st.markdown(
            "**What this means.** Medicaid/CHIP and uninsured patients are younger and less acute on average, so "
            "fewer of their admissions clear the threshold and the early request reaches them less often. **Review "
            "before launch:** a lower threshold for everyone, or a check that the missed admissions were less urgent. "
            "A threshold by insurance is ruled out: it would make insurance an input to care.")
    with st.expander("Why insurance is never a model input"):
        wp = fairness_frame(m["admission"]["fairness_with_payer"]).set_index("group")
        blind = fairness_frame(m["admission"]["fairness_fixed"]).set_index("group")
        comp = pd.DataFrame({"auc_blind": blind.auc, "auc_payer": wp.auc,
                             "fnr_blind": blind.fnr, "fnr_payer": wp.fnr}).reset_index()
        st.dataframe(comp, hide_index=True, width="stretch", column_config={
            "group": "Group", "auc_blind": number_column("AUC without insurance", decimals=2),
            "auc_payer": number_column("AUC with insurance", decimals=2),
            "fnr_blind": percent_column("Missed without insurance"),
            "fnr_payer": percent_column("Missed with insurance")})
        st.markdown(
            "A model that sees insurance is no more accurate and does not close the gap in missed admissions "
            "(fixed 70% threshold). Insurance mostly stands in for income, so it stays out.")

    section_heading("Discharge Readiness by insurance group")
    show_fairness(dis, "Discharges within 24 h")
    st.markdown(explain(dis, "discharge list"))
    with st.expander("Status and review criteria"):
        st.dataframe(tolerance_rows(), hide_index=True, width="stretch")
        st.caption("Any group with fewer than 30 true or false cases reads 'insufficient data'.")

    readers = m.get("note_reader", {})
    llm = readers.get("llm", {})
    rules = readers.get("rules", {})
    if llm.get("by_payer") and rules.get("by_payer"):
        section_heading("AI note reader by insurance group")
        st.caption("Local language model and rule-based reader, scored on the same synthetic sample.")
        scores = []
        for label, reader in (("Local AI reader", llm), ("Rule-based reader", rules)):
            for group, row in reader["by_payer"].items():
                scores.append({"group": group, "reader": label, "notes": row.get("notes"),
                               "precision": row.get("precision"), "recall": row.get("recall")})
        st.dataframe(pd.DataFrame(scores), hide_index=True, width="stretch", column_config={
            "group": "Insurance group", "reader": "Reader", "notes": number_column("Notes"),
            "precision": percent_column("Precision"), "recall": percent_column("Recall"),
        })


# ------------------------------------------------------------------ waits and walkouts
with tab_waits:
    t = clock.minutes_from_start
    t0 = L.day_start(clock.day) - WINDOW_DAYS * MIN_PER_DAY
    ed = L.data("ed_visits")
    window = ed[(ed.arrival_min >= t0) & (ed.arrival_min < L.day_start(clock.day)) & (ed.departure_min <= t)]
    if window.empty:
        st.caption("No completed visits from earlier replay days are available for comparison.")
    else:
        po = payer_outcomes(window)
        ref = po.loc[C.COMMERCIAL]
        rows = []
        for g in (C.COMMERCIAL, C.MEDICAID, C.UNINSURED, C.MEDICARE, C.OTHER):
            r = po.loc[g]
            brief_d2p = C.DOOR_TO_PROVIDER_BY_PAYER_MIN.get(g)
            brief_lwbs = C.LWBS_BY_PAYER.get(g)
            rows.append({
                "group": g, "visits": r.visits, "d2p": r.d2p_median,
                "d2p_gap": "Reference" if g == C.COMMERCIAL else f"{r.d2p_median - ref.d2p_median:+.1f}",
                "lwbs": r.lwbs_pct,
                "lwbs_gap": "Reference" if g == C.COMMERCIAL else f"{r.lwbs_pct - ref.lwbs_pct:+.1f}",
                "brief": (f"{brief_d2p} min, {100 * brief_lwbs:.1f}%" if brief_d2p is not None else "Not given")})
        section_heading("How long each insurance group waits, and how many leave",
                        sub=f"Replay of ED visits, {max(C.YEAR_START, clock.day - timedelta(days=WINDOW_DAYS)):%b %d} "
                            f"to {clock.day - timedelta(days=1):%b %d, %Y}. Gaps are against commercially insured "
                            "patients.")
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", column_config={
            "group": "Group", "visits": number_column("Visits"),
            "d2p": number_column("Median wait to see a provider (min)", decimals=0),
            "d2p_gap": "Wait gap (min)",
            "lwbs": number_column("Left without being seen (%)", decimals=1),
            "lwbs_gap": "Walkout gap (pts)",
            "brief": "Case brief, full year"})
        def _gap_sentence(g: str) -> str:
            r = po.loc[g]
            wait, walk = r.d2p_median - ref.d2p_median, r.lwbs_pct - ref.lwbs_pct
            return (f"**{g}** patients waited **{abs(wait):.0f} minutes {'longer' if wait >= 0 else 'less'}** to see "
                    f"a provider and left without being seen **{abs(walk):.1f} points {'more' if walk >= 0 else 'less'} "
                    "often**")

        if po.loc[[C.COMMERCIAL, C.MEDICAID, C.UNINSURED], ["d2p_median", "lwbs_pct"]].notna().all().all():
            st.markdown(f"Compared with commercially insured patients, {_gap_sentence(C.MEDICAID)}. "
                        f"{_gap_sentence(C.UNINSURED)}.")
    g = C.EQUITY_GUARDRAIL
    st.markdown(f"**Equity guardrail.** After launch, each month is compared with the months before launch. If any "
            f"tracked gap widens by more than **{g['door_to_provider_gap_min']:g} minutes** (wait) or "
            f"**{g['lwbs_gap_pts']:g} points** (walkouts) for **{g['consecutive_months']} months in a row**, the "
            "tool is reviewed or paused.")

# ------------------------------------------------------------------ pause rules
with tab_pause:
    pc = C.PAUSE_CONDITIONS
    best = m["admission"]["test"][m["admission"]["chosen"]]
    worst_fnr_gap = max((r["fnr"] - adm.loc[adm.group == "All patients", "fnr"].iloc[0]) * 100
                        for r in adm.to_dict(orient="records") if r["group"] != "All patients" and r["fnr"] is not None)
    n = len(log)
    rate = (log.decision == "override").mean() if n else None
    section_heading("When the tool is reviewed or paused")
    st.dataframe(pd.DataFrame([
        {"Condition": f"Admission model AUC below {pc['min_auc']:.2f} over 4 weeks",
         "Latest check": f"{best['auc']:.2f}", "Status": "OK" if best["auc"] >= pc["min_auc"] else "Pause"},
        {"Condition": f"Any insurance group misses {pc['max_fnr_gap_pts']:g}+ points more admissions than "
                      "overall for 2 weeks",
         "Latest check": f"{worst_fnr_gap:+.1f} pts (worst group)",
         "Status": "Review" if worst_fnr_gap > pc["max_fnr_gap_pts"] else "OK"},
        {"Condition": f"Calibration drifts more than {pc['max_calibration_drift_pts']:g} points",
         "Latest check": f"{best['calibration_gap_pts']:+.1f} pts", "Status": "OK"},
        {"Condition": f"Override rate above {pc['max_override_rate']:.0%} (mistrust) or below "
                      f"{pc['min_override_rate']:.0%} (rubber-stamping)",
         "Latest check": f"{rate:.0%} this session" if rate is not None else "No decisions yet",
         "Status": "Watch" if rate is None else (
             "Review" if rate > pc["max_override_rate"] or rate < pc["min_override_rate"] else "OK")},
        {"Condition": "Any tracked insurance gap wider than before launch for 2 months in a row",
         "Latest check": "See Waits and walkouts by group", "Status": "Monitored monthly"},
        {"Condition": f"Data feed down for more than {pc['max_feed_outage_min']} min",
         "Latest check": "Simulated feed", "Status": "Fallback: phone and whiteboard, bed huddle every 2 hours"},
    ]), hide_index=True, width="stretch")

    section_heading("Who acts, and who is accountable when it is wrong")
    st.dataframe(pd.DataFrame([
        {"Recommendation": "Early bed request (hourly, per unit)", "Acts on it": "Bed manager",
         "Accountable when wrong": "Bed manager (can override), house supervisor"},
        {"Recommendation": "Likely discharge on the rounds list", "Acts on it": "Unit team at rounds",
         "Accountable when wrong": "Attending physician (owns every discharge decision)"},
        {"Recommendation": "Barrier found in a note", "Acts on it": "Case manager or nurse",
         "Accountable when wrong": "Case management lead"},
        {"Recommendation": "Bed forecast", "Acts on it": "Charge nurse", "Accountable when wrong": "Nursing operations"},
        {"Recommendation": "Model accuracy and fairness", "Acts on it": "Tool owner (clinical informatics)",
         "Accountable when wrong": "AI oversight committee; pauses or retrains"},
    ]), hide_index=True, width="stretch")
    st.caption("No recommendation executes automatically. Admission and discharge decisions stay with clinicians.")
