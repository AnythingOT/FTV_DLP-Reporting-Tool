"""Small widgets: calendar popup, date-time picker, tooltip."""

import calendar
from datetime import date, datetime, timedelta

import tkinter as tk
from tkinter import ttk



class Tooltip:
    """Shows a short help text when the mouse rests on a widget."""

    def __init__(self, widget, text, delay=500):
        self.widget, self.text, self.delay = widget, text, delay
        self.tip = self.job = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _e=None):
        self._cancel()
        self.job = self.widget.after(self.delay, self._show)

    def _cancel(self):
        if self.job:
            self.widget.after_cancel(self.job)
            self.job = None

    def _show(self):
        x = self.widget.winfo_rootx() + 10
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.geometry(f"+{x}+{y}")
        tk.Label(self.tip, text=self.text, justify="left", background="#FFFFE6", relief="solid",
                 borderwidth=1, wraplength=360, padx=6, pady=4).pack()

    def _hide(self, _e=None):
        self._cancel()
        if self.tip:
            self.tip.destroy()
            self.tip = None


class CalendarPopup(tk.Toplevel):
    def __init__(self, anchor, current, on_pick):
        super().__init__(anchor)
        self.withdraw()
        self.title("Select date")
        self.transient(anchor.winfo_toplevel())
        self.resizable(False, False)
        self.on_pick = on_pick
        self.sel = current
        self.year, self.month = current.year, current.month
        frame = ttk.Frame(self, padding=10)
        frame.pack(fill="both", expand=True)
        nav = ttk.Frame(frame)
        nav.pack(fill="x")
        ttk.Button(nav, text="‹", width=3, command=lambda: self.shift(-1)).pack(side="left")
        self.title_var = tk.StringVar()
        ttk.Label(nav, textvariable=self.title_var, anchor="center",
                  font=("Segoe UI Semibold", 10)).pack(side="left", expand=True, fill="x")
        ttk.Button(nav, text="›", width=3, command=lambda: self.shift(1)).pack(side="right")
        self.days = ttk.Frame(frame)
        self.days.pack(pady=(8, 0))
        ttk.Button(frame, text="Today", command=lambda: self.pick(date.today())).pack(fill="x", pady=(8, 0))
        self.bind("<Escape>", lambda e: self.destroy())
        self.render()
        self.update_idletasks()
        self.geometry(f"+{anchor.winfo_rootx()}+{anchor.winfo_rooty() + anchor.winfo_height() + 2}")
        self.deiconify()
        self.grab_set()
        self.focus_set()

    def shift(self, delta):
        m = self.month - 1 + delta
        self.year, self.month = self.year + m // 12, m % 12 + 1
        self.render()

    def render(self):
        for w in self.days.winfo_children():
            w.destroy()
        self.title_var.set(f"{calendar.month_name[self.month]} {self.year}")
        for i, name in enumerate(("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")):
            ttk.Label(self.days, text=name, width=4, anchor="center").grid(row=0, column=i)
        today = date.today()
        weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(self.year, self.month)
        for r, week in enumerate(weeks, start=1):
            for c, d in enumerate(week):
                if d.month != self.month:
                    ttk.Label(self.days, text="", width=4).grid(row=r, column=c)
                    continue
                style = "Accent.TButton" if d == self.sel else "TButton"
                b = ttk.Button(self.days, text=str(d.day), width=3, style=style,
                               command=lambda d=d: self.pick(d))
                if d > today + timedelta(days=1):     # tomorrow stays selectable: the plant may be a day ahead
                    b.state(["disabled"])
                b.grid(row=r, column=c, padx=1, pady=1)

    def pick(self, d):
        self.grab_release()
        self.destroy()
        self.on_pick(d)


class DateTimePicker(ttk.Frame):
    """Date field (opens the built-in calendar) + hour/minute.
    Hour and minute change with the arrows, the mouse wheel or the keyboard up/down keys.
    The calendar is built in on purpose: tkcalendar is GPLv3, which would put licence
    obligations on every distributed exe."""

    def __init__(self, master, on_change):
        super().__init__(master)
        self.on_change = on_change
        self.day = date.today()
        self._last = None      # last value reported, so on_change fires only on a real change
        self.btn = ttk.Button(self, width=13, command=self.open_calendar)
        self.btn.pack(side="left")
        self.hour = tk.StringVar(value="00")
        self.minute = tk.StringVar(value="00")
        for var, top in ((self.hour, 23), (self.minute, 59)):
            sp = ttk.Spinbox(self, from_=0, to=top, wrap=True, width=3, format="%02.0f",
                             textvariable=var, command=self._changed)
            sp.pack(side="left", padx=(8, 0) if var is self.hour else (0, 0))
            sp.bind("<FocusOut>", lambda e: self._changed())
            sp.bind("<Return>", lambda e: self._changed())
            sp.bind("<MouseWheel>", lambda e, w=sp: self._step(w, 1 if e.delta > 0 else -1))
            sp.bind("<Button-4>", lambda e, w=sp: self._step(w, 1))    # Linux wheel
            sp.bind("<Button-5>", lambda e, w=sp: self._step(w, -1))
            sp.bind("<Up>", lambda e, w=sp: self._step(w, 1))
            sp.bind("<Down>", lambda e, w=sp: self._step(w, -1))
            if var is self.hour:
                ttk.Label(self, text=":").pack(side="left", padx=3)

    def _step(self, widget, delta):
        widget.event_generate("<<Increment>>" if delta > 0 else "<<Decrement>>")
        self._changed()
        return "break"

    def get(self):
        try:
            h, m = int(float(self.hour.get())), int(float(self.minute.get()))
        except ValueError:
            raise ValueError("Enter the time as hours and minutes.")
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError("Hours must be 0-23 and minutes 0-59.")
        return datetime(self.day.year, self.day.month, self.day.day, h, m)

    def set(self, dt):
        self.day = dt.date()
        self.btn.configure(text=self._label(self.day))
        self.hour.set(f"{dt.hour:02d}")
        self.minute.set(f"{dt.minute:02d}")
        self._last = self._current()

    def _current(self):
        return self.day, self.hour.get(), self.minute.get()

    def open_calendar(self):
        CalendarPopup(self.btn, self.day, self._picked)

    def _picked(self, d):
        self.day = d
        self.btn.configure(text=self._label(d))
        self._changed()

    @staticmethod
    def _label(d):
        return f"{d:%Y-%m-%d}  ▾"

    def _changed(self):
        for var in (self.hour, self.minute):
            try:
                var.set(f"{int(float(var.get())):02d}")
            except ValueError:
                pass
        # Only report real changes: this also runs when a time box merely loses focus, and
        # reporting that would discard the fetched data just because the user clicked a button.
        if self._current() != self._last:
            self._last = self._current()
            self.on_change()
