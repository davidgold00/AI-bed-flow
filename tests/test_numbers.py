"""Every number in docs/NUMBERS.md comes from a saved artifact or the config, and is current."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

from halvian import config as C

ROOT = Path(__file__).resolve().parents[1]
NUMBERS = ROOT / "docs" / "NUMBERS.md"
needs = pytest.mark.skipif(not (ROOT / "models" / "scenarios.json").is_file(), reason="train the models first")


def _exporter():
    spec = importlib.util.spec_from_file_location("export_numbers", ROOT / "scripts" / "export_numbers.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["export_numbers"] = module  # dataclasses look their module up while the script loads
    spec.loader.exec_module(module)
    return module


def _rows() -> list[tuple[str, str, str]]:
    out = []
    for line in NUMBERS.read_text().splitlines():
        m = re.match(r"^\| (.+?) \| .+ \| .+ \| `([^`]+)` · `(.+)` \|$", line)
        if m:
            out.append(m.groups())
    return out


def _expand(key: str) -> list[str]:
    """Concrete paths for a cited key: "a, b" lists, {x, y} alternatives anywhere, a trailing .{x, y} set."""
    if "{" not in key and ", " in key:
        return [k.strip() for k in key.split(",")]
    m = re.search(r"\{([^}]*)\}", key)
    if not m:
        return [key]
    head, tail = key[:m.start()], key[m.end():]
    return [p for alt in m.group(1).split(",") for p in _expand(f"{head}{alt.strip()}{tail}")]


def _resolve(obj, path: str):
    """Follow a.b[0]['name'].c through nested dicts and lists."""
    for part in re.findall(r"\[[^\]]+\]|[^.\[\]]+", path):
        if part.startswith("["):
            inner = part[1:-1].strip("'\"")
            obj = obj[int(inner)] if inner.isdigit() else obj[inner]
        else:
            obj = obj[part]
    return obj


@needs
def test_numbers_md_is_exactly_what_the_artifacts_produce_now():
    ex = _exporter()
    rows = ex.collect_numbers(ex.read_json(ex.SCENARIOS), ex.read_json(ex.METRICS), ex.read_json(ex.VALIDATION))
    assert ex.render_numbers(rows) == NUMBERS.read_text(), "docs/NUMBERS.md is stale: run scripts/export_numbers.py"


@needs
def test_every_number_cites_a_source_that_exists():
    rows = _rows()
    assert len(rows) > 50
    cache: dict[str, dict] = {}
    for display, file, key in rows:
        if file == "halvian/config.py":
            name = re.match(r"^[A-Z_][A-Z0-9_]*", key).group()
            value = getattr(C, name)
            for sub in re.findall(r"\[([^\]]+)\]", key):
                value = value[sub.strip("'\"")]
            assert value is not None, (display, key)
            continue
        path = ROOT / file
        assert path.is_file(), (display, file)
        data = cache.setdefault(file, json.loads(path.read_text()))
        for concrete in _expand(re.sub(r"\s*\([^)]*\)$", "", key)):  # drop a note such as "(entry count)"
            assert _resolve(data, concrete) is not None, (display, file, concrete)
