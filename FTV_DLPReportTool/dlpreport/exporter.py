"""Builds the export job from a fetch result and writes the file(s). No UI code here."""

import getpass
import os
import platform
import re
from datetime import datetime

from .writers import ExportJob

EXTENSIONS = ("xlsx", "csv", "pdf")


def safe_name(text):
    return re.sub(r'[\\/:*?"<>|\s]+', "_", text).strip("_")


def unique_path(path):
    base, ext = os.path.splitext(path)
    n = 1
    while os.path.exists(path):
        path, n = f"{base}_{n}{ext}", n + 1
    return path


def build_job(result):
    p, col, health = result["params"], result["col"], result["health"]
    g = p.get("groups_info") or {}
    meta = [("HMI PC", f"{p['profile']} ({p['host']})"), ("HMI server (bucket)", p["bucket"]),
            ("Period", f"{p['start']:%Y-%m-%d %H:%M:%S} to {p['end']:%Y-%m-%d %H:%M:%S}"),
            ("Machine time zone", p.get("tz_label", "")),
            ("Data", "Good values only (status C)" if p["good_only"] else "All values, status shown"),
            ("Values fetched", f"{col.values:,}"), ("Values excluded (status not C)", f"{col.excluded:,}"),
            ("Log groups", f"{g.get('file')} imported {g.get('imported')}" if g.get("tags") else "not imported"),
            ("Heartbeat tag", p.get("heartbeat") or "none"),
            ("Exported", f"{datetime.now():%Y-%m-%d %H:%M:%S} by {getpass.getuser()} on {platform.node()}")]
    return ExportJob(f"{p['profile']} - data log", meta, p["tags"], p["groups"], col, health, p["tz"],
                     not p["good_only"])


def export(kind, result, folder):
    """Write one export (CSV also writes *_events.csv). Returns the path of the main file."""
    from .writers.csv_out import write_csv, write_events_csv
    from .writers.excel import write_xlsx
    from .writers.pdf import write_pdf

    job, p = build_job(result), result["params"]
    folder = os.path.normpath(folder)
    os.makedirs(folder, exist_ok=True)
    name = safe_name(f"{p['profile']}_{p['bucket']}_{p['start']:%Y%m%d-%H%M}_{p['end']:%Y%m%d-%H%M}")
    path = unique_path(os.path.join(folder, f"{name}.{kind}"))
    outputs = [(path, {"xlsx": write_xlsx, "csv": write_csv, "pdf": write_pdf}[kind])]
    if kind == "csv":
        outputs.append((path[:-4] + "_events.csv", write_events_csv))
    for target, writer in outputs:
        part = target + ".part"            # write under a temporary name, rename when complete
        try:
            writer(part, job)
            os.replace(part, target)
        finally:
            if os.path.exists(part):
                os.remove(part)
    return path
