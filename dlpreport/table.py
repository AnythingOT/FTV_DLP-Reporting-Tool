"""Collects fetched records into the export table and the health-check input."""

from collections import defaultdict
from dataclasses import dataclass, field

from .constants import GOOD, MARKER_FIELD


@dataclass
class Collected:
    data: dict = field(default_factory=lambda: defaultdict(dict))      # tag -> {ns: (text, status)}
    fields: dict = field(default_factory=dict)                         # tag -> V_I / V_D / V_B / V_S
    health: dict = field(default_factory=lambda: defaultdict(lambda: {"vals": [], "markers": [], "hb": []}))
    dups: list = field(default_factory=list)                           # (ns, tag, cell): 2nd record, same tag + time
    values: int = 0
    excluded: int = 0
    times: list = field(default_factory=list)

    @property
    def rows(self):
        return len(self.times) + len(self.dups)


def collect(records, display_tags, good_only, heartbeat_tag=""):
    """Every record feeds the health check; only display tags (and, if chosen, status C) feed the table."""
    out = Collected()
    shown = set(display_tags)
    for ns, tag, fld, text, status in records:
        h = out.health[tag]
        if fld == MARKER_FIELD:
            if text:
                h["markers"].append((ns, text))
            continue
        h["vals"].append((ns, status))
        if tag == heartbeat_tag:
            h["hb"].append((ns, text, status))
        if tag not in shown:
            continue
        out.values += 1
        out.fields.setdefault(tag, fld)
        if good_only and status != GOOD:
            out.excluded += 1
            continue
        d = out.data[tag]
        if ns in d:      # e.g. the same timestamp stored with two different statuses: keep both
            out.dups.append((ns, tag, (text, status)))
        else:
            d[ns] = (text, status)
    for h in out.health.values():
        h["vals"].sort()
        h["markers"].sort()
        h["hb"].sort()
    out.times = sorted({ns for tag in display_tags for ns in out.data.get(tag, {})})
    return out


def iter_rows(collected, tags):
    """(ns, [(text, status) or None per tag]) in time order - built lazily, no copy of the data."""
    cols = [collected.data.get(t, {}) for t in tags]
    index = {t: i for i, t in enumerate(tags)}
    extra = defaultdict(list)
    for ns, tag, cell in collected.dups:
        if tag in index:
            extra[ns].append((index[tag], cell))
    for ns in collected.times:
        yield ns, [c.get(ns) for c in cols]
        for i, cell in extra.get(ns, ()):
            row = [None] * len(cols)
            row[i] = cell
            yield ns, row


def cell_text(cell, include_status):
    if cell is None:
        return ""
    text, status = cell
    return f"{text} [{status}]" if include_status and status != GOOD else text
