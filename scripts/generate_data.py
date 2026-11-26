"""Generate the synthetic Halvian year and save it to data/.

    python scripts/generate_data.py

Deterministic: the same seed (config.SEED) always produces identical files.
All data are synthetic.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from halvian.data.gaps import explicit_adjustments, gap_decomposition  # noqa: E402
from halvian.data.generate import DATA_DIR, generate  # noqa: E402


def main() -> None:
    t0 = time.time()
    out = generate()
    decomp = gap_decomposition()
    decomp.to_json(DATA_DIR / "equity_decomposition.json", orient="records", indent=1)
    explicit_adjustments().to_json(DATA_DIR / "payer_parameters.json", orient="records", indent=1)
    print("Payer gap decomposition (how much comes from mechanisms vs explicit adjustments):")
    print(decomp.to_string(index=False))
    sizes = {p.name: p.stat().st_size / 1e6 for p in sorted(DATA_DIR.glob("*"))}
    for name, mb in sizes.items():
        print(f"  {name:28s} {mb:6.2f} MB")
    print(f"  total {sum(sizes.values()):.1f} MB, {time.time() - t0:.1f} s")
    if not out["checks"].Pass.all():
        print("WARNING: some calibration checks fail; run scripts/validate.py for the table")


if __name__ == "__main__":
    main()
