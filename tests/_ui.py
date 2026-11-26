"""Shared AppTest readers for the UI tests."""

from html import unescape


def html_text(app) -> str:
    return unescape(" ".join(item.proto.body for item in app.get("html")))


def kpi_value(app, label: str) -> str | None:
    """A headline number by its label, whether drawn as st.metric or as a design-system kpi card."""
    for m in app.metric:
        if m.label == label:
            return m.value
    html = html_text(app)
    marker = f"<dt>{label}</dt><dd class=\"hv-kpi-value\">"
    if marker in html:
        return html.split(marker, 1)[1].split("</dd>", 1)[0]
    return None


def page_sentences(app) -> list[str]:
    """Every visible sentence on the page: titles, headings, text, captions, metrics and HTML (styles removed)."""
    import re

    out = []
    for kind in ("title", "header", "subheader", "markdown", "caption"):
        out += [e.value for e in getattr(app, kind)]
    out += [f"{m.label}: {m.value}" for m in app.metric]
    for h in app.get("html"):
        body = re.sub(r"<style.*?</style>", " ", unescape(h.proto.body), flags=re.S)
        if "--hv-" in body or "@font-face" in body:  # the stylesheet itself
            continue
        out.append(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)))
    sentences = []
    for text in out:
        sentences += [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n", re.sub(r"[*_`]", "", text)) if s.strip()]
    return sentences
