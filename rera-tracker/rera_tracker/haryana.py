"""Reader for the public pages of Haryana RERA (https://haryanarera.gov.in).

Only pages that the site links openly from its own menus are read here: the
registered-projects list, a project's details page, its list of quarterly
progress reports and an individual quarterly report.  None of them sits behind
a login or a captcha.  The site's "search by registration number" form does
have a captcha, so this module never touches it.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Dict, List, Optional
from urllib.parse import urlparse

from .tables import Cell, Table, parse_tables, plain_text, squash, to_number

HOST = "haryanarera.gov.in"
BASE = "https://" + HOST
AUTHORITIES = {"panchkula": 1, "gurugram": 2}

_MONTHS = {
    name: number
    for number, name in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1
    )
}
_HEARING_TEXT_LIMIT = 600


class ParseError(Exception):
    """The page did not have the layout this reader expects."""


def parse_date(text: str) -> Optional[date]:
    """Parse the date formats used on the site; ``None`` for blanks and placeholders."""
    text = squash(text)
    day = month = year = None
    match = re.fullmatch(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})", text)
    if match:
        day, month, year = (int(g) for g in match.groups())
    else:
        match = re.fullmatch(r"(\d{1,2})[\-\s]([A-Za-z]{3})[A-Za-z]*[\-\s,]+(\d{4})", text)
        if match:
            day, year = int(match.group(1)), int(match.group(3))
            month = _MONTHS.get(match.group(2).lower())
        else:
            match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text)
            if match:
                year, month, day = (int(g) for g in match.groups())
    if not (day and month and year):
        return None
    if year < 1990:  # the site shows 01/01/1970 where it has no date
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _iso(value: Optional[date]) -> Optional[str]:
    return value.isoformat() if value else None


def same_site(url: Optional[str]) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    return parsed.scheme == "https" and parsed.hostname == HOST


def _checked(url: str) -> str:
    if not same_site(url):
        raise ValueError("refusing to fetch a URL outside %s: %r" % (HOST, url))
    return url


# --------------------------------------------------------------------------
# Registered projects list
# --------------------------------------------------------------------------
@dataclass
class ListedProject:
    authority: str
    project_id: str
    name: str
    builder: str
    location: str
    district: str
    reg_no: str
    registered_with: str
    registered_on: Optional[str]
    valid_upto: Optional[str]
    lapsed: bool
    corrigendum: bool
    occ: bool
    monitoring: bool
    site_id: Optional[int]
    detail_url: Optional[str]
    form_url: Optional[str]
    certificate_url: Optional[str]
    qpr_url: Optional[str]
    monitoring_url: Optional[str]

    @property
    def key(self) -> str:
        return "%s:%s" % (self.authority, self.project_id)

    def to_dict(self) -> Dict[str, object]:
        data = asdict(self)
        data["key"] = self.key
        return data


_LIST_COLUMNS = {
    "reg": ("registration certificate",),
    "pid": ("project id",),
    "name": ("project name",),
    "builder": ("builder",),
    "location": ("project location",),
    "district": ("project district",),
    "regwith": ("registered with",),
    "form": ("form a-h", "details of project"),
    "valid": ("registration up",),
    "cert": ("view certificate",),
    "qpr": ("quarterly",),
    "monitoring": ("monitoring",),
    "occ": ("oc/cc",),
}


def _first(urls: List[str], needle: str) -> Optional[str]:
    for url in urls:
        if needle in url and same_site(url):
            return url
    return None


def _project_ref(project_id: str, reg_no: str) -> Optional[str]:
    """The site's project ID, or an ID built from the registration number.

    A few dozen projects registered in 2017-18 show "NA" as their project ID.
    """
    if project_id and project_id.upper() not in ("NA", "N/A", "-", "--"):
        return project_id
    core = re.split(r"\s+DATED\b|\(", reg_no, maxsplit=1, flags=re.I)[0]
    slug = re.sub(r"[^A-Za-z0-9]+", "-", core).strip("-").upper()
    return "REG-" + slug if slug else None


def parse_registered_projects(html: str, authority: str) -> List[ListedProject]:
    if authority not in AUTHORITIES:
        raise ValueError("unknown authority %r" % authority)
    table: Optional[Table] = None
    for candidate in parse_tables(html).tables:
        if candidate.find_column("project id") is not None and candidate.find_column("registration up") is not None:
            table = candidate
            break
    if table is None:
        raise ParseError("registered-projects table not found")
    col = {name: table.find_column(*needles) for name, needles in _LIST_COLUMNS.items()}

    def cell(row: List[Cell], name: str) -> Cell:
        index = col[name]
        return row[index] if index is not None and index < len(row) else Cell()

    projects: List[ListedProject] = []
    seen = set()
    for row in table.rows:
        reg_cell = cell(row, "reg")
        lapsed = "lapsed" in reg_cell.text.lower()
        reg_no = squash(re.sub(r"lapsed\s+project", "", reg_cell.text, flags=re.I))
        project_id = _project_ref(cell(row, "pid").text, reg_no)
        if not project_id:
            continue
        registered_on = None
        dated = re.search(r"DATED\s*:?\s*(\d{1,2}[./\-]\d{1,2}[./\-]\d{4})", reg_no, flags=re.I)
        if dated:
            registered_on = _iso(parse_date(dated.group(1)))

        site_id = None
        detail_url = None
        for link in cell(row, "pid").links + reg_cell.links:
            match = re.search(r"/searchprojectDetail/(\d+)", link)
            if match:
                site_id = int(match.group(1))
                detail_url = "%s/view_project/searchprojectDetail/%d" % (BASE, site_id)
                break

        monitoring_cell = cell(row, "monitoring")
        monitoring_url = _first(monitoring_cell.popups + monitoring_cell.links, "view_monitoring_cases")
        project = ListedProject(
            authority=authority,
            project_id=project_id,
            name=cell(row, "name").text,
            builder=cell(row, "builder").text,
            location=cell(row, "location").text,
            district=cell(row, "district").text,
            reg_no=reg_no,
            registered_with=cell(row, "regwith").text,
            registered_on=registered_on,
            valid_upto=_iso(parse_date(cell(row, "valid").text)),
            lapsed=lapsed,
            corrigendum="corrigendum" in cell(row, "cert").text.lower(),
            occ="oc/cc" in cell(row, "occ").text.lower(),
            monitoring=bool(monitoring_url) or "monitoring" in monitoring_cell.text.lower(),
            site_id=site_id,
            detail_url=detail_url,
            form_url=_first(cell(row, "form").links, "project_preview_open"),
            certificate_url=_first(cell(row, "cert").links, "view_certificate"),
            qpr_url=_first(cell(row, "qpr").popups + cell(row, "qpr").links, "print_quarterly_schedules"),
            monitoring_url=monitoring_url,
        )
        if project.key in seen:
            continue
        seen.add(project.key)
        projects.append(project)
    return projects


# --------------------------------------------------------------------------
# Quarterly progress reports
# --------------------------------------------------------------------------
@dataclass
class Quarter:
    no: int
    year: int
    start: Optional[str] = None
    end: Optional[str] = None
    action: str = ""
    fields: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return {"no": self.no, "year": self.year, "start": self.start, "end": self.end}


def parse_quarter_schedule(html: str) -> List[Quarter]:
    """Quarters for which the site shows a progress report, oldest first."""
    table: Optional[Table] = None
    for candidate in parse_tables(html).tables:
        if candidate.find_column("quarter no") is not None:
            table = candidate
            break
    if table is None:
        raise ParseError("quarterly-progress table not found")
    quarters: Dict[tuple, Quarter] = {}
    for row in table.rows:
        if not row:
            continue
        match = re.search(r"(\d)\s*of\s*(\d{4})", row[0].text)
        if not match:
            continue
        number, year = int(match.group(1)), int(match.group(2))
        if not 1 <= number <= 4:
            continue
        quarter = Quarter(no=number, year=year)
        if len(row) > 1:
            quarter.start = _iso(parse_date(row[1].text))
        if len(row) > 2:
            quarter.end = _iso(parse_date(row[2].text))
        for candidate_cell in reversed(row):
            if candidate_cell.forms:
                quarter.action = candidate_cell.forms[0].action
                quarter.fields = dict(candidate_cell.forms[0].fields)
                break
        quarters[(year, number)] = quarter
    return [quarters[key] for key in sorted(quarters)]


@dataclass
class QuarterReport:
    submitted_on: Optional[str]
    values: Dict[str, float]
    documents: List[Dict[str, Optional[str]]]

    def to_dict(self) -> Dict[str, object]:
        return {"submitted_on": self.submitted_on, "values": dict(self.values), "documents": list(self.documents)}


# (key, part of the section title, start of the row label); amounts are in lakh rupees.
_REPORT_FIELDS = [
    ("collected_from_buyers", "cash inflow", "amount collected from allottees"),
    ("loans_availed", "cash inflow", "amount availed from the bank"),
    ("inflow_total", "cash inflow", "total"),
    ("outflow_total", "cash outflow", "total"),
    ("escrow_open", "project account", "opening balance"),
    ("escrow_deposited", "project account", "amount deposited"),
    ("escrow_withdrawn", "project account", "amount withdrawn"),
    ("escrow_close", "project account", "balance at the end"),
    ("plots_total", "", "total plots"),
    ("apartments_total", "", "total apartments"),
    ("estimated_cost", "estimated cost", "total"),
]
_REPORT_SUMS = [
    ("plots_sold_in_quarter", "plots sold in the quarter"),
    ("apartments_sold_in_quarter", "apartments sold in the quarter"),
]


def parse_quarter_report(html: str) -> QuarterReport:
    text = plain_text(html)
    submitted = None
    match = re.search(
        r"Report Online Submission Date\s*:?\s*(\d{1,2}[\-/ ][A-Za-z0-9]{2,9}[\-/ ]\d{4})", text, flags=re.I
    )
    if match:
        submitted = parse_date(match.group(1))

    entries: List[tuple] = []
    documents: List[Dict[str, Optional[str]]] = []
    for table in parse_tables(html).tables:
        section = table.heading.lower()
        in_documents = False
        for row in table.rows:
            texts = [c.text for c in row]
            if any("document description" in t.lower() for t in texts):
                in_documents = True
                continue
            if in_documents:
                if len(texts) >= 3 and texts[1]:
                    documents.append({"description": texts[1], "uploaded_on": _iso(parse_date(texts[2]))})
                continue
            if len(texts) == 1:
                if texts[0] and to_number(texts[0]) is None:
                    section = texts[0].lower()
                continue
            if len(texts) >= 2:
                value = to_number(texts[-1])
                label = texts[-2]
                if value is not None and label and to_number(label) is None:
                    entries.append((section, label.lower(), value))

    if not entries and submitted is None:
        raise ParseError("quarterly report has no recognisable content")

    values: Dict[str, float] = {}
    for key, section_part, label_start in _REPORT_FIELDS:
        for section, label, value in entries:
            if section_part in section and label.startswith(label_start):
                values[key] = value
                break
    for key, section_part in _REPORT_SUMS:
        matching = [value for section, _label, value in entries if section_part in section]
        if matching:
            values[key] = sum(matching)
    return QuarterReport(_iso(submitted), values, documents)


# --------------------------------------------------------------------------
# Project details page
# --------------------------------------------------------------------------
@dataclass
class Hearing:
    date: Optional[str]
    status: str
    text: str
    order_url: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class ProjectDetail:
    status: Optional[str]
    next_hearing: Optional[str]
    hearings: List[Hearing]

    def to_dict(self) -> Dict[str, object]:
        return {
            "status": self.status,
            "next_hearing": self.next_hearing,
            "hearings": [h.to_dict() for h in self.hearings],
        }


def parse_project_detail(html: str) -> ProjectDetail:
    status = next_hearing = None
    hearings: List[Hearing] = []
    found = False
    for table in parse_tables(html).tables:
        status_col = table.find_column("current status")
        if status_col is not None and table.rows:
            found = True
            row = table.rows[0]
            if status_col < len(row):
                status = row[status_col].text or None
            next_col = table.find_column("next date of hearing")
            if next_col is not None and next_col < len(row):
                next_hearing = row[next_col].text or None
            continue
        date_col = table.find_column("date of hearing")
        text_col = table.find_column("proceedings")
        if date_col is not None and text_col is not None:
            found = True
            state_col = table.find_column("status")
            order_col = table.find_column("order")
            for row in table.rows:
                if max(date_col, text_col) >= len(row):
                    continue
                order_url = None
                if order_col is not None and order_col < len(row):
                    order_url = next((u for u in row[order_col].links if same_site(u)), None)
                text = row[text_col].text
                if len(text) > _HEARING_TEXT_LIMIT:
                    text = text[:_HEARING_TEXT_LIMIT].rstrip() + "…"
                hearings.append(
                    Hearing(
                        date=_iso(parse_date(row[date_col].text)),
                        status=row[state_col].text if state_col is not None and state_col < len(row) else "",
                        text=text,
                        order_url=order_url,
                    )
                )
    if not found:
        raise ParseError("project details tables not found")
    return ProjectDetail(status, next_hearing, hearings)


# --------------------------------------------------------------------------
# Live access
# --------------------------------------------------------------------------
class HaryanaSource:
    """Fetches and parses the pages above through a polite fetcher."""

    name = "haryana"

    def __init__(self, fetcher) -> None:
        self.fetcher = fetcher

    @staticmethod
    def list_url(authority: str) -> str:
        return "%s/admincontrol/registered_projects/%d" % (BASE, AUTHORITIES[authority])

    def fetch_listed(self, authority: str) -> List[ListedProject]:
        return parse_registered_projects(self.fetcher.get(self.list_url(authority)), authority)

    def fetch_detail(self, detail_url: str) -> ProjectDetail:
        return parse_project_detail(self.fetcher.get(_checked(detail_url)))

    def fetch_quarters(self, qpr_url: str) -> List[Quarter]:
        return parse_quarter_schedule(self.fetcher.get(_checked(qpr_url)))

    def fetch_report(self, quarter: Quarter) -> QuarterReport:
        return parse_quarter_report(self.fetcher.post(_checked(quarter.action), quarter.fields))
