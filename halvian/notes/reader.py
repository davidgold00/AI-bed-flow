"""Read discharge barriers from synthetic notes and score the detected spans.

``RuleBasedNoteReader`` is the fast full-year reader (the discharge model's feature source).
``LLMNoteReader`` is the AI note reader: a local language model with the rules as fallback.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from typing import Protocol, TypedDict

import pandas as pd

from halvian import config as C

PLACEHOLDER_LABEL = "Placeholder: rule-based stand-in for the LLM note reader."  # rule findings only
READER_LABEL = "AI note reader (local language model) with a rule-based fallback."

# Local rule settings until they are available in halvian.config. Confidence
# describes the strength of a text match and is not an estimated probability.
_CONTEXT_WORDS = 6
_EXPLICIT_CONFIDENCE = 0.90
_CONTEXTUAL_CONFIDENCE = 0.75


class BarrierFinding(TypedDict):
    type: str
    evidence_span: tuple[int, int]
    confidence: float


class NoteReader(Protocol):
    """Return one finding per active barrier, using half-open character offsets."""

    def read(self, note_text: str) -> list[BarrierFinding]: ...


_NEED = r"(?:needs?|needing|requires?|still needs?)"
_WAIT = r"(?:awaiting|waiting (?:for|on)|pending|working on)"
_HOME = r"(?:hh|vna|home (?:health|nursing|care(?: services)?))"
_PLACEMENT = r"(?:snf|ltach|(?:acute )?rehab|placement|nursing (?:home|facility)|skilled nursing)"
_AUTH = r"(?:(?:insurance|ins|prior) auth(?:orization)?|auth(?:orization)?|payer approval|coverage application)"
_FAMILY = r"(?:dtr|daughter|son|family|spouse|wife|husband|caregiver)"
_RIDE = r"(?:ride(?: home)?|(?:medical )?transport(?:ation)?(?: home)?|wheelchair van)"
_MED = r"(?:dme|home (?:o2|oxygen)|(?:hospital )?bed delivery|nebulizer|(?:specialty )?med(?:ication)?s?|rx|prescriptions?)"
_PENDING = r"(?:pending|outstanding|not (?:yet )?(?:arranged|accepted|confirmed|received|delivered|available)|(?:hasn['’]?t|has not) confirmed)"
_CLAUSE = re.compile(r"[^,;.!?\n]+")
_CONTRAST = re.compile(r"\b(?:but|however|although|whereas)\b", re.IGNORECASE)
_NEGATION = re.compile(
    r"\b(?:no|denies|denied|without|does not|doesn['’]?t|do not|don['’]?t)"
    r"\s+(?:(?:evidence|sign|history)\s+of\s+)?(?:need(?:s|ing)?\s+(?:for\s+)?)?$",
    re.IGNORECASE,
)
_RESOLUTION = re.compile(
    r"^\s+(?:(?:is|was|already|now|has been)\s+)*(?:confirmed|arranged|set up|obtained|"
    r"approved|received|delivered|booked|accepted|filled|resolved|not (?:needed|required))\b",
    re.IGNORECASE,
)
_NON_DISCHARGE_TRANSPORT = re.compile(
    r"^\s+to\s+(?:mri|ct|imaging|radiology|x[- ]?ray|ultrasound|procedure)\b", re.IGNORECASE
)

# Strong patterns express an open task. Contextual patterns depend on shorthand
# cues that have a more limited meaning in these synthetic notes.
_RULES = {
    "home_care": (
        (
            rf"{_NEED}\s+{_HOME}(?:\s+set up before (?:dc|d/c|discharge))?",
            rf"{_WAIT}\s+{_HOME}(?:\s+start date)?",
            rf"{_HOME}(?:\s+(?:referral|agency|services))?\s+{_PENDING}",
        ),
        (),
    ),
    "transport": (
        (
            rf"(?:no|has no)\s+{_RIDE}\b(?!\s+(?:issues?|concerns?|needed|required))",
            rf"{_RIDE}\s+{_PENDING}",
            rf"{_NEED}\s+{_RIDE}",
            rf"{_WAIT}\s+{_RIDE}",
        ),
        (),
    ),
    "placement": (
        (
            rf"{_NEED}\s+{_PLACEMENT}",
            rf"{_WAIT}\s+{_PLACEMENT}(?:\s+bed)?",
            rf"{_PLACEMENT}(?:\s+(?:bed|placement|referral))?\s+{_PENDING}",
            rf"no\s+{_PLACEMENT}\s+bed\s+yet",
            rf"awaiting bed offer from\s+{_PLACEMENT}",
        ),
        (r"(?:pt|ot) recs? acute rehab",),
    ),
    "family_pickup": (
        (
            rf"{_FAMILY}\s+(?:can['’]?t|cannot|unable to)\s+(?:pick up|take (?:pt|patient) home|drive)(?:\s+until\s+\w+)?",
            rf"{_FAMILY}\s+out of town",
            r"no one to pick up(?:\s+until\s+\w+)?",
            rf"waiting (?:for|on)\s+{_FAMILY}(?:\s+\w+)?",
        ),
        (),
    ),
    "insurance_auth": (
        (
            rf"{_WAIT}\s+{_AUTH}",
            rf"{_AUTH}\s+{_PENDING}",
        ),
        (),
    ),
    "meds_equipment": (
        (
            rf"{_WAIT}\s+{_MED}(?:\s+delivery)?",
            rf"{_MED}(?:\s+delivery)?\s+(?:{_PENDING}|not in stock)",
            r"pharmacy\s+(?:can['’]?t|cannot|unable to)\s+fill\s+(?:the\s+)?(?:rx|prescription)",
        ),
        (rf"{_NEED}\s+{_MED}\s+(?:at|for)\s+home",),
    ),
}
_COMPILED_RULES = {
    barrier: tuple(
        (re.compile(r"\b(?:" + "|".join(phrases) + r")\b", re.IGNORECASE), confidence)
        for phrases, confidence in zip(groups, (_EXPLICIT_CONFIDENCE, _CONTEXTUAL_CONFIDENCE), strict=True)
        if phrases
    )
    for barrier, groups in _RULES.items()
}


def _clauses(text: str):
    for match in _CLAUSE.finditer(text):
        clause = match.group()
        start = 0
        for split in _CONTRAST.finditer(clause):
            yield match.start() + start, clause[start:split.start()]
            start = split.end()
        yield match.start() + start, clause[start:]


def _suppressed(clause: str, match: re.Match, barrier: str) -> bool:
    before = " ".join(clause[:match.start()].split()[-_CONTEXT_WORDS:])
    after = " ".join(clause[match.end():].split()[:_CONTEXT_WORDS])
    following = f" {after}" if after else ""
    if _NEGATION.search(f"{before} ") or _RESOLUTION.match(following):
        return True
    return barrier == "transport" and bool(_NON_DISCHARGE_TRANSPORT.match(following))


_RESOLUTION_REFERENCE = re.compile(
    r"^\s*(?:got it|it was|it is|this was)\s+(?:arranged|confirmed|obtained|resolved)\b",
    re.IGNORECASE,
)


class RuleBasedNoteReader:
    """Detect explicit barriers in synthetic note text and return the evidence spans."""

    def read(self, note_text: str) -> list[BarrierFinding]:
        findings: dict[str, BarrierFinding] = {}
        clauses = list(_clauses(note_text))
        for index, (offset, clause) in enumerate(clauses):
            if index + 1 < len(clauses) and _RESOLUTION_REFERENCE.match(clauses[index + 1][1]):
                continue
            for barrier, rules in _COMPILED_RULES.items():
                for rule, confidence in rules:
                    for match in rule.finditer(clause):
                        if _suppressed(clause, match, barrier):
                            continue
                        candidate: BarrierFinding = {
                            "type": barrier,
                            "evidence_span": (offset + match.start(), offset + match.end()),
                            "confidence": confidence,
                        }
                        current = findings.get(barrier)
                        if current is None or confidence > current["confidence"]:
                            findings[barrier] = candidate
        return sorted(findings.values(), key=lambda item: item["evidence_span"])

    def read_many(self, texts: Iterable[str]) -> list[list[BarrierFinding]]:
        """Read a batch in input order using the same character offset rules."""
        return [self.read(text) for text in texts]


_RESOLVED_WORDS = re.compile(
    r"\b(?:confirmed|arranged|set up|obtained|approved|received|delivered|booked|accepted|filled|in hand|"
    r"resolved|picking up)\b", re.IGNORECASE)
_OPEN_WORDS = re.compile(
    r"\b(?:not|no|hasnt|cant|pending|awaiting|waiting|until|yet|unable|outstanding|needs?|needing|requires?|"
    r"before)\b|n['’]t\b", re.IGNORECASE)
_NO_NEED = re.compile(
    r"^\s*(?:no|denies|declines|does not|doesn['’]?t)\b(?!.*\buntil\b).*"
    r"\b(?:issues?|needs?|needed|required|barriers?|concerns?)\b", re.IGNORECASE)
_IMAGING = re.compile(r"\bto\s+(?:mri|ct|imaging|radiology|x[- ]?ray|ultrasound|procedure)\b", re.IGNORECASE)


def locate_evidence(text: str, evidence: str) -> tuple[int, int] | None:
    """Character offsets of ``evidence`` in ``text`` (verbatim, ignoring letter case), or None."""
    ev = evidence.strip().strip("\"'`").strip().rstrip(".,;:")
    if len(ev) < 3:
        return None
    i = text.find(ev)
    if i < 0:
        i = text.lower().find(ev.lower())
    return (i, i + len(ev)) if i >= 0 else None


def span_is_inactive(text: str, start: int, end: int, barrier: str) -> bool:
    """True if the evidence reads as resolved, negated or not about discharge (the rules' own checks)."""
    ev = text[start:end]
    if _NO_NEED.search(ev) or (_RESOLVED_WORDS.search(ev) and not _OPEN_WORDS.search(ev)):
        return True
    if barrier == "transport" and _IMAGING.search(ev):
        return True
    for offset, clause in _clauses(text):
        if offset <= start < offset + len(clause):
            before = " ".join(text[offset:start].split()[-_CONTEXT_WORDS:])
            after = " ".join(text[end:offset + len(clause)].split()[:_CONTEXT_WORDS])
            following = f" {after}" if after else ""
            if _NEGATION.search(f"{before} ") or _RESOLUTION.match(following):
                return True
            return barrier == "transport" and bool(_NON_DISCHARGE_TRANSPORT.match(following))
    return False


# ----------------------------------------------------------------------------- AI reader checks
# g1: verbatim evidence, plus the rules' negation and resolution checks.
# g2: g1, plus the evidence's own clause must name the barrier's subject and say the task is still
#     open. A finding the model gave the wrong type is relabelled to the one type its words name.
#     Designed on training-month notes only (two independent development draws).
GUARD_VERSION = "g2"

_SUBJECT_WORDS = {
    "placement": ("snf", "rehab", "ltach", "ltac", "placement", "facility", "nursing home", "skilled nursing",
                  "assisted living", "alf", "long term care", "ltc", "group home", "bed offer", "acceptance",
                  "accepting", "hospice"),
    "home_care": ("hh", "home health", "vna", "home nursing", "home care", "home services", "home pt",
                  "home infusion", "visiting nurse", "home aide", "hospice"),
    "insurance_auth": ("auth", "authorization", "insurance", "ins", "payer", "coverage", "medicaid", "medicare",
                       "precert", "benefits", "financial counselor"),
    "family_pickup": ("family", "daughter", "dtr", "son", "wife", "husband", "spouse", "partner", "caregiver",
                      "mother", "mom", "father", "dad", "sister", "brother", "niece", "nephew", "friend",
                      "neighbor", "relative", "pick up", "pickup", "no one"),
    "transport": ("ride", "transport", "transportation", "van", "wheelchair van", "ambulance", "cab", "taxi", "bus",
                  "driver", "car", "stretcher", "medicab", "way home"),
    "meds_equipment": ("rx", "prescription", "prescriptions", "pharmacy", "meds", "med", "medication",
                       "medications", "dme", "walker", "wheelchair", "hospital bed", "commode", "nebulizer", "neb",
                       "cpap", "bipap", "concentrator", "oxygen", "o2", "supplies", "insulin", "glucometer",
                       "wound vac", "cane", "crutches", "brace", "equipment", "delivery", "in stock"),
}
_OPEN_TASK_WORDS = ("pending", "awaiting", "waiting", "wait", "need", "needs", "needed", "needing", "require",
                    "requires", "required", "until", "cant", "cannot", "unable", "hasnt", "no", "none", "not",
                    "outstanding", "unavailable", "sent", "working", "denied", "appeal", "backordered", "delayed",
                    "away", "out of town")
_SUBJECT_FIRST = "insurance_auth"  # an approval still pending for any service is the insurance task
_ANCHORS = sorted(((t, tuple(a.split())) for t, ws in _SUBJECT_WORDS.items() for a in ws), key=lambda x: -len(x[1]))


def _tokens(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", s.lower().replace("'", "").replace("\u2019", ""))


def _close(a: str, b: str) -> bool:
    """Equal, or one typo apart: a missing or extra letter (4+ letters) or a swap or wrong letter (5+)."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1 or max(len(a), len(b)) < 4 or min(len(a), len(b)) < 3:
        return False
    if len(a) == len(b):
        if len(a) < 5:
            return False  # "meds" and "neds" are different words
        d = [i for i in range(len(a)) if a[i] != b[i]]
        return len(d) == 1 or (len(d) == 2 and d[1] == d[0] + 1 and a[d[0]] == b[d[1]] and a[d[1]] == b[d[0]])
    short, long_ = (a, b) if len(a) < len(b) else (b, a)
    i = 0
    while i < len(short) and short[i] == long_[i]:
        i += 1
    return short[i:] == long_[i + 1:]


def barrier_subjects(text: str) -> set[str]:
    """Barrier types whose subject words (typo-tolerant) appear in ``text``; longer phrases win."""
    toks = _tokens(text)
    used = [False] * len(toks)
    found: set[str] = set()
    for barrier, words in _ANCHORS:
        n = len(words)
        for i in range(len(toks) - n + 1):
            if any(used[i:i + n]):
                continue
            if all(_close(toks[i + k], words[k]) for k in range(n)):
                found.add(barrier)
                if n > 1:
                    used[i:i + n] = [True] * n
    return found


def says_open(text: str) -> bool:
    """True if ``text`` says a task is still open (pending, awaiting, needs, until, can't, not yet...)."""
    toks = _tokens(text)
    for phrase in _OPEN_TASK_WORDS:
        words = phrase.split()
        for i in range(len(toks) - len(words) + 1):
            if all(_close(toks[i + k], w) if len(w) >= 4 else toks[i + k] == w for k, w in enumerate(words)):
                return True
    return False


def _qualifies(clause: str) -> set[str]:
    return barrier_subjects(clause) if says_open(clause) else set()


def check_open_task(text: str, span: tuple[int, int], barrier: str) -> tuple[str, tuple[int, int]] | None:
    """Guard g2: (barrier type, span) to keep, or None to drop.

    A clause the evidence touches must name a barrier subject and say the task is open. If the
    evidence's clause says it is open but names no subject ("none avail until Sun"), the clause
    just before it in the same sentence may supply the subject when it qualifies on its own,
    and the span grows to include it. The model's type is kept when the words support it,
    otherwise relabelled to the single type they name.
    """
    parts = list(_clauses(text))
    idx = [k for k, (o, c) in enumerate(parts) if o < span[1] and o + len(c) > span[0]]
    subjects: set[str] = set()
    for k in idx:
        subjects |= _qualifies(parts[k][1])
    if not subjects and idx and idx[0] > 0:
        prev_off, prev = parts[idx[0] - 1]
        gap = text[prev_off + len(prev):parts[idx[0]][0]]
        if gap.strip() == "," and says_open(parts[idx[0]][1]):
            subjects = _qualifies(prev)
            if subjects:
                span = (prev_off + len(prev) - len(prev.lstrip()), span[1])
    if not subjects:
        return None
    if _SUBJECT_FIRST in subjects and barrier in ("placement", "home_care", "meds_equipment"):
        return _SUBJECT_FIRST, span
    if barrier in subjects:
        return barrier, span
    if len(subjects) == 1:
        return next(iter(subjects)), span
    if _SUBJECT_FIRST in subjects:
        return _SUBJECT_FIRST, span
    return None


def findings_from_answer(text: str, answer: dict | None, rule_types: set[str], *, guard: str = GUARD_VERSION,
                         stats: Counter | None = None) -> list[BarrierFinding]:
    """Turn the model's JSON answer into verified findings under a guard version ("g1" or "g2")."""
    stats = stats if stats is not None else Counter()
    found: dict[str, BarrierFinding] = {}
    items = answer.get("barriers", []) if isinstance(answer, dict) else []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        barrier, status = item.get("barrier_type"), item.get("status")
        stats["model_items"] += 1
        if barrier not in C.BARRIER_TYPES or status != "active":
            stats["not_active"] += 1
            continue
        span = locate_evidence(text, str(item.get("evidence", "")))
        if span is None:
            stats["evidence_not_in_note"] += 1
            continue
        if span_is_inactive(text, span[0], span[1], barrier):
            stats["negated_or_resolved"] += 1
            continue
        if guard == "g2":
            checked = check_open_task(text, span, barrier)
            if checked is None:
                stats["no_open_task_named"] += 1
                continue
            if checked[0] != barrier:
                stats["relabelled"] += 1
            barrier, span = checked
        if barrier not in found:
            conf = C.LLM_CONFIDENCE_AGREE if barrier in rule_types else C.LLM_CONFIDENCE_ALONE
            found[barrier] = {"type": barrier, "evidence_span": span, "confidence": conf}
            stats["kept"] += 1
    return sorted(found.values(), key=lambda f: f["evidence_span"])


class LLMNoteReader:
    """AI note reader: a local language model (Ollama on this machine) with a rule-based fallback.

    The model returns each barrier it sees with a status (active, resolved or negated) and a
    quoted evidence phrase, under a JSON schema, at temperature 0 with a fixed seed. A finding
    is kept only if it is active, its evidence appears verbatim in the note (offsets are taken
    from that match, never from the model), the rules' negation and resolution checks do not
    contradict it, and its clause names the barrier's subject and says the task is open (guard
    g2). If the server is down, the call times out or the output is not valid, the rule-based
    reader answers instead and ``read_detailed`` says so. No cloud calls, no keys.
    ``last_answer`` keeps the model's raw JSON for the audit trail.
    """

    def __init__(self, model: str = C.LLM_MODEL, timeout_s: float = C.LLM_TIMEOUT_S,
                 fallback: NoteReader | None = None, guard: str = GUARD_VERSION):
        self.model, self.timeout_s, self.guard = model, timeout_s, guard
        self.fallback = fallback if fallback is not None else RuleBasedNoteReader()
        self.stats: Counter = Counter()
        self.last_answer: dict | None = None

    def read_detailed(self, note_text: str) -> tuple[list[BarrierFinding], str, str]:
        """Return (findings, status, detail). Status is "llm", or "fallback" with the reason in detail."""
        from halvian.notes.ollama import OllamaUnavailable, chat_json
        from halvian.notes.prompt import SCHEMA, messages

        self.last_answer = None
        text = note_text if isinstance(note_text, str) else ""
        rules = self.fallback.read(text)
        if not text.strip():
            return [], "llm", ""
        try:
            raw = chat_json(messages(text), SCHEMA, model=self.model, timeout_s=self.timeout_s)
        except OllamaUnavailable as exc:
            self.stats["fallback"] += 1
            msg = str(exc).lower()
            reason = ("local model timed out" if "timed out" in msg else
                      f"{self.model} is not installed" if ("404" in msg or "not found" in msg) else
                      "local model not running")
            return rules, "fallback", reason
        except (ValueError, KeyError, TypeError):
            self.stats["fallback"] += 1
            return rules, "fallback", "model output was not valid"
        self.last_answer = raw if isinstance(raw, dict) else None
        found = findings_from_answer(text, raw, {f["type"] for f in rules}, guard=self.guard, stats=self.stats)
        return found, "llm", ""

    def read(self, note_text: str) -> list[BarrierFinding]:
        return self.read_detailed(note_text)[0]


def _metrics(counts: Counter, notes: int) -> dict[str, int | float | None]:
    tp, fp, fn = (counts[key] for key in ("tp", "fp", "fn"))
    return {
        "notes": notes,
        "support": tp + fn,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "f1": 2 * tp / (2 * tp + fp + fn) if tp + fp + fn else None,
    }


def score_note_reader(
    notes: pd.DataFrame, labels: pd.DataFrame, *, reader: NoteReader | None = None
) -> dict:
    """Score note × barrier predictions against note_labels.parquet records.

    Pass all notes, including negatives. Notes need note_id and text. An optional
    payer column (joined through stay_id) enables payer-level scores. Labels
    contain note_id and barrier_type. Metrics use pooled counts within each
    group. An undefined metric is returned as None.
    """
    if notes["note_id"].isna().any() or notes["note_id"].duplicated().any():
        raise ValueError("Each note needs one unique note ID.")
    if not labels["note_id"].isin(notes["note_id"]).all():
        raise ValueError("Labels include note IDs missing from the corpus.")
    if not labels["barrier_type"].isin(C.BARRIER_TYPES).all():
        raise ValueError("Labels contain unknown barrier types.")

    expected = labels.groupby("note_id")["barrier_type"].agg(set).to_dict()
    by_type: dict[str, Counter] = {barrier: Counter() for barrier in C.BARRIER_TYPES}
    by_payer: dict[str, Counter] = defaultdict(Counter)
    payer_notes: Counter = Counter()
    overall: Counter = Counter()
    reader = reader if reader is not None else RuleBasedNoteReader()
    columns = notes[["note_id", "text"]].assign(payer=notes.get("payer"))

    for note_id, text, payer in columns.itertuples(index=False, name=None):
        truth = expected.get(note_id, set())
        found = {hit["type"] for hit in reader.read(text if pd.notna(text) else "")}
        events = (
            ("tp", truth & found),
            ("fp", found - truth),
            ("fn", truth - found),
        )
        if pd.notna(payer):
            payer_notes[payer] += 1
        for key, barriers in events:
            for barrier in barriers:
                by_type[barrier][key] += 1
            overall[key] += len(barriers)
            if pd.notna(payer):
                by_payer[payer][key] += len(barriers)

    return {
        "overall": _metrics(overall, len(notes)),
        "by_barrier": {barrier: _metrics(counts, len(notes)) for barrier, counts in by_type.items()},
        "by_payer": {payer: _metrics(by_payer[payer], payer_notes[payer]) for payer in sorted(payer_notes)},
    }
