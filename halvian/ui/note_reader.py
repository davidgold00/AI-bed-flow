"""Display saved and on-demand findings from the local note-reader contract."""

from hashlib import sha256
from html import escape
from importlib import import_module
from time import perf_counter

import streamlit as st

from halvian import config as C
from halvian.data.live import highlight
from halvian.notes.reader import RuleBasedNoteReader
from halvian.ui import navigation as NAV
from halvian.ui.discharge_actions import REASONS
from halvian.ui.session import DemoClock, latest_action, record_action

LOCAL = "Read locally with Ollama"
BACKUP = "Rule-based backup"


def _rules(text: str) -> dict:
    start = perf_counter()
    findings = []
    for item in RuleBasedNoteReader().read(text):
        lo, hi = item["evidence_span"]
        barrier = item["type"]
        findings.append({
            "barrier_type": barrier, "start": lo, "end": hi, "evidence": text[lo:hi],
            "label": C.BARRIER_LABELS[barrier], "owner": C.BARRIER_OWNER[barrier],
            "confidence": item["confidence"], "reader": "rules",
        })
    return {"status": "fallback", "model": BACKUP, "latency_ms": (perf_counter() - start) * 1000,
            "findings": findings}


def analyze(text: str) -> tuple[dict, dict]:
    """Run the optional backend when requested. The dashboard opens without it."""
    try:
        backend = import_module("halvian.notes.live")
    except ImportError:
        return _rules(text), {}
    try:
        result = backend.analyze_note(text)
    except Exception:  # The saved replay and backup remain usable if the optional service fails.
        return _rules(text), {}
    try:
        details = backend.reader_status()
    except Exception:
        details = {}
    return result, details


def show_evidence(text: str, findings: list[dict]) -> None:
    spans = [item for item in findings if 0 <= item["start"] < item["end"] <= len(text)]
    parts = [f"<mark>{escape(segment)}</mark>" if label else escape(segment)
             for segment, label in highlight(text, spans)]
    st.html(f'<div class="hv-note">{"".join(parts)}</div>')


def show_saved_note(text: str, findings: list[dict]) -> None:
    readers = {item.get("reader") == "llm" for item in findings}
    if not readers:
        st.caption("No open discharge task was found in this note.")
    else:
        who = " and ".join(name for flag, name in ((True, "the local AI reader"), (False, "the rule-based backup"))
                           if flag in readers)
        st.caption(f"Saved findings from {who}.")
    show_evidence(text, findings)


def read_control(text: str, key: str, *, saved: list[dict] | None = None,
                 submitted: bool | None = None) -> dict | None:
    """Read once per button click. Keep the result alongside the matching input."""
    if submitted is None:
        submitted = st.button("Read this note", icon=":material/query_stats:", key=f"read_note_{key}")
    if submitted:
        if not text.strip():
            st.caption("Enter a fictional discharge note to read.")
            return None
        with st.spinner("Reading the synthetic note locally"):
            result, reader = analyze(text)
        st.session_state[f"note_result_{key}"] = (text, result, reader)
    last = st.session_state.get(f"note_result_{key}")
    if not last or last[0] != text:
        if saved is not None:
            show_saved_note(text, saved)
        return None
    _, result, reader = last
    status = result["status"]
    if status == "error":
        st.caption("The reader could not analyze this note. Retry, or read the note yourself.")
    else:
        details = [f"{LOCAL if status == 'llm' else BACKUP}: {result['model']}", f"{result['latency_ms']:,.0f} ms"]
        if status == "llm" and reader.get("available") and reader.get("prompt_version"):
            details.append(f"Prompt {reader['prompt_version']}")
        st.caption(" · ".join(details))
    findings = result["findings"]
    show_evidence(text, findings)
    for item in findings:
        label = item["label"]
        st.markdown(f"**{label}** · {item['owner']} · match strength {item['confidence']:.0%}")
        st.caption(f"Evidence: {item['evidence']}")
    if not findings and status != "error":
        st.caption("No active discharge barrier was found in this note.")
    return result


def try_note_reader(notes: dict[str, str], clock: DemoClock) -> None:
    with st.expander("Try the Ollama note reader", expanded=st.query_params.get("view") == NAV.NOTE_READER_PARAMS["view"]):
        st.caption("Choose a synthetic note or paste a fictional one. Read this note runs Ollama locally and highlights discharge barriers.")
        source = st.radio("Note source", ("Saved example", "Paste synthetic text"), horizontal=True)
        submitted = None
        if source == "Saved example":
            choice = st.selectbox("Synthetic stay", list(notes))
            text = notes[choice]
        else:
            with st.form("paste_synthetic_note", border=False):
                text = st.text_area("Synthetic note", key="synthetic_note_text", height=100,
                                    placeholder="Enter a fictional discharge note.")
                submitted = st.form_submit_button("Read this note", icon=":material/query_stats:")
        result = read_control(text, "try", submitted=submitted)
        if not result:
            return
        if not result["findings"]:
            return
        findings = {item["barrier_type"]: item for item in result["findings"]}
        barrier = st.selectbox("Finding to review", list(findings), format_func=lambda key: findings[key]["label"])
        note_id = sha256(text.encode()).hexdigest()[:12]
        rec = f"note-demo|{note_id}|{barrier}"
        prior = latest_action(rec)
        if prior:
            st.caption("Finding approved for this demonstration." if prior.decision == "approve"
                       else f"Finding overridden. {prior.reason}.")
        st.caption("Reviewing this example leaves the rounds estimate unchanged.")
        options = st.container(horizontal=True)
        args = {"page": "Note reader demonstration", "role": findings[barrier]["owner"], "clock": clock}
        options.button("Approve finding", on_click=record_action, args=(rec, "approve"), kwargs=args)
        with options.popover("Override", key="sample_finding_override"):
            reason = st.selectbox("Reason", REASONS, key="sample_finding_reason")
            st.button("Confirm override", key="sample_confirm_override", on_click=record_action,
                      args=(rec, "override"), kwargs={**args, "reason": reason})
