"""Export writers. All take an ExportJob."""

from dataclasses import dataclass

from ..constants import GOOD, STATUS_TEXT
from ..timeutil import fmt_duration, fmt_ns


@dataclass
class ExportJob:
    title: str
    meta: list                 # [(label, value)]
    tags: list                 # column order
    groups: dict               # tag -> group name ("" if no import)
    collected: object          # table.Collected
    health: object             # health.HealthReport
    tz: object
    include_status: bool

    @property
    def grouped(self):
        return any(self.groups.get(t) for t in self.tags)


def event_rows(job):
    """Header + rows for event lists (Excel Events sheet, events CSV, PDF)."""
    rows = [["Tag", "Group", "Severity", "Start", "End", "Duration", "Event"]]
    for e in job.health.events:
        rows.append([e.tag, e.where or "-", e.severity, fmt_ns(e.start, job.tz), fmt_ns(e.end, job.tz),
                     fmt_duration(e.end - e.start) if e.end > e.start else "", e.text])
    return rows


def summary_rows(job):
    rows = [["Tag", "Group", "Expected interval", "Records", "Good (C)", "Expected", "Completeness", "Other statuses"]]
    for s in job.health.summaries:
        other = ", ".join(f"{k}:{n}" for k, n in sorted(s.statuses.items()) if k != GOOD) or "-"
        rows.append([s.tag, s.group or "-", f"{s.expected_s:g} s" if s.expected_s else "not defined",
                     s.values, s.good, s.expected or "-",
                     f"{s.completeness:.1f} %" if s.completeness is not None else "-", other])
    return rows


def legend_rows():
    return [[k, v] for k, v in STATUS_TEXT.items()]
