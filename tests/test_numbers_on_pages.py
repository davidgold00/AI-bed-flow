"""Every number a page shows is honest: simulated outcomes only as ranges, claims traceable to NUMBERS.md.

Renders each page with AppTest. Two rules:

1. A sentence about a simulated outcome (minutes saved, freed capacity, change in waits or walkouts) may show
   numbers only inside an "X to Y" range. The break-even arithmetic is exempt.
2. A number next to a model score or a case benchmark (AUC, precision, recall, F1, missed, national, case
   brief) must match a number in docs/NUMBERS.md once rounded to the shown precision.

Live replay counts (patients waiting, beds now) are not claims and are not checked here.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from _ui import page_sentences
from streamlit.testing.v1 import AppTest

from halvian.ui import navigation as NAV

ROOT = Path(__file__).resolve().parents[1]
APP = str(ROOT / "app.py")
needs = pytest.mark.skipif(not (ROOT / "models" / "impact_ranges.json").is_file(), reason="train the models first")

NUM = r"[-+−]?\$?\d[\d,]*(?:\.\d+)?"
RANGE = re.compile(rf"{NUM}\s*(?:%|h|min|minutes|hours|M|K| million| points| pts)?\s+to\s+{NUM}")
OUTCOME = re.compile(r"saved per admi|freed (?:ED )?capacity|simulated winter quarter|fewer walkouts|shorter wait|"
                     r"less boarding", re.I)
BREAK_EVEN = re.compile(r"break.even|pays for itself|needed to break", re.I)
CLAIM = re.compile(r"\bAUC\b|precision|recall|\bF1\b|national|benchmark|\bmisses\b|missed|case brief", re.I)


def numbers(text: str) -> list[tuple[float, int]]:
    """Numbers in the text as (value, decimals shown), without $ , % signs."""
    out = []
    for raw in re.findall(r"(?<![\w.])(?<![A-Za-z]-)[-+−]?\$?\d[\d,]*(?:\.\d+)?", text):
        clean = raw.replace("$", "").replace(",", "").replace("−", "-")
        out.append((float(clean), len(clean.split(".")[1]) if "." in clean else 0))
    return out


def documented() -> set[float]:
    values = set()
    for line in (ROOT / "docs" / "NUMBERS.md").read_text().splitlines():
        if line.startswith("| ") and not line.startswith("| Number") and not line.startswith("| ---"):
            for value, _ in numbers(line.split(" | ")[0]):
                values |= {value, value * 100, value / 100}
    return values


def known(value: float, places: int, pool: set[float]) -> bool:
    return any(round(v, places) == round(value, places) for v in pool)


def problems(sentences: list[str], pool: set[float]) -> tuple[list[str], list[str]]:
    point_estimates, undocumented = [], []
    for sentence in sentences:
        if OUTCOME.search(sentence) and not BREAK_EVEN.search(sentence):
            rest = RANGE.sub(" ", sentence)
            rest = re.sub(r"13,600|\$350|x 1\.5|\b(?:1|2|3|4|5)\b(?= synthetic years)", " ", rest)
            if numbers(rest):
                point_estimates.append(sentence)
        if CLAIM.search(sentence):
            for value, places in numbers(RANGE.sub(" ", sentence)):
                if not known(value, places, pool) and value not in (0, 1, 100):
                    undocumented.append(f"{value:g} in: {sentence[:120]}")
            for match in RANGE.finditer(sentence):
                for value, places in numbers(match.group()):
                    if not known(value, places, pool):
                        undocumented.append(f"{value:g} in: {sentence[:120]}")
    return point_estimates, undocumented


def test_the_rules_catch_what_they_should():
    pool = {0.857, 79.1, 3.5}
    point, undoc = problems(["The tool saves 16.4 minutes saved per admission.",
                             "10 to 20 minutes saved per admission, simulated winter quarter.",
                             "The model AUC is 0.91 on synthetic data.", "AUC 0.86 vs 79% overall."], pool)
    assert point == ["The tool saves 16.4 minutes saved per admission."]
    assert len(undoc) == 1 and undoc[0].startswith("0.91")


@needs
@pytest.mark.parametrize("spec", NAV.ALL_PAGES, ids=lambda spec: spec.url)
def test_page_numbers_are_ranges_or_documented(spec):
    app = AppTest.from_file(APP, default_timeout=60).run()
    app.switch_page(spec.path).run()
    assert not app.exception
    point_estimates, undocumented = problems(page_sentences(app), documented())
    assert not point_estimates, f"simulated outcomes shown as a single number: {point_estimates}"
    assert not undocumented, f"numbers not in docs/NUMBERS.md: {undocumented}"


OPERATIONAL = [NAV.BED_BOARD, NAV.ADMISSION_FLAGS, NAV.DISCHARGE, NAV.BED_FORECAST, NAV.GUIDED_DEMO]
PAYER_WORDS = re.compile(r"Medicaid|Medicare|Uninsured|Commercial(?:ly)? insured|\bCommercial\b|workers' comp")


@needs
@pytest.mark.parametrize("spec", OPERATIONAL, ids=lambda spec: spec.url)
def test_operational_screens_never_show_payer(spec):
    app = AppTest.from_file(APP, default_timeout=60).run()
    app.switch_page(spec.path).run()
    shown = [s for s in page_sentences(app) if PAYER_WORDS.search(s)]
    frames = [c for df in app.dataframe for c in df.value.columns if "payer" in str(c).lower()]
    assert not shown and not frames, (shown, frames)
