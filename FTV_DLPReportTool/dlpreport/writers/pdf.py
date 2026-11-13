"""PDF: page 1 = information and log health; then the data table with group header rows.
Tag names are shown in full, wrapped only at ] : . \\ ; values and times are exact text."""

import math
import re
from xml.sax.saxutils import escape

from ..app_info import APP_NAME, VERSION
from ..constants import (PDF_ROWS_PER_PAGE, PDF_ROWS_PER_TABLE, PDF_TAGS_PER_SECTION,
                         SEVERITY_COLOR)
from ..table import cell_text, iter_rows
from ..timeutil import fmt_ns
from . import event_rows, legend_rows, summary_rows


def estimate_pages(n_rows, n_tags):
    return 1 + math.ceil(max(n_rows, 1) / PDF_ROWS_PER_PAGE) * math.ceil(max(n_tags, 1) / PDF_TAGS_PER_SECTION)


def wrap_tag_name(name, font, size, width):
    from reportlab.pdfbase.pdfmetrics import stringWidth
    parts = re.findall(r"[^\]:.\\]+[\]:.\\]*|[\]:.\\]+", name) or [name]
    lines, cur = [], ""
    for part in parts:
        if cur and stringWidth(cur + part, font, size) > width:
            lines.append(cur)
            cur = part
        else:
            cur += part
    lines.append(cur)
    return lines


def _runs(values):
    out = []
    for v in values:
        if out and out[-1][0] == v:
            out[-1] = (v, out[-1][1] + 1)
        else:
            out.append((v, 1))
    return out


def write_pdf(path, job):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    page_w, _ = landscape(A4)
    margin = 12 * mm
    width = page_w - 2 * margin
    styles = getSampleStyleSheet()
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=7.5, leading=9.5)
    head = ParagraphStyle("head", parent=small, fontName="Helvetica-Bold", fontSize=6.5, leading=8,
                          textColor=colors.white)
    group_head = ParagraphStyle("ghead", parent=head, alignment=1)
    h2 = ParagraphStyle("h2", parent=styles["Heading3"], keepWithNext=1)
    long_cell = ParagraphStyle("long", parent=small, fontSize=6.5, leading=7.5, alignment=2, wordWrap="CJK")
    accent = colors.HexColor("#1F4E79")
    plain = TableStyle([("FONTSIZE", (0, 0), (-1, -1), 7.5), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)])

    def grid_table(rows, widths, first_col_color=None):
        data = [[Paragraph(escape(str(v)), head if i == 0 else small) for v in r] for i, r in enumerate(rows)]
        t = Table(data, colWidths=widths, repeatRows=1)
        cmds = [("BACKGROUND", (0, 0), (-1, 0), accent), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 1), (-1, -1), 0.25, colors.HexColor("#C9D1DB")),
                ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)]
        if first_col_color is not None:
            c = first_col_color
            for i, r in enumerate(rows[1:], start=1):
                cmds.append(("TEXTCOLOR", (c, i), (c, i), colors.HexColor(SEVERITY_COLOR.get(r[c], "#000000"))))
        t.setStyle(TableStyle(cmds))
        return t

    doc = SimpleDocTemplate(path, pagesize=landscape(A4), leftMargin=margin, rightMargin=margin,
                            topMargin=margin, bottomMargin=margin + 4 * mm, title=job.title, author=APP_NAME)
    story = [Paragraph(escape(job.title), styles["Title"])]
    t = Table([[k, Paragraph(escape(str(v)), small)] for k, v in job.meta], colWidths=[45 * mm, width - 45 * mm])
    t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 7.5), ("TEXTCOLOR", (0, 0), (0, -1), colors.grey),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
    story += [t, Spacer(1, 4)]

    color = SEVERITY_COLOR.get(job.health.overall, "#000000")
    story += [Paragraph(f'Log health: <font color="{color}">{escape(job.health.headline()[12:])}</font>', h2)]
    for note in job.health.notes:
        story.append(Paragraph("Note: " + escape(note), small))
    events = event_rows(job)
    if len(events) > 1:
        story += [Spacer(1, 3), grid_table(events, [62 * mm, 24 * mm, 16 * mm, 38 * mm, 38 * mm, 18 * mm,
                                                    width - 196 * mm], first_col_color=2)]
    else:
        story.append(Paragraph("No events in this period.", small))
    story += [Paragraph("Per tag", h2),
              grid_table(summary_rows(job), [70 * mm, 30 * mm, 24 * mm, 18 * mm, 18 * mm, 18 * mm, 22 * mm,
                                             width - 200 * mm]),
              Paragraph("Status codes", h2)]
    lt = Table(legend_rows(), colWidths=[12 * mm, width - 12 * mm])
    lt.setStyle(plain)
    story += [lt, PageBreak()]

    # ---- data
    tags = job.tags
    hdr_rows = 2 if job.grouped else 1
    time_w = 42 * mm
    col_w = (width - time_w) / PDF_TAGS_PER_SECTION
    rows = list(iter_rows(job.collected, tags))
    sections = [list(range(i, min(i + PDF_TAGS_PER_SECTION, len(tags)))) for i in range(0, len(tags), PDF_TAGS_PER_SECTION)]
    for si, idxs in enumerate(sections):
        if len(sections) > 1:
            story.append(Paragraph(f"Tags {idxs[0] + 1}-{idxs[-1] + 1} of {len(tags)}", h2))
        names = [Paragraph("<br/>".join(escape(x) for x in wrap_tag_name(tags[i], "Helvetica-Bold", 6.5, col_w - 16)),
                           head) for i in idxs]
        header = [[Paragraph("Time", head)] + names]
        cmds = [("BACKGROUND", (0, 0), (-1, hdr_rows - 1), accent), ("FONTSIZE", (0, 0), (-1, -1), 6.5),
                ("ROWBACKGROUNDS", (0, hdr_rows), (-1, -1), [colors.white, colors.HexColor("#F1F4F8")]),
                ("GRID", (0, hdr_rows), (-1, -1), 0.25, colors.HexColor("#C9D1DB")),
                ("ALIGN", (1, hdr_rows), (-1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)]
        if job.grouped:
            top, col = [Paragraph("Time", head)], 1
            for g, run in _runs([job.groups.get(tags[i], "") for i in idxs]):
                top += [Paragraph(escape(g), group_head)] + [""] * (run - 1)
                if run > 1:
                    cmds.append(("SPAN", (col, 0), (col + run - 1, 0)))
                col += run
            header = [top, [""] + names]
            cmds += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2E6A9E")), ("SPAN", (0, 0), (0, 1)),
                     ("LINEBEFORE", (1, 0), (-1, 1), 0.4, colors.HexColor("#5C8BB5"))]
        style = TableStyle(cmds)

        def fit(text):      # plain strings are fast; only over-long values need a wrapping paragraph
            if len(text) > 14 and stringWidth(text, "Helvetica", 6.5) > col_w - 12:
                return Paragraph(escape(text), long_cell)
            return text

        for start in range(0, max(len(rows), 1), PDF_ROWS_PER_TABLE):
            part = rows[start:start + PDF_ROWS_PER_TABLE]
            data = header + [[fmt_ns(ns, job.tz)] + [fit(cell_text(cells[i], job.include_status)) for i in idxs]
                             for ns, cells in part]
            tbl = Table(data, colWidths=[time_w] + [col_w] * len(idxs), repeatRows=hdr_rows)
            tbl.setStyle(style)
            story.append(tbl)
        if si < len(sections) - 1:
            story.append(PageBreak())

    def footer(canvas, _doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.grey)
        canvas.drawString(margin, 8 * mm, f"{job.title}   |   {APP_NAME} {VERSION}")
        canvas.drawRightString(page_w - margin, 8 * mm, f"Page {canvas.getPageNumber()}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
