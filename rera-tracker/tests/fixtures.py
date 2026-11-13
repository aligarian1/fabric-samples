"""Synthetic pages that copy the markup quirks of haryanarera.gov.in.

Every project, builder and figure here is invented.  No page from the real site
is stored in this repository.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional

BASE = "https://haryanarera.gov.in"
LINK_CLASS = "link-underline link-underline-opacity-0 link-underline-opacity-100-hover"

_PAGE_TOP = """<!DOCTYPE html><html><head><title>Haryana Real Estate Regulatory Authority</title>
<SCRIPT type="text/javascript"> window.history.forward(); function noBack() { window.history.forward(); } </SCRIPT>
<style>.x { color: red }</style></head><body onload="customstopBack()">
</tr> <noscript> <meta http-equiv="refresh" content="0; URL='https://haryanarera.gov.in/noscript.php'" /> </noscript> </table>
<div id="password_policy" class="modal fade"><div class="modal-header"><h3 id="myModalLabel">Password Policy</h3></div>
<div class="modal-body"><table> <tr><td> 1.Password must at least be 8 characters.</0d></tr>
<tr><td> 2.Password must not be the same as the previous 3 passwords.</td></tr> </table></div></div>
"""
_PAGE_END = "</body></html>"

_LIST_HEADERS = [
    "Serial No.", "Registration Certificate Number", "Project ID", "Project Name", "Builder", "Project Location",
    "Project District", "Registered With", "Details of Project(Form A-H)", "Registration Up-to", "View Certificate",
    "View Quarterly Progress", "Monitoring Orders", "View OC/CC/PCC", "View Proceedings",
]


def detail_url(site_id: int) -> str:
    return "%s/view_project/searchprojectDetail/%d" % (BASE, site_id)


def qpr_url(token: str) -> str:
    return "%s/assistancecontrol/print_quarterly_schedules/Mg==/%s/MjAyNA==" % (BASE, token)


def list_row(
    serial: int,
    project_id: str,
    name: str,
    builder: str,
    valid: str,
    reg_no: str = "GGM/900/1/2024/1 DATED 01.02.2024",
    site_id: Optional[int] = None,
    qpr_token: Optional[str] = None,
    lapsed: bool = False,
    corrigendum: bool = False,
    occ: bool = False,
    monitoring: bool = False,
) -> str:
    reg = reg_no + (" <br><span style=\"color:red\">Lapsed Project</span>" if lapsed else "")
    if site_id is not None:
        pid = '<a class="%s" href="%s" target="_blank">%s</a>' % (LINK_CLASS, detail_url(site_id), project_id)
        form = '<a class="%s" href="%s/view_project/project_preview_open/%d" method="post" target="_blank"><img src="%s/images/pdf.png"></a>' % (
            LINK_CLASS, BASE, site_id, BASE)
    else:
        pid = project_id
        form = ""
    cert = '<a class="%s" href="%s/view_project/view_certificate/TOKEN%d" method="post" target="_blank"><img src="%s/images/pdf.png"></a><br><br>' % (
        LINK_CLASS, BASE, serial, BASE)
    if corrigendum:
        cert += ' <br><br><a class="%s" onclick="view_corrigendums(%d,\'C\');">View Corrigendum</a>' % (LINK_CLASS, serial)
    quarterly = ""
    if qpr_token:
        quarterly = (
            '<a class="%s" onclick="window.open(\'%s\',\'popUpWindow\',\'height=500,width=400,left=100,top=100,'
            'resizable=yes,scrollbars=yes,toolbar=yes,menubar=no,location=no,directories=no, status=yes\');">View</a>'
        ) % (LINK_CLASS, qpr_url(qpr_token))
    monitor = "--"
    if monitoring:
        monitor = (
            '<a class="%s" onclick="window.open(\'%s/assistancecontrol/view_monitoring_cases/MON%d\',\'popUpWindow\','
            '\'height=500,width=600\');">View Monitoring Cases</a>'
        ) % (LINK_CLASS, BASE, serial)
    occ_cell = '<a class="%s" onclick="view_corrigendums(%d,\'OC\');">View OC/CC/PCC</a>' % (LINK_CLASS, serial) if occ else " "
    cells = [str(serial), reg, " %s " % pid, name, builder, "SECTOR 99 GURUGRAM<br>", "GURUGRAM", "HRERA", form, valid,
             cert, quarterly, monitor, occ_cell]
    return "<tr> " + " ".join("<td>%s</td>" % c for c in cells) + " </tr>"


def list_page(rows: Iterable[str]) -> str:
    head = "<thead><tr>" + "".join('<th align="center">%s</th>' % h for h in _LIST_HEADERS) + "</tr></thead>"
    side = (
        '<table class="table table-striped table-bordered" style="width:100%;"><thead><tr><th>Serial No.</th>'
        "<th>Document Type</th><th>Remarks</th><th>View</th></tr></thead><tbody></tbody></table>"
    )
    return (
        _PAGE_TOP + side
        + '<table id="compliant_hearing" class="table table-striped table-bordered" style="width:100%;">'
        + head + "<tbody>" + "\n".join(rows) + "</tbody></table>" + _PAGE_END
    )


def schedule_page(quarters: Iterable[tuple], project_no: str = "9001", project_year: str = "2024") -> str:
    """``quarters`` holds (number, year, start, end) with dates like 01-Jul-2026."""
    rows = []
    for number, year, start, end in quarters:
        rows.append(
            "<tr> <td>%d of %d</td> <td>%s</td> <td>%s</td> <!-- <td></td> --> <td> "
            '<form action="%s/view_project/quaterly_schedule_preview_open" method="post" target="_blank"> '
            '<input type="hidden" value="%d" name="quarter_no"> <input type="hidden" value="%d" name="quarter_year"> '
            '<input type="hidden" value="2" name="reracode_project"> <input type="hidden" value="%s" name="temp_project_id"> '
            '<input type="hidden" value="%s" name="temp_project_year"> <input type="submit" name="submit" value="View"> '
            "</form> </td> </tr>" % (number, year, start, end, BASE, number, year, project_no, project_year)
        )
    return (
        _PAGE_TOP
        + '<div class="col-lg-12 cus-top-heading" align="center">View Quarterly Progress</div>'
        + '<table class="table table-striped table-bordered" style="width:100%;"> <thead> <tr align="center"> '
        + '<th align="center">Quarter No</th> <th align="center">Quarter Start Date</th> '
        + '<th align="center">Quarter End Date</th> <th align="center">View Details</th> </tr> </thead> <tbody> '
        + " ".join(rows) + " </tbody> </table>" + _PAGE_END
    )


def report_page(
    submitted: str = "15-Oct-2026",
    collected: float = 1741.3,
    escrow: tuple = (35.08, 1218.91, 1047.43, 206.56),
    apartments_total: int = 240,
    apartments_sold: Iterable[int] = (4, 3),
) -> str:
    def one_cell(title: str) -> str:
        return "<table width='100%%'><tr><td align='center'><b>%s</b></td></tr></table>" % title

    def rows(items: List[tuple]) -> str:
        return "".join("<tr>" + "".join("<td>%s</td>" % c for c in item) + "</tr>" for item in items)

    sold_rows = [("S.No.", "Type/Size", "Apartments Sold in the Quarter")]
    sold_rows += [(i + 1, "TYPE %d" % (i + 1), n) for i, n in enumerate(apartments_sold)]
    return (
        "<html><body><center><b>Quarterly Schedules</b></center><b>HRERA Gurugram</b>"
        "<b>Project Registration Number : GGM/900/1/2024/1 DATED 01.02.2024</b>"
        "<b>Report Online Submission Date : %s</b>" % submitted
        + "<b>Project Basic Details</b><table>" + rows([("Particulars", "Details"), ("Project Name", "SUNRISE HEIGHTS"),
                                                       ("Area of Project", "9.903")]) + "</table>"
        + "<b>Estimated cost of the Project (ref. REP-I Part-C)</b><table>"
        + rows([("S.No.", "Particulars", "Amount (In Lakhs)"), (1, "Cost of the land (if included in the estimated cost)", "2293.03"),
                ("", "Total", "6980.07")]) + "</table>"
        + one_cell("Financial Information for quarter ending on 30/09/2026 (JUL-SEP) ;")
        + one_cell("Cash Inflow")
        + "<table>" + rows([("S.No.", "Cash Inflow", "Amount (In Lakhs)"), (1, "Opening Balance", "28944.56"),
                            (2, "Amount collected from allottees against booked plots and/or apartments", collected),
                            (3, "Amount availed from the bank/financial institutions", 0), ("", "Total", "33961.56")]) + "</table>"
        + "<b>Cash Outflow</b><table>" + rows([("S.No.", "Cash Outflow", "Amount (In Lakhs)"),
                                               (1, "Expenditure on construction of apartments", "-51.58"), ("", "Total", "656.76")]) + "</table>"
        + "<b>RERA Project Account As per Rep - I Part D</b><table>"
        + rows([("S.No.", "Information relating to Escrow Account", "Amount (In Lakhs)"),
                (1, "Opening balance at the beginning of the quarter", escrow[0]),
                (2, "Amount deposited in Escrow Account", escrow[1]),
                (3, "Amount withdrawn during the quarter", escrow[2]),
                (4, "Balance at the end of the quarter", escrow[3])]) + "</table>"
        + one_cell("Details of the Booked Apartments")
        + "<table>" + rows([("Total Apartments in the colony", apartments_total),
                            ("Apartments sold upto the date of Registration", 12)]) + "</table>"
        + "<b>Apartments sold in the Quarter</b><table>" + rows(sold_rows) + "</table>"
        + "<table>" + rows([("Sr. No.", "Document Description", "Date of Upload Document", "View"),
                            (1, "CERTIFICATE OF THE REGISTERED ARCHITECT OF THE PROJECT", "15-10-2026", "View"),
                            (2, "CERTIFICATE OF CHARTERED ACCOUNTANT OF THE PROJECT", "15-10-2026", "View")]) + "</table>"
        + "</body></html>"
    )


def detail_page(status: str, next_hearing: str, hearings: Iterable[Dict[str, str]]) -> str:
    def heading(text: str) -> str:
        return '<div class="col-lg-12 col-md-12 cus-top-heading-2" id="empprofile" align="center">%s</div>' % text

    hearing_rows = []
    for item in hearings:
        order = ""
        if item.get("order"):
            order = '<a class="%s" href="%s/view_project/viewOrderPdf/%s" target="_blank">View Order</a>' % (
                LINK_CLASS, BASE, item["order"])
        hearing_rows.append("<tr> <td>%s</td> <td>%s</td> <td>%s</td> <td>%s </td> </tr>" % (
            item["date"], item["text"], item["status"], order))
    return (
        _PAGE_TOP
        + '<div class="cus-top-heading" id="empprofile" align="center">Comprehensive Project Details </div>'
        + heading("Project Location Details")
        + '<table id="table" class="table"><thead><tr><th>Project Name</th><th>Project Location</th><th>Promoter Name</th></tr></thead>'
        + "<tbody><tr><td>SUNRISE HEIGHTS</td><td>SECTOR 99 GURUGRAM</td><td>EXAMPLE BUILDERS PVT LTD</td></tr></tbody></table>"
        + heading("Project Detail")
        + '<table id="table" class="table"><thead><tr><th>Project Registration Number</th><th>Project Id</th>'
        + "<th>Current Status</th><th>Next Date of Hearing</th><th>View Notice</th></tr></thead><tbody><tr>"
        + "<td>GGM/900/1/2024/1 DATED 01.02.2024</td><td>RERA-GRG-9001-2024</td><td>%s</td><td>%s</td>" % (status, next_hearing)
        + '<td> <form action="%s/view_project/viewNotice/NTkz" method="post" target="_blank">' % BASE
        + '<input type="submit" name="submit" value="View Notice"></form></td></tr></tbody></table>'
        + heading("Project Listing Details")
        + '<table id="table" class="table"><thead><tr><th>Date of Hearing</th><th>Proceedings of the day</th>'
        + "<th>Status</th><th>Order</th></tr></thead><tbody>" + " ".join(hearing_rows) + "</tbody></table>"
        + _PAGE_END
    )
