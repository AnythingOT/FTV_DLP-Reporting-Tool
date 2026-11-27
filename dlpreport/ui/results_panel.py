"""Right side: Preview tab and Log health tab (tag-wise tree, like FactoryTalk Diagnostics)."""

from collections import Counter

import tkinter as tk
from tkinter import ttk

from ..constants import CRITICAL, INFO, PREVIEW_ROWS, SEVERITY_COLOR, SEVERITY_RANK, WARNING
from ..table import cell_text, iter_rows
from ..timeutil import fmt_duration, fmt_ns
from .theme import STRIPE, bold_font
from .widgets import Card


def short_ns(ns, tz):
    """Preview only: 4 decimals (exports keep all 9)."""
    return fmt_ns(ns, tz)[:-5]


class ResultsPanel(Card):
    def __init__(self, master):
        super().__init__(master, padding=(12, 10))
        self.nb = ttk.Notebook(self.body, style="Card.TNotebook")
        self.nb.pack(fill="both", expand=True)
        self.prev_tv, self.prev_info = self._tab("Preview", "headings")
        self.health_tv, self.health_info = self._tab("Log health", "tree headings")
        tv = self.health_tv
        tv["columns"] = ("start", "end", "dur", "event")
        tv.heading("#0", text="Tag / severity", anchor="center")
        tv.column("#0", width=330, stretch=False)
        for c, text, w in (("start", "Start", 190), ("end", "End", 190), ("dur", "Duration", 90), ("event", "Event", 520)):
            tv.heading(c, text=text, anchor="center")
            tv.column(c, width=w, stretch=c == "event")
        for sev, color in SEVERITY_COLOR.items():
            tv.tag_configure(sev, foreground=color)
        tv.tag_configure("tag", font=bold_font())
        tv.bind("<Button-1>", self._toggle)
        self.clear("Select tags and click Fetch data.")

    def _tab(self, title, show):
        frame = ttk.Frame(self.nb, style="Card.TFrame", padding=(0, 8, 0, 0))
        self.nb.add(frame, text=title)
        body = ttk.Frame(frame, style="Card.TFrame")
        body.pack(fill="both", expand=True)
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        tv = ttk.Treeview(body, show=show, selectmode="none")
        ys = ttk.Scrollbar(body, orient="vertical", command=tv.yview)
        xs = ttk.Scrollbar(body, orient="horizontal", command=tv.xview)
        tv.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        tv.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        info = tk.StringVar()
        tv.tag_configure("odd", background=STRIPE)
        ttk.Label(frame, textvariable=info, style="CardMuted.TLabel", wraplength=900,
                  justify="left").pack(anchor="w", pady=(6, 0))
        return tv, info

    def clear(self, message):
        self.prev_tv.delete(*self.prev_tv.get_children())
        self.health_tv.delete(*self.health_tv.get_children())
        self.prev_info.set(message)
        self.health_info.set("")
        self.nb.tab(1, text="Log health")

    def show(self, collected, tags, include_status, tz, health):
        tv = self.prev_tv
        tv.delete(*tv.get_children())
        tv["columns"] = [f"c{i}" for i in range(len(tags) + 1)]
        tv.heading("c0", text="Time")
        tv.column("c0", width=220, stretch=False)
        for i, tag in enumerate(tags, start=1):
            tv.heading(f"c{i}", text=tag)
            tv.column(f"c{i}", width=max(90, min(320, len(tag) * 7 + 16)), stretch=False, anchor="e")
        for n, (ns, cells) in enumerate(iter_rows(collected, tags)):
            if n >= PREVIEW_ROWS:
                break
            tv.insert("", "end", values=[fmt_ns(ns, tz)] + [cell_text(c, include_status) for c in cells],
                      tags=("odd",) if n % 2 else ())
        total = collected.rows
        self.prev_info.set(f"{total:,} rows × {len(tags)} tags" +
                           (f"   (preview shows the first {PREVIEW_ROWS:,})" if total > PREVIEW_ROWS else "") +
                           (f"   ·   {collected.excluded:,} value(s) with status ≠ C excluded" if collected.excluded else ""))
        self.show_health(health, tz, tags)

    def show_health(self, health, tz, tags):
        tv = self.health_tv
        tv.delete(*tv.get_children())
        by_tag = {}
        for e in health.events:
            by_tag.setdefault(e.tag, []).append(e)
        for t in list(tags) + [t for t in by_tag if t not in tags]:
            events = by_tag.get(t, [])
            counts = Counter(e.severity for e in events)
            worst = min((e.severity for e in events), key=lambda s: SEVERITY_RANK[s], default=None)
            summary = ", ".join(f"{counts[s]} {s.lower()}" for s in (CRITICAL, WARNING, INFO) if counts.get(s)) or "OK"
            parent = tv.insert("", "end", text=f"{'▸' if events else '✓'}  {t}", values=("", "", "", summary),
                               tags=("tag", worst or "OK"), open=False)
            for e in events:
                tv.insert(parent, "end", text=e.severity, tags=(e.severity,), values=(
                    short_ns(e.start, tz), short_ns(e.end, tz),
                    fmt_duration(e.end - e.start) if e.end > e.start else "", e.text))
        self.health_info.set("   ".join(health.notes))
        c = health.counts()
        label = ", ".join(f"{c[s]} {s.lower()}" for s in (CRITICAL, WARNING) if c.get(s))
        self.nb.tab(1, text=f"Log health ({label})" if label else "Log health")

    def _toggle(self, event):
        tv = self.health_tv
        iid = tv.identify_row(event.y)
        if iid and not tv.parent(iid) and tv.get_children(iid):
            opened = not tv.item(iid, "open")
            tv.item(iid, open=opened)
            text = tv.item(iid, "text")
            tv.item(iid, text=("▾" if opened else "▸") + text[1:])
            return "break"
        return None
