"""Settings window: HMI PCs (connection, sign-in, time zone, heartbeat, log groups) and General.
Rarely changed options are under 'Show advanced'."""

import copy
import logging
import os
import queue
import threading
from datetime import datetime

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ..dlp_export import parse_dlp_export
from ..influx import InfluxSource, friendly_error, profile_url
from ..settings import DEFAULT_GENERAL, new_profile, settings_dir
from ..timeutil import tz_choices
from .widgets import Tooltip

log = logging.getLogger("dlpreport")
AUTH_MODES = {"API token": "token", "Username and password": "user"}
INT_FIELDS = {"max_days": (1, 366), "max_tags": (1, 1000), "batch_size": (1, 200),
              "timeout_s": (5, 3600), "value_alert": (1000, 100_000_000)}


class SettingsDialog(tk.Toplevel):
    def __init__(self, master, settings, on_save):
        super().__init__(master)
        self.title("Settings")
        self.transient(master)
        self.resizable(False, False)
        self.on_save = on_save
        self.data = copy.deepcopy(settings)
        if not self.data["profiles"]:
            self.data["profiles"].append(new_profile())
        self.cur = None
        self.q = queue.Queue()
        self.tz_items = tz_choices()

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=14, pady=(14, 8))
        nb.add(self._build_profiles(nb), text="HMI PCs")
        nb.add(self._build_general(nb), text="General")
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=14, pady=(0, 14))
        ttk.Label(bar, text=f"Saved in {settings_dir()}", foreground="grey").pack(side="left")
        ttk.Button(bar, text="Save", style="Accent.TButton", command=self.save).pack(side="right")
        ttk.Button(bar, text="Cancel", command=self.destroy).pack(side="right", padx=8)
        self.refresh_profiles(select=0)
        self.grab_set()
        self.after(150, self._poll)

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _row(parent, r, label, widget, tip=None):
        ttk.Label(parent, text=label).grid(row=r, column=0, sticky="w", pady=4, padx=(0, 12))
        widget.grid(row=r, column=1, sticky="w", pady=4)
        if tip:
            Tooltip(widget, tip)
        return r + 1

    # ------------------------------------------------------------------ HMI PCs tab
    def _build_profiles(self, nb):
        f = ttk.Frame(nb, padding=14)
        left = ttk.Frame(f)
        left.grid(row=0, column=0, sticky="ns")
        self.plist = ttk.Treeview(left, show="tree", selectmode="browse", height=14)
        self.plist.column("#0", width=190)
        self.plist.pack(fill="y", expand=True)
        self.plist.bind("<<TreeviewSelect>>", self.on_profile_select)
        btns = ttk.Frame(left)
        btns.pack(fill="x", pady=(8, 0))
        ttk.Button(btns, text="Add", command=self.add_profile).pack(side="left", expand=True, fill="x")
        ttk.Button(btns, text="Remove", command=self.remove_profile).pack(side="left", expand=True, fill="x", padx=(6, 0))

        form = ttk.Frame(f)
        form.grid(row=0, column=1, sticky="nsew", padx=(18, 0))
        v = self.v = {k: tk.StringVar() for k in ("name", "host", "port", "org", "token", "username",
                                                  "password", "tz", "auth", "heartbeat_tag")}
        v["https"], v["verify_ssl"], v["adv"] = tk.BooleanVar(), tk.BooleanVar(), tk.BooleanVar()
        r = self._row(form, 0, "Machine name", ttk.Entry(form, textvariable=v["name"], width=42))
        r = self._row(form, r, "Host name or IP", ttk.Entry(form, textvariable=v["host"], width=42),
                      "Use the IP address if this PC and the HMI PC are in different domains/workgroups.")
        r = self._row(form, r, "Port", ttk.Entry(form, textvariable=v["port"], width=8))
        auth = ttk.Combobox(form, textvariable=v["auth"], values=list(AUTH_MODES), state="readonly", width=26)
        auth.bind("<<ComboboxSelected>>", lambda e: self._auth_fields())
        r = self._row(form, r, "Sign in with", auth)
        self.auth_entries = {k: ttk.Entry(form, textvariable=v[k], width=42, show="•" if k != "username" else "")
                             for k in ("token", "username", "password")}
        r = self._row(form, r, "API token (read-only)", self.auth_entries["token"])
        r = self._row(form, r, "Username (member)", self.auth_entries["username"])
        r = self._row(form, r, "Password", self.auth_entries["password"])
        r = self._row(form, r, "Machine time zone",
                      ttk.Combobox(form, textvariable=v["tz"], state="readonly", width=26,
                                   values=[label for label, _ in self.tz_items]),
                      "Time zone of the HMI PC / plant. All exported times use it.")
        r = self._row(form, r, "Heartbeat tag (optional)", ttk.Entry(form, textvariable=v["heartbeat_tag"], width=42),
                      "Name of a PLC counter that increments while the PLC runs, logged PERIODICALLY in "
                      "DataLogPro. If it stops changing, the log health check reports it (PLC in Program "
                      "mode or frozen data).")
        ttk.Button(form, text="Test connection", command=self.test_connection).grid(row=r, column=1, sticky="w", pady=(10, 2))
        self.test_var = tk.StringVar()
        ttk.Label(form, textvariable=self.test_var, wraplength=360, justify="left").grid(row=r + 1, column=1, sticky="w")
        ttk.Separator(form).grid(row=r + 2, column=0, columnspan=2, sticky="ew", pady=10)
        ttk.Label(form, text="Log groups").grid(row=r + 3, column=0, sticky="nw", pady=4)
        gbox = ttk.Frame(form)
        gbox.grid(row=r + 3, column=1, sticky="w", pady=4)
        self.groups_var = tk.StringVar()
        ttk.Label(gbox, textvariable=self.groups_var, wraplength=360, justify="left").pack(anchor="w")
        gb = ttk.Frame(gbox)
        gb.pack(anchor="w", pady=(6, 0))
        ttk.Button(gb, text="Import DataLogPro export…", command=self.import_groups).pack(side="left")
        ttk.Button(gb, text="Clear", command=self.clear_groups).pack(side="left", padx=6)
        ttk.Checkbutton(form, text="Show advanced", variable=v["adv"], command=self._advanced).grid(
            row=r + 4, column=1, sticky="w", pady=(10, 0))
        self.adv = ttk.Frame(form)
        self.adv.grid(row=r + 5, column=0, columnspan=2, sticky="w")
        a = self._row(self.adv, 0, "Organization", ttk.Entry(self.adv, textvariable=v["org"], width=20),
                      "Always 'Rockwell' for the built-in InfluxDB.")
        a = self._row(self.adv, a, "", ttk.Checkbutton(self.adv, text="Use HTTPS", variable=v["https"]))
        self._row(self.adv, a, "", ttk.Checkbutton(self.adv, text="Verify HTTPS certificate", variable=v["verify_ssl"]))
        self.adv.grid_remove()
        return f

    def _advanced(self):
        (self.adv.grid if self.v["adv"].get() else self.adv.grid_remove)()

    def _auth_fields(self):
        user = AUTH_MODES.get(self.v["auth"].get()) == "user"
        self.auth_entries["token"].state(["disabled"] if user else ["!disabled"])
        for k in ("username", "password"):
            self.auth_entries[k].state(["!disabled"] if user else ["disabled"])

    def _tz_label(self, value):
        return next((label for label, v in self.tz_items if v == value), self.tz_items[0][0])

    def _tz_value(self, label):
        return next((v for lab, v in self.tz_items if lab == label), "local")

    def store_form(self):
        if self.cur is None or self.cur >= len(self.data["profiles"]):
            return
        p = self.data["profiles"][self.cur]
        for k in ("name", "host", "org", "token", "username", "heartbeat_tag"):
            p[k] = self.v[k].get().strip()
        p["password"] = self.v["password"].get()
        try:
            p["port"] = int(self.v["port"].get())
        except ValueError:
            pass
        p["tz"] = self._tz_value(self.v["tz"].get())
        p["auth"] = AUTH_MODES.get(self.v["auth"].get(), "token")
        p["https"], p["verify_ssl"] = bool(self.v["https"].get()), bool(self.v["verify_ssl"].get())
        if self.plist.exists(str(self.cur)):
            self.plist.item(str(self.cur), text=p["name"] or "(no name)")

    def load_form(self, idx):
        p = self.data["profiles"][idx]
        for k in ("name", "host", "org", "token", "username", "password", "heartbeat_tag"):
            self.v[k].set(p.get(k, ""))
        self.v["port"].set(str(p.get("port", 8086)))
        self.v["tz"].set(self._tz_label(p.get("tz", "local")))
        self.v["auth"].set(next(k for k, val in AUTH_MODES.items() if val == p.get("auth", "token")))
        self.v["https"].set(bool(p.get("https")))
        self.v["verify_ssl"].set(bool(p.get("verify_ssl")))
        self._auth_fields()
        self.test_var.set("")
        self.cur = idx
        self._show_groups()

    def refresh_profiles(self, select=None):
        self.cur = None
        self.plist.delete(*self.plist.get_children())
        for i, p in enumerate(self.data["profiles"]):
            self.plist.insert("", "end", iid=str(i), text=p.get("name") or "(no name)")
        if select is not None and self.data["profiles"]:
            self.plist.selection_set(str(select))
            self.load_form(select)

    def on_profile_select(self, _e=None):
        sel = self.plist.selection()
        if not sel or (self.cur is not None and int(sel[0]) == self.cur):
            return
        self.store_form()
        self.load_form(int(sel[0]))

    def add_profile(self):
        self.store_form()
        self.data["profiles"].append(new_profile(f"HMI PC {len(self.data['profiles']) + 1}", ""))
        self.refresh_profiles(select=len(self.data["profiles"]) - 1)

    def remove_profile(self):
        if self.cur is None:
            return
        if len(self.data["profiles"]) == 1:
            messagebox.showinfo("Settings", "At least one HMI PC is needed.", parent=self)
            return
        del self.data["profiles"][self.cur]
        self.refresh_profiles(select=0)

    # ------------------------------------------------------------------ log groups
    def _show_groups(self):
        g = self.data["profiles"][self.cur].get("groups") or {}
        if g.get("tags"):
            n = len({x for e in g["tags"].values() for x in e["groups"]})
            self.groups_var.set(f"{len(g['tags'])} tags in {n} group(s)\n{g.get('file', '')}, imported {g.get('imported', '')}")
        else:
            self.groups_var.set("Not imported: tags are shown as one flat list and gaps cannot be checked.")

    def import_groups(self):
        path = filedialog.askopenfilename(parent=self, title="Select the DataLogPro export",
                                          filetypes=[("DataLogPro export", "*.csv *.xlsx"), ("All files", "*.*")])
        if not path:
            return
        try:
            data = parse_dlp_export(path)
        except Exception as exc:
            log.exception("Import of %s failed", path)
            messagebox.showerror("Settings", f"Could not import the file.\n\n{exc}", parent=self)
            return
        data["file"], data["imported"] = os.path.basename(path), datetime.now().strftime("%Y-%m-%d %H:%M")
        self.data["profiles"][self.cur]["groups"] = data
        self._show_groups()

    def clear_groups(self):
        self.data["profiles"][self.cur]["groups"] = {}
        self._show_groups()

    # ------------------------------------------------------------------ test connection
    def test_connection(self):
        self.store_form()
        prof = dict(self.data["profiles"][self.cur])
        general = self._read_general(silent=True) or self.data["general"]
        self.test_var.set("Testing…")

        def work():
            try:
                src = InfluxSource(prof, general)
                try:
                    if not src.ping():
                        raise ConnectionError("connection refused")
                    buckets, version = src.list_buckets(), src.server_version()
                finally:
                    src.close()
                self.q.put(f"Connected (InfluxDB {version}). HMI server bucket(s): {', '.join(buckets) or 'none visible'}")
            except Exception as exc:
                log.exception("Test connection failed")
                self.q.put(friendly_error(exc, profile_url(prof)))

        threading.Thread(target=work, daemon=True).start()

    def _poll(self):
        try:
            while True:
                self.test_var.set(self.q.get_nowait())
        except queue.Empty:
            pass
        try:
            self.after(150, self._poll)
        except tk.TclError:
            pass

    # ------------------------------------------------------------------ General tab
    def _build_general(self, nb):
        f = ttk.Frame(nb, padding=14)
        g = self.data["general"]
        self.g = {k: tk.StringVar(value=str(g.get(k, DEFAULT_GENERAL[k]))) for k in DEFAULT_GENERAL}
        self.g_adv = tk.BooleanVar()
        folder = ttk.Frame(f)
        ttk.Entry(folder, textvariable=self.g["output_folder"], width=46).pack(side="left")
        ttk.Button(folder, text="Browse", command=self.browse).pack(side="left", padx=(6, 0))
        r = self._row(f, 0, "Save files to", folder)
        r = self._row(f, r, "Maximum days per fetch", ttk.Spinbox(f, from_=1, to=366, textvariable=self.g["max_days"], width=8))
        r = self._row(f, r, "Maximum tags per fetch", ttk.Spinbox(f, from_=1, to=1000, textvariable=self.g["max_tags"], width=8))
        ttk.Checkbutton(f, text="Show advanced", variable=self.g_adv, command=self._general_advanced).grid(
            row=r, column=1, sticky="w", pady=(10, 0))
        self.gadv = ttk.Frame(f)
        self.gadv.grid(row=r + 1, column=0, columnspan=2, sticky="w")
        a = self._row(self.gadv, 0, "Tags per query", ttk.Spinbox(self.gadv, from_=1, to=200, textvariable=self.g["batch_size"], width=8),
                      "A fetch is split into queries of this many tags. Lower = lighter on the HMI PC.")
        a = self._row(self.gadv, a, "Query timeout (s)", ttk.Spinbox(self.gadv, from_=5, to=3600, textvariable=self.g["timeout_s"], width=8))
        a = self._row(self.gadv, a, "Ask before fetching more than (values)",
                      ttk.Spinbox(self.gadv, from_=1000, to=100_000_000, increment=100_000, textvariable=self.g["value_alert"], width=12))
        self._row(self.gadv, a, "Gap tolerance (x expected interval)",
                  ttk.Spinbox(self.gadv, from_=1.5, to=10, increment=0.5, textvariable=self.g["gap_tolerance"], width=8),
                  "A gap is reported when no value arrives within this many expected intervals.")
        self.gadv.grid_remove()
        return f

    def _general_advanced(self):
        (self.gadv.grid if self.g_adv.get() else self.gadv.grid_remove)()

    def browse(self):
        folder = filedialog.askdirectory(parent=self, initialdir=self.g["output_folder"].get())
        if folder:
            self.g["output_folder"].set(os.path.normpath(folder))

    def _read_general(self, silent=False):
        out = {"output_folder": os.path.normpath(self.g["output_folder"].get().strip() or DEFAULT_GENERAL["output_folder"])}
        try:
            for k, (lo, hi) in INT_FIELDS.items():
                val = int(float(self.g[k].get()))
                if not lo <= val <= hi:
                    raise ValueError(k)
                out[k] = val
            tol = float(self.g["gap_tolerance"].get())
            if not 1.0 < tol <= 10:
                raise ValueError("gap_tolerance")
            out["gap_tolerance"] = tol
        except ValueError:
            if not silent:
                messagebox.showerror("Settings", "Check the numbers on the General tab (including Advanced).", parent=self)
            return None
        return out

    def save(self):
        self.store_form()
        general = self._read_general()
        if general is None:
            return
        names = [p["name"] for p in self.data["profiles"]]
        if any(not n for n in names) or len(set(names)) != len(names):
            messagebox.showerror("Settings", "Each HMI PC needs a unique machine name.", parent=self)
            return
        for p in self.data["profiles"]:
            if not p["host"]:
                messagebox.showerror("Settings", f"Enter a host name or IP for '{p['name']}'.", parent=self)
                return
            if p["auth"] == "user" and not p["username"]:
                messagebox.showerror("Settings", f"Enter a username for '{p['name']}'.", parent=self)
                return
        self.data["general"] = general
        self.grab_release()
        self.destroy()
        self.on_save(self.data)
