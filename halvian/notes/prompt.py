"""The one versioned prompt for the AI note reader.

Change the wording only by bumping ``PROMPT_VERSION``. ``PROMPT_ID`` adds a hash of the
system text, the worked examples and the output schema, so cached results always say
exactly which prompt produced them. The worked examples are written by hand; none is
taken from the synthetic notes, and none from the evaluation sample.
"""

from __future__ import annotations

import hashlib
import json

from halvian import config as C

PROMPT_VERSION = "v1"

SYSTEM = """You read short inpatient progress notes written by hospital staff. Find NON-MEDICAL tasks \
that are still open and are holding up the patient's discharge. Report only these six types:
- placement: waiting for a rehab, skilled nursing (SNF), LTACH or nursing-facility bed, referral or acceptance.
- home_care: home health (HH), VNA or home nursing not yet set up.
- insurance_auth: insurance or prior authorization, payer approval or a coverage application still pending.
- family_pickup: family or a caregiver cannot pick the patient up or take them home yet.
- transport: no ride home, or medical transport or a wheelchair van not yet arranged.
- meds_equipment: a medication, prescription, home oxygen or equipment (DME, walker, hospital bed, \
nebulizer) not yet delivered, filled or in stock.

Rules:
- status "active" only if the task is still open now.
- status "resolved" if the note says it is done: confirmed, arranged, set up, booked, obtained, approved, \
received, delivered, filled, accepted, or family picking up at a set time.
- status "negated" if the note says there is no such need, for example "no barriers to dc" or "denies need for HH".
- Ignore medical care and routine events: transport to imaging (MRI, CT), family visiting or at the bedside, \
medicines given in hospital or reconciled, oxygen as treatment, insurance verified on admission, a PT evaluation.
- evidence must be copied exactly from the note, character for character: the shortest phrase that shows the task.
- Notes use abbreviations and may contain typos: dc = discharge, pt = patient, HH = home health, \
dtr = daughter, DME = durable medical equipment, rx = prescription, auth = authorization, tmrw = tomorrow.
- If there is nothing to report, return an empty list."""

# Hand-written worked examples (not drawn from the data).
EXAMPLES: list[tuple[str, list[dict]]] = [
    ("pt resting, VSS; awaiting acceptance from rehab unit, family visited",
     [{"barrier_type": "placement", "evidence": "awaiting acceptance from rehab unit", "status": "active"}]),
    ("ambulating w/ cane, ride home booked for 11am. walker delivery still pending",
     [{"barrier_type": "transport", "evidence": "ride home booked for 11am", "status": "resolved"},
      {"barrier_type": "meds_equipment", "evidence": "walker delivery still pending", "status": "active"}]),
    ("transport to ultrasound done, son at bedside. no home oxygen needs per RT",
     [{"barrier_type": "meds_equipment", "evidence": "no home oxygen needs", "status": "negated"}]),
    ("BP improved. husband unable to drive pt home until Tues; prior authorization approved",
     [{"barrier_type": "family_pickup", "evidence": "husband unable to drive pt home until Tues",
       "status": "active"},
      {"barrier_type": "insurance_auth", "evidence": "prior authorization approved", "status": "resolved"}]),
    ("tolerating diet, labs stable", []),
]

SCHEMA = {
    "type": "object",
    "properties": {
        "barriers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "barrier_type": {"type": "string", "enum": list(C.BARRIER_TYPES)},
                    "evidence": {"type": "string"},
                    "status": {"type": "string", "enum": ["active", "resolved", "negated"]},
                },
                "required": ["barrier_type", "evidence", "status"],
            },
        }
    },
    "required": ["barriers"],
}


def _fingerprint() -> str:
    blob = json.dumps({"v": PROMPT_VERSION, "system": SYSTEM, "examples": EXAMPLES, "schema": SCHEMA},
                      sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()[:10]


PROMPT_ID = f"{PROMPT_VERSION}-{_fingerprint()}"


def messages(note: str) -> list[dict]:
    """The chat messages for one note: instructions, worked examples, then the note."""
    out = [{"role": "system", "content": SYSTEM}]
    for text, answer in EXAMPLES:
        out.append({"role": "user", "content": f"Note: {text}"})
        out.append({"role": "assistant", "content": json.dumps({"barriers": answer})})
    out.append({"role": "user", "content": f"Note: {note}"})
    return out
