"""Write data/stress_notes.parquet and data/stress_labels.parquet (the new-phrasing stress test).

    python scripts/make_stress_notes.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from halvian.notes.stress import stress_notes  # noqa: E402

if __name__ == "__main__":
    notes, labels = stress_notes()
    notes.to_parquet(ROOT / "data" / "stress_notes.parquet", index=False)
    labels.to_parquet(ROOT / "data" / "stress_labels.parquet", index=False)
    print(f"{len(notes)} stress notes, {len(labels)} labelled barriers")
