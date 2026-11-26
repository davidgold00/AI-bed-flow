"""The case requirements the dashboard must meet on its own, checked against the committed data and code."""

from pathlib import Path

import pytest

from halvian.requirements import (
    FAIL,
    JUDGMENT,
    PASS,
    REQUIREMENTS,
    RUBRIC_FILE,
    SLIDES,
    evaluate_all,
)

ROOT = Path(__file__).resolve().parents[1]

requires_demo_artifacts = pytest.mark.skipif(
    not (ROOT / "models" / "scenarios.json").is_file() or not (ROOT / "data" / "validation.json").is_file(),
    reason="Generate the synthetic data and train the models first.")


def test_ids_are_unique():
    ids = [req.id for req in REQUIREMENTS]
    assert len(ids) == len(set(ids))


@requires_demo_artifacts
def test_no_requirement_fails():
    failing = [(req.id, res.detail) for req, res in evaluate_all() if res.status == FAIL]
    assert not failing, failing


@requires_demo_artifacts
def test_every_demo_requirement_the_app_can_meet_passes():
    demo = [(req.id, res) for req, res in evaluate_all() if req.id.startswith("D")]
    checked = [(rid, res) for rid, res in demo if res.status not in (SLIDES, JUDGMENT)]
    assert len(checked) >= 6
    assert all(res.status == PASS for _, res in checked), [(rid, res.detail) for rid, res in checked]


@pytest.mark.skipif(not RUBRIC_FILE.is_file(), reason="The organizer rubric is a private fixture.")
def test_every_rubric_line_is_answered():
    """Read the rubric spreadsheet itself; every scored line must map to at least one requirement row."""
    from halvian.requirements import rubric_coverage, rubric_lines

    lines = rubric_lines()
    assert len(lines) == 15 and sum(line["points"] for line in lines) == 37
    cover = rubric_coverage()
    assert set(cover) == {line["id"] for line in lines}, "a requirement points at a rubric line that does not exist"
    assert all(cover[line["id"]] for line in lines), {k: v for k, v in cover.items() if not v}


def test_the_ai_note_reader_is_covered():
    ids = {req.id for req in REQUIREMENTS}
    assert {"N1", "N2", "N3", "N4", "N5", "N6", "N7"} <= ids
