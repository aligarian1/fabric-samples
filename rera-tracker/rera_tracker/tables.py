"""Dependency-free helpers for reading HTML tables.

The Haryana RERA site is plain server-rendered HTML with a few quirks: stray
closing tags, links that exist only as ``onclick="window.open('...')"``
handlers, and tiny forms used as "View" buttons.  This module turns such a page
into a list of tables whose cells keep their text, links, pop-up links and
forms, so the site-specific code can stay short.
"""
from __future__ import annotations

import html as _html
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Dict, List, Optional

_WS = re.compile(r"\s+")
_WINDOW_OPEN = re.compile(r"window\.open\(\s*['\"]([^'\"]+)['\"]")
_NUMBER = re.compile(r"-?\d+(?:,\d{2,3})*(?:\.\d+)?")
_HEADING_TAGS = ("b", "h1", "h2", "h3", "h4")


def squash(text: str) -> str:
    """Collapse runs of whitespace and trim."""
    return _WS.sub(" ", text or "").strip()


def to_number(text: str) -> Optional[float]:
    """Return the number in ``text`` if the whole string is a number."""
    text = squash(text)
    if not text or not _NUMBER.fullmatch(text):
        return None
    return float(text.replace(",", ""))


def plain_text(html: str) -> str:
    """Strip comments, scripts, styles and tags from a page."""
    text = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    text = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return squash(_html.unescape(text))


@dataclass
class Form:
    action: str
    fields: Dict[str, str] = field(default_factory=dict)


@dataclass
class Cell:
    text: str = ""
    links: List[str] = field(default_factory=list)
    popups: List[str] = field(default_factory=list)
    onclicks: List[str] = field(default_factory=list)
    forms: List[Form] = field(default_factory=list)
    is_header: bool = False


@dataclass
class Table:
    heading: str
    headers: List[str]
    rows: List[List[Cell]]
    attrs: Dict[str, str] = field(default_factory=dict)

    def find_column(self, *needles: str) -> Optional[int]:
        """Index of the first header containing any of ``needles`` (case-insensitive)."""
        lowered = [h.lower() for h in self.headers]
        for needle in needles:
            needle = needle.lower()
            for i, header in enumerate(lowered):
                if needle in header:
                    return i
        return None


@dataclass
class ParsedPage:
    tables: List[Table]
    headings: List[str]


class _OpenTable:
    def __init__(self, attrs: Dict[str, str], heading: str) -> None:
        self.attrs = attrs
        self.heading = heading
        self.rows: List[List[Cell]] = []
        self.row: Optional[List[Cell]] = None
        self.cell: Optional[Cell] = None
        self.parts: List[str] = []


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: List[Table] = []
        self.headings: List[str] = []
        self._stack: List[_OpenTable] = []
        self._skip = 0
        self._form: Optional[Form] = None
        self._heading_parts: Optional[List[str]] = None
        self._heading_tag = ""
        self._heading_depth = 0
        self._last_heading = ""

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _note_onclick(cell: Cell, onclick: str) -> None:
        onclick = (onclick or "").strip()
        if not onclick:
            return
        cell.onclicks.append(onclick)
        cell.popups.extend(_WINDOW_OPEN.findall(onclick))

    @staticmethod
    def _close_cell(top: _OpenTable) -> None:
        if top.cell is None:
            return
        top.cell.text = squash("".join(top.parts))
        if top.row is None:
            top.row = []
        top.row.append(top.cell)
        top.cell = None
        top.parts = []

    def _close_row(self, top: _OpenTable) -> None:
        self._close_cell(top)
        if top.row:
            top.rows.append(top.row)
        top.row = None

    def _finish_table(self, top: _OpenTable) -> None:
        headers: List[str] = []
        data: List[List[Cell]] = []
        for row in top.rows:
            if all(cell.is_header for cell in row):
                if not headers:
                    headers = [cell.text for cell in row]
            else:
                data.append(row)
        self.tables.append(Table(top.heading, headers, data, top.attrs))
        # A one-cell table is used on the site as a section title.
        if len(top.rows) == 1 and len(top.rows[0]) == 1:
            title = top.rows[0][0].text
            if title and to_number(title) is None:
                self._last_heading = title

    # -- HTMLParser hooks --------------------------------------------------
    def handle_starttag(self, tag: str, attrs) -> None:
        a = {k: (v or "") for k, v in attrs}
        if tag in ("script", "style"):
            self._skip += 1
            return
        if tag == "table":
            self._stack.append(_OpenTable(a, self._last_heading))
            return
        top = self._stack[-1] if self._stack else None
        if top is not None:
            if tag == "tr":
                self._close_row(top)
                top.row = []
            elif tag in ("td", "th"):
                self._close_cell(top)
                top.cell = Cell(is_header=(tag == "th"))
                top.parts = []
            elif top.cell is not None:
                cell = top.cell
                if tag == "a":
                    href = a.get("href", "").strip()
                    if href and not href.lower().startswith("javascript"):
                        cell.links.append(href)
                    self._note_onclick(cell, a.get("onclick", ""))
                elif tag == "form":
                    self._form = Form(action=a.get("action", "").strip())
                    cell.forms.append(self._form)
                elif tag == "input":
                    if self._form is not None and a.get("name"):
                        self._form.fields[a["name"]] = a.get("value", "")
                    self._note_onclick(cell, a.get("onclick", ""))
                elif tag == "button":
                    self._note_onclick(cell, a.get("onclick", ""))
                elif tag == "br":
                    top.parts.append(" ")
            return
        # Outside any table: look for section headings.
        if self._heading_parts is None:
            if tag == "div" and "cus-top-heading" in a.get("class", ""):
                self._heading_parts, self._heading_tag, self._heading_depth = [], "div", 1
            elif tag in _HEADING_TAGS:
                self._heading_parts, self._heading_tag, self._heading_depth = [], tag, 1
        elif tag == self._heading_tag:
            self._heading_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
            return
        top = self._stack[-1] if self._stack else None
        if top is not None:
            if tag in ("td", "th"):
                self._close_cell(top)
            elif tag == "tr":
                self._close_row(top)
            elif tag == "form":
                self._form = None
            elif tag == "table":
                self._close_row(top)
                self._stack.pop()
                self._finish_table(top)
            return
        if self._heading_parts is not None and tag == self._heading_tag:
            self._heading_depth -= 1
            if self._heading_depth <= 0:
                text = squash("".join(self._heading_parts))
                self._heading_parts = None
                if text:
                    self._last_heading = text
                    self.headings.append(text)

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        top = self._stack[-1] if self._stack else None
        if top is not None:
            if top.cell is not None:
                top.parts.append(data)
            return
        if self._heading_parts is not None:
            self._heading_parts.append(data)


def parse_tables(html: str) -> ParsedPage:
    """Parse ``html`` and return its tables (in closing order) and headings."""
    parser = _TableParser()
    parser.feed(html)
    parser.close()
    # Close anything the page left open.
    while parser._stack:  # noqa: SLF001 - internal tidy-up
        top = parser._stack.pop()
        parser._close_row(top)
        parser._finish_table(top)
    return ParsedPage(parser.tables, parser.headings)
