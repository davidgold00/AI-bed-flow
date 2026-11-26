"""Pre-push identity checks. Exits non-zero if either check fails.

1. Commit author and committer emails must all be GitHub noreply addresses.
2. No real email address may appear in tracked files. This runs the exact
   ``git grep -nE`` pattern from CLAUDE.md. Compressed binary files (parquet, joblib) can
   contain random byte runs that happen to fit the pattern, so each binary match is
   decoded and its real string content scanned. A text match always fails.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERN = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
EMAIL = re.compile(PATTERN)
ALLOWED_AUTHOR = re.compile(r"^\d+\+[A-Za-z0-9-]+@users\.noreply\.github\.com$")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False).stdout


def check_authors() -> list[str]:
    emails = set(git("log", "--format=%ae%n%ce").split())
    return [e for e in emails if not ALLOWED_AUTHOR.match(e)]


def decoded_strings(path: Path) -> list[str]:
    if path.suffix == ".parquet":
        import pandas as pd

        df = pd.read_parquet(path)
        cols = [c for c in df.columns if not str(df[c].dtype).startswith(("float", "int", "bool"))]
        return [str(c) for c in df.columns] + [str(v) for c in cols for v in df[c].astype(str).unique()]
    if path.suffix == ".joblib":
        import joblib

        return re.findall(r"'([^']*)'", repr(joblib.load(path)))
    return [path.read_text(errors="ignore")]


def check_files() -> list[str]:
    problems = []
    out = git("grep", "-nE", PATTERN)
    for line in out.splitlines():
        if line.startswith("Binary file ") and line.endswith(" matches"):
            path = ROOT / line[len("Binary file "):-len(" matches")]
            hits = [s for s in decoded_strings(path) if EMAIL.search(s)]
            if hits:
                problems.append(f"{path.name}: {hits[:3]}")
        else:
            problems.append(line)
    return problems


def main() -> int:
    bad_authors = check_authors()
    bad_files = check_files()
    print("Author/committer emails:", bad_authors if bad_authors else "OK (noreply only)")
    print("Email addresses in tracked files:", bad_files if bad_files else "none")
    return 1 if bad_authors or bad_files else 0


if __name__ == "__main__":
    raise SystemExit(main())
