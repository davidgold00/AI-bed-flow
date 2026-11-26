"""Run the AI note reader (a local model via Ollama) on the evaluation sample and the demo-day notes.

    python scripts/run_llm_reader.py              # measure, size, run, cache and evaluate
    python scripts/run_llm_reader.py --measure-only

Steps: check the local server and model, time a small batch of training-month notes (never
the evaluation sample), size the evaluation sample so the whole run fits the budget
(config.LLM_EVAL_BUDGET_MIN), read the demo-day notes, the new-phrasing stress set and the
sealed evaluation sample B, cache every result in models/llm_note_findings.parquet with the
model name, prompt and guard versions, the model's raw answer and the time, then score the
model, the rules and their union and write them to models/metrics.json under note_reader.
The previous run's scores move to note_reader.history and its cache to
models/llm_note_findings_<version>.parquet. A checkpoint file lets an interrupted run resume.
Identical note texts are read once.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from halvian import config as C  # noqa: E402
from halvian.notes import evaluate as E  # noqa: E402
from halvian.notes.ollama import OllamaUnavailable, installed_models  # noqa: E402
from halvian.notes.prompt import PROMPT_ID  # noqa: E402
from halvian.notes.reader import GUARD_VERSION, LLMNoteReader  # noqa: E402

DATA, MODELS = ROOT / "data", ROOT / "models"
PARTIAL = MODELS / "llm_note_findings.partial.parquet"
WHY_MODEL = ("This Mac has {ram} GB of RAM. The team plan uses llama3.2:3b-instruct below 16 GB "
             "(llama3.1:8b and qwen2.5:7b would be compared only with 16 GB or more).")


def ram_gb() -> int:
    import subprocess

    try:
        return round(int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True,
                                        check=True).stdout) / 2**30)
    except (OSError, ValueError, subprocess.CalledProcessError):
        return 0


def read_rows(reader: LLMNoteReader, note_id: str, text: str, purpose: str) -> tuple[list[dict], float]:
    t0 = time.perf_counter()
    findings, status, detail = reader.read_detailed(text)
    if status != "llm":  # one retry after a timeout or a malformed answer
        time.sleep(2)
        findings, status, detail = reader.read_detailed(text)
    ms = (time.perf_counter() - t0) * 1000
    base = {"note_id": note_id, "purpose": purpose, "status": status, "detail": detail, "model": C.LLM_MODEL,
            "prompt_version": PROMPT_ID, "guard_version": GUARD_VERSION,
            "answer": json.dumps(reader.last_answer) if reader.last_answer is not None else None,
            "read_at": datetime.now(UTC).isoformat(timespec="seconds"), "latency_ms": round(ms, 1)}
    if not findings:
        return [{**base, "barrier_type": None, "start": None, "end": None, "evidence": None,
                 "confidence": None}], ms
    return [{**base, "barrier_type": f["type"], "start": int(f["evidence_span"][0]),
             "end": int(f["evidence_span"][1]), "evidence": text[f["evidence_span"][0]:f["evidence_span"][1]],
             "confidence": float(f["confidence"])} for f in findings], ms


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--measure-only", action="store_true")
    ap.add_argument("--budget-min", type=float, default=C.LLM_EVAL_BUDGET_MIN)
    args = ap.parse_args()
    t_start = time.perf_counter()

    try:
        names = installed_models(timeout_s=2)
    except OllamaUnavailable:
        sys.exit("Ollama is not running. Start it with `ollama serve`, then `ollama pull " + C.LLM_MODEL + "`.")
    if C.LLM_MODEL not in names:
        sys.exit(f"Model {C.LLM_MODEL} is not installed. Run `ollama pull {C.LLM_MODEL}`.")

    notes = pd.read_parquet(DATA / "notes.parquet")
    labels = pd.read_parquet(DATA / "note_labels.parquet")
    stays = pd.read_parquet(DATA / "inpatient_stays.parquet", columns=["stay_id", "payer"])
    days = pd.read_parquet(DATA / "inpatient_days.parquet", columns=["note_id", "rounds_min"])
    stress = E.load_stress()
    stress_ids = [] if stress is None else list(stress[0].note_id)
    text_of = notes.set_index("note_id").text
    if stress is not None:
        text_of = pd.concat([text_of, stress[0].set_index("note_id").text])
    reader = LLMNoteReader()

    # ---- warm up and time a small batch from the training months (never the evaluation sample)
    print(f"Model {C.LLM_MODEL}, prompt {PROMPT_ID}. Loading the model...")
    reader.read_detailed("pt resting comfortably, awaiting rehab bed")
    sample_full = E.sealed_sample(notes, labels, stays)
    dev_pool = notes[(notes.written_min < E.TEST_START) & ~notes.note_id.isin(sample_full.note_id)]
    dev = dev_pool.sample(40, random_state=7)
    secs = []
    for t in dev.text:
        t0 = time.perf_counter()
        reader.read_detailed(t)
        secs.append(time.perf_counter() - t0)
    per_note = float(np.mean(secs))
    print(f"Measured {len(secs)} training-month notes: {per_note:.2f} s per note (median {np.median(secs):.2f}).")

    demo_ids = E.demo_note_ids(days)
    budget_s = args.budget_min * 60 * 0.85 - (time.perf_counter() - t_start)  # keep 15% headroom
    demo_texts = text_of.loc[demo_ids].nunique()
    room = max(0, int(budget_s / per_note) - demo_texts - len(stress_ids))
    scale = min(1.0, room / max(sample_full.text.nunique(), 1))
    sample = sample_full if scale >= 1 else E.sealed_sample(
        notes, labels, stays, per_cell=max(5, int(C.LLM_EVAL_PER_CELL * scale)),
        no_barrier=max(50, int(C.LLM_EVAL_NO_BARRIER * scale)))
    est_min = (demo_texts + len(stress_ids) + sample.text.nunique()) * per_note / 60
    print(f"Plan: {len(demo_ids)} demo-day notes ({demo_texts} unique texts) + {len(stress_ids)} stress notes + "
          f"{len(sample)} evaluation notes ({sample.text.nunique()} unique) = about {est_min:.0f} min.")
    sizing = {"measured_notes": len(secs), "measured_s_per_note": round(per_note, 3),
              "budget_min": args.budget_min, "sample_scale": round(scale, 3), "estimated_min": round(est_min, 1)}
    if args.measure_only:
        print(json.dumps(sizing, indent=1))
        return

    # ---- read: demo notes first (the app needs them), then the sample; resume from a checkpoint
    purpose = {nid: "demo" for nid in demo_ids}
    purpose.update({nid: "stress" for nid in stress_ids})
    for nid in sample.note_id:
        purpose[nid] = "demo+evaluation" if nid in purpose else "evaluation"
    order = demo_ids + stress_ids + [n for n in sample.note_id if n not in set(demo_ids)]
    rows: list[dict] = []
    done: set[str] = set()
    if PARTIAL.is_file():
        prev = pd.read_parquet(PARTIAL)
        if (len(prev) and prev.prompt_version.iloc[0] == PROMPT_ID and prev.model.iloc[0] == C.LLM_MODEL
                and "guard_version" in prev and prev.guard_version.iloc[0] == GUARD_VERSION):
            rows = prev.to_dict(orient="records")
            done = set(prev.note_id)
            print(f"Resuming: {len(done)} notes already read.")
    by_text: dict[str, list[dict]] = {}
    for r in rows:
        by_text.setdefault(text_of[r["note_id"]], []).append(r)
    t_run = time.perf_counter()
    for k, nid in enumerate(order, start=1):
        if nid in done:
            continue
        text = text_of[nid]
        if text in by_text:  # identical text already read: reuse the model's answer
            rows += [{**r, "note_id": nid, "purpose": purpose[nid]} for r in by_text[text]]
        else:
            new, _ = read_rows(reader, nid, text, purpose[nid])
            by_text[text] = new
            rows += new
        if k % 100 == 0:
            pd.DataFrame(rows).to_parquet(PARTIAL, index=False)
            rate = (time.perf_counter() - t_run) / max(1, k - len(done))
            print(f"  {k}/{len(order)} notes, {rate:.2f} s per note, about "
                  f"{(len(order) - k) * rate / 60:.0f} min left", flush=True)
    cache = pd.DataFrame(rows)
    cache["purpose"] = cache.note_id.map(purpose)
    old = E.load_cache()
    if old is not None:  # keep the previous run's cache for the audit trail
        tag = f"{old.prompt_version.iloc[0]}_{old.guard_version.iloc[0] if 'guard_version' in old else 'g1'}"
        if tag != f"{PROMPT_ID}_{GUARD_VERSION}":
            old.to_parquet(MODELS / f"llm_note_findings_{tag}.parquet", index=False, compression="zstd")
    cache.to_parquet(E.CACHE, index=False, compression="zstd")
    PARTIAL.unlink(missing_ok=True)
    wall = (time.perf_counter() - t_start) / 60
    print(f"Cached {cache.note_id.nunique()} notes in {E.CACHE.relative_to(ROOT)} ({wall:.1f} min).")

    # ---- evaluate and record
    scores = E.evaluate_cache(cache, notes, labels, stays)
    metrics_path = MODELS / "metrics.json"
    metrics = json.loads(metrics_path.read_text())
    nr = metrics.setdefault("note_reader", {})
    if "llm" in nr and "llm_run" in nr:  # move the previous AI reader run into the history
        prev_id = f"{nr['llm_run']['prompt_version']}+{nr['llm_run'].get('guard_version', 'g1')}"
        if prev_id != f"{PROMPT_ID}+{GUARD_VERSION}":
            history = nr.setdefault("history", [])
            history.append({"reader": prev_id, "sample": nr["llm"].get("sample", "A"),
                            "sample_n": nr["llm"]["sample_n"], "wall_minutes": nr["llm_run"].get("wall_minutes"),
                            **{who: {"overall": nr[who]["overall"], "by_barrier": nr[who]["by_barrier"],
                                     "by_payer": nr[who]["by_payer"]}
                               for who in ("llm", "rules", "combined") if who in nr}})
    nr.update(scores)
    nr["llm_run"] = {
        "model": C.LLM_MODEL, "display_name": C.LLM_DISPLAY_NAME, "prompt_version": PROMPT_ID,
        "guard_version": GUARD_VERSION, "stress_notes": len(stress_ids),
        "why_this_model": WHY_MODEL.format(ram=ram_gb()), "temperature": C.LLM_TEMPERATURE, "seed": C.LLM_SEED,
        "notes_read": int(cache.note_id.nunique()), "unique_texts_read": len(by_text),
        "demo_notes": len(demo_ids), "evaluation_notes": int(len(sample)),
        "fallback_notes": int(cache[cache.status != "llm"].note_id.nunique()),
        "wall_minutes": round(wall, 1), "sizing": sizing, "guard_counts": dict(reader.stats),
        "finished_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    metrics_path.write_text(json.dumps(metrics, indent=1))
    for label, block in (("sample B", scores), ("stress set", scores.get("stress", {}))):
        for who in ("llm", "llm_checks_g1", "rules", "combined"):
            if who in block:
                o = block[who]["overall"]
                print(f"{label}: {who:14s} precision {o['precision']:.3f} recall {o['recall']:.3f} "
                      f"F1 {o['f1']:.3f} (n={block[who]['sample_n']})")


if __name__ == "__main__":
    main()
