"""Discrete-event simulation (DES) of Halvian's ED and inpatient units.

How it works, in plain language
-------------------------------
The simulation keeps a calendar of upcoming events (an arrival, the end of triage, a bed
coming free...) and always processes the earliest one next. Each event changes the state
of the hospital and may schedule new events. The rules:

1. **Front door.** Walk-ins register (2/2/1 clerks per shift), everyone is triaged
   (2/2/1 triage nurses; ambulance arrivals first). ESI 1 patients go straight to a
   resuscitation bay.
2. **Rooms.** Patients wait for a room in order of acuity (ESI), then arrival. ESI 4 and 5
   patients who have waited 90 minutes are moved up to ESI 3 priority so nobody waits
   indefinitely. ESI 1 use
   the 4 resuscitation bays, behavioral health patients the 4 behavioral rooms, ESI 4 and
   5 the 8 fast-track rooms while fast-track is open (9:00 to 23:00), everyone else the 32
   treatment rooms. Any patient can overflow into a free treatment room.
3. **Providers.** After a short nurse assessment in the room, physicians and advanced
   practice providers (7/7/3 per shift) see patients in ESI order. The first provider contact ends the door-to-provider wait. After
   tests and treatment, a provider makes the disposition (these tasks go first, to free
   rooms).
4. **Leaving without being seen.** Each patient has a patience time. If it runs out before
   a provider sees them, they leave (and free their room if they had one).
5. **Boarding.** An admitted patient **keeps the ED room** until an inpatient bed is ready:
   the bed manager processes the request, the request waits for a clean bed on the right
   unit (first come, first served), the unit gets ready and the patient is transported.
   Only then is the ED room free for the next patient. This blocking is what links slow
   inpatient discharges to long ED waits and walkouts. After waiting 4 hours, a patient
   can be placed "off-service" in a clean bed on another unit (ICU patients only in the
   ICU or step-down), as bed managers do in practice.
6. **Inpatient beds.** A stay lasts until the patient is medically ready, plus any
   non-medical barrier delay, then the patient leaves at the unit's usual afternoon
   discharge time. The bed is then dirty until housekeeping is notified and cleans it.
   In tool runs, each 07:00 rounds scores the inpatients present at that moment; for a
   flagged, acted-on stay the team can bring departure forward by up to the hours-saved
   setting, never before medical readiness, and a barrier the note reader did not find
   cannot be bypassed.
7. **The AI tool (impact runs only).** Each hour, patients flagged at triage (and past the
   staff response delay) have their admission probabilities summed per unit; the unit
   reserves that many clean beds and the bed manager pre-processes those requests. Only
   information known at that hour is used; lead time is measured afterwards from events. Flagged inpatients' discharge work starts
   earlier. Adoption, lead time, threshold and hours saved are settings.

The engine is deterministic: all randomness was drawn in ``cohort.py``, and ties are
broken by a sequence counter.
"""

from __future__ import annotations

import heapq
import math
from collections import deque
from dataclasses import dataclass

import numpy as np
import pandas as pd

from halvian import config as C
from halvian.data.cohort import MIN_PER_DAY, Cohort, minutes_from_start
from halvian.models.thresholds import moving_threshold

(ARRIVAL, REG_DONE, TRIAGE_DONE, EVAL_DONE, WORKUP_DONE, DISPO_DONE, ED_DEPART, PATIENCE,
 BED_REQUEST, BED_ARRIVAL, IP_DISCHARGE, BED_CLEAN, SHIFT, FT_OPEN, FT_CLOSE, BATCH,
 RES_EXPIRE, NONED, OVERFLOW, NURSE_DONE, PROMOTE, ROUNDS) = range(22)

# patient status codes
(S_REG_Q, S_REG, S_TRI_Q, S_TRI, S_WAIT, S_ROOMED, S_SEEN, S_DECIDED, S_GONE,
 S_LWBS) = range(1, 11)

SPACE_TYPES = ("main", "fast_track", "resus", "behavioral")
SPACE_PREFIX = {"main": "T", "fast_track": "FT", "resus": "R", "behavioral": "BH"}
UNIT_INDEX = {u: k for k, u in enumerate(C.UNIT_NAMES)}
INF = math.inf


@dataclass(frozen=True)
class ToolSettings:
    """Settings for a run with the AI tool switched on.

    ``p_admit`` and ``pred_unit`` are aligned with the cohort's ED rows (scores known at
    triage). ``rounds_scorer(now, info)`` is called at each 07:00 rounds in scenario time
    with the inpatients present at that moment and returns, for each, the discharge
    probability and the barrier type the note reader found in that morning's note (or
    None). Nothing from the baseline run is reused (REVIEW finding 3).

    ``bed_board_cut`` is the Live Bed Board lever (assumption A22): after go-live, on units in
    scope, the housekeeping notification delay and bed request processing are cut by this
    share. It scales each patient's pre-drawn delay, so the random streams stay paired.
    """

    enabled: bool = False
    start_min: float = 0.0
    adoption: float = C.IMPACT_DEFAULTS["adoption"]
    staff_response_delay_h: float = C.IMPACT_DEFAULTS["staff_response_delay_h"]
    threshold: float = C.IMPACT_DEFAULTS["threshold"]
    moving: bool = C.MOVING_THRESHOLD_ON
    typical_crowding: float = 0.8
    discharge_hours_saved: float = C.IMPACT_DEFAULTS["discharge_hours_saved"]
    scope_units: tuple[str, ...] = C.UNIT_NAMES
    discharge_threshold: float = C.DISCHARGE_LIST_THRESHOLD
    p_admit: np.ndarray | None = None
    pred_unit: np.ndarray | None = None
    rounds_scorer: object | None = None
    bed_board_cut: float = 0.0


@dataclass
class SimResult:
    ed: pd.DataFrame  # cohort columns plus outcome columns, one row per ED arrival
    stays: pd.DataFrame  # one row per inpatient bed request (ED, direct, elective)
    tool_log: dict  # reservation and acceleration counters (impact runs)


def _shift_index(t: float) -> int:
    h = (t % MIN_PER_DAY) / 60.0
    if 7 <= h < 15:
        return 0
    if 15 <= h < 23:
        return 1
    return 2


def run(cohort: Cohort, tool: ToolSettings | None = None, end_min: float | None = None) -> SimResult:
    """Simulate from the cohort's first arrival until every scheduled event is done."""
    tool = tool or ToolSettings()
    params = cohort.params
    ed, ne = cohort.ed, cohort.nonED
    n, m = len(ed), len(ne)
    end_min = end_min if end_min is not None else minutes_from_start(C.YEAR_END)
    start_min = math.floor(min(ed.arrival_min.iloc[0], ne.request_min.iloc[0] if m else INF)
                           / MIN_PER_DAY) * MIN_PER_DAY
    start_weekday = C.WARMUP_START.weekday()

    # ---- per-patient inputs as Python lists (fast scalar access)
    arr = ed.arrival_min.tolist()
    esi = ed.esi.tolist()
    amb = (ed.arrival_mode == "Ambulance").tolist()
    bh = ed.is_behavioral.tolist()
    t_reg = ed.t_registration.tolist()
    t_tri = ed.t_triage.tolist()
    t_eval = ed.t_eval.tolist()
    t_nurse = ed.t_nurse_assess.tolist()
    t_workup = ed.t_workup.tolist()
    t_dispo = ed.t_dispo.tolist()
    t_eddc = ed.t_ed_discharge.tolist()
    patience = ed.patience.tolist()
    admit = ed.would_admit.tolist()
    unit_ed = [UNIT_INDEX[u] for u in ed.admit_unit]
    t_accept = ed.t_admit_acceptance.tolist()

    # per-request draws: ED rows first (index i), then non-ED rows (index n + j)
    def cat(col_ed, col_ne):
        return ed[col_ed].tolist() + (ne[col_ne].tolist() if m else [])

    d_req = cat("t_bed_request", "t_bed_request")
    d_ready = cat("t_bed_readiness", "t_bed_readiness")
    d_trans = cat("t_transport", "t_transport")
    d_clean = cat("t_clean", "t_clean")
    d_notify = cat("t_clean_notify", "t_clean_notify")
    d_los = cat("ip_los_ready_h", "ip_los_ready_h")
    d_bdelay = cat("ip_barrier_delay_h", "ip_barrier_delay_h")
    d_has_barrier = [b is not None and b == b for b in cat("ip_barrier", "ip_barrier")]
    d_clock = cat("ip_discharge_clock_h", "ip_discharge_clock_h")
    d_wk = cat("ip_weekend_u", "ip_weekend_u")
    d_adopt_dc = cat("adopt_dc_u", "adopt_dc_u")
    ne_t = ne.request_min.tolist() if m else []
    ne_unit = [UNIT_INDEX[u] for u in ne.unit] if m else []
    ne_elective = (ne.source == "Elective").tolist() if m else []

    tool_on = tool.enabled
    t_start_tool = tool.start_min
    scope = {UNIT_INDEX[u] for u in tool.scope_units}
    if tool_on:
        p_adm = tool.p_admit.tolist()
        p_unit = tool.pred_unit.tolist()
        adopt_u = ed.adopt_u.tolist()
        response_min = tool.staff_response_delay_h * 60.0
        thr_floor = min(tool.threshold, C.MOVING_THRESHOLD_FLOOR) if tool.moving else tool.threshold
    bb_keep = 1.0 - tool.bed_board_cut  # share of a bed board delay left when the lever applies

    def bed_board(u, now):
        return bb_keep if tool_on and now >= t_start_tool and u in scope else 1.0

    hold_prob = params.weekend_hold_prob
    cutoff_h = params.discharge_same_day_cutoff_h

    # ---- outputs
    nan = float("nan")
    reg_start = [nan] * n
    reg_end = [nan] * n
    triage_end = [nan] * n
    roomed = [nan] * n
    room_type = [""] * n
    room_id = [-1] * n
    prov_start = [nan] * n
    eval_end = [nan] * n
    decision = [nan] * n
    departure = [nan] * n
    lwbs_time = [nan] * n
    status = [0] * n
    leave_pending = [False] * n
    preprocessed = [False] * n
    promoted = [False] * n
    promote_min = params.low_acuity_promote_after_min
    flag_time = [nan] * n
    claimed_reserved = [False] * n
    ed_req = [-1] * n
    queue_at_room = [0] * n  # patients waiting ahead when roomed (diagnostic)

    rq_kind, rq_idx, rq_unit, rq_time = [], [], [], []
    rq_queue, rq_assigned, rq_bed, rq_arrival = [], [], [], []
    rq_ready, rq_discharge, rq_clean, rq_accel, rq_dep_base = [], [], [], [], []
    rq_bed_unit: list[int] = []
    rq_version: list[int] = []
    rq_e_base: list[float] = []
    rq_acted: list[float] = []
    rq_component: list[str] = []
    in_bed: set[int] = set()
    d_btype = cat("ip_barrier", "ip_barrier")
    overflow_wait: list[int] = []
    overflow_min = params.overflow_after_h * 60.0
    icu_idx = UNIT_INDEX["ICU"]
    sd_idx = UNIT_INDEX["Step-down"]

    def compatible(req_u, bed_u):
        if req_u == icu_idx:
            return bed_u in (icu_idx, sd_idx)
        return bed_u != icu_idx

    # ---- resources
    events: list = []
    seq = 0

    clock = [-INF]

    def push(t, code, a=0, b=0):
        nonlocal seq
        if t < clock[0] - 1e-9:
            raise RuntimeError(f"event {code} scheduled in the past ({t} < {clock[0]})")
        seq += 1
        heapq.heappush(events, (t, seq, code, a, b))

    reg_q: deque = deque()
    tri_q_amb: deque = deque()
    tri_q_walk: deque = deque()
    reg_busy = tri_busy = prov_busy = 0
    shift = _shift_index(start_min)
    reg_cap = C.REGISTRATION_CLERKS[shift]
    tri_cap = C.TRIAGE_NURSES[shift]
    prov_cap = C.PROVIDERS[shift]
    staffed_cap = C.STAFFED_SPACES[shift]
    ft_open = False

    free_rooms = {s: list(range(C.ED_SPACES[s])) for s in SPACE_TYPES}
    for s in SPACE_TYPES:
        heapq.heapify(free_rooms[s])
    h_resus: list = []
    h_bh: list = []
    h_ft: list = []
    h_main: list = []
    prov_tasks: list = []
    in_rooms = 0
    in_front = 0

    n_units = len(C.UNIT_NAMES)
    free_beds = [list(range(C.UNITS[u])) for u in C.UNIT_NAMES]
    unit_q = [deque() for _ in range(n_units)]
    reserved: list[list] = [[] for _ in range(n_units)]
    res_token = 0
    log = {"reserved": 0, "claimed": 0, "expired": 0, "idle_reserved_min": 0.0,
           "preprocessed": 0, "accelerated_discharges": 0, "accel_minutes": 0.0, "batches": 0,
           "rounds_flags": 0, "accel_barrier": 0, "accel_routine": 0}
    candidates: set = set()

    # ---- helpers
    def pop_valid(h):
        while h:
            e = heapq.heappop(h)
            if status[e[2]] == S_WAIT:
                return e[2]
        return -1

    def clean_top(h):
        while h and status[h[0][2]] != S_WAIT:
            heapq.heappop(h)

    def room(i, stype, now):
        nonlocal in_rooms, in_front
        status[i] = S_ROOMED
        roomed[i] = now
        room_type[i] = stype
        room_id[i] = heapq.heappop(free_rooms[stype])
        in_front -= 1
        in_rooms += 1
        queue_at_room[i] = in_front
        if esi[i] == 1:
            heapq.heappush(prov_tasks, (1, now, i, 0))
        else:
            push(now + t_nurse[i], NURSE_DONE, i)

    def prio(i):
        return 3 if promoted[i] else esi[i]

    def assign_rooms(now):
        fr = free_rooms
        while fr["resus"]:
            if in_rooms >= staffed_cap:
                clean_top(h_resus)
                if not h_resus:
                    break
            i = pop_valid(h_resus)
            if i < 0:
                clean_top(h_main)
                if h_main and h_main[0][0] <= 2:
                    i = pop_valid(h_main)
                else:
                    break
            room(i, "resus", now)
        while fr["behavioral"] and in_rooms < staffed_cap:
            i = pop_valid(h_bh)
            if i < 0:
                break
            room(i, "behavioral", now)
        if ft_open:
            while fr["fast_track"] and in_rooms < staffed_cap:
                i = pop_valid(h_ft)
                if i < 0:
                    break
                room(i, "fast_track", now)
        while fr["main"] and in_rooms < staffed_cap:
            i = pop_valid(h_main)
            if i < 0:
                break
            room(i, "main", now)
        try_prov(now)

    def to_waiting(i, now):
        nonlocal in_front
        status[i] = S_WAIT
        key = (esi[i], arr[i], i)
        if esi[i] == 1:
            heapq.heappush(h_resus, key)
        elif bh[i]:
            heapq.heappush(h_bh, key)
        elif esi[i] >= 4:
            heapq.heappush(h_ft, key)
            if now - arr[i] >= promote_min:  # already waited long enough
                promoted[i] = True
                key = (3, arr[i], i)
            else:
                push(arr[i] + promote_min, PROMOTE, i)
        heapq.heappush(h_main, key)
        if tool_on and adopt_u[i] < tool.adoption and p_adm[i] >= thr_floor:
            candidates.add(i)

    def free_room(i):
        nonlocal in_rooms
        heapq.heappush(free_rooms[room_type[i]], room_id[i])
        in_rooms -= 1

    def try_reg(now):
        nonlocal reg_busy
        while reg_busy < reg_cap and reg_q:
            i = reg_q.popleft()
            if status[i] != S_REG_Q:
                continue
            status[i] = S_REG
            reg_busy += 1
            reg_start[i] = now
            push(now + t_reg[i], REG_DONE, i)

    def try_tri(now):
        nonlocal tri_busy
        while tri_busy < tri_cap and (tri_q_amb or tri_q_walk):
            i = tri_q_amb.popleft() if tri_q_amb else tri_q_walk.popleft()
            if status[i] != S_TRI_Q:
                continue
            status[i] = S_TRI
            tri_busy += 1
            push(now + t_tri[i], TRIAGE_DONE, i)

    def try_prov(now):
        nonlocal prov_busy
        while prov_busy < prov_cap and prov_tasks:
            _, _, i, task = heapq.heappop(prov_tasks)
            if task == 0:
                if status[i] != S_ROOMED:
                    continue
                status[i] = S_SEEN
                prov_start[i] = now
                prov_busy += 1
                push(now + t_eval[i], EVAL_DONE, i)
            else:
                prov_busy += 1
                push(now + t_dispo[i], DISPO_DONE, i)

    def lwbs(i, now):
        nonlocal in_front
        was_roomed = status[i] == S_ROOMED
        status[i] = S_LWBS
        lwbs_time[i] = now
        departure[i] = now
        candidates.discard(i)
        if was_roomed:
            free_room(i)
            assign_rooms(now)
        else:
            in_front -= 1

    def give_bed(k, u, bed, now):
        rq_assigned[k] = now
        rq_bed[k] = bed
        rq_bed_unit[k] = u
        push(now + d_ready[_draw(k)] + d_trans[_draw(k)], BED_ARRIVAL, k)

    def try_beds(u, now):
        q = unit_q[u]
        fb = free_beds[u]
        while q and fb:
            give_bed(q.popleft(), u, heapq.heappop(fb), now)
        j = 0
        while fb and j < len(overflow_wait):
            k = overflow_wait[j]
            if rq_assigned[k] == rq_assigned[k]:  # already placed
                overflow_wait.pop(j)
                continue
            if compatible(rq_unit[k], u):
                overflow_wait.pop(j)
                unit_q[rq_unit[k]].remove(k)
                give_bed(k, u, heapq.heappop(fb), now)
            else:
                j += 1

    def _draw(k):
        return rq_idx[k] if rq_kind[k] == 0 else n + rq_idx[k]

    def new_request(kind, idx, u, now):
        rq_kind.append(kind)
        rq_idx.append(idx)
        rq_unit.append(u)
        rq_time.append(now)
        for lst in (rq_queue, rq_assigned, rq_arrival, rq_ready, rq_discharge, rq_clean, rq_dep_base):
            lst.append(nan)
        rq_bed.append(-1)
        rq_bed_unit.append(u)
        rq_version.append(0)
        rq_e_base.append(nan)
        rq_acted.append(nan)
        rq_component.append("")
        rq_accel.append(False)
        return len(rq_kind) - 1

    def discharge_time(e):
        day = math.floor(e / MIN_PER_DAY)
        hour = (e - day * MIN_PER_DAY) / 60.0
        return day, hour

    # ---- seed the calendar
    first_day = int(start_min // MIN_PER_DAY)
    last_day = int(end_min // MIN_PER_DAY) + 1
    for dday in range(first_day, last_day):
        base = dday * MIN_PER_DAY
        for h in C.SHIFT_START_HOURS:
            push(base + h * 60, SHIFT)
        push(base + C.FAST_TRACK_HOURS[0] * 60, FT_OPEN)
        push(base + C.FAST_TRACK_HOURS[1] * 60, FT_CLOSE)
    if tool_on:
        push(math.ceil(max(start_min, t_start_tool) / 60.0) * 60.0, BATCH)
        if tool.rounds_scorer is not None:
            r0 = math.ceil((max(start_min, t_start_tool) - 7 * 60) / MIN_PER_DAY) * MIN_PER_DAY + 7 * 60
            push(r0, ROUNDS)
    next_arr = 0
    if n:
        push(arr[0], ARRIVAL, 0)
    if m:
        push(ne_t[0], NONED, 0)

    # ---- main loop
    while events:
        now, _, code, a, b = heapq.heappop(events)
        clock[0] = now
        if code == ARRIVAL:
            i = a
            next_arr = i + 1
            if next_arr < n:
                push(arr[next_arr], ARRIVAL, next_arr)
            in_front += 1
            push(now + patience[i], PATIENCE, i)
            if esi[i] == 1:
                triage_end[i] = now
                to_waiting(i, now)
                assign_rooms(now)
            elif amb[i]:
                status[i] = S_TRI_Q
                tri_q_amb.append(i)
                try_tri(now)
            else:
                status[i] = S_REG_Q
                reg_q.append(i)
                try_reg(now)
        elif code == REG_DONE:
            i = a
            reg_busy -= 1
            reg_end[i] = now
            if leave_pending[i]:
                lwbs(i, now)
            else:
                status[i] = S_TRI_Q
                tri_q_walk.append(i)
                try_tri(now)
            try_reg(now)
        elif code == TRIAGE_DONE:
            i = a
            tri_busy -= 1
            triage_end[i] = now
            if leave_pending[i]:
                lwbs(i, now)
            else:
                to_waiting(i, now)
                assign_rooms(now)
            try_tri(now)
        elif code == NURSE_DONE:
            i = a
            if status[i] == S_ROOMED:
                heapq.heappush(prov_tasks, (prio(i), now, i, 0))
                try_prov(now)
        elif code == PROMOTE:
            i = a
            if status[i] in (S_WAIT, S_ROOMED) and not promoted[i]:
                promoted[i] = True
                if status[i] == S_WAIT:
                    heapq.heappush(h_main, (3, arr[i], i))
                    assign_rooms(now)
                else:
                    heapq.heappush(prov_tasks, (3, now, i, 0))
                    try_prov(now)
        elif code == EVAL_DONE:
            i = a
            prov_busy -= 1
            eval_end[i] = now
            push(now + t_workup[i], WORKUP_DONE, i)
            try_prov(now)
        elif code == WORKUP_DONE:
            i = a
            heapq.heappush(prov_tasks, (0, now, i, 1))
            try_prov(now)
        elif code == DISPO_DONE:
            i = a
            prov_busy -= 1
            decision[i] = now
            status[i] = S_DECIDED
            candidates.discard(i)
            if admit[i]:
                u = unit_ed[i]
                k = new_request(0, i, u, now)
                ed_req[i] = k
                active = tool_on and now >= t_start_tool and u in scope
                if active and reserved[u]:
                    bed, rtime, _tok = reserved[u].pop(0)
                    log["claimed"] += 1
                    log["idle_reserved_min"] += now - rtime
                    claimed_reserved[i] = True
                    rq_queue[k] = now
                    rq_assigned[k] = now
                    rq_bed[k] = bed
                    rq_bed_unit[k] = u
                    push(now + t_accept[i] + C.RESERVED_BED_HANDOFF_MIN + d_trans[i],
                         BED_ARRIVAL, k)
                elif active and preprocessed[i]:
                    push(now + t_accept[i], BED_REQUEST, k)
                else:
                    push(now + t_accept[i] + d_req[i] * (bb_keep if active else 1.0), BED_REQUEST, k)
            else:
                push(now + t_eddc[i], ED_DEPART, i)
            try_prov(now)
        elif code == ED_DEPART:
            i = a
            departure[i] = now
            status[i] = S_GONE
            free_room(i)
            assign_rooms(now)
        elif code == PATIENCE:
            i = a
            s = status[i]
            if s in (S_REG_Q, S_TRI_Q, S_WAIT, S_ROOMED):
                lwbs(i, now)
            elif s in (S_REG, S_TRI):
                leave_pending[i] = True
        elif code == BED_REQUEST:
            k = a
            rq_queue[k] = now
            unit_q[rq_unit[k]].append(k)
            try_beds(rq_unit[k], now)
            if rq_assigned[k] != rq_assigned[k]:
                push(now + overflow_min, OVERFLOW, k)
        elif code == OVERFLOW:
            k = a
            if rq_assigned[k] != rq_assigned[k]:
                overflow_wait.append(k)
                best, best_free = -1, 0
                for u2 in range(n_units):
                    if u2 != rq_unit[k] and compatible(rq_unit[k], u2) and len(free_beds[u2]) > best_free:
                        best, best_free = u2, len(free_beds[u2])
                if best >= 0:
                    try_beds(best, now)
        elif code == BED_ARRIVAL:
            k = a
            rq_arrival[k] = now
            dk = _draw(k)
            if rq_kind[k] == 0:
                i = rq_idx[k]
                departure[i] = now
                status[i] = S_GONE
                free_room(i)
                assign_rooms(now)
            ready = now + d_los[dk] * 60.0
            e = ready + d_bdelay[dk] * 60.0
            day, hour = discharge_time(e)
            if hour >= cutoff_h:
                day += 1
            wd = (start_weekday + day) % 7
            if wd >= 5 and d_wk[dk] < hold_prob:
                day += 7 - wd
            dep = day * MIN_PER_DAY + d_clock[dk] * 60.0
            if dep < e + 60.0:
                dep = e + 60.0
            rq_dep_base[k] = dep
            rq_ready[k] = ready
            rq_e_base[k] = e
            rq_discharge[k] = dep
            in_bed.add(k)
            push(dep, IP_DISCHARGE, k, 0)
        elif code == IP_DISCHARGE:
            k = a
            if b != rq_version[k]:
                continue  # superseded by an earlier, rescheduled departure
            in_bed.discard(k)
            dk = _draw(k)
            t_clean_done = now + d_notify[dk] * bed_board(rq_bed_unit[k], now) + d_clean[dk]
            rq_clean[k] = t_clean_done
            push(t_clean_done, BED_CLEAN, rq_bed_unit[k], rq_bed[k])
        elif code == BED_CLEAN:
            heapq.heappush(free_beds[a], b)
            try_beds(a, now)
        elif code == NONED:
            j = a
            if j + 1 < m:
                push(ne_t[j + 1], NONED, j + 1)
            k = new_request(1, j, ne_unit[j], now)
            push(now if ne_elective[j] else now + d_req[n + j] * bed_board(ne_unit[j], now), BED_REQUEST, k)
        elif code == SHIFT:
            shift = _shift_index(now + 1)
            reg_cap = C.REGISTRATION_CLERKS[shift]
            tri_cap = C.TRIAGE_NURSES[shift]
            prov_cap = C.PROVIDERS[shift]
            staffed_cap = C.STAFFED_SPACES[shift]
            assign_rooms(now)
            try_reg(now)
            try_tri(now)
            try_prov(now)
        elif code == FT_OPEN:
            ft_open = True
            assign_rooms(now)
        elif code == FT_CLOSE:
            ft_open = False
        elif code == BATCH:
            log["batches"] += 1
            crowd = (in_rooms + in_front) / C.ED_TOTAL_SPACES
            thr = moving_threshold(crowd, tool.typical_crowding, base=tool.threshold,
                                   enabled=tool.moving)
            expected = [0.0] * n_units
            for i in list(candidates):
                s = status[i]
                if s not in (S_WAIT, S_ROOMED, S_SEEN):
                    candidates.discard(i)
                    continue
                if p_adm[i] < thr:
                    continue
                # Only information observable now: triage completed and the staff response
                # delay has passed. No future event times are read (REVIEW finding 1).
                if now < triage_end[i] + response_min:
                    continue
                if not preprocessed[i]:
                    preprocessed[i] = True
                    flag_time[i] = now
                    log["preprocessed"] += 1
                expected[p_unit[i]] += p_adm[i]
            for u in scope:
                need = round(expected[u]) - len(reserved[u])
                while need > 0 and free_beds[u] and not unit_q[u]:
                    bed = heapq.heappop(free_beds[u])
                    res_token += 1
                    reserved[u].append((bed, now, res_token))
                    log["reserved"] += 1
                    push(now + C.RESERVATION_EXPIRY_H * 60.0, RES_EXPIRE, u, res_token)
                    need -= 1
            if now + 60.0 < end_min:
                push(now + 60.0, BATCH)
        elif code == ROUNDS:
            # 07:00 rounds in scenario time: score the inpatients present right now.
            if now + MIN_PER_DAY < end_min:
                push(now + MIN_PER_DAY, ROUNDS)
            ks = [k for k in sorted(in_bed) if rq_acted[k] != rq_acted[k] and rq_bed_unit[k] in scope]
            if not ks:
                continue
            info = {"k": ks, "draw": [_draw(k) for k in ks], "kind": [rq_kind[k] for k in ks],
                    "bed_arrival": [rq_arrival[k] for k in ks], "ready": [rq_ready[k] for k in ks],
                    "unit": [C.UNIT_NAMES[rq_bed_unit[k]] for k in ks]}
            probs, found = tool.rounds_scorer(now, info)
            hs = tool.discharge_hours_saved * 60.0
            for k, pk, fk in zip(ks, probs, found, strict=True):
                # The rounds list shows likely discharges and anyone whose note flags a
                # barrier (case managers work those barriers), as on the rounds page.
                if pk < tool.discharge_threshold and fk is None:
                    continue
                log["rounds_flags"] += 1
                dk = _draw(k)
                if d_adopt_dc[dk] >= tool.adoption:
                    continue
                rq_acted[k] = now
                if hs <= 0:
                    continue
                ready, e_base, dep = rq_ready[k], rq_e_base[k], rq_discharge[k]
                if d_has_barrier[dk] and fk == d_btype[dk] and e_base > now:
                    e_new = max(ready, now, e_base - hs)  # barrier work starts at rounds
                    lower = max(now, e_new + 60.0)
                    component = "barrier"
                elif d_has_barrier[dk] and e_base > now:
                    lower = max(now, e_base + 60.0)  # an undetected barrier cannot be bypassed
                    component = "routine"
                else:
                    lower = max(now, ready + 60.0)
                    component = "routine"
                new_dep = max(lower, dep - hs)
                if new_dep < dep - 1e-6:
                    rq_version[k] += 1
                    rq_discharge[k] = new_dep
                    rq_accel[k] = True
                    rq_component[k] = component
                    log["accelerated_discharges"] += 1
                    log["accel_minutes"] += dep - new_dep
                    log[f"accel_{component}"] += 1
                    push(new_dep, IP_DISCHARGE, k, rq_version[k])
        elif code == RES_EXPIRE:
            u, tok = a, b
            for idx, (bed, rtime, t2) in enumerate(reserved[u]):
                if t2 == tok:
                    reserved[u].pop(idx)
                    log["expired"] += 1
                    log["idle_reserved_min"] += now - rtime
                    heapq.heappush(free_beds[u], bed)
                    try_beds(u, now)
                    break

    # ---- assemble outputs
    out = ed.copy()
    out["reg_start_min"] = reg_start
    out["reg_end_min"] = reg_end
    out["triage_end_min"] = triage_end
    out["roomed_min"] = roomed
    out["room_type"] = room_type
    out["room_number"] = room_id
    out["provider_min"] = prov_start
    out["eval_end_min"] = eval_end
    out["decision_min"] = decision
    out["departure_min"] = departure
    out["lwbs"] = [s == S_LWBS for s in status]
    out["admitted"] = [k >= 0 for k in ed_req]
    out["claimed_reserved_bed"] = claimed_reserved
    out["preprocessed"] = preprocessed
    out["flag_time_min"] = flag_time
    out["queue_ahead_at_rooming"] = queue_at_room
    out["door_to_provider_min"] = out.provider_min - out.arrival_min
    out["disposition"] = np.where(
        out.lwbs, "Left without being seen",
        np.where(out.admitted, "Admitted",
                 np.where(out.decision_min.notna(), "Discharged", "In ED at end")))
    req_k = np.array(ed_req)
    rq_queue_arr = np.array(rq_queue) if rq_queue else np.array([])
    rq_assigned_arr = np.array(rq_assigned) if rq_assigned else np.array([])
    has = req_k >= 0
    for col, src in (("bed_request_min", rq_queue_arr), ("bed_assigned_min", rq_assigned_arr)):
        vals = np.full(n, np.nan)
        vals[has] = src[req_k[has]]
        out[col] = vals
    out["boarding_min"] = np.where(out.admitted, out.departure_min - out.decision_min, np.nan)
    out["room_label"] = [
        f"{SPACE_PREFIX[t]}{r + 1}" if t else "" for t, r in zip(room_type, room_id, strict=True)
    ]

    stays = pd.DataFrame({
        "kind": np.where(np.array(rq_kind) == 0, "ED", "NonED"),
        "row": rq_idx,
        "unit": [C.UNIT_NAMES[u] for u in rq_bed_unit],
        "intended_unit": [C.UNIT_NAMES[u] for u in rq_unit],
        "request_min": rq_time,
        "queue_entry_min": rq_queue,
        "bed_assigned_min": rq_assigned,
        "bed_number": rq_bed,
        "bed_arrival_min": rq_arrival,
        "ready_min": rq_ready,
        "discharge_min": rq_discharge,
        "discharge_base_min": rq_dep_base,
        "clean_min": rq_clean,
        "accelerated": rq_accel,
        "accel_component": rq_component,
        "acted_rounds_min": rq_acted,
        "has_barrier": [d_has_barrier[_draw(k)] for k in range(len(rq_kind))],
    })
    return SimResult(ed=out, stays=stays, tool_log=log)
