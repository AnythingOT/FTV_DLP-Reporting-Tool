"""Period selection: Today / Yesterday / Last… and From/To date-time pickers."""

from datetime import timedelta

import tkinter as tk
from tkinter import ttk

from ..constants import QUICK_RANGES
from ..timeutil import naive_to_aware, now_in
from .widgets import Card, DateTimePicker


class PeriodPanel(Card):
    def __init__(self, master, on_change, get_tz, get_max_days):
        super().__init__(master, title="Period")
        self.on_change, self.get_tz, self.get_max_days = on_change, get_tz, get_max_days
        self.note = ttk.Label(self.head, style="CardMuted.TLabel")
        self.note.pack(side="right")
        row = ttk.Frame(self.body, style="Card.TFrame")
        row.pack(fill="x")
        ttk.Button(row, text="Today", command=lambda: self.set_quick("today")).pack(side="left")
        ttk.Button(row, text="Yesterday", command=lambda: self.set_quick("yesterday")).pack(side="left", padx=8)
        self.last_var = tk.StringVar(value="Last…")
        self.last_cb = ttk.Combobox(row, textvariable=self.last_var, state="readonly", width=16)
        self.last_cb.pack(side="left")
        self.last_cb.bind("<<ComboboxSelected>>", lambda e: self._last_selected())
        ttk.Separator(row, orient="vertical").pack(side="left", fill="y", padx=18)
        ttk.Label(row, text="From", style="Card.TLabel").pack(side="left", padx=(0, 8))
        self.from_p = DateTimePicker(row, self.on_change)
        self.from_p.pack(side="left")
        ttk.Label(row, text="To", style="Card.TLabel").pack(side="left", padx=(20, 8))
        self.to_p = DateTimePicker(row, self.on_change)
        self.to_p.pack(side="left")
        self.update_limits()

    def update_limits(self):
        limit = self.get_max_days() * 1440
        self.last_cb["values"] = [label for label, minutes in QUICK_RANGES if minutes <= limit]
        self.note.configure(text=f"Max {self.get_max_days()} day(s)")

    def set_quick(self, kind, notify=True):
        now = now_in(self.get_tz()).replace(tzinfo=None, second=0, microsecond=0)
        midnight = now.replace(hour=0, minute=0)
        if kind == "today":
            start, end = midnight, max(now, midnight + timedelta(minutes=1))
        elif kind == "yesterday":
            start, end = midnight - timedelta(days=1), midnight
        else:
            start, end = now - timedelta(minutes=kind), now
        self.from_p.set(start)
        self.to_p.set(end)
        if kind in ("today", "yesterday"):
            self.last_var.set("Last…")
        if notify:
            self.on_change()

    def _last_selected(self):
        minutes = dict(QUICK_RANGES).get(self.last_var.get())
        if minutes:
            self.set_quick(minutes)

    def get_range(self):
        tz = self.get_tz()
        start = naive_to_aware(self.from_p.get(), tz)
        end = naive_to_aware(self.to_p.get(), tz)
        if start >= end:
            raise ValueError("'From' must be before 'To'.")
        if end - start > timedelta(days=self.get_max_days()):
            raise ValueError(f"The period is longer than {self.get_max_days()} day(s). "
                             "Shorten it or change the limit in Settings.")
        return start, end
