"""AnythingOT look (same palette as the other AnythingOT tools): navy header, orange accent,
white cards on a light grey background. Built on Tk's 'clam' theme, so no extra package is needed."""

import logging

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from ..constants import TREE_INDENT

log = logging.getLogger("dlpreport")

BRAND = "AnythingOT"

# --- palette
NAVY = "#0F1B2D"
NAVY_2 = "#1C2B42"
NAVY_3 = "#2A3B55"
ACCENT = "#F28C28"
ACCENT_DARK = "#D9771A"
ACCENT_SOFT = "#FFF4EA"
BG = "#F3F5F8"
CARD = "#FFFFFF"
BORDER = "#DDE2E9"
TEXT = "#1F2937"
MUTED = "#6B7280"
HEAD_MUTED = "#9FB0C8"
STRIPE = "#F8FAFC"
SELECT = "#FDE7D1"
BUTTON = "#EEF1F5"
BUTTON_HOVER = "#E2E7EE"
FOOTER = "#E9EDF2"
# connection status on the navy header (brighter than the report colours so they read on dark)
HEAD_OK, HEAD_BAD, HEAD_BUSY = "#4ADE80", "#F87171", "#FBBF24"

_family = None


def font_family():
    """First available of the usual UI fonts (Segoe UI on Windows)."""
    global _family
    if _family is None:
        fams = set(tkfont.families())
        _family = next((f for f in ("Segoe UI", "Inter", "Helvetica Neue", "DejaVu Sans", "Arial") if f in fams),
                       "TkDefaultFont")
    return _family


def apply_theme(root):
    fam = font_family()
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
        try:
            tkfont.nametofont(name).configure(family=fam, size=10)
        except tk.TclError:
            pass
    root.configure(bg=BG)
    # rows sized from the font, so they do not clip on high-DPI screens
    row_h = tkfont.nametofont("TkDefaultFont").metrics("linespace") + 10

    s = ttk.Style(root)
    s.theme_use("clam")
    s.configure(".", background=BG, foreground=TEXT, font=(fam, 10), bordercolor=BORDER,
                lightcolor=BORDER, darkcolor=BORDER, focuscolor=ACCENT, troughcolor=BG,
                selectbackground=SELECT, selectforeground=TEXT)

    # frames and labels
    s.configure("Card.TFrame", background=CARD)
    s.configure("Card.TLabel", background=CARD, foreground=TEXT)
    s.configure("CardMuted.TLabel", background=CARD, foreground=MUTED)
    s.configure("Muted.TLabel", background=BG, foreground=MUTED)
    s.configure("Section.TLabel", background=CARD, foreground=MUTED, font=(fam, 9, "bold"))
    s.configure("TSeparator", background=BORDER)

    # buttons
    s.configure("TButton", padding=(12, 5), background=BUTTON, relief="flat", anchor="center")
    s.map("TButton", background=[("disabled", "#F3F4F6"), ("pressed", "#D5DBE3"), ("active", BUTTON_HOVER)],
          foreground=[("disabled", "#A0A7B4")])
    s.configure("Accent.TButton", background=ACCENT, foreground="white", font=(fam, 10, "bold"),
                padding=(16, 5), bordercolor=ACCENT, lightcolor=ACCENT, darkcolor=ACCENT)
    s.map("Accent.TButton",
          background=[("disabled", "#E5C3A1"), ("pressed", ACCENT_DARK), ("active", ACCENT_DARK)],
          foreground=[("disabled", "white")],
          bordercolor=[("disabled", "#E5C3A1"), ("active", ACCENT_DARK)],
          lightcolor=[("disabled", "#E5C3A1"), ("active", ACCENT_DARK)],
          darkcolor=[("disabled", "#E5C3A1"), ("active", ACCENT_DARK)])
    s.configure("Header.TButton", background=NAVY_2, foreground="white", bordercolor=NAVY_3,
                lightcolor=NAVY_2, darkcolor=NAVY_2, padding=(12, 5))
    s.map("Header.TButton", background=[("pressed", NAVY), ("active", NAVY_3)])
    s.configure("Footer.TButton", background=FOOTER, foreground=ACCENT_DARK, padding=(8, 2),
                bordercolor=FOOTER, lightcolor=FOOTER, darkcolor=FOOTER)
    s.map("Footer.TButton", background=[("active", "#DDE3EA")], foreground=[("disabled", "#A0A7B4")])
    # calendar days: compact, the selected day in the accent colour
    s.configure("Day.TButton", padding=(2, 3), background=CARD, bordercolor=CARD,
                lightcolor=CARD, darkcolor=CARD)
    s.map("Day.TButton", background=[("disabled", CARD), ("active", ACCENT_SOFT)],
          foreground=[("disabled", "#C4C9D2")])
    s.configure("DaySel.TButton", padding=(2, 3), background=ACCENT, foreground="white",
                font=(fam, 10, "bold"), bordercolor=ACCENT, lightcolor=ACCENT, darkcolor=ACCENT)
    s.map("DaySel.TButton", background=[("active", ACCENT_DARK)])

    # check boxes
    for st, bg in (("TCheckbutton", BG), ("Card.TCheckbutton", CARD)):
        s.configure(st, background=bg, indicatorbackground="white", indicatorforeground="white",
                    upperbordercolor="#B8C0CC", lowerbordercolor="#B8C0CC")
        s.map(st, background=[("active", bg)],
              indicatorbackground=[("selected", ACCENT), ("pressed", SELECT)],
              upperbordercolor=[("selected", ACCENT)], lowerbordercolor=[("selected", ACCENT)])

    # entry fields
    for st in ("TEntry", "TSpinbox", "TCombobox"):
        s.configure(st, fieldbackground="white", padding=4, arrowcolor=MUTED, insertcolor=TEXT)
        s.map(st, bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)],
              fieldbackground=[("readonly", "white"), ("disabled", "#F3F4F6")])
    s.map("TCombobox", selectbackground=[("readonly", "white")], selectforeground=[("readonly", TEXT)],
          bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)],
          fieldbackground=[("readonly", "white"), ("disabled", "#F3F4F6")])
    root.option_add("*TCombobox*Listbox.selectBackground", SELECT)
    root.option_add("*TCombobox*Listbox.selectForeground", TEXT)
    root.option_add("*TCombobox*Listbox.font", (fam, 10))

    # tables
    s.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=TEXT, rowheight=row_h,
                bordercolor=BORDER, font=(fam, 10))
    s.configure("Treeview.Heading", background=BUTTON, foreground=TEXT, font=(fam, 10, "bold"),
                relief="flat", padding=(6, 5))
    s.map("Treeview.Heading", background=[("active", BUTTON_HOVER)])
    s.map("Treeview", background=[("selected", SELECT)], foreground=[("selected", TEXT)])

    # tabs
    s.configure("TNotebook", background=BG, bordercolor=BORDER, tabmargins=(0, 0, 0, 0))
    s.configure("Card.TNotebook", background=CARD)
    s.configure("TNotebook.Tab", background=BUTTON, foreground=MUTED, padding=(16, 6),
                bordercolor=BORDER, lightcolor=BUTTON, font=(fam, 10))
    s.map("TNotebook.Tab", background=[("selected", CARD), ("active", BUTTON_HOVER)],
          foreground=[("selected", TEXT)], lightcolor=[("selected", ACCENT)])

    # scrollbars, split bar, progress
    for orient in ("Vertical", "Horizontal"):
        s.configure(f"{orient}.TScrollbar", background="#D5DBE3", troughcolor=CARD, bordercolor=CARD,
                    lightcolor="#D5DBE3", darkcolor="#D5DBE3", arrowcolor=MUTED, gripcount=0)
        s.map(f"{orient}.TScrollbar", background=[("active", "#B8C0CC")])
    s.configure("TPanedwindow", background=BG)
    s.configure("Sash", sashthickness=12, gripcount=0, background=BG, lightcolor=BG, bordercolor=BG)
    s.configure("TProgressbar", background=ACCENT, troughcolor="#E5E7EB", bordercolor="#E5E7EB",
                lightcolor=ACCENT, darkcolor=ACCENT, thickness=6)

    _tree_style(root)
    return fam


def _tree_style(root):
    """No built-in expand arrow (Tk 9 draws it on every row); groups draw their own ▸/▾.
    Wider indent so tags sit clearly under their group."""
    try:
        style = ttk.Style(root)
        layout = [("Treeitem.padding", {"sticky": "nswe", "children": [
            ("Treeitem.image", {"side": "left", "sticky": ""}),
            ("Treeitem.text", {"side": "left", "sticky": ""})]})]
        style.layout("Item", layout)
        style.layout("Treeview.Item", layout)
        style.configure("Treeview", indent=TREE_INDENT)
    except tk.TclError:
        log.exception("Could not adjust the tree layout")


def make_icon():
    """32x32 window icon drawn in code: navy tile with an orange bar (same mark as the other AnythingOT tools)."""
    img = tk.PhotoImage(width=32, height=32)
    img.put(NAVY, to=(0, 0, 32, 32))
    img.put(ACCENT, to=(6, 22, 26, 26))
    img.put("white", to=(6, 8, 14, 18))
    img.put(NAVY, to=(8, 10, 12, 16))
    img.put("white", to=(16, 8, 26, 11))
    img.put("white", to=(19, 8, 23, 18))
    return img


def bold_font():
    f = tkfont.nametofont("TkDefaultFont").copy()
    f.configure(weight="bold")
    return f
