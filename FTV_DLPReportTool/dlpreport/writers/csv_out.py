"""CSV: one header row, exact text as stored. Events go to a companion *_events.csv."""

import csv

# Note: values are written exactly as stored. If such a CSV is opened in Excel, Excel itself may
# reformat them (e.g. "true" -> TRUE, long numbers) or treat text starting with "=" as a formula.
from ..table import iter_rows
from ..timeutil import fmt_ns
from . import event_rows


def write_csv(path, job):
    header = ["Time"]
    for tag in job.tags:
        header.append(tag)
        if job.include_status:
            header.append(f"{tag} Status")
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(header)
        for ns, cells in iter_rows(job.collected, job.tags):
            row = [fmt_ns(ns, job.tz)]
            for cell in cells:
                row.append(cell[0] if cell else "")
                if job.include_status:
                    row.append(cell[1] if cell else "")
            w.writerow(row)


def write_events_csv(path, job):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f).writerows(event_rows(job))
