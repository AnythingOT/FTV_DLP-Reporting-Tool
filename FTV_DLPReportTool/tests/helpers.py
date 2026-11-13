import csv
import os
import sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.dirname(HERE))

from dlpreport.dlp_export import expected_interval_s, norm_tag, parse_dlp_export  # noqa: E402
from dlpreport.influx import parse_flux_csv  # noqa: E402

FIX = os.path.join(HERE, "fixtures")


def records(name):
    with open(os.path.join(FIX, name), encoding="utf-8-sig") as f:
        return list(parse_flux_csv(csv.reader(f)))


def config():
    exp = parse_dlp_export(os.path.join(FIX, "dlpro_export.csv"))
    return {norm_tag(k): v for k, v in exp["tags"].items()}


def groups_and_intervals(tags, cfg):
    groups = {t: (cfg.get(norm_tag(t), {}).get("groups") or ["(Ungrouped)"])[0] for t in tags}
    intervals = {t: expected_interval_s(cfg.get(norm_tag(t))) for t in tags}
    return groups, intervals


def ordered_tags(recs, cfg):
    """Same column order as the app: log groups alphabetically, then (Ungrouped)."""
    def key(t):
        g = (cfg.get(norm_tag(t), {}).get("groups") or [None])[0]
        return (g is None, (g or "").lower(), t.lower())
    return sorted({r[1] for r in recs}, key=key)
