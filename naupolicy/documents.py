"""Text extraction for attached policy documents (PDF, DOCX)."""
from __future__ import annotations

import io
import re
import zipfile
from typing import Optional, Tuple
from xml.etree import ElementTree as ET

from .util import _heading_text, _is_caps_heading, caps_heading_line, reflow_pdf_text, strip_running_lines

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def extract_pdf(content: bytes) -> Tuple[Optional[str], Optional[str], int]:
    from pypdf import PdfReader
    try:
        reader = PdfReader(io.BytesIO(content))
        pages = []
        for page in reader.pages:
            try:
                pages.append(page.extract_text() or "")
            except Exception as e:  # pragma: no cover - damaged page
                pages.append(f"[page text could not be extracted: {e}]")
        n = len(reader.pages)
    except Exception as e:
        return None, f"pdf read error: {e}", 0
    pages = strip_running_lines(pages)
    raw = "\n\n".join(pages)
    if len(raw.strip()) < 40 * max(1, n) / 2:
        return reflow_pdf_text(raw) if raw.strip() else None, "little or no text layer (scanned PDF?)", n
    return reflow_pdf_text(raw), None, n


def extract_docx(content: bytes) -> Tuple[Optional[str], Optional[str], int]:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            xml = z.read("word/document.xml")
    except Exception as e:
        return None, f"docx read error: {e}", 0
    root = ET.fromstring(xml)
    body = root.find(f"{W}body")
    lines = []
    for el in list(body) if body is not None else []:
        if el.tag == f"{W}p":
            lines.append(_para_text(el))
        elif el.tag == f"{W}tbl":
            for tr in el.iter(f"{W}tr"):
                cells = [" ".join(_para_text(p) for p in tc.iter(f"{W}p")).strip() for tc in tr.iter(f"{W}tc")]
                lines.append("| " + " | ".join(cells) + " |")
    text = "\n\n".join(l for l in lines if l.strip())
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n", None, 0


def _para_text(p) -> str:
    parts = []
    for node in p.iter():
        if node.tag == f"{W}t" and node.text:
            parts.append(node.text)
        elif node.tag == f"{W}tab":
            parts.append("\t")
        elif node.tag in (f"{W}br", f"{W}cr"):
            parts.append("\n")
    style = p.find(f"{W}pPr/{W}pStyle")
    text = "".join(parts).strip()
    val = style.get(f"{W}val", "") if style is not None else ""
    m = re.match(r"Heading(\d)", val)
    if text and m:
        if _is_caps_heading(text):
            text = _heading_text(text)
        text = "#" * min(6, int(m.group(1)) + 2) + " " + text
    elif text and "List" in val:
        text = "- " + text
    elif text:
        text = caps_heading_line(text)
    return text


def extract_text(content: bytes, ext: str) -> Tuple[Optional[str], Optional[str], int]:
    """Return (text, problem, pages)."""
    if ext == "pdf":
        return extract_pdf(content)
    if ext == "docx":
        return extract_docx(content)
    return None, f"text extraction not supported for .{ext}", 0
