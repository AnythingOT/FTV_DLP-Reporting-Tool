"""Main window: wiring of connection, period, tags, fetch, results and downloads."""

import logging
import os
import queue
import threading
import time

import tkinter as tk
from tkinter import messagebox, ttk

from ..app_info import APP_NAME, VERSION
from ..constants import EXCEL_MAX_ROWS, PDF_PAGE_WARN
from ..health import analyze
from ..influx import InfluxSource, friendly_error, profile_url
from ..dlp_export import norm_tag
from ..exporter import export
from ..settings import load_settings, save_settings
from ..table import collect
from ..timeutil import dt_to_ns, profile_tz, tz_choices
from .period_panel import PeriodPanel
from .results_panel import ResultsPanel
from .settings_dialog import SettingsDialog
from .tag_panel import TagPanel
from .theme import (ACCENT, BRAND, FOOTER, HEAD_BAD, HEAD_BUSY, HEAD_MUTED, HEAD_OK, MUTED, NAVY, NAVY_2,
                    TEXT, apply_theme, font_family, make_icon)
from .widgets import Card, Tooltip

log = logging.getLogger("dlpreport")
FORMATS = {"xlsx": "Excel", "csv": "CSV", "pdf": "PDF"}


class App:
    def __init__(self, root):
        self.root = root
        self.settings = load_settings()
        self.q = queue.Queue()
        self.source = self.profile = self.result = self.last_file = None
        self.busy = False
        self.pending = {}
        self.generation = 0     # increases whenever the selection changes; stale fetch results are dropped
        apply_theme(root)
        root.title(f"{APP_NAME} {VERSION} · {BRAND}")
        self._icon = make_icon()      # keep a reference: Tk drops images nobody holds
        root.iconphoto(True, self._icon)
        root.geometry("1280x800")
        root.minsize(1060, 660)
        self._build()
        self.period.set_quick("yesterday", notify=False)
        self.root.after(100, self._poll)
        self.reload_profiles()

    # ------------------------------------------------------------------ layout
    def _build(self):
        r = self.root
        r.columnconfigure(0, weight=1)
        r.rowconfigure(2, weight=1)
        self._build_header()

        self.period = PeriodPanel(r, self.invalidate, lambda: profile_tz(self.profile),
                                  lambda: self.settings["general"]["max_days"])
        self.period.grid(row=1, column=0, sticky="ew", padx=16, pady=(14, 0))

        paned = ttk.PanedWindow(r, orient="horizontal")
        paned.grid(row=2, column=0, sticky="nsew", padx=16, pady=10)
        self.tags = TagPanel(paned, self.invalidate, self.load_tags)
        self.results = ResultsPanel(paned)
        paned.add(self.tags, weight=1)
        paned.add(self.results, weight=3)

        card = Card(r, padding=(14, 10))
        card.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 12))
        act = card.body
        self.good_var = tk.BooleanVar(value=True)
        cb = ttk.Checkbutton(act, text="Good data only (status C)", variable=self.good_var,
                             command=self.invalidate, style="Card.TCheckbutton")
        cb.pack(side="left")
        Tooltip(cb, "Only values with status C go into the data table. Excluded values are counted and "
                    "the log health check always uses all values.")
        self.buttons = {}
        tips = {"pdf": "PDF: printable record with log health (exact values).",
                "csv": "CSV: plain table for further processing (exact text) + events file.",
                "xlsx": "Excel: formatted report - grouped columns, Info and Events sheets "
                        "(numbers limited to 15 significant digits)."}
        for kind in ("pdf", "csv", "xlsx"):
            b = ttk.Button(act, text=FORMATS[kind], command=lambda k=kind: self.download(k))
            b.pack(side="right", padx=(6, 0))
            Tooltip(b, tips[kind])
            self.buttons[kind] = b
        ttk.Label(act, text="DOWNLOAD", style="Section.TLabel").pack(side="right", padx=(0, 4))
        ttk.Separator(act, orient="vertical").pack(side="right", fill="y", padx=16)
        self.fetch_btn = ttk.Button(act, text="Fetch data", style="Accent.TButton", command=self.fetch)
        self.fetch_btn.pack(side="right")
        self.progress = ttk.Progressbar(act, mode="indeterminate", length=140)
        self.progress.pack(side="right", padx=(0, 14))

        self._build_footer()
        self._update_buttons()

    def _build_header(self):
        f = font_family()
        bar = tk.Frame(self.root, bg=NAVY, height=64)
        bar.grid(row=0, column=0, sticky="ew")
        bar.pack_propagate(False)

        mark = tk.Frame(bar, bg=NAVY)
        mark.pack(side="left", padx=(18, 0))
        tk.Label(mark, text="Anything", bg=NAVY, fg="white", font=(f, 17, "bold")).pack(side="left")
        tk.Label(mark, text="OT", bg=NAVY, fg=ACCENT, font=(f, 17, "bold")).pack(side="left")
        tk.Frame(bar, bg=NAVY_2, width=1).pack(side="left", fill="y", padx=16, pady=14)
        title = tk.Frame(bar, bg=NAVY)
        title.pack(side="left")
        tk.Label(title, text=APP_NAME, bg=NAVY, fg="white", font=(f, 13, "bold")).pack(anchor="w")
        tk.Label(title, text="DataLog Pro reports from InfluxDB", bg=NAVY,
                 fg=HEAD_MUTED, font=(f, 9)).pack(anchor="w")

        ttk.Button(bar, text="⚙  Settings", style="Header.TButton",
                   command=self.open_settings).pack(side="right", padx=(0, 18))
        self.conn_var = tk.StringVar(value="● Not connected")
        self.conn_lbl = tk.Label(bar, textvariable=self.conn_var, bg=NAVY_2, fg=HEAD_BAD,
                                 font=(f, 9, "bold"), padx=10, pady=4)
        self.conn_lbl.pack(side="right", padx=(0, 16))
        self.profile_var = tk.StringVar()
        self.profile_cb = ttk.Combobox(bar, textvariable=self.profile_var, state="readonly", width=24)
        self.profile_cb.pack(side="right", padx=(0, 16))
        self.profile_cb.bind("<<ComboboxSelected>>", lambda e: self.on_profile_change())
        tk.Label(bar, text="HMI PC", bg=NAVY, fg=HEAD_MUTED, font=(f, 9)).pack(side="right", padx=(0, 8))
        self.bucket_frame = tk.Frame(bar, bg=NAVY)
        tk.Label(self.bucket_frame, text="HMI server", bg=NAVY, fg=HEAD_MUTED,
                 font=(f, 9)).pack(side="left", padx=(0, 8))
        self.bucket_var = tk.StringVar()
        self.bucket_cb = ttk.Combobox(self.bucket_frame, textvariable=self.bucket_var, state="readonly", width=18)
        self.bucket_cb.pack(side="left")
        self.bucket_cb.bind("<<ComboboxSelected>>", lambda e: self.on_bucket_change())

    def _build_footer(self):
        f = font_family()
        bar = tk.Frame(self.root, bg=FOOTER, height=30)
        bar.grid(row=4, column=0, sticky="ew")
        bar.pack_propagate(False)
        self.msg_var = tk.StringVar(value="Starting…")
        tk.Label(bar, textvariable=self.msg_var, bg=FOOTER, fg=TEXT, font=(f, 9)).pack(side="left", padx=12)
        tk.Label(bar, text=f"© {BRAND}  ·  {APP_NAME} v{VERSION}", bg=FOOTER, fg=MUTED,
                 font=(f, 9)).pack(side="right", padx=12)
        ttk.Button(bar, text="Open folder", style="Footer.TButton", command=self.open_folder).pack(side="right")
        self.open_btn = ttk.Button(bar, text="Open file", style="Footer.TButton",
                                   command=lambda: self._open(self.last_file))
        self.open_btn.pack(side="right")
        self.open_btn.state(["disabled"])

    # ------------------------------------------------------------------ state
    def general(self):
        return self.settings["general"]

    def _update_buttons(self):
        self.fetch_btn.state(["disabled"] if self.busy else ["!disabled"])
        ready = self.result is not None and not self.result.get("empty") and not self.busy
        for b in self.buttons.values():
            b.state(["!disabled"] if ready else ["disabled"])

    def set_conn(self, text, ok):
        self.conn_var.set(f"● {text}")
        busy = not ok and text.endswith("…")
        self.conn_lbl.configure(fg=HEAD_OK if ok else (HEAD_BUSY if busy else HEAD_BAD))

    def invalidate(self):
        self.generation += 1
        if self.result is not None:
            self.result = None
            self.results.clear("Selection changed. Click Fetch data to refresh.")
        self._update_buttons()

    # ------------------------------------------------------------------ background jobs
    def defer(self, kind, method):
        if self.busy:
            self.pending.pop(kind, None)
            self.pending[kind] = method
            return True
        return False

    def run_bg(self, fn, on_done, msg, on_error=None):
        self.busy = True
        self.progress.start(12)
        self.msg_var.set(msg)
        self._update_buttons()
        url = profile_url(self.profile) if self.profile else ""

        def target():
            try:
                self.q.put(("done", on_done, fn()))
            except Exception as exc:
                log.exception("Background task failed")
                self.q.put(("error", on_error, friendly_error(exc, url)))

        threading.Thread(target=target, daemon=True).start()

    def report(self, text):
        self.q.put(("status", None, text))

    def _poll(self):
        try:
            while True:
                kind, cb, payload = self.q.get_nowait()
                if kind == "status":
                    self.msg_var.set(payload)
                    continue
                self.busy = False
                self.progress.stop()
                self._update_buttons()
                if kind == "done":
                    cb(payload)
                else:
                    self.msg_var.set("Something went wrong. See the message.")
                    (cb or self._show_error)(payload)
        except queue.Empty:
            pass
        finally:
            # Always re-arm, even if a callback above failed: otherwise the window would never
            # again react to finished background work.
            if self.pending and not self.busy:
                self.root.after(10, self.pending.pop(next(iter(self.pending))))
            self.root.after(100, self._poll)

    def _show_error(self, message):
        messagebox.showerror(APP_NAME, message, parent=self.root)
        if "(401)" in message and self.profile and self.profile.get("auth") == "user":
            self.connect()      # a username/password session expires after a while: sign in again

    # ------------------------------------------------------------------ settings / profiles
    def open_settings(self):
        SettingsDialog(self.root, self.settings, self.apply_settings)

    def apply_settings(self, data):
        if self.profile:        # keep the current ticks of the selected HMI PC
            for p in data["profiles"]:
                if p["name"] == self.profile["name"]:
                    p["last_tags"] = sorted(self.tags.selected)
        self.settings = data
        save_settings(self.settings)
        self.period.update_limits()
        self.reload_profiles()

    def reload_profiles(self):
        names = [p["name"] for p in self.settings["profiles"]]
        self.profile_cb["values"] = names
        if not names:
            self.set_conn("No HMI PC set up", False)
            self.msg_var.set("Open Settings and add an HMI PC.")
            self.root.after(300, self.open_settings)
            return
        cur, last = self.profile_var.get(), self.settings.get("last_profile")
        self.profile_var.set(cur if cur in names else (last if last in names else names[0]))
        self.on_profile_change()

    def on_profile_change(self):
        self.profile = next((p for p in self.settings["profiles"] if p["name"] == self.profile_var.get()), None)
        if not self.profile:
            return
        self.settings["last_profile"] = self.profile["name"]
        save_settings(self.settings)
        self.tags.set_profile(self.profile)
        self.invalidate()
        self.connect()

    def on_bucket_change(self):
        self.profile["last_bucket"] = self.bucket_var.get()
        save_settings(self.settings)
        self.invalidate()
        self.load_tags()

    # ------------------------------------------------------------------ connect / tags
    def connect(self):
        if self.defer("connect", self.connect) or not self.profile:
            return
        prof, general = self.profile, dict(self.general())
        if (not prof.get("username") or not prof.get("password")) if prof.get("auth") == "user" else not prof.get("token"):
            self.set_conn("Sign-in details missing", False)
            self.msg_var.set(f"Add the token or username/password for '{prof['name']}' in Settings.")
            return
        old, self.source = self.source, None
        if old:
            old.close()
        self.set_conn("Connecting…", False)

        def work():
            src = InfluxSource(prof, general)
            if not src.ping():
                src.close()
                raise ConnectionError("connection refused")
            buckets = src.list_buckets()
            if len(buckets) > 1:
                buckets = [b for b in buckets if src.has_tagdata(b)] or buckets
            if not buckets:
                src.close()
                raise RuntimeError("Connected, but no bucket is visible. Check the read access.")
            return src, buckets, src.server_version()

        def failed(msg):
            self.set_conn("Not connected", False)
            messagebox.showerror(APP_NAME, msg, parent=self.root)

        self.run_bg(work, self._on_connected, f"Connecting to {prof['name']}…", failed)

    def _on_connected(self, result):
        self.source, buckets, version = result
        self.bucket_cb["values"] = buckets
        last = self.profile.get("last_bucket")
        self.bucket_var.set(last if last in buckets else buckets[0])
        if len(buckets) > 1:
            self.bucket_frame.pack(side="right", padx=(0, 16), before=self.profile_cb)
        else:
            self.bucket_frame.pack_forget()
        self.set_conn("Connected", True)
        self.load_tags()

    def load_tags(self):
        if self.defer("tags", self.load_tags) or not self.source:
            return
        src, bucket = self.source, self.bucket_var.get()
        self.run_bg(lambda: src.discover_tags(bucket), self._on_tags, "Loading tags…")

    def _on_tags(self, tag_map):
        self.tags.set_tags(tag_map)
        msg = f"{len(tag_map)} tag(s) logged in the last 30 days." if tag_map else "No DataLogPro tags in the last 30 days."
        logged = {norm_tag(k) for k in tag_map}
        missing = sum(1 for t in self.tags.export() if t not in logged)
        self.msg_var.set(msg + (f"  {missing} tag(s) of the imported configuration have no data." if missing else ""))

    # ------------------------------------------------------------------ fetch
    def fetch(self):
        if not self.source:
            messagebox.showerror(APP_NAME, "Not connected to an HMI PC.", parent=self.root)
            return
        try:
            start, end = self.period.get_range()
        except ValueError as e:
            messagebox.showerror(APP_NAME, str(e), parent=self.root)
            return
        tags = self.tags.chosen()
        if not tags:
            messagebox.showerror(APP_NAME, "Select at least one tag.", parent=self.root)
            return
        if len(tags) > self.general()["max_tags"]:
            messagebox.showerror(APP_NAME, f"Select {self.general()['max_tags']} tags or fewer (Settings).", parent=self.root)
            return
        self.profile["last_tags"] = sorted(self.tags.selected)
        save_settings(self.settings)
        p = dict(profile=self.profile["name"], host=self.profile["host"], bucket=self.bucket_var.get(), start=start,
                 end=end, tags=tags, tz=profile_tz(self.profile), good_only=self.good_var.get(),
                 heartbeat=self.tags.resolve(self.profile.get("heartbeat_tag", "").strip()),
                 groups={t: self.tags.group_of(t) for t in tags},
                 intervals={t: self.tags.interval_of(t) for t in tags},
                 periodic={t for t in tags if self.tags.is_periodic(t)},
                 tz_label=next((lab for lab, v in tz_choices() if v == self.profile.get("tz", "local")), "this PC"),
                 groups_info=self.profile.get("groups") or {})
        if p["heartbeat"]:
            p["intervals"][p["heartbeat"]] = self.tags.interval_of(p["heartbeat"])
            if self.tags.is_periodic(p["heartbeat"]):
                p["periodic"].add(p["heartbeat"])
        src, gen = self.source, self.generation
        p["generation"] = gen

        def counted(n):
            if gen != self.generation:
                self.msg_var.set("Selection changed. Click Fetch data again.")
                return
            limit = self.general()["value_alert"]
            if n > limit and not messagebox.askyesno(
                    APP_NAME, f"This selection contains {n:,} values (alert limit {limit:,}).\n\n"
                              "Fetching it needs time and memory on this PC and load on the HMI PC. Continue?",
                    parent=self.root):
                self.msg_var.set("Fetch cancelled.")
                return
            self.run_bg(lambda: self._fetch_work(src, p), self._on_fetched, f"Fetching {n:,} values…")

        self.run_bg(lambda: src.count_values(p["bucket"], start, end, tags), counted, "Counting values…")

    def _fetch_work(self, src, p):
        fetch_tags = p["tags"] + ([p["heartbeat"]] if p["heartbeat"] and p["heartbeat"] not in p["tags"] else [])

        def progress(records):
            for i, rec in enumerate(records, 1):
                if i % 100_000 == 0:
                    self.report(f"{i:,} records read…")
                yield rec

        col = collect(progress(src.fetch_records(p["bucket"], p["start"], p["end"], fetch_tags)),
                      p["tags"], p["good_only"], p["heartbeat"])
        self.report("Checking log health…")
        start_ns, end_ns = dt_to_ns(p["start"]), dt_to_ns(p["end"])
        now_ns = src.server_now_ns() or time.time_ns()      # the HMI PC's clock, not this PC's
        health = analyze(col.health, p["tags"], p["groups"], p["intervals"], start_ns, end_ns, now_ns,
                         self.general()["gap_tolerance"], p["heartbeat"], col.excluded, p["periodic"])
        last = src.last_data_time(p["bucket"], p["tags"]) if col.values == 0 else None
        return {"params": p, "col": col, "health": health, "empty": col.values == 0, "last": last}

    def _on_fetched(self, res):
        if res["params"]["generation"] != self.generation:     # selection changed while fetching
            self.msg_var.set("Selection changed. Click Fetch data again.")
            return
        self.result = res
        p, col = res["params"], res["col"]
        if res["empty"]:
            last = res["last"]
            when = (last.astimezone(p["tz"]) if p["tz"] else last.astimezone()) if last else None
            self.results.clear("No data for the selected tags in this period.  " +
                               (f"Last data: {when:%Y-%m-%d %H:%M:%S}" if when else "Nothing logged for these tags in the last 30 days."))
            self.results.show_health(res["health"], p["tz"], p["tags"])
            self.msg_var.set("No data found.")
        else:
            self.results.show(col, p["tags"], not p["good_only"], p["tz"], res["health"])
            self.msg_var.set(f"Fetched {col.values:,} values.")
        self._update_buttons()

    # ------------------------------------------------------------------ download
    def download(self, kind):
        if not self.result or self.result.get("empty"):
            return
        from ..writers.pdf import estimate_pages

        col, tags = self.result["col"], self.result["params"]["tags"]
        grouped = any(self.result["params"]["groups"].get(t) for t in tags)
        rows = col.rows + (2 if grouped else 1)
        if kind == "xlsx" and rows > EXCEL_MAX_ROWS:
            messagebox.showerror(APP_NAME, f"{rows:,} rows do not fit in Excel (max {EXCEL_MAX_ROWS:,}).\n\n"
                                           "Use CSV, or shorten the period. Nothing was cut.", parent=self.root)
            return
        if kind == "pdf":
            pages = estimate_pages(col.rows, len(tags))
            if pages > PDF_PAGE_WARN and not messagebox.askyesno(
                    APP_NAME, f"The PDF will have about {pages:,} pages. Create it anyway?", parent=self.root):
                return
        result, folder = self.result, self.general()["output_folder"]
        self.run_bg(lambda: export(kind, result, folder), self._on_saved, f"Saving {FORMATS[kind]} file…")

    def _on_saved(self, path):
        self.last_file = path
        self.open_btn.state(["!disabled"])
        self.msg_var.set("")

    def open_folder(self):
        folder = os.path.normpath(self.general()["output_folder"])
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError:
            pass
        self._open(folder)

    def _open(self, path):
        if not path:
            return
        path = os.path.normpath(path)   # '//tsclient/D/x' -> '\\tsclient\D\x' (os.startfile needs backslashes)
        try:
            os.startfile(path)
        except AttributeError:
            pass
        except OSError as exc:
            messagebox.showerror(APP_NAME, f"Cannot open:\n{path}\n\n{exc.strerror or exc}", parent=self.root)
