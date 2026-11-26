"""Developer tool: search the calibrated parameters so the simulation hits the brief.

Usage:
    python scripts/calibrate.py                 # global knobs only
    python scripts/calibrate.py --payer         # then the explicit payer adjustments

It prints suggested values; it never edits config.py. Copy the values into
``SimParams`` by hand and mark them ``[calibrated]``. Each knob is monotone in its target,
so a few rounds of secant search on one knob at a time converge quickly.

Global knobs (no payer-specific terms):
    admit_intercept      -> admission rate 16%
    patience_scale       -> LWBS 4.0%
    nurse_assess_median  -> median door-to-provider 55 min
    bed_process_scale    -> median boarding 3.5 h
    los_scale            -> occupancy 88%

Explicit payer adjustments (only with --payer, starting from zero):
    registration_extra_by_payer  -> door-to-provider gaps
    patience_mult_by_payer       -> LWBS gaps
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from halvian import config as C  # noqa: E402
from halvian.data.cohort import build_cohort  # noqa: E402
from halvian.data.simulate import run  # noqa: E402
from halvian.validation import compute_metrics, run_checks  # noqa: E402

GLOBAL = [
    # (knob, metric, target, bounds)
    ("admit_intercept", "admission_rate", C.ADMISSION_RATE, (-3.5, -2.0)),
    ("patience_scale", "lwbs_rate", C.LWBS_RATE, (0.8, 3.0)),
    ("nurse_assess_median", "d2p_median", C.MEDIAN_DOOR_TO_PROVIDER_MIN, (3.0, 25.0)),
    ("bed_process_scale", "boarding_median_h", C.MEDIAN_BOARDING_H, (0.8, 2.0)),
    ("los_scale", "occupancy", C.TARGET_OCCUPANCY, (0.8, 1.05)),
]


def evaluate(params: C.SimParams) -> dict:
    res = run(build_cohort(params=params))
    return compute_metrics(res.ed, res.stays)


def secant(params, knob, metric, target, bounds, x0, iters=4, tol=0.002):
    lo, hi = bounds
    x_prev = x0
    m_prev = evaluate(dataclasses.replace(params, **{knob: x_prev}))[metric]
    x = min(hi, max(lo, x0 * 1.08 if x0 else 0.1))
    for _ in range(iters):
        m_now = evaluate(dataclasses.replace(params, **{knob: x}))[metric]
        if abs(m_now / target - 1) < tol:
            return x, m_now
        if m_now == m_prev:
            break
        x_new = x + (target - m_now) * (x - x_prev) / (m_now - m_prev)
        step = max(abs(x) * 0.25, 0.05)  # damped: at most 25% per step
        x_new = min(x + step, max(x - step, x_new))
        x_prev, m_prev = x, m_now
        x = min(hi, max(lo, x_new))
    return x, m_now


COUPLED = ("patience_scale", "nurse_assess_median")  # LWBS and waits move together


def newton2(params, iters: int = 4, tol: float = 0.01):
    """Solve LWBS and median door-to-provider jointly (they are tightly coupled)."""
    knobs = COUPLED
    names = ("lwbs_rate", "d2p_median")
    targets = np.array([C.LWBS_RATE, C.MEDIAN_DOOR_TO_PROVIDER_MIN])
    bounds = [b for k, _, _, b in GLOBAL if k in knobs]
    x = np.array([getattr(params, k) for k in knobs], dtype=float)

    def f(xv):
        m = evaluate(dataclasses.replace(params, **dict(zip(knobs, xv, strict=True))))
        return np.array([m[nm] for nm in names]) / targets - 1

    r = f(x)
    for _ in range(iters):
        if np.abs(r).max() < tol:
            break
        jac = np.zeros((2, 2))
        for j in range(2):
            xp = x.copy()
            xp[j] *= 1.06
            jac[:, j] = (f(xp) - r) / (xp[j] - x[j])
        dx = np.linalg.solve(jac, -r)
        dx = np.clip(dx, -0.25 * np.abs(x), 0.25 * np.abs(x))
        x = np.array([min(hi, max(lo, v)) for v, (lo, hi) in zip(x + dx, bounds, strict=True)])
        r = f(x)
    print(f"        joint: {knobs[0]} = {x[0]:.4f}, {knobs[1]} = {x[1]:.4f}  ->  "
          f"LWBS {100 * (r[0] + 1) * targets[0]:.2f}%, median wait {(r[1] + 1) * targets[1]:.1f} min")
    return dataclasses.replace(params, **{k: round(float(v), 4) for k, v in zip(knobs, x, strict=True)})


def calibrate_global(params: C.SimParams, rounds: int = 3) -> C.SimParams:
    for r in range(rounds):
        for knob, metric, target, bounds in GLOBAL:
            if knob in COUPLED:
                continue
            x0 = getattr(params, knob)
            x, val = secant(params, knob, metric, target, bounds, x0)
            params = dataclasses.replace(params, **{knob: round(x, 4)})
            print(f"round {r + 1}: {knob:22s} = {x:8.4f}  ->  {metric} = {val:.4f} (target {target})")
        params = newton2(params)
    return params


def calibrate_payer(params: C.SimParams, rounds: int = 3) -> C.SimParams:
    """Smallest explicit adjustments for Medicaid/CHIP and Uninsured, relative to Commercial."""
    for r in range(rounds):
        m = evaluate(params)
        reg = dict(params.registration_extra_by_payer)
        pat = dict(params.patience_mult_by_payer)
        for p in (C.MEDICAID, C.UNINSURED):
            gap_target = C.DOOR_TO_PROVIDER_BY_PAYER_MIN[p] - C.DOOR_TO_PROVIDER_BY_PAYER_MIN[C.COMMERCIAL]
            gap_sim = m["d2p_by_payer"][p] - m["d2p_by_payer"][C.COMMERCIAL]
            reg[p] = round(max(0.0, reg[p] + 0.8 * (gap_target - gap_sim)), 2)
            ratio_target = C.LWBS_BY_PAYER[p] / C.LWBS_BY_PAYER[C.COMMERCIAL]
            ratio_sim = m["lwbs_by_payer"][p] / m["lwbs_by_payer"][C.COMMERCIAL]
            pat[p] = round(min(1.0, pat[p] * (ratio_sim / ratio_target) ** 0.8), 3)
        params = dataclasses.replace(params, registration_extra_by_payer=reg, patience_mult_by_payer=pat)
        print(f"round {r + 1}: registration extra {reg}")
        print(f"          patience multipliers {pat}")
        params = calibrate_global(params, rounds=1)
    return params


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--payer", action="store_true", help="also fit explicit payer adjustments")
    ap.add_argument("--rounds", type=int, default=3)
    args = ap.parse_args()
    params = calibrate_global(C.DEFAULT_PARAMS, rounds=args.rounds)
    if args.payer:
        params = calibrate_payer(params)
    m = evaluate(params)
    checks = run_checks(m)
    print(f"\nPassed {int(checks.Pass.sum())} of {len(checks)} checks")
    print(checks[~checks.Pass][["Target", "Simulated"]].to_string(index=False))
    print("\nSuggested values:")
    for knob, *_ in GLOBAL:
        print(f"    {knob} = {getattr(params, knob)}")
    if args.payer:
        print(f"    registration_extra_by_payer = {params.registration_extra_by_payer}")
        print(f"    patience_mult_by_payer = {params.patience_mult_by_payer}")


if __name__ == "__main__":
    main()
