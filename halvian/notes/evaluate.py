"""Evaluate the AI note reader against the rules on a fixed, stratified sample of notes.

Scale is the honest constraint: the synthetic year has about 107,000 notes, too many for a
language model on a laptop. So the local model reads

* an **evaluation sample** of test-quarter notes (October to December, months no prompt was
  written against), balanced across barrier type x payer group plus notes with no barrier,
  half of which contain barrier words (resolved, negated or distractor phrases),
* **every note the app shows on the two demo days**, and
* the **new-phrasing stress set** (``halvian.notes.stress``), wording neither reader was built on,

and the rule-based reader stays the full-year feature source for the discharge model.
Sample A (tag 4242) scored the first reader (prompt v1, checks g1). Its errors were studied, so
the current reader (checks g2, designed on training-month notes only) is scored on **sample B**
(tag 4243): drawn afterwards with the same design, sharing no note and no note text with A.
The model's raw answer is cached too, so B also shows the same answers under the old checks.
Results are cached in ``models/llm_note_findings.parquet``. Nothing here calls the model:
``scripts/run_llm_reader.py`` fills the cache, and this module scores it, so
``scripts/train_models.py`` can rebuild the metrics without the model running.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from halvian import config as C
from halvian.data.cohort import minutes_from_start
from halvian.notes.reader import RuleBasedNoteReader, findings_from_answer, score_note_reader

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "models" / "llm_note_findings.parquet"
STRESS_NOTES = ROOT / "data" / "stress_notes.parquet"
STRESS_LABELS = ROOT / "data" / "stress_labels.parquet"
SAMPLE_A_TAG, SAMPLE_B_TAG = 4242, 4243
TEST_START = minutes_from_start(date(2025, 10, 1))
BARRIER_WORDS = (r"\b(?:snf|rehab|ltach|placement|hh|vna|home (?:health|care|nursing)|auth|insurance|payer|"
                 r"coverage|dtr|daughter|son|family|spouse|pick ?up|ride|transport|van|dme|o2|oxygen|rx|"
                 r"pharmacy|meds?|nebulizer|walker|bed)\b")


def notes_with_payer(notes: pd.DataFrame, stays: pd.DataFrame) -> pd.DataFrame:
    return notes.merge(stays[["stay_id", "payer"]], on="stay_id", how="left", validate="many_to_one")


def evaluation_sample(notes: pd.DataFrame, labels: pd.DataFrame, stays: pd.DataFrame, *,
                      per_cell: int = C.LLM_EVAL_PER_CELL, no_barrier: int = C.LLM_EVAL_NO_BARRIER,
                      seed: int = C.SEED, tag: int = SAMPLE_A_TAG,
                      exclude: pd.DataFrame | None = None) -> pd.DataFrame:
    """Test-quarter notes balanced across barrier type x payer group, plus no-barrier notes.

    Returns note_id, text, payer and stratum. Deterministic for a given seed, tag and sizes.
    ``exclude`` drops those notes and any note with the same text (a disjoint sample).
    """
    rng = np.random.default_rng([seed, tag])
    pool = notes_with_payer(notes[notes.written_min >= TEST_START], stays)
    if exclude is not None:
        pool = pool[~pool.note_id.isin(set(exclude.note_id)) & ~pool.text.isin(set(exclude.text))]
    lab = labels.merge(pool[["note_id", "payer"]], on="note_id")
    picked: list[pd.DataFrame] = []
    taken: set[str] = set()
    for barrier in C.BARRIER_TYPES:
        for payer in C.PAYERS:
            ids = sorted(set(lab[(lab.barrier_type == barrier) & (lab.payer == payer)].note_id) - taken)
            chosen = list(rng.choice(ids, size=min(per_cell, len(ids)), replace=False)) if ids else []
            taken |= set(chosen)
            picked.append(pool[pool.note_id.isin(chosen)].assign(stratum=f"{barrier} | {payer}"))
    clean = pool[~pool.note_id.isin(labels.note_id)]
    worded = clean[clean.text.str.contains(BARRIER_WORDS, case=False, regex=True)]
    plain = clean[~clean.note_id.isin(worded.note_id)]
    for name, frame, k in (("no barrier, barrier words", worded, no_barrier // 2),
                           ("no barrier", plain, no_barrier - no_barrier // 2)):
        per_payer = max(1, k // len(C.PAYERS))
        for payer in C.PAYERS:
            ids = sorted(frame[frame.payer == payer].note_id)
            chosen = list(rng.choice(ids, size=min(per_payer, len(ids)), replace=False)) if ids else []
            picked.append(frame[frame.note_id.isin(chosen)].assign(stratum=f"{name} | {payer}"))
    out = pd.concat(picked, ignore_index=True)
    return out[["note_id", "stay_id", "text", "payer", "stratum"]].sort_values("note_id").reset_index(drop=True)


def sealed_sample(notes: pd.DataFrame, labels: pd.DataFrame, stays: pd.DataFrame, **sizes) -> pd.DataFrame:
    """Sample B: the same design as sample A, disjoint from it by note and by note text."""
    first = evaluation_sample(notes, labels, stays)
    return evaluation_sample(notes, labels, stays, tag=SAMPLE_B_TAG, exclude=first, **sizes)


def load_stress() -> tuple[pd.DataFrame, pd.DataFrame] | None:
    if not STRESS_NOTES.is_file():
        return None
    return pd.read_parquet(STRESS_NOTES), pd.read_parquet(STRESS_LABELS)


def demo_note_ids(days: pd.DataFrame) -> list[str]:
    """Every note on the 07:00 rounds list for both demo days (what the app shows)."""
    times = {minutes_from_start(d) + 7 * 60 for d in C.DEMO_DAYS.values()}
    return sorted(days[days.rounds_min.isin(times)].note_id.unique())


class _CachedReader:
    """Replay cached findings by note text, so the scorer can treat the cache like a reader."""

    def __init__(self, by_text: dict[str, list[dict]]):
        self.by_text = by_text

    def read(self, note_text: str) -> list[dict]:
        return self.by_text.get(note_text, [])


def _findings_by_text(cache: pd.DataFrame, texts: pd.Series) -> dict[str, list[dict]]:
    rows = cache[cache.barrier_type.notna()]
    found = {nid: [] for nid in cache.note_id.unique()}
    for r in rows.itertuples():
        found[r.note_id].append({"type": r.barrier_type, "evidence_span": (int(r.start), int(r.end)),
                                 "confidence": float(r.confidence)})
    text_of = texts.to_dict()
    return {text_of[nid]: f for nid, f in found.items() if nid in text_of}


class _AnswerReader:
    """Re-apply a guard version to the model's cached raw answers (no model call)."""

    def __init__(self, cache: pd.DataFrame, texts: pd.Series, guard: str):
        rules = RuleBasedNoteReader()
        first = cache.drop_duplicates("note_id").set_index("note_id")
        self.by_text: dict[str, list[dict]] = {}
        for nid, answer in first["answer"].items():
            text = texts.get(nid)
            if text is None or not isinstance(answer, str):
                continue
            parsed = json.loads(answer) if answer else None
            self.by_text[text] = findings_from_answer(text, parsed, {f["type"] for f in rules.read(text)},
                                                      guard=guard)

    def read(self, note_text: str) -> list[dict]:
        return self.by_text.get(note_text, [])


class _UnionReader:
    def __init__(self, a, b):
        self.a, self.b = a, b

    def read(self, note_text: str) -> list[dict]:
        out = {f["type"]: f for f in self.b.read(note_text)}
        out.update({f["type"]: f for f in self.a.read(note_text)})  # the model's span wins when both agree
        return sorted(out.values(), key=lambda f: f["evidence_span"])


def _score_all(sample: pd.DataFrame, lab: pd.DataFrame, rows: pd.DataFrame, texts: pd.Series, common: dict) -> dict:
    llm = _CachedReader(_findings_by_text(rows, texts))
    rules = RuleBasedNoteReader()
    out = {
        "llm": {**score_note_reader(sample, lab, reader=llm), **common},
        "rules": {**score_note_reader(sample, lab, reader=rules), **common},
        "combined": {**score_note_reader(sample, lab, reader=_UnionReader(llm, rules)), **common},
    }
    if "answer" in rows and rows["answer"].notna().any():
        out["llm_checks_g1"] = {**score_note_reader(sample, lab, reader=_AnswerReader(rows, texts, "g1")), **common}
    return out


def evaluate_cache(cache: pd.DataFrame, notes: pd.DataFrame, labels: pd.DataFrame, stays: pd.DataFrame) -> dict:
    """Precision, recall and F1 for the model, the rules and their union on the cached sample.

    Also, when the cache holds them, the same model answers under the old checks (g1) and the
    scores on the new-phrasing stress set (``stress``).
    """
    sample_ids = set(cache[cache.purpose.str.contains("evaluation")].note_id)  # includes demo+evaluation
    sample = notes_with_payer(notes[notes.note_id.isin(sample_ids)], stays)
    llm_rows = cache[cache.note_id.isin(sample_ids) & (cache.status == "llm")]
    fallback_n = int(cache[cache.note_id.isin(sample_ids) & (cache.status != "llm")].note_id.nunique())
    sample = sample[sample.note_id.isin(set(llm_rows.note_id))]  # score only notes the model actually read
    lab = labels[labels.note_id.isin(set(sample.note_id))]
    meta = cache.iloc[0] if len(cache) else None
    common = {"sample_n": int(len(sample)), "sample_labelled_barriers": int(len(lab)),
              "sample_fallback_notes": fallback_n,
              "sample": "B (sealed)" if "guard_version" in cache else "A",
              "model": None if meta is None else str(meta.model),
              "prompt_version": None if meta is None else str(meta.prompt_version),
              "guard_version": str(meta.guard_version) if meta is not None and "guard_version" in cache else "g1"}
    out = _score_all(sample, lab, llm_rows, notes.set_index("note_id").text, common)
    stress = load_stress()
    st_rows = cache[(cache.purpose == "stress") & (cache.status == "llm")]
    if stress is not None and len(st_rows):
        st_notes, st_labels = stress
        st_sample = st_notes[st_notes.note_id.isin(set(st_rows.note_id))]
        st_lab = st_labels[st_labels.note_id.isin(set(st_sample.note_id))]
        st_common = {**common, "sample_n": int(len(st_sample)), "sample_labelled_barriers": int(len(st_lab)),
                     "sample": "new-phrasing stress set"}
        out["stress"] = _score_all(st_sample, st_lab, st_rows, st_notes.set_index("note_id").text, st_common)
    return out


def load_cache() -> pd.DataFrame | None:
    return pd.read_parquet(CACHE) if CACHE.is_file() else None
