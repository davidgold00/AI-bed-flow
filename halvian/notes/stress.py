"""A new-phrasing stress test for the note readers: wording neither reader was built on.

The synthetic notes come from templates, and the rule-based reader was written for those
templates, so scoring both readers on them favors the rules. This bank is written in other
clinical styles (full sentences, different abbreviations and word order). It was written and
committed before either reader was run on it, and neither the rules, the prompt nor the AI
reader's checks were changed after seeing its results. Labels come from construction: each
note contains known active barriers, plus resolved, negated and distracting phrases that are
not barriers. It is small and synthetic: a test of robustness to new wording, not of
real-world accuracy.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from halvian import config as C

ACTIVE = {
    "placement": (
        "PT/OT recommending SAR. Referrals faxed to 3 facilities, no bed offers so far",
        "Dispo: subacute rehab, still waiting to hear back from Maple Grove",
        "Will need long-term care placement; daughter touring facilities this week",
        "Not safe for home per PT. Looking for a SNF bed, none offered yet",
        "Case mgmt working on LTACH referral",
        "Plan is IRF once a bed opens",
        "Dispo pending skilled nursing acceptance",
        "Family wants assisted living; no openings until next month",
    ),
    "home_care": (
        "Going home w/ VNA once the agency confirms a start date",
        "Needs home infusion set up for IV abx before d/c",
        "Home health PT/OT ordered, agency has not accepted yet",
        "Dispo home with services; HH intake still not done",
        "Requires visiting nurse for wound care, no agency covering his zip code yet",
        "Will need a home aide, case mgmt still searching",
        "Awaiting home hospice intake visit",
        "D/c home once the home care agency calls back",
    ),
    "insurance_auth": (
        "Precert for SAR submitted, payer has not responded",
        "Insurance denied rehab, peer-to-peer scheduled for tomorrow",
        "Medicaid application in process, financial counselor following",
        "Pending prior authorization for home infusion",
        "Plan needs approval from the insurer before transfer",
        "Waiting on benefits check for SNF days",
        "Auth for LTACH still under review",
        "Coverage for wound vac not approved yet",
    ),
    "family_pickup": (
        "Wife works nights, cannot come get him until Saturday morning",
        "Daughter lives 3 hours away, earliest she can drive up is Friday",
        "No family available to bring pt home today",
        "Caregiver out of state until the 14th",
        "Husband recovering from his own surgery, unable to pick her up",
        "Pt's sister is the only contact and is unreachable",
        "Family not able to take him home before Monday",
        "Son can only collect her after his shift ends tomorrow",
    ),
    "transport": (
        "Will need stretcher transport home; ambulance company has nothing until tomorrow",
        "Lives alone, no car, medicab being arranged",
        "No way to get home today",
        "Needs a wheelchair-accessible van, first slot Thursday",
        "Ride-share voucher requested, not yet approved",
        "Transport home awaiting scheduling",
        "Cab voucher pending from social work",
        "EMS transfer home not booked",
    ),
    "meds_equipment": (
        "Home O2 concentrator not delivered yet, vendor says Tuesday",
        "Needs hospital bed and commode at home before d/c",
        "Specialty pharmacy can't fill apixaban until Monday",
        "Insulin pen supplies backordered",
        "Walker ordered, DME vendor has not dropped it off",
        "CPAP machine still with the supplier",
        "Wound vac for home not yet available",
        "Pharmacy out of stock of his inhaler, bridging supply requested",
    ),
}
NOT_BARRIERS = (  # resolved, negated or not about discharge
    "Rehab bed accepted for tomorrow 10am", "SNF offered a bed and family agreed",
    "VNA start of care confirmed for Thursday", "First home health visit booked for Monday",
    "Prior auth came back approved", "Insurance approved the SAR stay",
    "Daughter will pick him up at 3pm", "Wife here to drive her home after lunch",
    "Ambulance booked for 11", "Ride home confirmed with a neighbor",
    "Oxygen concentrator delivered to home yesterday", "Discharge meds filled and at bedside",
    "No home services needed per PT", "Does not need DME", "No transportation concerns",
    "No placement needs, going home with spouse", "Transported to IR for line placement",
    "PICC placement done", "Insulin drip titrated overnight", "Holding lisinopril for soft BP",
    "On 3L O2, wean as tolerated", "Family at bedside, updated on plan", "Rehab exercises with PT this morning",
    "Insurance card scanned at registration", "Pharmacy consulted for vanc dosing",
    "Bed alarm on, fall precautions", "Wheelchair to bathroom with assist", "Daughter brought the home meds list",
)
FILLER = (
    "Afebrile, VSS", "Tolerating regular diet", "Pain 3/10, controlled", "Ambulated 200 ft with walker",
    "Labs stable, K repleted", "Slept well overnight", "Incision c/d/i", "Abx day 3 of 5",
    "Cr back to baseline", "Euvolemic on exam", "Mobility improving with PT", "Plan reviewed with attending",
)


def stress_notes(seed: int = C.SEED, per_phrase: int = 3, clean: int = 160) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Notes and labels. Each active phrase appears in ``per_phrase`` notes; ``clean`` notes have none."""
    rng = np.random.default_rng([seed, 777])
    rows, labels = [], []

    def compose(parts: list[str]) -> str:
        order = rng.permutation(len(parts))
        return ". ".join(parts[i] for i in order) + "."

    k = 0
    for barrier, phrases in ACTIVE.items():
        for phrase in phrases:
            for _ in range(per_phrase):
                k += 1
                nid = f"ST-{k:04d}"
                parts = [phrase, *rng.choice(FILLER, size=rng.integers(1, 3), replace=False)]
                if rng.random() < 0.5:
                    parts.append(str(rng.choice(NOT_BARRIERS)))
                rows.append({"note_id": nid, "text": compose(parts)})
                labels.append({"note_id": nid, "barrier_type": barrier})
    for _ in range(clean):
        k += 1
        nid = f"ST-{k:04d}"
        parts = [*rng.choice(NOT_BARRIERS, size=rng.integers(1, 3), replace=False),
                 *rng.choice(FILLER, size=rng.integers(1, 3), replace=False)]
        rows.append({"note_id": nid, "text": compose(parts)})
    return pd.DataFrame(rows), pd.DataFrame(labels, columns=["note_id", "barrier_type"])
