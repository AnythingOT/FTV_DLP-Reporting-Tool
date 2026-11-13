"""Light theme only: Sun Valley (sv-ttk) if installed, otherwise Tk's built-in 'clam'."""

import logging

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from ..constants import ACCENT, TREE_INDENT

log = logging.getLogger("dlpreport")


def apply_theme(root):
    try:
        import sv_ttk
        sv_ttk.set_theme("light")
        themed = True
    except ImportError:
        style = ttk.Style(root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Accent.TButton", foreground="white", background=ACCENT)
        style.map("Accent.TButton", background=[("disabled", "#9BB8D3"), ("active", "#1975C5")])
        themed = False
    _tree_style(root)
    return themed


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


def bold_font():
    f = tkfont.nametofont("TkDefaultFont").copy()
    f.configure(weight="bold")
    return f
