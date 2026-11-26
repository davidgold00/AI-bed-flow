"""Synthetic inpatient notes with separately stored ground-truth barrier labels.

Each inpatient gets one short, typed, shorthand note per day (written before 07:00
rounds). Notes mix clinical status, mobility, discharge-barrier statements, resolved or
negated barriers ("ride confirmed", "no barriers to dc") and distractors that reuse
barrier words innocently ("transport to MRI this am"). Some words carry typos. A barrier
is not always written down, and it is usually documented only after case management has
identified it, so a reader cannot be perfect.

Ground truth (which barrier types the note asserts as active) is returned separately and
saved to ``note_labels.parquet``. It is never used as a model feature.

Everything here is synthetic text produced from templates. No real notes were used.
"""

from __future__ import annotations

import numpy as np

DAY_ABBR = ("Mon", "Tues", "Wed", "Thurs", "Fri", "Sat", "Sun")

ACTIVE = {
    "placement": [
        "SNF placement pending",
        "awaiting rehab bed",
        "needs SNF, referrals sent",
        "PT recs acute rehab, awaiting acceptance",
        "case mgmt working on SNF placement",
        "awaiting bed offer from rehab facility",
        "LTACH referral pending",
        "needs placement, no SNF bed yet",
    ],
    "home_care": [
        "needs HH set up before dc",
        "home health referral pending",
        "awaiting HH start date",
        "needs home nursing, not yet arranged",
        "VNA referral not yet accepted",
        "home care services not arranged",
        "HH agency hasnt confirmed",
    ],
    "insurance_auth": [
        "awaiting insurance auth for SNF",
        "prior auth pending for rehab",
        "ins auth pending",
        "waiting on payer approval for dc plan",
        "auth not yet received",
        "coverage application pending, needed for dc plan",
    ],
    "family_pickup": [
        "dtr can't pick up until {day}",
        "family unable to take pt home until {day}",
        "son out of town, back {day}",
        "no one to pick up until {day}",
        "spouse can't drive, waiting on family {day}",
    ],
    "transport": [
        "no ride until {day}",
        "needs wheelchair van, none avail until {day}",
        "transport home not arranged",
        "no transportation home",
        "awaiting medical transport",
        "pt has no ride home",
    ],
    "meds_equipment": [
        "waiting on DME delivery (walker)",
        "home O2 not delivered yet",
        "pharmacy can't fill rx until tmrw",
        "awaiting hospital bed delivery for home",
        "needs nebulizer at home, pending",
        "specialty med not in stock, pending",
    ],
}
RESOLVED = {
    "placement": ["SNF bed accepted for {day}", "rehab accepted pt", "placement confirmed"],
    "home_care": ["HH set up, starts {day}", "home health arranged", "VNA confirmed"],
    "insurance_auth": ["auth obtained", "ins approval received", "auth approved"],
    "family_pickup": ["dtr picking up at {time}", "family picking up {day}", "son confirmed pickup"],
    "transport": ["ride confirmed for {time}", "transport arranged", "wheelchair van booked {time}"],
    "meds_equipment": ["DME delivered", "home O2 delivered", "rx filled, in hand"],
}
NEGATED = [
    "no barriers to dc",
    "no dc needs identified",
    "denies need for HH",
    "does not need SNF per PT",
    "no transport issues, wife driving",
    "lives w/ spouse, ride confirmed",
    "no home care needs",
    "no auth needed",
]
DISTRACTORS = [
    "transport to MRI this am",
    "transport to CT done",
    "dtr at bedside, updated on plan",
    "family meeting held re: goals",
    "home meds reconciled",
    "insurance verified on admission",
    "wife visited, questions answered",
    "rx for abx sent",
    "pharmacy reviewed home meds",
    "PT eval completed",
]
CLINICAL_EARLY = [
    "on IV abx",
    "NPO for procedure",
    "pain controlled on IV meds",
    "O2 2L NC",
    "trop trending",
    "febrile overnight",
    "BP soft, holding meds",
    "Cr up from baseline",
]
CLINICAL_LATE = [
    "afebrile x24h",
    "tolerating PO",
    "VSS",
    "transitioned to PO abx",
    "O2 weaned to RA",
    "labs improving",
    "pain controlled on PO meds",
    "BP stable",
]
MOBILITY = {
    "low": ["needs 2 assist to stand", "bedbound", "max assist w/ transfers"],
    "mid": ["ambulating w/ walker", "PT eval pending", "steady w/ 1 assist"],
    "high": ["ambulating in hall", "ambulating independently", "up ad lib"],
}


def _typo(word: str, rng: np.random.Generator) -> str:
    if len(word) < 4 or not word.isalpha():
        return word
    k = int(rng.integers(1, len(word) - 1))
    kind = rng.integers(3)
    if kind == 0:  # swap
        return word[:k] + word[k + 1] + word[k] + word[k + 2:]
    if kind == 1:  # drop
        return word[:k] + word[k + 1:]
    return word[:k] + word[k] + word[k:]  # double


def _fill(template: str, rng, when_min: float, base_weekday: int) -> str:
    day_idx = int(when_min // 1440)
    day = DAY_ABBR[(base_weekday + day_idx) % 7]
    hour = int((when_min % 1440) // 60)
    hour = min(max(hour, 9), 18)
    time = f"{hour - 12 if hour > 12 else hour}{'pm' if hour >= 12 else 'am'}"
    return template.format(day=day, time=time)


def make_note(
    rng: np.random.Generator,
    t_min: float,
    progress: float,
    mobility: float,
    barrier: str | None,
    identified_min: float,
    resolved_min: float,
    base_weekday: int,
    typo_rate: float = 0.04,
) -> tuple[str, list[str]]:
    """One note and the list of barrier types it asserts as active (ground truth)."""
    parts: list[str] = []
    labels: list[str] = []
    clinical = CLINICAL_LATE if progress > 0.6 else CLINICAL_EARLY
    parts.append(clinical[rng.integers(len(clinical))])
    if rng.uniform() < 0.6:
        band = "low" if mobility < 12 else ("mid" if mobility < 18 else "high")
        parts.append(MOBILITY[band][rng.integers(len(MOBILITY[band]))])
    if barrier:
        if identified_min <= t_min < resolved_min and rng.uniform() < 0.85:
            tpl = ACTIVE[barrier][rng.integers(len(ACTIVE[barrier]))]
            parts.append(_fill(tpl, rng, resolved_min, base_weekday))
            labels.append(barrier)
        elif t_min >= resolved_min and rng.uniform() < 0.6:
            tpl = RESOLVED[barrier][rng.integers(len(RESOLVED[barrier]))]
            parts.append(_fill(tpl, rng, t_min + 6 * 60, base_weekday))
    elif rng.uniform() < 0.35:
        parts.append(NEGATED[rng.integers(len(NEGATED))])
    if rng.uniform() < 0.45:
        parts.append(DISTRACTORS[rng.integers(len(DISTRACTORS))])
    rng.shuffle(parts)
    if rng.uniform() < 0.5:
        parts.insert(0, "pt")
        text = " ".join([parts[0], ", ".join(parts[1:])])
    else:
        text = rng.choice([", ", "; ", ". "]).join(parts)
    words = text.split(" ")
    words = [_typo(w, rng) if rng.uniform() < typo_rate else w for w in words]
    return " ".join(words), labels
