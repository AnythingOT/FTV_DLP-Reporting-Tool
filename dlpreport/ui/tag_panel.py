"""Tag list: flat list, or a tree of DataLogPro log groups when an export is imported.
Tag names are always shown exactly as stored."""

from collections import defaultdict

import tkinter as tk
from tkinter import ttk

from ..constants import GROUP_ROW_BG, NOT_IN_EXPORT, TYPE_LABEL, UNGROUPED
from ..dlp_export import expected_interval_s, is_periodic, norm_tag
from .theme import bold_font
from .widgets import Card, Tooltip


class TagPanel(Card):
    def __init__(self, master, on_change, on_refresh):
        super().__init__(master, title="Tags", padding=(12, 10))
        self.on_change, self.on_refresh = on_change, on_refresh
        self.profile = None
        self.tag_map = {}
        self.selected = set()
        self.visible = []
        self.item_tag, self.tag_items, self.group_children = {}, defaultdict(list), {}
        self._export_cache = (None, {})

        self.count_var = tk.StringVar()
        ttk.Label(self.head, textvariable=self.count_var, style="CardMuted.TLabel").pack(side="right")
        top = ttk.Frame(self.body, style="Card.TFrame")
        top.pack(fill="x")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self.refresh())
        ttk.Label(top, text="Search", style="Card.TLabel").pack(side="left")
        ttk.Entry(top, textvariable=self.search_var).pack(side="left", fill="x", expand=True, padx=(8, 0))

        body = ttk.Frame(self.body, style="Card.TFrame")
        body.pack(fill="both", expand=True, pady=8)
        self.tv = ttk.Treeview(body, columns=("type", "logging"), show="tree headings", selectmode="none")
        self.tv.heading("#0", text="Group / tag", anchor="w")
        self.tv.heading("type", text="Type")
        self.tv.heading("logging", text="Logging")
        self.tv.column("#0", width=320, minwidth=180)
        self.tv.column("type", width=60, stretch=False, anchor="center")
        self.tv.column("logging", width=120, stretch=False)
        self.tv.tag_configure("group", font=bold_font(), background=GROUP_ROW_BG)
        sb = ttk.Scrollbar(body, orient="vertical", command=self.tv.yview)
        self.tv.configure(yscrollcommand=sb.set)
        self.tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        self.tv.bind("<Button-1>", self._click)

        bottom = ttk.Frame(self.body, style="Card.TFrame")
        bottom.pack(fill="x")
        b = ttk.Button(bottom, text="Select shown", command=self.select_shown)
        b.pack(side="left")
        Tooltip(b, "Tick every tag currently shown (use Search to narrow the list first).")
        ttk.Button(bottom, text="Clear", command=self.clear).pack(side="left", padx=8)
        b = ttk.Button(bottom, text="↻ Refresh", command=self.on_refresh)
        b.pack(side="left")
        Tooltip(b, "Reload the tag list (tags logged in the last 30 days).")

    # ------------------------------------------------------------------ data
    def set_profile(self, profile):
        self.profile = profile
        self.selected = set(profile.get("last_tags", [])) if profile else set()
        self.tag_map = {}
        self.refresh()

    def set_tags(self, tag_map):
        self.tag_map = tag_map
        self.refresh()

    def export(self):
        """Imported DataLogPro configuration, keyed for matching (built once per import)."""
        tags = ((self.profile or {}).get("groups") or {}).get("tags", {})
        if self._export_cache[0] is not tags:
            self._export_cache = (tags, {norm_tag(k): v for k, v in tags.items()})
        return self._export_cache[1]

    def groups_for(self, tag, export=None):
        export = self.export() if export is None else export
        if not export:
            return []
        e = export.get(norm_tag(tag))
        return (e["groups"] or [UNGROUPED]) if e else [NOT_IN_EXPORT]

    def group_of(self, tag):
        return (self.groups_for(tag) or [""])[0]

    def interval_of(self, tag):
        return expected_interval_s(self.export().get(norm_tag(tag)))

    def is_periodic(self, tag):
        return is_periodic(self.export().get(norm_tag(tag)))

    def resolve(self, name):
        """Stored tag name for a name typed by the user (case and leading '::' do not matter)."""
        key = norm_tag(name)
        return next((t for t in self.tag_map if norm_tag(t) == key), name)

    def order_key(self, tag):
        groups = self.groups_for(tag)
        if not groups:
            return 0, "", tag.lower()
        return {UNGROUPED: 1, NOT_IN_EXPORT: 2}.get(groups[0], 0), groups[0].lower(), tag.lower()

    def chosen(self):
        return sorted(self.selected & set(self.tag_map), key=self.order_key)

    # ------------------------------------------------------------------ tree
    def refresh(self):
        tv = self.tv
        tv.delete(*tv.get_children())
        self.item_tag, self.tag_items, self.group_children = {}, defaultdict(list), {}
        f = self.search_var.get().strip().lower()
        export = self.export()
        names = sorted(self.tag_map, key=str.lower)

        def info(t):
            e = export.get(norm_tag(t)) or {}
            return e.get("type") or TYPE_LABEL.get(self.tag_map[t], "?"), e.get("trigger", "")

        if not export:
            self.visible = [t for t in names if f in t.lower()]
            for t in self.visible:
                self._insert("", t, *info(t))
        else:
            groups = defaultdict(list)
            for t in names:
                for g in self.groups_for(t, export):
                    if f in t.lower() or f in g.lower():
                        groups[g].append(t)
            special = [g for g in (UNGROUPED, NOT_IN_EXPORT) if g in groups]
            order = sorted((g for g in groups if g not in special), key=str.lower) + special
            self.visible = sorted({t for g in order for t in groups[g]}, key=str.lower)
            expand = bool(f) or len(order) <= 8
            for gi, g in enumerate(order):
                giid = f"g{gi}"
                self.group_children[giid] = (g, groups[g])
                tv.insert("", "end", iid=giid, text=g, open=expand, values=("", ""), tags=("group",))
                for t in groups[g]:
                    self._insert(giid, t, *info(t))
                self._update_group(giid)
        self._update_count()

    def _insert(self, parent, tag, typ, trigger):
        iid = f"t{len(self.item_tag)}"
        self.tv.insert(parent, "end", iid=iid, text=self._text(tag), values=(typ, trigger))
        self.item_tag[iid] = tag
        self.tag_items[tag].append(iid)

    def _text(self, tag):
        return f"{'☑' if tag in self.selected else '☐'}  {tag}"

    def _update_group(self, giid):
        name, tags = self.group_children[giid]
        n = sum(t in self.selected for t in tags)
        mark = "☑" if n == len(tags) else ("☐" if n == 0 else "▣")
        arrow = "▾" if self.tv.item(giid, "open") else "▸"
        self.tv.item(giid, text=f"{arrow}  {mark}  {name}   ({n}/{len(tags)})")

    def _update_count(self):
        n = len(self.selected & set(self.tag_map))
        hint = "" if self.export() else "   ·   no log groups (Settings)"
        self.count_var.set(f"{n} of {len(self.tag_map)} selected{hint}")

    def _sync(self, tags):
        for t in tags:
            for iid in self.tag_items.get(t, []):
                self.tv.item(iid, text=self._text(t))
        for giid in self.group_children:
            self._update_group(giid)
        self._update_count()
        self.on_change()

    def _click(self, event):
        tv = self.tv
        if tv.identify_region(event.x, event.y) not in ("tree", "cell"):
            return None
        iid = tv.identify_row(event.y)
        if not iid:
            return "break"
        if iid in self.group_children:
            box = tv.bbox(iid, "#0")
            if box and event.x - box[0] < 26:          # ▸/▾ = expand / collapse
                tv.item(iid, open=not tv.item(iid, "open"))
                self._update_group(iid)
                return "break"
            tags = self.group_children[iid][1]
            if all(t in self.selected for t in tags):
                self.selected.difference_update(tags)
            else:
                self.selected.update(tags)
        else:
            tags = [self.item_tag[iid]]
            self.selected.symmetric_difference_update(tags)
        self._sync(tags)
        return "break"

    def select_shown(self):
        self.selected.update(self.visible)
        self._sync(self.visible)

    def clear(self):
        tags = list(self.selected & set(self.tag_map))
        self.selected.difference_update(self.tag_map)
        self._sync(tags)
