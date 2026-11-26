"""Print the calibration table (Target | Simulated | Tolerance | Pass) for the saved data.

    python scripts/validate.py

Exits with status 1 if any check fails.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from halvian.data.generate import DATA_DIR  # noqa: E402
from halvian.validation import compute_metrics, info_rows, run_checks  # noqa: E402


def main() -> int:
    ed = pd.read_parquet(DATA_DIR / "ed_visits.parquet")
    stays = pd.read_parquet(DATA_DIR / "inpatient_stays.parquet")
    m = compute_metrics(ed, stays)
    checks = run_checks(m)
    pd.set_option("display.width", 220)
    pd.set_option("display.max_colwidth", 80)
    print(checks[["Target", "Simulated", "Tolerance", "Pass"]].to_string(index=False))
    print(f"\n{int(checks.Pass.sum())} of {len(checks)} checks pass.\n")
    print("Reported, not pass/fail:")
    print(info_rows(m).to_string(index=False))
    return 0 if checks.Pass.all() else 1


if __name__ == "__main__":
    raise SystemExit(main())
