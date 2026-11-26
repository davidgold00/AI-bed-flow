"""End-to-end browser QA: every page and the demo click path at 1440x900 and 1920x1080.

    pip install -r scripts/requirements-qa.txt      # Playwright; it drives the Chrome already installed
    python scripts/qa_browser.py                     # starts the app on a spare port, checks, stops it
    python scripts/qa_browser.py --url http://127.0.0.1:8502   # check a running app instead

Fails (exit 1) on any Streamlit exception, JavaScript error, horizontal overflow, clipped text, a page
slower than 3 seconds once warm, a "Page not found" dialog or a broken in-app link. Screenshots go to
qa_screens/ (git-ignored). Nothing leaves this machine: the app runs on 127.0.0.1.
"""

from __future__ import annotations

import argparse
import json
import re
import socket
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from halvian.ui import navigation as NAV  # noqa: E402

OUT = ROOT / "qa_screens"
VIEWPORTS = {"1440x900": (1440, 900), "1920x1080": (1920, 1080)}
MAX_SECONDS = 3.0

# Clipped text: an element whose content is wider than its box while the box hides the overflow.
CLIP_JS = """
() => {
  const out = [];
  const main = document.querySelector('[data-testid="stAppViewContainer"]') || document.body;
  for (const el of main.querySelectorAll('p, span, label, button, a, h1, h2, h3, h4, input, div[data-baseweb="select"] div')) {
    if (!el.offsetParent) continue;
    const box = el.getBoundingClientRect();
    if (box.width < 3 || box.height < 3) continue;  // visually hidden, such as the skip link
    if (el.closest('.js-plotly-plot, [data-testid="stDataFrame"], [data-testid="stDataFrameResizable"], .stPlotlyChart, [data-testid="stIconMaterial"], .material-symbols-rounded')) continue;
    const cs = getComputedStyle(el);
    const hides = cs.textOverflow === 'ellipsis' || ['hidden', 'clip'].includes(cs.overflowX) || el.tagName === 'INPUT';
    if (!hides) continue;
    const text = (el.tagName === 'INPUT' ? el.value : el.innerText || '').trim();
    if (!text) continue;
    if (el.scrollWidth > el.clientWidth + 2) out.push(text.slice(0, 80));
  }
  return [...new Set(out)];
}
"""
OVERFLOW_JS = "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
EXC_JS = """() => Array.from(document.querySelectorAll('[data-testid="stException"]')).map(e => e.innerText.slice(0, 300))"""
NOT_FOUND_JS = "() => document.body.innerText.includes('Page not found')"
LINKS_JS = """() => Array.from(document.querySelectorAll('a[href]')).map(a => a.href)
  .filter(h => h.startsWith(location.origin))"""


@dataclass
class Report:
    problems: list[str] = field(default_factory=list)
    info: dict[str, str] = field(default_factory=dict)
    timings: dict[str, float] = field(default_factory=dict)
    shots: list[str] = field(default_factory=list)

    def fail(self, where: str, what: str) -> None:
        self.problems.append(f"{where}: {what}")


def wait_ready(page: Page, timeout: float = 30.0) -> float:
    """Seconds until Streamlit has finished its script run and the page content is drawn."""
    start = time.perf_counter()
    page.wait_for_selector('[data-testid="stAppViewContainer"] h1', timeout=timeout * 1000)
    deadline = start + timeout
    quiet_since = None
    while time.perf_counter() < deadline:
        running = page.evaluate("""() => !!document.querySelector('[data-testid="stStatusWidget"]')
            || !!document.querySelector('[data-testid="stSkeleton"]')
            || !!document.querySelector('[data-testid="stSpinner"]')""")
        if not running:
            quiet_since = quiet_since or time.perf_counter()
            if time.perf_counter() - quiet_since > 0.35:
                return quiet_since - start
        else:
            quiet_since = None
        time.sleep(0.05)
    return timeout


def check(page: Page, report: Report, where: str, shot: str, *, timed: float | None = None) -> None:
    for exc in page.evaluate(EXC_JS):
        report.fail(where, f"exception: {exc}")
    if page.evaluate(NOT_FOUND_JS):
        report.fail(where, "'Page not found' dialog")
    overflow = page.evaluate(OVERFLOW_JS)
    if overflow > 1:
        report.fail(where, f"horizontal overflow of {overflow}px")
    for text in page.evaluate(CLIP_JS):
        report.fail(where, f"clipped text: {text!r}")
    if timed is not None:
        report.timings[where] = round(timed, 2)
        if timed > MAX_SECONDS:
            report.fail(where, f"slow: {timed:.1f} s")
    path = OUT / f"{shot}.png"
    # Streamlit scrolls inside its own container, so grow the viewport to the content for a whole-page shot
    size = page.viewport_size
    height = page.evaluate("""() => Math.max(...Array.from(document.querySelectorAll(
        '[data-testid="stMain"], [data-testid="stAppViewContainer"], [data-testid="stMainBlockContainer"]'))
        .map(e => e.scrollHeight), document.body.scrollHeight)""")
    page.set_viewport_size({"width": size["width"], "height": min(max(height + 80, size["height"]), 9000)})
    page.wait_for_timeout(300)
    page.screenshot(path=str(path))
    page.set_viewport_size(size)
    report.shots.append(str(path.relative_to(ROOT)))


def visit(page: Page, url: str, report: Report, where: str, shot: str) -> None:
    page.goto(url)
    check(page, report, where, shot, timed=wait_ready(page))


def click(page: Page, report: Report, where: str, role: str, name: str, *, exact: bool = False) -> None:
    target = page.get_by_role(role, name=name, exact=exact).first
    try:
        target.scroll_into_view_if_needed(timeout=10_000)
        target.click(timeout=10_000)
    except Exception as exc:  # noqa: BLE001 - reported, then the run continues
        report.fail(where, f"could not click {role} {name!r}: {str(exc).splitlines()[0]}")
        return
    wait_ready(page)


def demo_path(page: Page, base: str, report: Report, tag: str) -> None:
    """Overview, guided demo (approve, read the note, record transport, forecast), Results, decision log."""
    w = f"{tag} demo"
    visit(page, f"{base}/", report, f"{w} overview", f"{tag}_demo_01_overview")
    click(page, report, w, "button", "Start the guided demo")
    check(page, report, f"{w} guided demo", f"{tag}_demo_02_guided")
    click(page, report, w, "button", "Approve request")
    check(page, report, f"{w} approved", f"{tag}_demo_03_approved")
    click(page, report, w, "button", "Next: discharge task")
    click(page, report, w, "button", "Read this note")
    page.wait_for_timeout(1500)
    wait_ready(page, 90)
    body = page.inner_text("body")
    live = [line.strip() for line in body.splitlines() if re.search(r"\d ms\b", line)]  # this read's model and latency
    reader = ("unknown" if not live else f"rule-based backup: {live[0]}" if "Rule-based" in live[0]
              else f"local model: {live[0]}")
    report.info[f"{tag} note reader"] = reader
    if reader == "unknown":
        report.fail(w, "the note reader did not say which reader answered")
    check(page, report, f"{w} note read", f"{tag}_demo_04_note")
    click(page, report, w, "button", "Record transport as arranged")
    check(page, report, f"{w} transport", f"{tag}_demo_05_transport")
    click(page, report, w, "button", "Next: bed forecast")
    check(page, report, f"{w} forecast", f"{tag}_demo_06_forecast")
    click(page, report, w, "link", "Finish: see the decisions in the log")
    check(page, report, f"{w} decision log", f"{tag}_demo_07_log")
    if "approve" not in page.inner_text("body").lower():
        report.fail(w, "the decision log does not show the approval")
    visit(page, f"{base}/{NAV.IMPACT.url}", report, f"{w} results", f"{tag}_demo_08_results")


def run(base: str, *, demo: bool = True) -> Report:
    OUT.mkdir(exist_ok=True)
    report = Report()
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        for tag, (w, h) in VIEWPORTS.items():
            ctx = browser.new_context(viewport={"width": w, "height": h})
            page = ctx.new_page()
            page.on("pageerror", lambda e, tag=tag: report.fail(f"{tag} js", str(e)[:200]))
            page.on("console", lambda m, tag=tag: m.type == "error" and "Failed to load resource" not in m.text
                    and report.fail(f"{tag} console", m.text[:200]))
            # Streamlit probes <page>/_stcore/... on a deep link before it falls back to the root: not a fault
            page.on("response", lambda r, tag=tag: r.status >= 400 and r.url.startswith(base)
                    and "/_stcore/" not in r.url and report.fail(f"{tag} http {r.status}", r.url))
            page.goto(f"{base}/")  # warm the server caches so timings measure a page, not a cold start
            wait_ready(page, 90)
            urls = {"overview-root": "", **{spec.url: spec.url for spec in NAV.ALL_PAGES}}
            links: set[str] = set()
            for name, path in urls.items():
                visit(page, f"{base}/{path}", report, f"{tag} {name}", f"{tag}_{name}")
                links |= set(page.evaluate(LINKS_JS))
            for href in sorted(links):
                try:
                    with urllib.request.urlopen(href.split("?")[0], timeout=10) as r:  # noqa: S310 - 127.0.0.1 only
                        if r.status != 200:
                            report.fail(f"{tag} link", f"{href} -> {r.status}")
                except Exception as exc:  # noqa: BLE001
                    report.fail(f"{tag} link", f"{href}: {exc}")
            if demo:
                demo_path(page, base, report, tag)
            ctx.close()
        browser.close()
    return report


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", help="check a running app instead of starting one")
    ap.add_argument("--no-demo", action="store_true")
    args = ap.parse_args()
    proc = None
    base = args.url
    if not base:
        port = free_port()
        proc = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "app.py", "--server.port", str(port),
                                 "--server.address", "127.0.0.1", "--server.headless", "true"], cwd=ROOT,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        base = f"http://127.0.0.1:{port}"
        for _ in range(60):
            try:
                urllib.request.urlopen(base, timeout=2)  # noqa: S310
                break
            except Exception:  # noqa: BLE001
                time.sleep(1)
    try:
        report = run(base.rstrip("/"), demo=not args.no_demo)
    finally:
        if proc:
            proc.terminate()
    (OUT / "report.json").write_text(json.dumps({"problems": report.problems, "info": report.info,
                                                 "timings": report.timings, "screenshots": report.shots}, indent=1))
    for key, value in report.info.items():
        print("INFO", key, "->", value)
    for line in report.problems:
        print("FAIL", line)
    slowest = sorted(report.timings.items(), key=lambda kv: -kv[1])[:5]
    print(f"{len(report.problems)} problems; {len(report.shots)} screenshots in qa_screens/; slowest: {slowest}")
    return 1 if report.problems else 0


if __name__ == "__main__":
    sys.exit(main())
