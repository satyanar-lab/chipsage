"""PDF text + errata extraction — the ONLY module that imports PyMuPDF.

Mirrors the role of :mod:`chipsage.svd` for Tier-1: it is the single place that touches the
third-party parser (here ``pymupdf``) and adapts it into the vendor-agnostic domain model
(:class:`~chipsage.models.PageText`, :class:`~chipsage.models.Erratum`). Everything downstream
speaks the model and never imports ``pymupdf``.

Tier-3 law (Constitution): text is extracted **verbatim** and page-anchored. Nothing here
paraphrases — it reproduces the datasheet's own words and records the page they came from.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pymupdf

from .models import Erratum, PageText

# The structured labels each erratum lists, in the datasheet's own wording. They appear as
# standalone lines above their values; we use them to reconstruct clean section text.
_ERRATA_LABELS = (
    "Reference",
    "Summary",
    "Description",
    "Workaround",
    "Affects",
    "Fixed by",
    "Fixed in",
    "Notes",
    "Impact",
)


def _page_label(page: pymupdf.Page, index: int) -> str:
    """The datasheet's printed page label, falling back to the 1-based physical page."""
    label = page.get_label() if hasattr(page, "get_label") else ""
    return label or str(index + 1)


def document_title(path: str | Path) -> str | None:
    """The PDF's embedded title (used for citations), or ``None`` if absent."""
    with pymupdf.open(path) as doc:
        title = (doc.metadata or {}).get("title")
    return title.strip() if title else None


def page_count(path: str | Path) -> int:
    with pymupdf.open(path) as doc:
        return doc.page_count


def extract_pages(path: str | Path) -> Iterator[PageText]:
    """Yield the verbatim text of every page, page-anchored for citation."""
    with pymupdf.open(path) as doc:
        for i in range(doc.page_count):
            page = doc.load_page(i)
            yield PageText(pdf_page=i + 1, label=_page_label(page, i), text=page.get_text())


def _errata_bounds(doc: pymupdf.Document) -> tuple[int, int]:
    """Return the ``[start, end)`` physical-page range of the errata appendix.

    The appendix begins at the large "Appendix _: Errata" heading and ends at the next
    top-level "Appendix" heading (or the end of the document).
    """
    start = end = None
    for i in range(doc.page_count):
        for block in doc.load_page(i).get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    text = span["text"].strip()
                    if span["size"] >= 20 and text.startswith("Appendix") and "Errata" in text:
                        start = i
                    elif (
                        start is not None
                        and end is None
                        and span["size"] >= 20
                        and text.startswith("Appendix")
                        and "Errata" not in text
                    ):
                        end = i
    if start is None:
        return 0, 0
    return start, (end if end is not None else doc.page_count)


def _line_text(spans: list[dict]) -> str:
    return "".join(span["text"] for span in spans).strip()


def _reconstruct(body: list[str]) -> tuple[str, str | None]:
    """Rebuild an erratum body from its collected lines, and pull out its Summary title.

    Wrapped/superscript line-breaks are joined with spaces within each labelled section, so
    the stored text reads as clean prose while remaining the datasheet's own words. The
    redundant "Reference" section (it just repeats the code) is dropped.
    """
    sections: list[tuple[str | None, list[str]]] = []
    for line in body:
        if line in _ERRATA_LABELS:
            sections.append((line, []))
        elif sections:
            sections[-1][1].append(line)
        else:
            sections.append((None, [line]))

    parts: list[str] = []
    title: str | None = None
    for label, lines in sections:
        value = re.sub(r"\s+", " ", " ".join(lines)).strip()
        if label == "Reference":
            continue
        if label == "Summary":
            title = value or None
        if label:
            parts.append(label)
        if value:
            parts.append(value)
    return "\n".join(parts).strip(), title


def extract_errata(path: str | Path, code_prefix: str) -> list[Erratum]:
    """Extract every ``{code_prefix}-E<n>`` erratum, grouped under its datasheet block heading.

    Headings are identified by font size: the hardware-block heading (~16pt bold) sets the
    peripheral grouping; the erratum code (~12pt bold) opens a new entry. The body between one
    code heading and the next is captured verbatim (running footers stripped).
    """
    code_re = re.compile(rf"^{re.escape(code_prefix)}-E\d+$")
    out: list[Erratum] = []

    with pymupdf.open(path) as doc:
        start, end = _errata_bounds(doc)
        peripheral: str | None = None
        cur: dict | None = None

        def flush() -> None:
            nonlocal cur
            if cur is not None:
                text, title = _reconstruct(cur["body"])
                out.append(
                    Erratum(
                        code=cur["code"],
                        peripheral=cur["peripheral"],
                        title=title,
                        label=cur["label"],
                        pdf_page=cur["pdf_page"],
                        text=text,
                    )
                )
            cur = None

        for i in range(start, end):
            page = doc.load_page(i)
            label = _page_label(page, i)
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    spans = line["spans"]
                    text = _line_text(spans)
                    if not text:
                        continue
                    max_size = max(span["size"] for span in spans)
                    bold = any("Bold" in span["font"] for span in spans)
                    # The running header/footer (doc title, block name, page number) and the
                    # big appendix title are the datasheet's only RobotoSlab text; erratum
                    # headings and body prose never are — so font family cleanly strips them.
                    is_slab = all("RobotoSlab" in span["font"] for span in spans)

                    # hardware-block heading (~16pt bold) — the peripheral grouping
                    if (
                        14.5 <= max_size <= 19.5
                        and bold
                        and not is_slab
                        and not code_re.match(text)
                        and len(text) < 48
                    ):
                        flush()
                        peripheral = text
                        continue
                    # erratum code heading (~12pt bold)
                    if 10.5 <= max_size <= 13.5 and bold and code_re.match(text):
                        flush()
                        cur = {
                            "code": text,
                            "peripheral": peripheral,
                            "label": label,
                            "pdf_page": i + 1,
                            "body": [],
                        }
                        continue
                    # drop the running header/footer and the appendix title (all RobotoSlab)
                    if is_slab:
                        continue
                    # appendix intro sentence
                    if text.startswith(("Hardware blocks are listed", "Alphabetical by")):
                        continue
                    if cur is not None:
                        cur["body"].append(text)
        flush()

    return out
