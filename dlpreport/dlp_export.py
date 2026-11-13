"""Import of the DataLogPro editor export (log groups, tag types, trigger settings)."""

import csv
import re

UNIT_SECONDS = {"millisecond": 0.001, "second": 1, "minute": 60, "hour": 3600, "day": 86400}
UNIT_SHORT = {"millisecond": "ms", "second": "s", "minute": "min", "hour": "h", "day": "d"}


def norm_tag(name):
    """Match key only (never displayed): case-insensitive, leading '::' ignored."""
    return name.strip().lstrip(":").lower()


def _read_rows(path):
    """Original CSV, CSV re-saved by Excel (',' or ';'), or .xlsx."""
    if path.lower().endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook
        wb = load_workbook(path, read_only=True, data_only=True)
        try:
            return [["" if c is None else str(c) for c in row] for row in wb.worksheets[0].iter_rows(values_only=True)]
        finally:
            wb.close()
    with open(path, "rb") as f:
        raw = f.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")
    lines = text.splitlines()
    header = next((ln for ln in lines if ln.lower().startswith("group name")), "")
    delimiter = ";" if header.count(";") > header.count(",") else ","
    return list(csv.reader(lines, delimiter=delimiter))


def _seconds(value, unit):
    try:
        v = float(value)
    except ValueError:
        return None
    factor = UNIT_SECONDS.get(unit.strip().lower())
    return v * factor if factor and v > 0 else None


def parse_dlp_export(path):
    """-> {"version", "tags": {tag: {groups, type, trigger, interval_s, heartbeat_s}}}"""
    rows = _read_rows(path)
    hdr = next((i for i, r in enumerate(rows) if len(r) >= 2 and r[0].strip().lower() == "group name"
                and r[1].strip().lower() == "tag name"), None)
    if hdr is None:
        raise ValueError("This is not a DataLogPro export: the 'Group Name, Tag Name' header was not found.")
    col = {h.strip().lower(): i for i, h in enumerate(rows[hdr]) if h.strip()}

    def get(row, name):
        i = col.get(name)
        return row[i].strip() if i is not None and i < len(row) else ""

    tags = {}
    for row in rows[hdr + 1:]:
        tag = get(row, "tag name")
        if not tag:
            continue
        kind = get(row, "trigger type").lower().replace(" ", "")
        interval = heartbeat = None
        if kind == "periodic":
            unit = get(row, "interval unit")
            interval = _seconds(get(row, "interval value"), unit)
            trigger = f"Periodic {get(row, 'interval value')} {UNIT_SHORT.get(unit.lower(), unit)}"
        elif kind == "onchange":
            trigger = "On change"
            hb_unit = get(row, "heartbeatrate unit")
            heartbeat = _seconds(get(row, "heartbeatrate value"), hb_unit)
            if heartbeat:
                trigger += f", heartbeat {get(row, 'heartbeatrate value')} {UNIT_SHORT.get(hb_unit.lower(), hb_unit)}"
        elif kind == "ondemand":
            trigger = "On demand"
        else:
            trigger = get(row, "trigger type")
        entry = tags.setdefault(tag, {"groups": [], "type": get(row, "tag type"), "trigger": trigger,
                                      "interval_s": interval, "heartbeat_s": heartbeat,
                                      "periodic": kind == "periodic"})
        # a tag in several log groups is written at the fastest of their rates
        for key, value in (("interval_s", interval), ("heartbeat_s", heartbeat)):
            if value and (not entry[key] or value < entry[key]):
                entry[key] = value
        entry["periodic"] = entry["periodic"] or kind == "periodic"
        group = get(row, "group name")
        if group and group not in entry["groups"]:
            entry["groups"].append(group)
    if not tags:
        raise ValueError("The export contains no tags.")
    version = rows[1][0].strip() if len(rows) > 1 and rows[1] else ""
    return {"version": version, "tags": tags}


def expected_interval_s(entry):
    """Seconds between values that DataLogPro must write at least, or None if not defined."""
    if not entry:
        return None
    if entry.get("interval_s"):
        return entry["interval_s"]
    if entry.get("heartbeat_s"):
        return entry["heartbeat_s"]
    m = re.match(r"Periodic ([\d.]+) (ms|s|min|h|d)$", entry.get("trigger", ""))  # older imports
    if m:
        factor = {"ms": 0.001, "s": 1, "min": 60, "h": 3600, "d": 86400}[m.group(2)]
        return float(m.group(1)) * factor
    return None


def is_periodic(entry):
    """True if the tag is logged at a fixed interval (only then can the interval itself be checked)."""
    if not entry:
        return False
    if "periodic" in entry:
        return bool(entry["periodic"])
    return entry.get("trigger", "").startswith("Periodic")   # imports made by older versions
