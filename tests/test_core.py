"""Run: py -m unittest discover -s tests -v"""

import os
import tempfile
import unittest
from datetime import timedelta, timezone

from helpers import FIX, config, groups_and_intervals, ordered_tags, records

from dlpreport.dlp_export import parse_dlp_export
from dlpreport.health import analyze
from dlpreport.influx import flux_str
from dlpreport.table import collect
from dlpreport.timeutil import NS, fmt_ns, parse_rfc3339_ns

VM = timezone(timedelta(hours=-8))


def run_health(fixture, heartbeat=""):
    recs = records(fixture)
    tags = ordered_tags(recs, config())
    groups, intervals = groups_and_intervals(tags, config())
    col = collect(recs, tags, True, heartbeat)
    start, end = min(r[0] for r in recs), max(r[0] for r in recs) + NS
    return col, analyze(col.health, tags, groups, intervals, start, end, end, 2.0, heartbeat, col.excluded)


class TimeTests(unittest.TestCase):
    def test_nanoseconds_kept(self):
        ns = parse_rfc3339_ns("2026-11-10T10:41:40.8564209Z")
        self.assertEqual(ns % NS, 856420900)
        self.assertEqual(fmt_ns(ns, VM), "2026-11-10 02:41:40.856420900")

    def test_no_fraction(self):
        self.assertEqual(parse_rfc3339_ns("2026-11-10T10:41:40Z") % NS, 0)


class ImportTests(unittest.TestCase):
    def test_export(self):
        tags = parse_dlp_export(os.path.join(FIX, "dlpro_export.csv"))["tags"]
        self.assertEqual(len(tags), 8)
        self.assertEqual(tags["system\\Hour"]["groups"], ["NewGroup1"])
        self.assertEqual(tags["::[DLPro]Program:MainProgram.M101_Sim.ACC"]["groups"], [])
        self.assertEqual(tags["[DLPro]M101_OnCMD"]["interval_s"], 10)

    def test_flux_escape(self):
        self.assertEqual(flux_str('a\\b"c${x}'), '"a\\\\b\\"c\\${x}"')


class DataTests(unittest.TestCase):
    def test_values_exact_text(self):
        recs = records("run_datalog_stop_plc_crash.csv")
        values = {r[3] for r in recs if r[2] == "V_B"}
        self.assertEqual(values, {"true", "false"})          # booleans as stored, not 0/1

    def test_good_only_excludes(self):
        col, _ = run_health("run_datalog_stop_plc_crash.csv")
        self.assertEqual(col.excluded, 239)
        self.assertTrue(all(s == "C" for d in col.data.values() for _, s in d.values()))


class HealthTests(unittest.TestCase):
    def kinds(self, report):
        return {(e.severity, e.kind) for e in report.events}

    def test_normal_stop_and_plc_crash(self):
        _, rep = run_health("run_datalog_stop_plc_crash.csv")
        kinds = self.kinds(rep)
        self.assertIn(("Info", "stop"), kinds)
        self.assertIn(("Info", "startup_stale"), kinds)
        self.assertIn(("Warning", "badstatus"), kinds)
        self.assertNotIn(("Critical", "gap"), kinds)          # stop was explained by E/B markers
        stops = [e for e in rep.events if e.kind == "stop"]
        self.assertEqual(len(stops), 8)                      # tag-wise: one event per tag
        self.assertEqual(stops[0].where, "NewGroup1")

    def test_abnormal_interruption_and_interval_change(self):
        _, rep = run_health("run_hmi_client_tests.csv")
        gaps = [e for e in rep.events if e.kind == "gap"]
        self.assertTrue(any(fmt_ns(e.start, VM).startswith("2026-11-10 02:51:41") for e in gaps))
        self.assertIn(("Warning", "interval"), self.kinds(rep))
        self.assertEqual(rep.overall, "Critical")

    def test_heartbeat_detects_program_mode(self):
        _, rep = run_health("run_hmi_client_tests.csv", heartbeat="::[DLPro]Program:MainProgram.M101_Sim2.ACC")
        frozen = [e for e in rep.events if e.kind == "heartbeat"]
        self.assertTrue(any(fmt_ns(e.start, VM)[11:19] == "04:32:50" for e in frozen))


class WriterTests(unittest.TestCase):
    def test_all_formats(self):
        from openpyxl import load_workbook

        from dlpreport.exporter import export

        recs = records("run_datalog_stop_plc_crash.csv")
        tags = ordered_tags(recs, config())
        groups, intervals = groups_and_intervals(tags, config())
        col = collect(recs, tags, False, "")
        start, end = min(r[0] for r in recs), max(r[0] for r in recs) + NS
        from datetime import datetime
        rep = analyze(col.health, tags, groups, intervals, start, end, end, 2.0, "", 0)
        params = dict(profile="Test PC", host="localhost", bucket="TestFT16", tags=tags, groups=groups, tz=VM,
                      good_only=False, start=datetime.fromtimestamp(start // NS, VM),
                      end=datetime.fromtimestamp(end // NS, VM), tz_label="UTC-08:00")
        result = {"params": params, "col": col, "health": rep}
        with tempfile.TemporaryDirectory() as d:
            paths = {kind: export(kind, result, d) for kind in ("xlsx", "csv", "pdf")}
            self.assertTrue(all(os.path.exists(p) for p in paths.values()))
            self.assertTrue(os.path.exists(paths["csv"][:-4] + "_events.csv"))
            self.assertFalse([f for f in os.listdir(d) if f.endswith(".sha256")])
            wb = load_workbook(paths["xlsx"])
            self.assertEqual(wb.sheetnames, ["Sheet1", "Info", "Events"])
            ws = wb["Sheet1"]
            self.assertEqual(ws["A2"].value, "Time")
            self.assertTrue(str(ws["A3"].value).endswith("123865700"))   # nanoseconds kept
            # B = separator with group name, C = first tag, D = its status column
            self.assertEqual(ws["B1"].value, "NewGroup1")
            self.assertIsNone(ws["B2"].value)
            dims = ws.column_dimensions
            self.assertEqual(dims["C"].outlineLevel, 1)
            self.assertEqual(dims["D"].outlineLevel, 2)
            self.assertFalse(dims["B"].outlineLevel)
            # system tags had stale values -> status visible; a tag with only C would be hidden
            info = wb["Events"]
            self.assertEqual(info["A1"].value, "Tag")


if __name__ == "__main__":
    unittest.main()


class RecheckTests(unittest.TestCase):
    """Cases found in the code review."""

    @staticmethod
    def series(times_s, status="C"):
        return {"vals": [(int(t * NS), status) for t in times_s], "markers": [], "hb": []}

    def test_slower_than_configured_is_one_interval_event_not_a_flood(self):
        h = {"T": self.series(range(0, 3000, 30))}          # logged every 30 s, configured 10 s
        rep = analyze(h, ["T"], {}, {"T": 10.0}, 0, 3000 * NS, 3000 * NS, 2.5)
        self.assertEqual([(e.severity, e.kind) for e in rep.events], [("Warning", "interval")])

    def test_real_outage_inside_a_slow_log_is_still_reported(self):
        times = list(range(0, 900, 30)) + list(range(2000, 2900, 30))
        rep = analyze({"T": self.series(times)}, ["T"], {}, {"T": 10.0}, 0, 2900 * NS, 2900 * NS, 2.5)
        self.assertEqual(sorted(e.kind for e in rep.events), ["gap", "interval"])

    def test_on_change_tag_may_log_faster_than_its_heartbeat(self):
        h = {"T": self.series(range(0, 600))}               # changes every second, heartbeat 60 s
        rep = analyze(h, ["T"], {}, {"T": 60.0}, 0, 600 * NS, 600 * NS, 2.5, periodic=set())
        self.assertEqual(rep.events, [])
        self.assertIsNone(rep.summaries[0].completeness)

    def test_many_irregular_gaps_are_summarised(self):
        times, t = [], 0
        for i in range(60):
            times.append(t)
            t += 40 + (i * 37) % 200                         # irregular gaps, all above the limit
        rep = analyze({"T": self.series(times)}, ["T"], {}, {"T": 10.0}, 0, t * NS, times[-1] * NS, 2.5)
        self.assertEqual(len([e for e in rep.events if e.kind == "gap"]), 1)

    def test_same_tag_same_time_keeps_both_records(self):
        recs = [(5, "T", "V_I", "1", "C"), (5, "T", "V_I", "2", "E"), (9, "T", "V_I", "3", "C")]
        col = collect(recs, ["T"], False)
        from dlpreport.table import iter_rows
        self.assertEqual(col.rows, 3)
        self.assertEqual([c[0][0] for _, c in iter_rows(col, ["T"])], ["1", "2", "3"])

    def test_tag_in_two_groups_uses_fastest_interval(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "x.csv")
            with open(path, "w") as f:
                f.write("Version\nV14.0,x\nGroup Name,Tag Name,Tag Type,Trigger Type,Interval Value,Interval Unit,\n"
                        "Slow,T,REAL,Periodic,1,Minute,\nFast,T,REAL,Periodic,5,Second,\n")
            tags = parse_dlp_export(path)["tags"]
        self.assertEqual(tags["T"]["interval_s"], 5)
        self.assertEqual(tags["T"]["groups"], ["Slow", "Fast"])

    def test_excel_keeps_text_as_text(self):
        from openpyxl import load_workbook

        from dlpreport.exporter import export
        from datetime import datetime
        recs = [(1 * NS, "S", "V_S", "=1+1", "C"), (2 * NS, "S", "V_S", "a\x01b", "C"),
                (1 * NS, "B", "V_B", "true", "C"), (1 * NS, "I", "V_I", "12345678901234567", "C")]
        col = collect(recs, ["S", "B", "I"], True)
        rep = analyze(col.health, ["S", "B", "I"], {}, {}, 0, 3 * NS, 3 * NS, 2.5)
        params = dict(profile="PC", host="h", bucket="b", tags=["S", "B", "I"], groups={}, tz=timezone.utc,
                      good_only=True, start=datetime(2026, 1, 1, tzinfo=timezone.utc),
                      end=datetime(2026, 1, 2, tzinfo=timezone.utc))
        with tempfile.TemporaryDirectory() as d:
            path = export("xlsx", {"params": params, "col": col, "health": rep}, d)
            self.assertFalse([f for f in os.listdir(d) if f.endswith(".part")])
            ws = load_workbook(path)["Sheet1"]
            self.assertEqual(ws["B2"].value, "=1+1")
            self.assertEqual(ws["B2"].data_type, "s")          # not a formula
            self.assertEqual(ws["B3"].value, "a\\x01b")         # control character made visible
            self.assertIs(ws["C2"].value, True)
            path = export("csv", {"params": params, "col": col, "health": rep}, d)
            with open(path, encoding="utf-8-sig", newline="") as f:
                self.assertIn("12345678901234567", f.read())   # CSV keeps every digit
