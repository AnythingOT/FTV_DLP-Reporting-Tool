"""Excel: Sheet1 = data, Info, Events. Streaming (write-only) mode keeps memory low.
Numbers are written as numbers (Excel keeps 15 significant digits); time is text with full nanoseconds.

Column layout with imported log groups:
  A = Time | separator (group name) | tag columns of the group | separator | ...
Each group's tag columns are one outline group (level 1, expanded). The narrow separator column keeps
groups apart - Excel merges outline groups that touch. Status columns (only when 'Good data only' is
off) are outline level 2 and hidden, except for tags with E/S/U/D or unknown statuses (the normal
start record N does not count)."""

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.dimensions import ColumnDimension

from ..constants import EXCEL_SHEET, GOOD, SEVERITY_COLOR, START_STATUS
from ..table import iter_rows
from ..timeutil import fmt_ns
from . import event_rows, legend_rows, summary_rows

BAND = PatternFill("solid", fgColor="2E6A9E")
HEAD = PatternFill("solid", fgColor="1F4E79")
WHITE_BOLD = Font(bold=True, color="FFFFFF")
BOLD = Font(bold=True)


def _value(ws, text, field):
    """Number / boolean for numeric tags; everything else as a real text cell.
    Text is forced to type 'string': openpyxl would otherwise turn a value starting with '=' into a
    formula. Control characters, which an .xlsx file cannot contain, are shown as \\xNN."""
    if text == "":
        return None
    try:
        if field == "V_I":
            return int(text)
        if field == "V_D":
            return float(text)
        if field == "V_B" and text.lower() in ("true", "false"):
            return text.lower() == "true"
    except ValueError:
        pass
    cell = WriteOnlyCell(ws, value=ILLEGAL_CHARACTERS_RE.sub(lambda m: f"\\x{ord(m.group()):02x}", text))
    cell.data_type = "s"
    return cell


def _cell(ws, value, font=None, fill=None, wrap=False):
    c = WriteOnlyCell(ws, value=value)
    if font:
        c.font = font
    if fill:
        c.fill = fill
    if wrap:
        c.alignment = Alignment(wrap_text=True, vertical="center")
    return c


def _layout(job):
    """List of columns after Time: ("sep", group) | ("value", tag) | ("status", tag)."""
    cols, prev = [], None
    for t in job.tags:
        g = job.groups.get(t, "")
        if job.grouped and g != prev:
            cols.append(("sep", g))
            prev = g
        cols.append(("value", t))
        if job.include_status:
            cols.append(("status", t))
    return cols


def write_xlsx(path, job):
    wb = Workbook(write_only=True)
    ws = wb.create_sheet(EXCEL_SHEET)
    fields = {t: job.collected.fields.get(t, "V_S") for t in job.tags}
    cols = _layout(job)
    bad = {t for t in job.tags if any(s not in (GOOD, START_STATUS) for _, s in job.collected.data.get(t, {}).values())}
    value_level = 1 if job.grouped else 0
    ws.sheet_properties.outlinePr.summaryRight = False      # +/- sits on the separator (left of each group)
    ws.column_dimensions["A"] = ColumnDimension(ws, index="A", width=32)
    for i, (kind, ref) in enumerate(cols, start=2):
        letter = get_column_letter(i)
        if kind == "sep":
            dim = ColumnDimension(ws, index=letter, width=3)
        elif kind == "value":
            dim = ColumnDimension(ws, index=letter, width=18, outlineLevel=value_level)
        else:
            dim = ColumnDimension(ws, index=letter, width=12, outlineLevel=value_level + 1, hidden=ref not in bad)
        ws.column_dimensions[letter] = dim
    header_rows = 2 if job.grouped else 1
    ws.freeze_panes = f"B{header_rows + 1}"
    ws.auto_filter.ref = (f"A{header_rows}:{get_column_letter(len(cols) + 1)}"
                          f"{header_rows + max(job.collected.rows, 1)}")

    if job.grouped:
        ws.append([_cell(ws, None, fill=BAND)] +
                  [_cell(ws, ref if kind == "sep" else None, WHITE_BOLD, BAND) for kind, ref in cols])
    ws.append([_cell(ws, "Time", WHITE_BOLD, HEAD)] +
              [_cell(ws, None if kind == "sep" else (ref if kind == "value" else f"{ref} Status"),
                     WHITE_BOLD, HEAD, wrap=True) for kind, ref in cols])
    for ns, cells in iter_rows(job.collected, job.tags):
        by_tag = dict(zip(job.tags, cells))
        row = [fmt_ns(ns, job.tz)]
        for kind, ref in cols:
            cell = by_tag.get(ref)
            if kind == "sep":
                row.append(None)
            elif kind == "value":
                row.append(_value(ws, cell[0], fields[ref]) if cell else None)
            else:
                row.append(cell[1] if cell else None)
        ws.append(row)

    info = wb.create_sheet("Info")
    info.column_dimensions["A"] = ColumnDimension(info, index="A", width=28)
    info.column_dimensions["B"] = ColumnDimension(info, index="B", width=110)
    info.append([_cell(info, job.title, Font(bold=True, size=14))])
    info.append([])
    for label, value in job.meta:
        info.append([_cell(info, label, BOLD), value])
    info.append([])
    color = SEVERITY_COLOR.get(job.health.overall, "#000000").lstrip("#")
    info.append([_cell(info, "Log health", BOLD), _cell(info, job.health.headline(), Font(bold=True, color=color))])
    for note in job.health.notes:
        info.append(["", note])
    info.append([])
    info.append([_cell(info, "Status codes", BOLD)])
    for code, text in legend_rows():
        info.append([code, text])
    info.append([])
    info.append([_cell(info, "Per tag", BOLD)])
    for i, r in enumerate(summary_rows(job)):
        info.append([_cell(info, v, BOLD) for v in r] if i == 0 else r)

    ev = wb.create_sheet("Events")
    for col, width in zip("ABCDEFG", (40, 18, 10, 32, 32, 14, 90)):
        ev.column_dimensions[col] = ColumnDimension(ev, index=col, width=width)
    rows = event_rows(job)
    ev.append([_cell(ev, v, WHITE_BOLD, HEAD) for v in rows[0]])
    for r in rows[1:]:
        sev = Font(bold=True, color=SEVERITY_COLOR.get(r[2], "#000000").lstrip("#"))
        ev.append(r[:2] + [_cell(ev, r[2], sev)] + r[3:])
    if len(rows) == 1:
        ev.append(["No events in this period."])
    wb.save(path)
