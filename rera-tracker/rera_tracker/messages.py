"""Plain-language messages, in English and Hindi.

Messages state what the public record shows and link to it.  They never judge
a builder: no "delayed", "fraud" or "safe", only dates and figures as filed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Tuple

from .detect import Event, last_ended_quarter, latest_quarter, quarter_end

LANGS = ("en", "hi")
LIST_URL = "https://haryanarera.gov.in"

_MONTHS = {
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    "hi": ["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"],
}
_QUARTERS = {
    "en": {1: "Jan–Mar", 2: "Apr–Jun", 3: "Jul–Sep", 4: "Oct–Dec"},
    "hi": {1: "जनवरी–मार्च", 2: "अप्रैल–जून", 3: "जुलाई–सितंबर", 4: "अक्टूबर–दिसंबर"},
}

_T: Dict[str, Dict[str, str]] = {
    "en": {
        "t.baseline": "Tracking started",
        "t.marked_lapsed": "Marked as a lapsed project",
        "t.occ_uploaded": "Occupation or completion certificate now on record",
        "t.corrigendum_added": "Correction notice added to the registration",
        "t.monitoring_started": "Monitoring case on record",
        "t.validity_extended": "Registration extended",
        "t.validity_changed": "Registration date changed",
        "t.registration_expired": "Registration date has passed",
        "t.registration_expiring": "Registration ends soon",
        "t.status_changed": "Status changed",
        "t.next_hearing": "Next hearing date",
        "t.new_hearing": "New hearing entry",
        "t.new_report": "New quarterly report filed",
        "t.report_overdue": "No quarterly report on record",
        "t.removed_from_list": "No longer in the registered-projects list",
        "b.marked_lapsed": 'The HRERA registered-projects list now shows this project as a "Lapsed Project".',
        "b.occ_uploaded": "The HRERA list now shows an occupation, completion or part-completion certificate (OC/CC/PCC) entry for this project.",
        "b.corrigendum_added": "The HRERA list now shows a corrigendum (a correction notice) against this project's registration certificate.",
        "b.monitoring_started": "The HRERA list now shows monitoring cases for this project.",
        "b.validity": "The registration was valid up to {old}. The HRERA list now shows {new}.",
        "b.registration_expired": "The registration was valid up to {date}, which was {days} days ago. The HRERA list shows no later date and no occupation or completion certificate.",
        "b.registration_expiring": "The registration is valid up to {date}, which is {days} days away.",
        "b.status_changed": 'Status on the HRERA project page changed from "{old}" to "{new}".',
        "b.next_hearing": "The HRERA project page now shows the next date of hearing as: {value}",
        "b.hearing": "Hearing on {date}. Status: {status}.",
        "b.hearing_text": "Record: {text}",
        "b.hearing_order": "Order: {url}",
        "b.report_filed": "The builder filed the report for {quarter} on {date}.",
        "b.report_filed_nodate": "A report for {quarter} is now on record.",
        "b.collected": "Collected from buyers in the quarter: {amount}",
        "b.previous": " (previous report: {amount})",
        "b.account": "Project bank account: opened at {open}, {deposited} deposited, {withdrawn} withdrawn, closed at {close}",
        "b.units": "Units sold in the quarter: {sold} (the project has {total})",
        "b.report_overdue": "No quarterly report for the quarter that ended on {end} appears on the HRERA site as of {today}.",
        "b.latest_is": "The latest report on record is for {quarter}.",
        "b.no_reports": "No quarterly report is on record for this project.",
        "b.removed_from_list": "This project no longer appears in the HRERA registered-projects list.",
        "f.page": "Official page: {url}",
        "f.unsubscribe": "Stop these alerts or delete your data: {url}",
        "f.source": "Source: public records on the Haryana RERA website (haryanarera.gov.in). Figures are as filed by the builder. This is information, not legal advice.",
        "s.project_id": "Project ID",
        "s.builder": "Builder",
        "s.location": "Location",
        "s.reg_no": "Registration no.",
        "s.valid": "Registration valid up to",
        "s.days_left": "{days} days left",
        "s.days_ago": "passed {days} days ago",
        "s.not_shown": "not shown",
        "s.lapsed": "Listed as a lapsed project",
        "s.occ": "OC/CC/PCC on record",
        "s.yes": "Yes",
        "s.no": "No",
        "s.status": "Status",
        "s.next_hearing": "Next hearing",
        "s.reports": "Quarterly reports on record",
        "s.latest_report": "Latest report: {quarter}, filed on {date}",
        "s.latest_report_nodate": "Latest report: {quarter}",
        "s.hearings": "Recent hearing entries",
    },
    "hi": {
        "t.baseline": "ट्रैकिंग शुरू",
        "t.marked_lapsed": "प्रोजेक्ट 'लैप्स्ड' के रूप में दर्ज",
        "t.occ_uploaded": "OC/CC दस्तावेज़ अब दर्ज",
        "t.corrigendum_added": "रजिस्ट्रेशन पर शुद्धिपत्र दर्ज",
        "t.monitoring_started": "मॉनिटरिंग केस दर्ज",
        "t.validity_extended": "रजिस्ट्रेशन की अवधि बढ़ी",
        "t.validity_changed": "रजिस्ट्रेशन की तारीख बदली",
        "t.registration_expired": "रजिस्ट्रेशन की तारीख निकल चुकी है",
        "t.registration_expiring": "रजिस्ट्रेशन जल्द समाप्त होगा",
        "t.status_changed": "स्थिति बदली",
        "t.next_hearing": "अगली सुनवाई की तारीख",
        "t.new_hearing": "सुनवाई की नई प्रविष्टि",
        "t.new_report": "नई तिमाही रिपोर्ट दाखिल",
        "t.report_overdue": "तिमाही रिपोर्ट दर्ज नहीं",
        "t.removed_from_list": "रजिस्टर्ड प्रोजेक्ट सूची में अब नहीं",
        "b.marked_lapsed": 'HRERA की रजिस्टर्ड प्रोजेक्ट सूची में यह प्रोजेक्ट अब "Lapsed Project" के रूप में दर्ज है।',
        "b.occ_uploaded": "HRERA की सूची में इस प्रोजेक्ट के लिए अब ऑक्यूपेशन/कम्प्लीशन सर्टिफिकेट (OC/CC/PCC) की प्रविष्टि दिख रही है।",
        "b.corrigendum_added": "HRERA की सूची में इस प्रोजेक्ट के रजिस्ट्रेशन सर्टिफिकेट पर अब शुद्धिपत्र (corrigendum) दिख रहा है।",
        "b.monitoring_started": "HRERA की सूची में इस प्रोजेक्ट के लिए अब मॉनिटरिंग केस दिख रहे हैं।",
        "b.validity": "रजिस्ट्रेशन पहले {old} तक वैध था। HRERA की सूची में अब {new} दिख रहा है।",
        "b.registration_expired": "रजिस्ट्रेशन {date} तक वैध था, यानी {days} दिन पहले तक। HRERA की सूची में कोई नई तारीख या ऑक्यूपेशन/कम्प्लीशन सर्टिफिकेट नहीं दिख रहा है।",
        "b.registration_expiring": "रजिस्ट्रेशन {date} तक वैध है, यानी {days} दिन बाकी हैं।",
        "b.status_changed": 'HRERA के प्रोजेक्ट पेज पर स्थिति "{old}" से बदलकर "{new}" हो गई है।',
        "b.next_hearing": "HRERA के प्रोजेक्ट पेज पर अगली सुनवाई की तारीख अब यह दिख रही है: {value}",
        "b.hearing": "सुनवाई की तारीख: {date}। स्थिति: {status}।",
        "b.hearing_text": "विवरण: {text}",
        "b.hearing_order": "आदेश: {url}",
        "b.report_filed": "बिल्डर ने {quarter} की रिपोर्ट {date} को दाखिल की।",
        "b.report_filed_nodate": "{quarter} की रिपोर्ट अब दर्ज है।",
        "b.collected": "इस तिमाही में खरीदारों से मिली रकम: {amount}",
        "b.previous": " (पिछली रिपोर्ट: {amount})",
        "b.account": "प्रोजेक्ट का बैंक खाता: शुरुआत में {open}, {deposited} जमा, {withdrawn} निकासी, अंत में {close}",
        "b.units": "इस तिमाही में बिकी यूनिट: {sold} (प्रोजेक्ट में कुल {total})",
        "b.report_overdue": "{end} को समाप्त तिमाही की रिपोर्ट {today} तक HRERA की साइट पर नहीं दिखी।",
        "b.latest_is": "सबसे ताज़ा दर्ज रिपोर्ट {quarter} की है।",
        "b.no_reports": "इस प्रोजेक्ट की कोई तिमाही रिपोर्ट दर्ज नहीं है।",
        "b.removed_from_list": "यह प्रोजेक्ट अब HRERA की रजिस्टर्ड प्रोजेक्ट सूची में नहीं दिख रहा है।",
        "f.page": "आधिकारिक पेज: {url}",
        "f.unsubscribe": "ये अलर्ट बंद करें या अपना डेटा मिटाएँ: {url}",
        "f.source": "स्रोत: हरियाणा RERA की वेबसाइट (haryanarera.gov.in) की सार्वजनिक जानकारी। आंकड़े बिल्डर द्वारा दाखिल किए गए हैं। यह केवल जानकारी है, कानूनी सलाह नहीं।",
        "s.project_id": "प्रोजेक्ट आईडी",
        "s.builder": "बिल्डर",
        "s.location": "स्थान",
        "s.reg_no": "रजिस्ट्रेशन नंबर",
        "s.valid": "रजिस्ट्रेशन की वैधता",
        "s.days_left": "{days} दिन बाकी",
        "s.days_ago": "{days} दिन पहले समाप्त",
        "s.not_shown": "दर्ज नहीं",
        "s.lapsed": "लैप्स्ड प्रोजेक्ट के रूप में दर्ज",
        "s.occ": "OC/CC/PCC दर्ज",
        "s.yes": "हाँ",
        "s.no": "नहीं",
        "s.status": "स्थिति",
        "s.next_hearing": "अगली सुनवाई",
        "s.reports": "दर्ज तिमाही रिपोर्ट",
        "s.latest_report": "सबसे ताज़ा रिपोर्ट: {quarter}, {date} को दाखिल",
        "s.latest_report_nodate": "सबसे ताज़ा रिपोर्ट: {quarter}",
        "s.hearings": "हाल की सुनवाई",
    },
}


def _lang(lang: str) -> str:
    return lang if lang in LANGS else "en"


def tr(lang: str, key: str, **values: object) -> str:
    return _T[_lang(lang)][key].format(**values)


def fmt_date(iso: Optional[str], lang: str) -> str:
    if not iso:
        return tr(lang, "s.not_shown")
    value = date.fromisoformat(iso)
    return "%d %s %d" % (value.day, _MONTHS[_lang(lang)][value.month - 1], value.year)


def fmt_money(lakhs: float, lang: str) -> str:
    """Format an amount given in lakh rupees."""
    hindi = _lang(lang) == "hi"
    if abs(lakhs) >= 100:
        return "₹%s %s" % ("{:,.2f}".format(lakhs / 100.0), "करोड़" if hindi else "crore")
    return "₹%s %s" % ("{:,.2f}".format(lakhs), "लाख" if hindi else "lakh")


def quarter_label(no: int, year: int, lang: str) -> str:
    return "%s %d" % (_QUARTERS[_lang(lang)][no], year)


def _report_lines(report: Optional[dict], previous: Optional[dict], lang: str) -> List[str]:
    values = (report or {}).get("values") or {}
    earlier = (previous or {}).get("values") or {}
    lines: List[str] = []
    if "collected_from_buyers" in values:
        line = tr(lang, "b.collected", amount=fmt_money(values["collected_from_buyers"], lang))
        if "collected_from_buyers" in earlier:
            line += tr(lang, "b.previous", amount=fmt_money(earlier["collected_from_buyers"], lang))
        lines.append(line)
    if all(k in values for k in ("escrow_open", "escrow_deposited", "escrow_withdrawn", "escrow_close")):
        lines.append(
            tr(
                lang,
                "b.account",
                open=fmt_money(values["escrow_open"], lang),
                deposited=fmt_money(values["escrow_deposited"], lang),
                withdrawn=fmt_money(values["escrow_withdrawn"], lang),
                close=fmt_money(values["escrow_close"], lang),
            )
        )
    sold = [values[k] for k in ("plots_sold_in_quarter", "apartments_sold_in_quarter") if k in values]
    total = [values[k] for k in ("plots_total", "apartments_total") if k in values]
    if sold and total:
        lines.append(tr(lang, "b.units", sold=int(sum(sold)), total=int(sum(total))))
    return lines


def _footer(state: dict, lang: str, unsubscribe_url: Optional[str] = None) -> List[str]:
    url = state.get("detail_url") or state.get("list_url") or LIST_URL
    lines = ["", tr(lang, "f.page", url=url)]
    if unsubscribe_url:
        lines.append(tr(lang, "f.unsubscribe", url=unsubscribe_url))
    lines.append(tr(lang, "f.source"))
    return lines


def _title(state: dict) -> str:
    name = state.get("name") or state.get("project_id") or ""
    builder = state.get("builder")
    return "%s (%s)" % (name, builder) if builder else name


def _overdue_lines(data: dict, today: date, lang: str) -> List[str]:
    lines = [
        tr(lang, "b.report_overdue", end=fmt_date(str(data["quarter_end"]), lang), today=fmt_date(today.isoformat(), lang))
    ]
    latest = data.get("latest")
    if latest:
        lines.append(tr(lang, "b.latest_is", quarter=quarter_label(latest["no"], latest["year"], lang)))
    else:
        lines.append(tr(lang, "b.no_reports"))
    return lines


@dataclass
class Facts:
    """What a status page or message says about one project, as plain strings."""

    title: str
    rows: List[Tuple[str, str]]
    reports: Optional[str]  # None when the quarterly list was never read
    latest: Optional[str]
    report_lines: List[str]
    warnings: List[str]
    hearings_label: str
    hearings: List[Tuple[str, str, str]]
    page_url: str
    page_line: str
    source_line: str


def facts(state: dict, today: date, lang: str = "en", overdue_grace_days: int = 30) -> Facts:
    """Collect everything we can say about a project in ``lang``."""
    rows: List[Tuple[str, str]] = [(tr(lang, "s.project_id"), state.get("project_id", ""))]
    if state.get("builder"):
        rows.append((tr(lang, "s.builder"), state["builder"]))
    place = ", ".join(p for p in (state.get("location"), state.get("district")) if p)
    if place:
        rows.append((tr(lang, "s.location"), place))
    if state.get("reg_no"):
        rows.append((tr(lang, "s.reg_no"), state["reg_no"]))

    valid = state.get("valid_upto")
    valid_text = fmt_date(valid, lang)
    if valid:
        days = (date.fromisoformat(valid) - today).days
        valid_text += " (%s)" % (tr(lang, "s.days_left", days=days) if days >= 0 else tr(lang, "s.days_ago", days=-days))
    rows.append((tr(lang, "s.valid"), valid_text))
    rows.append((tr(lang, "s.lapsed"), tr(lang, "s.yes" if state.get("lapsed") else "s.no")))
    rows.append((tr(lang, "s.occ"), tr(lang, "s.yes" if state.get("occ") else "s.no")))
    if state.get("status"):
        rows.append((tr(lang, "s.status"), state["status"]))
    if state.get("next_hearing"):
        rows.append((tr(lang, "s.next_hearing"), state["next_hearing"]))

    reports = latest_line = None
    report_lines: List[str] = []
    warnings: List[str] = []
    if "quarters" in state:
        quarters = state.get("quarters") or []
        reports = "%s: %d" % (tr(lang, "s.reports"), len(quarters))
        latest = latest_quarter(state)
        report = state.get("latest_report")
        if latest:
            label = quarter_label(latest["no"], latest["year"], lang)
            if report and report.get("submitted_on"):
                latest_line = tr(lang, "s.latest_report", quarter=label, date=fmt_date(report["submitted_on"], lang))
            else:
                latest_line = tr(lang, "s.latest_report_nodate", quarter=label)
            report_lines = _report_lines(report, None, lang)
        if not state.get("occ"):
            number, year = last_ended_quarter(today)
            end = quarter_end(number, year)
            if (today - end).days > overdue_grace_days and latest and (latest["year"], latest["no"]) < (year, number):
                data = {"quarter_end": end.isoformat(), "latest": None}
                warnings.append(_overdue_lines(data, today, lang)[0])

    hearings: List[Tuple[str, str, str]] = []
    for hearing in sorted(state.get("hearings") or [], key=lambda h: h.get("date") or "", reverse=True)[:3]:
        text = hearing.get("text") or ""
        if len(text) > 220:
            text = text[:220].rstrip() + "…"
        hearings.append((fmt_date(hearing.get("date"), lang), hearing.get("status") or "", text))

    page_url = state.get("detail_url") or state.get("list_url") or LIST_URL
    return Facts(
        title=_title(state),
        rows=rows,
        reports=reports,
        latest=latest_line,
        report_lines=report_lines,
        warnings=warnings,
        hearings_label=tr(lang, "s.hearings"),
        hearings=hearings,
        page_url=page_url,
        page_line=tr(lang, "f.page", url=page_url),
        source_line=tr(lang, "f.source"),
    )


def render_status(
    state: dict,
    today: date,
    lang: str = "en",
    overdue_grace_days: int = 30,
    unsubscribe_url: Optional[str] = None,
) -> str:
    """A full plain-language status report for one project."""
    f = facts(state, today, lang, overdue_grace_days)
    lines = [f.title, ""]
    lines.extend("%s: %s" % row for row in f.rows)
    if f.reports is not None:
        lines.append("")
        lines.append(f.reports)
        if f.latest:
            lines.append(f.latest)
        lines.extend("  " + line for line in f.report_lines)
        lines.extend("! " + warning for warning in f.warnings)
    if f.hearings:
        lines.append("")
        lines.append("%s:" % f.hearings_label)
        lines.extend("  %s — %s: %s" % hearing for hearing in f.hearings)
    lines.extend(_footer(state, lang, unsubscribe_url))
    return "\n".join(lines)


def render(
    event: Event, state: dict, today: date, lang: str = "en", unsubscribe_url: Optional[str] = None
) -> Tuple[str, str]:
    """(subject, body) for one event."""
    lang = _lang(lang)
    kind, data = event.kind, event.data
    subject = "%s — %s" % (tr(lang, "t." + kind), _title(state))
    if kind == "baseline":
        return subject, render_status(state, today, lang, unsubscribe_url=unsubscribe_url)

    lines: List[str] = []
    if kind in ("marked_lapsed", "occ_uploaded", "corrigendum_added", "monitoring_started", "removed_from_list"):
        lines.append(tr(lang, "b." + kind))
    elif kind in ("validity_extended", "validity_changed"):
        lines.append(tr(lang, "b.validity", old=fmt_date(str(data["old"]), lang), new=fmt_date(str(data["new"]), lang)))
    elif kind in ("registration_expired", "registration_expiring"):
        lines.append(tr(lang, "b." + kind, date=fmt_date(str(data["valid_upto"]), lang), days=data["days"]))
    elif kind == "status_changed":
        lines.append(tr(lang, "b.status_changed", old=data["old"], new=data["new"]))
    elif kind == "next_hearing":
        lines.append(tr(lang, "b.next_hearing", value=data["value"]))
    elif kind == "new_hearing":
        lines.append(tr(lang, "b.hearing", date=fmt_date(data.get("date"), lang), status=data.get("status") or "-"))
        if data.get("text"):
            lines.append(tr(lang, "b.hearing_text", text=data["text"]))
        if data.get("order_url"):
            lines.append(tr(lang, "b.hearing_order", url=data["order_url"]))
    elif kind == "new_report":
        quarter = data["quarter"]
        label = quarter_label(quarter["no"], quarter["year"], lang)
        report = data.get("report") or {}
        if report.get("submitted_on"):
            lines.append(tr(lang, "b.report_filed", quarter=label, date=fmt_date(report["submitted_on"], lang)))
        else:
            lines.append(tr(lang, "b.report_filed_nodate", quarter=label))
        lines.extend(_report_lines(report, data.get("previous"), lang))
    elif kind == "report_overdue":
        lines.extend(_overdue_lines(data, today, lang))
    else:
        lines.append(kind)

    body = [_title(state), "%s: %s" % (tr(lang, "s.project_id"), state.get("project_id", "")), ""]
    body.extend(lines)
    body.extend(_footer(state, lang, unsubscribe_url))
    return subject, "\n".join(body)
