"""
Tkinter desktop app to view and edit Cobblemon spawn configurations.
Compile to .exe with: pyinstaller --onefile --windowed exe.py
Made by Dopamine (@nhankio on Discord)
"""

import glob
import json
import os
import re
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from get_default_pokemons import reset, set_blank

# When frozen (--windowed), stdout/stderr are None which breaks tqdm/print.
# Redirect them to devnull so background operations don't choke.
if getattr(sys, "frozen", False):
    _devnull = open(os.devnull, "w")
    if sys.stdout is None:
        sys.stdout = _devnull
    if sys.stderr is None:
        sys.stderr = _devnull

# When frozen by PyInstaller, __file__ points to a temp dir.
# Use the exe's directory so data lands next to the .exe.
if getattr(sys, "frozen", False):
    _BASE_DIR = os.path.dirname(sys.executable)
else:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SPAWN_DIR = os.path.join(_BASE_DIR, ".default", "spawn_pool_world")

BUCKETS = ["common", "uncommon", "rare", "ultra-rare"]
SPAWN_TYPES = ["pokemon", "pokemon-herd", "npc"]
POSITION_TYPES = ["grounded", "submerged", "surface", "seafloor", "lavafloor", "fishing"]
PRESET_OPTIONS = [
    "ancient_city", "derelict", "desert_pyramid", "end_city", "foliage",
    "illager_structures", "jungle_pyramid", "lava", "mansion",
    "mansion_bedrooms", "mansion_dining", "natural", "nether_fossil",
    "nether_structures", "ocean_monument", "ocean_ruins", "pillager_outpost",
    "redstone", "ruined_portal", "saccharine_tree", "salt", "stronghold",
    "trail_ruins", "treetop", "urban", "water", "webs", "wild",
]
TIME_RANGES = [
    "", "any", "day", "night", "morning", "noon", "afternoon",
    "evening", "midnight", "predawn", "dawn", "dusk", "twilight",
]
MOON_PHASES = [
    "", "full", "new", "crescent", "gibbous", "quarter", "waxing", "waning",
]

CONDITION_BOOL_FIELDS = [
    "canSeeSky", "isRaining", "isThundering", "isSlimeChunk", "fluidIsSource",
]
CONDITION_INT_FIELDS = [
    "minSkyLight", "maxSkyLight", "minLight", "maxLight",
    "minY", "maxY", "minX", "maxX", "minZ", "maxZ",
    "minLureLevel", "maxLureLevel",
    "minHeight", "maxHeight", "minDepth", "maxDepth",
]
CONDITION_LIST_FIELDS = [
    "biomes", "structures", "neededNearbyBlocks", "neededBaseBlocks",
    "dimensions", "markers",
]
CONDITION_STRING_FIELDS = ["bait", "rodType", "rod", "fluid"]


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def load_pokemon_files():
    files = []
    for path in sorted(glob.glob(os.path.join(SPAWN_DIR, "*.json"))):
        fname = os.path.basename(path)
        match = re.match(r"(\d+)_(.+)\.json", fname)
        if match:
            dex = int(match.group(1))
            name = match.group(2).replace("_", " ").title()
            display = f"#{dex:04d} {name}"
        else:
            display = fname
        files.append((fname, display))
    return files


def load_pokemon_names():
    names = set()
    for path in glob.glob(os.path.join(SPAWN_DIR, "*.json")):
        fname = os.path.basename(path)
        match = re.match(r"\d+_(.+?)(?:_herd)?\.json", fname)
        if match:
            names.add(match.group(1))
    return sorted(names)


def load_spawn_data(filename):
    path = os.path.join(SPAWN_DIR, filename)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_spawn_data(filename, data):
    path = os.path.join(SPAWN_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
        f.write("\n")


# ---------------------------------------------------------------------------
# Scrollable frame widget
# ---------------------------------------------------------------------------

class ScrollableFrame(ttk.Frame):
    def __init__(self, parent, **kw):
        super().__init__(parent, **kw)
        self._canvas = tk.Canvas(self, highlightthickness=0)
        self._scrollbar = ttk.Scrollbar(self, orient="vertical", command=self._canvas.yview)
        self.inner = ttk.Frame(self._canvas)

        self.inner.bind("<Configure>", lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._window = self._canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self._canvas.configure(yscrollcommand=self._scrollbar.set)

        self._canvas.pack(side="left", fill="both", expand=True)
        self._scrollbar.pack(side="right", fill="y")

        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._bind_mousewheel(self._canvas)
        self._bind_mousewheel(self.inner)

    def _on_canvas_configure(self, event):
        self._canvas.itemconfigure(self._window, width=event.width)

    def _bind_mousewheel(self, widget):
        widget.bind("<MouseWheel>", self._on_mousewheel)
        widget.bind("<Button-4>", self._on_mousewheel)
        widget.bind("<Button-5>", self._on_mousewheel)

    def _on_mousewheel(self, event):
        if event.num == 4:
            self._canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self._canvas.yview_scroll(1, "units")
        else:
            self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def bind_mousewheel_recursive(self, widget):
        self._bind_mousewheel(widget)
        for child in widget.winfo_children():
            self.bind_mousewheel_recursive(child)


# ---------------------------------------------------------------------------
# Collapsible frame
# ---------------------------------------------------------------------------

class CollapsibleFrame(ttk.LabelFrame):
    def __init__(self, parent, title="", expanded=False, **kw):
        super().__init__(parent, text="", **kw)
        self._expanded = tk.BooleanVar(value=expanded)
        self._toggle_btn = ttk.Checkbutton(
            self, text=title, variable=self._expanded,
            command=self._toggle, style="Toolbutton",
        )
        self._toggle_btn.pack(fill="x", padx=2, pady=(2, 0))
        self.content = ttk.Frame(self)
        if expanded:
            self.content.pack(fill="both", expand=True, padx=4, pady=4)

    def _toggle(self):
        if self._expanded.get():
            self.content.pack(fill="both", expand=True, padx=4, pady=4)
        else:
            self.content.pack_forget()


# ---------------------------------------------------------------------------
# Multi-select listbox with checkboxes (for presets)
# ---------------------------------------------------------------------------

class ChecklistPopup:
    """A popup window with checkboxes for multi-select."""

    def __init__(self, parent, title, options, selected, callback):
        self.callback = callback
        self.top = tk.Toplevel(parent)
        self.top.title(title)
        self.top.geometry("250x400")
        self.top.transient(parent)
        self.top.grab_set()

        self.vars = {}
        frame = ScrollableFrame(self.top)
        frame.pack(fill="both", expand=True, padx=5, pady=5)
        for opt in options:
            var = tk.BooleanVar(value=opt in selected)
            self.vars[opt] = var
            ttk.Checkbutton(frame.inner, text=opt, variable=var).pack(anchor="w")

        btn_frame = ttk.Frame(self.top)
        btn_frame.pack(fill="x", padx=5, pady=5)
        ttk.Button(btn_frame, text="OK", command=self._ok).pack(side="right")
        ttk.Button(btn_frame, text="Cancel", command=self.top.destroy).pack(side="right", padx=5)

    def _ok(self):
        selected = [opt for opt, var in self.vars.items() if var.get()]
        self.callback(selected)
        self.top.destroy()


# ---------------------------------------------------------------------------
# Condition editor
# ---------------------------------------------------------------------------

class ConditionEditor(ttk.Frame):
    def __init__(self, parent, cond, **kw):
        super().__init__(parent, **kw)
        self._build(cond)

    def _build(self, cond):
        # Time range + Moon phase
        row = ttk.Frame(self)
        row.pack(fill="x", pady=2)

        ttk.Label(row, text="Time range:").pack(side="left")
        self.time_var = tk.StringVar(value=cond.get("timeRange", ""))
        ttk.Combobox(row, textvariable=self.time_var, values=TIME_RANGES,
                     state="readonly", width=12).pack(side="left", padx=(2, 10))

        ttk.Label(row, text="Moon phase:").pack(side="left")
        self.moon_var = tk.StringVar(value=str(cond.get("moonPhase", "")))
        ttk.Combobox(row, textvariable=self.moon_var, values=MOON_PHASES,
                     state="readonly", width=12).pack(side="left", padx=2)

        # Bool fields
        self.bool_vars = {}
        bool_frame = ttk.Frame(self)
        bool_frame.pack(fill="x", pady=2)
        for i, field in enumerate(CONDITION_BOOL_FIELDS):
            var = tk.BooleanVar(value=cond.get(field, False))
            self.bool_vars[field] = var
            ttk.Checkbutton(bool_frame, text=field, variable=var).grid(
                row=i // 3, column=i % 3, sticky="w", padx=4, pady=1)

        # Int fields
        self.int_vars = {}
        int_frame = ttk.LabelFrame(self, text="Numeric fields")
        int_frame.pack(fill="x", pady=2)
        for i, field in enumerate(CONDITION_INT_FIELDS):
            r, c = divmod(i, 3)
            ttk.Label(int_frame, text=field + ":").grid(row=r, column=c * 2, sticky="e", padx=(4, 2), pady=1)
            current = cond.get(field)
            var = tk.StringVar(value=str(current) if current is not None else "")
            self.int_vars[field] = (var, current is not None)
            ttk.Entry(int_frame, textvariable=var, width=8).grid(row=r, column=c * 2 + 1, sticky="w", padx=2, pady=1)

        # List fields
        self.list_texts = {}
        for field in CONDITION_LIST_FIELDS:
            lf = ttk.LabelFrame(self, text=f"{field} (one per line)")
            lf.pack(fill="x", pady=2)
            txt = tk.Text(lf, height=3, width=50)
            txt.pack(fill="x", padx=4, pady=2)
            current = cond.get(field, [])
            if current:
                txt.insert("1.0", "\n".join(current))
            self.list_texts[field] = txt

        # String fields
        self.str_vars = {}
        str_frame = ttk.Frame(self)
        str_frame.pack(fill="x", pady=2)
        for i, field in enumerate(CONDITION_STRING_FIELDS):
            ttk.Label(str_frame, text=field + ":").grid(row=0, column=i * 2, sticky="e", padx=(4, 2))
            var = tk.StringVar(value=cond.get(field, ""))
            self.str_vars[field] = var
            ttk.Entry(str_frame, textvariable=var, width=15).grid(row=0, column=i * 2 + 1, padx=2)

    def get_data(self):
        result = {}
        time_val = self.time_var.get()
        if time_val:
            result["timeRange"] = time_val
        moon_val = self.moon_var.get()
        if moon_val:
            result["moonPhase"] = moon_val

        for field, var in self.bool_vars.items():
            if var.get():
                result[field] = True

        for field, (var, had_value) in self.int_vars.items():
            raw = var.get().strip()
            if raw:
                try:
                    val = int(raw)
                    if had_value or val != 0:
                        result[field] = val
                except ValueError:
                    pass

        for field, txt in self.list_texts.items():
            content = txt.get("1.0", "end").strip()
            entries = [line.strip() for line in content.split("\n") if line.strip()]
            if entries:
                result[field] = entries

        for field, var in self.str_vars.items():
            val = var.get().strip()
            if val:
                result[field] = val

        return result


# ---------------------------------------------------------------------------
# Weight multiplier editor
# ---------------------------------------------------------------------------

class WeightMultiplierEditor(ttk.Frame):
    def __init__(self, parent, wm, index, delete_callback, **kw):
        super().__init__(parent, **kw)
        self.delete_callback = delete_callback
        self.index = index

        header = ttk.Frame(self)
        header.pack(fill="x", pady=2)
        ttk.Label(header, text=f"Multiplier {index + 1}:").pack(side="left")
        self.mult_var = tk.StringVar(value=str(wm.get("multiplier", 1.0)))
        ttk.Entry(header, textvariable=self.mult_var, width=10).pack(side="left", padx=4)
        ttk.Button(header, text="Delete", width=6, command=lambda: self.delete_callback(self)).pack(side="right")

        coll = CollapsibleFrame(self, title="Multiplier condition", expanded=True)
        coll.pack(fill="x", pady=2)
        self.cond_editor = ConditionEditor(coll.content, wm.get("condition", {}))
        self.cond_editor.pack(fill="x")

    def get_data(self):
        try:
            mult = float(self.mult_var.get())
        except ValueError:
            mult = 1.0
        return {"multiplier": mult, "condition": self.cond_editor.get_data()}


# ---------------------------------------------------------------------------
# Herd pokemon editor
# ---------------------------------------------------------------------------

class HerdPokemonEditor(ttk.Frame):
    def __init__(self, parent, hp, index, pokemon_names, delete_callback, **kw):
        super().__init__(parent, **kw)
        self.delete_callback = delete_callback
        self.index = index

        header = ttk.Frame(self)
        header.pack(fill="x", pady=2)
        ttk.Label(header, text=f"Herd member {index + 1}").pack(side="left")
        ttk.Button(header, text="Delete", width=6, command=lambda: self.delete_callback(self)).pack(side="right")

        row1 = ttk.Frame(self)
        row1.pack(fill="x", pady=2)

        ttk.Label(row1, text="Pokemon:").pack(side="left")
        self.pokemon_var = tk.StringVar(value=hp.get("pokemon", ""))
        ttk.Combobox(row1, textvariable=self.pokemon_var, values=pokemon_names,
                     width=20).pack(side="left", padx=(2, 10))

        ttk.Label(row1, text="Level range:").pack(side="left")
        self.level_var = tk.StringVar(value=hp.get("levelRange", ""))
        ttk.Entry(row1, textvariable=self.level_var, width=10).pack(side="left", padx=2)

        row2 = ttk.Frame(self)
        row2.pack(fill="x", pady=2)

        ttk.Label(row2, text="Weight:").pack(side="left")
        self.weight_var = tk.StringVar(value=str(hp.get("weight", 1)))
        ttk.Entry(row2, textvariable=self.weight_var, width=8).pack(side="left", padx=(2, 10))

        self.leader_var = tk.BooleanVar(value=hp.get("isLeader", False))
        ttk.Checkbutton(row2, text="Is leader", variable=self.leader_var).pack(side="left", padx=10)

        ttk.Label(row2, text="Max times (0=unlimited):").pack(side="left")
        self.max_times_var = tk.StringVar(value=str(hp.get("maxTimes", 0) or 0))
        ttk.Entry(row2, textvariable=self.max_times_var, width=6).pack(side="left", padx=2)

        row3 = ttk.Frame(self)
        row3.pack(fill="x", pady=2)
        ttk.Label(row3, text="Level range offset:").pack(side="left")
        self.offset_var = tk.StringVar(value=hp.get("levelRangeOffset", ""))
        ttk.Entry(row3, textvariable=self.offset_var, width=10).pack(side="left", padx=2)

    def get_data(self):
        result = {
            "pokemon": self.pokemon_var.get(),
            "levelRange": self.level_var.get(),
        }
        try:
            result["weight"] = float(self.weight_var.get())
        except ValueError:
            result["weight"] = 1.0
        result["isLeader"] = self.leader_var.get()
        try:
            mt = int(self.max_times_var.get())
            if mt > 0:
                result["maxTimes"] = mt
        except ValueError:
            pass
        offset = self.offset_var.get().strip()
        if offset:
            result["levelRangeOffset"] = offset
        return result


# ---------------------------------------------------------------------------
# Drops editor
# ---------------------------------------------------------------------------

class DropsEditor(ttk.Frame):
    def __init__(self, parent, drops, **kw):
        super().__init__(parent, **kw)
        self.entries_frame = None
        self.entry_widgets = []

        has_drops = drops is not None
        self.enabled_var = tk.BooleanVar(value=has_drops)
        ttk.Checkbutton(self, text="Enable drops", variable=self.enabled_var,
                        command=self._toggle).pack(anchor="w")

        self.content = ttk.Frame(self)

        ttk.Label(self.content, text="Drop amount:").pack(side="top", anchor="w")
        self.amount_var = tk.StringVar(value=str((drops or {}).get("amount", 1)))
        ttk.Entry(self.content, textvariable=self.amount_var, width=6).pack(anchor="w", pady=2)

        self.entries_frame = ttk.Frame(self.content)
        self.entries_frame.pack(fill="x", pady=2)

        ttk.Button(self.content, text="Add drop entry", command=self._add_entry).pack(anchor="w", pady=2)

        if has_drops:
            self.content.pack(fill="x", padx=4, pady=4)
            for entry in drops.get("entries", []):
                self._add_entry(entry)

    def _toggle(self):
        if self.enabled_var.get():
            self.content.pack(fill="x", padx=4, pady=4)
        else:
            self.content.pack_forget()

    def _add_entry(self, entry=None):
        if entry is None:
            entry = {"item": "", "percentage": 0.0}
        row = ttk.Frame(self.entries_frame)
        row.pack(fill="x", pady=1)

        ttk.Label(row, text="Item:").pack(side="left")
        item_var = tk.StringVar(value=entry.get("item", ""))
        ttk.Entry(row, textvariable=item_var, width=25).pack(side="left", padx=2)

        ttk.Label(row, text="Qty range:").pack(side="left")
        qr_var = tk.StringVar(value=entry.get("quantityRange", ""))
        ttk.Entry(row, textvariable=qr_var, width=8).pack(side="left", padx=2)

        ttk.Label(row, text="% chance:").pack(side="left")
        pct_var = tk.StringVar(value=str(entry.get("percentage", 0.0)))
        ttk.Entry(row, textvariable=pct_var, width=8).pack(side="left", padx=2)

        widget_data = {"row": row, "item": item_var, "qr": qr_var, "pct": pct_var}
        self.entry_widgets.append(widget_data)
        ttk.Button(row, text="X", width=2,
                   command=lambda w=widget_data: self._delete_entry(w)).pack(side="right")

    def _delete_entry(self, widget_data):
        widget_data["row"].destroy()
        self.entry_widgets.remove(widget_data)

    def get_data(self):
        if not self.enabled_var.get():
            return None
        try:
            amount = int(self.amount_var.get())
        except ValueError:
            amount = 1
        entries = []
        for wd in self.entry_widgets:
            item = wd["item"].get().strip()
            if not item:
                continue
            e = {"item": item}
            qr = wd["qr"].get().strip()
            if qr:
                e["quantityRange"] = qr
            try:
                pct = float(wd["pct"].get())
                if pct > 0:
                    e["percentage"] = pct
            except ValueError:
                pass
            entries.append(e)
        return {"amount": amount, "entries": entries}


# ---------------------------------------------------------------------------
# Single spawn editor
# ---------------------------------------------------------------------------

class SpawnEditor(ttk.LabelFrame):
    def __init__(self, parent, spawn, index, pokemon_names, delete_callback, **kw):
        super().__init__(parent, text=f"Spawn: {spawn.get('id', f'spawn-{index}')}", **kw)
        self.delete_callback = delete_callback
        self.index = index
        self.pokemon_names = pokemon_names
        self.herd_editors = []
        self.wm_editors = []
        self._build(spawn)

    def _build(self, spawn):
        # Delete button
        top = ttk.Frame(self)
        top.pack(fill="x", padx=4, pady=2)
        self.delete_var = tk.BooleanVar(value=False)
        ttk.Button(top, text="Delete this spawn", command=lambda: self.delete_callback(self)).pack(side="right")

        # ID + Type
        row = ttk.Frame(self)
        row.pack(fill="x", padx=4, pady=2)
        ttk.Label(row, text="ID:").pack(side="left")
        self.id_var = tk.StringVar(value=spawn.get("id", ""))
        ttk.Entry(row, textvariable=self.id_var, width=25).pack(side="left", padx=(2, 10))

        ttk.Label(row, text="Type:").pack(side="left")
        self.type_var = tk.StringVar(value=spawn.get("type", "pokemon"))
        type_cb = ttk.Combobox(row, textvariable=self.type_var, values=SPAWN_TYPES,
                               state="readonly", width=14)
        type_cb.pack(side="left", padx=2)
        type_cb.bind("<<ComboboxSelected>>", self._on_type_change)

        # Pokemon (non-herd only)
        self.pokemon_frame = ttk.Frame(self)
        self.pokemon_frame.pack(fill="x", padx=4, pady=2)
        ttk.Label(self.pokemon_frame, text="Pokemon:").pack(side="left")
        self.pokemon_var = tk.StringVar(value=spawn.get("pokemon", ""))
        ttk.Entry(self.pokemon_frame, textvariable=self.pokemon_var, width=25).pack(side="left", padx=2)

        # Presets + Position + Bucket
        row2 = ttk.Frame(self)
        row2.pack(fill="x", padx=4, pady=2)

        ttk.Label(row2, text="Presets:").pack(side="left")
        self.presets_list = list(spawn.get("presets", []))
        self.presets_label = ttk.Label(row2, text=", ".join(self.presets_list) or "(none)")
        self.presets_label.pack(side="left", padx=2)
        ttk.Button(row2, text="Edit", width=4,
                   command=self._edit_presets).pack(side="left", padx=2)

        ttk.Label(row2, text="Position:").pack(side="left", padx=(10, 0))
        pos = spawn.get("spawnablePositionType", "grounded")
        self.pos_var = tk.StringVar(value=pos)
        ttk.Combobox(row2, textvariable=self.pos_var, values=POSITION_TYPES,
                     state="readonly", width=10).pack(side="left", padx=2)

        ttk.Label(row2, text="Bucket:").pack(side="left", padx=(10, 0))
        bucket = spawn.get("bucket", "common")
        self.bucket_var = tk.StringVar(value=bucket)
        ttk.Combobox(row2, textvariable=self.bucket_var, values=BUCKETS,
                     state="readonly", width=10).pack(side="left", padx=2)

        # Level + Weight
        row3 = ttk.Frame(self)
        row3.pack(fill="x", padx=4, pady=2)

        is_herd = self.type_var.get() == "pokemon-herd"
        level_field = "levelRange" if is_herd else "level"
        ttk.Label(row3, text="Level range:").pack(side="left")
        self.level_var = tk.StringVar(value=spawn.get(level_field, spawn.get("level", "")))
        ttk.Entry(row3, textvariable=self.level_var, width=10).pack(side="left", padx=(2, 10))

        ttk.Label(row3, text="Weight:").pack(side="left")
        self.weight_var = tk.StringVar(value=str(spawn.get("weight", 1.0)))
        ttk.Entry(row3, textvariable=self.weight_var, width=10).pack(side="left", padx=2)

        # Herd-specific
        self.herd_frame = ttk.LabelFrame(self, text="Herd settings")

        herd_top = ttk.Frame(self.herd_frame)
        herd_top.pack(fill="x", padx=4, pady=2)
        ttk.Label(herd_top, text="Max herd size:").pack(side="left")
        self.herd_size_var = tk.StringVar(value=str(spawn.get("maxHerdSize", 5)))
        ttk.Entry(herd_top, textvariable=self.herd_size_var, width=6).pack(side="left", padx=(2, 10))
        ttk.Label(herd_top, text="Min dist between spawns:").pack(side="left")
        self.herd_dist_var = tk.StringVar(value=str(spawn.get("minDistanceBetweenSpawns", 1.5)))
        ttk.Entry(herd_top, textvariable=self.herd_dist_var, width=8).pack(side="left", padx=2)

        self.herd_members_frame = ttk.Frame(self.herd_frame)
        self.herd_members_frame.pack(fill="x", padx=4, pady=2)
        ttk.Button(self.herd_frame, text="Add herd member",
                   command=self._add_herd_member).pack(anchor="w", padx=4, pady=2)

        if is_herd:
            self.herd_frame.pack(fill="x", padx=4, pady=2)
            self.pokemon_frame.pack_forget()
            for hp in spawn.get("herdablePokemon", []):
                self._add_herd_member(hp)

        # Weight multipliers
        wm_coll = CollapsibleFrame(self, title="Weight multipliers", expanded=False)
        wm_coll.pack(fill="x", padx=4, pady=2)
        self.wm_frame = wm_coll.content

        wm_single = spawn.get("weightMultiplier")
        wms = spawn.get("weightMultipliers", [])
        if wm_single and not wms:
            wms = [wm_single]
        for wm in wms:
            self._add_weight_multiplier(wm)
        ttk.Button(self.wm_frame, text="Add multiplier",
                   command=self._add_weight_multiplier).pack(anchor="w", pady=2)

        # Condition
        cond_coll = CollapsibleFrame(self, title="Condition", expanded=False)
        cond_coll.pack(fill="x", padx=4, pady=2)
        self.cond_editor = ConditionEditor(cond_coll.content, spawn.get("condition", {}))
        self.cond_editor.pack(fill="x")

        # Anticondition
        anti_coll = CollapsibleFrame(self, title="Anticondition", expanded=False)
        anti_coll.pack(fill="x", padx=4, pady=2)
        self.anti_editor = ConditionEditor(anti_coll.content, spawn.get("anticondition", {}))
        self.anti_editor.pack(fill="x")

        # Drops
        drops_coll = CollapsibleFrame(self, title="Drops", expanded=False)
        drops_coll.pack(fill="x", padx=4, pady=2)
        self.drops_editor = DropsEditor(drops_coll.content, spawn.get("drops"))
        self.drops_editor.pack(fill="x")

    def _on_type_change(self, _event=None):
        is_herd = self.type_var.get() == "pokemon-herd"
        if is_herd:
            self.pokemon_frame.pack_forget()
            self.herd_frame.pack(fill="x", padx=4, pady=2)
        else:
            self.herd_frame.pack_forget()
            self.pokemon_frame.pack(fill="x", padx=4, pady=2)

    def _edit_presets(self):
        all_opts = list(PRESET_OPTIONS) + [p for p in self.presets_list if p not in PRESET_OPTIONS]
        ChecklistPopup(self, "Select presets", all_opts, self.presets_list, self._set_presets)

    def _set_presets(self, selected):
        self.presets_list = selected
        self.presets_label.configure(text=", ".join(selected) or "(none)")

    def _add_herd_member(self, hp=None):
        if hp is None:
            hp = {"pokemon": "", "levelRange": "1-10", "weight": 1}
        idx = len(self.herd_editors)
        editor = HerdPokemonEditor(self.herd_members_frame, hp, idx,
                                   self.pokemon_names, self._delete_herd_member)
        editor.pack(fill="x", pady=2)
        self.herd_editors.append(editor)

    def _delete_herd_member(self, editor):
        editor.destroy()
        self.herd_editors.remove(editor)

    def _add_weight_multiplier(self, wm=None):
        if wm is None:
            wm = {"multiplier": 1.0, "condition": {}}
        idx = len(self.wm_editors)
        editor = WeightMultiplierEditor(self.wm_frame, wm, idx, self._delete_wm)
        editor.pack(fill="x", pady=2)
        self.wm_editors.append(editor)

    def _delete_wm(self, editor):
        editor.destroy()
        self.wm_editors.remove(editor)

    def get_data(self):
        result = {
            "id": self.id_var.get(),
            "type": self.type_var.get(),
        }

        is_herd = result["type"] == "pokemon-herd"
        if not is_herd:
            result["pokemon"] = self.pokemon_var.get()

        if self.presets_list:
            result["presets"] = list(self.presets_list)

        result["spawnablePositionType"] = self.pos_var.get()
        result["bucket"] = self.bucket_var.get()

        level_key = "levelRange" if is_herd else "level"
        result[level_key] = self.level_var.get()

        try:
            result["weight"] = float(self.weight_var.get())
        except ValueError:
            result["weight"] = 1.0

        if is_herd:
            try:
                result["maxHerdSize"] = int(self.herd_size_var.get())
            except ValueError:
                result["maxHerdSize"] = 5
            try:
                result["minDistanceBetweenSpawns"] = float(self.herd_dist_var.get())
            except ValueError:
                result["minDistanceBetweenSpawns"] = 1.5
            result["herdablePokemon"] = [e.get_data() for e in self.herd_editors]

        wm_data = [e.get_data() for e in self.wm_editors]
        if wm_data:
            result["weightMultipliers"] = wm_data

        cond = self.cond_editor.get_data()
        if cond:
            result["condition"] = cond

        anti = self.anti_editor.get_data()
        if anti:
            result["anticondition"] = anti

        drops = self.drops_editor.get_data()
        if drops is not None:
            result["drops"] = drops

        return result


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

class CobblemonSpawnEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("Cobblemon Spawn Editor")
        self.root.geometry("1200x800")
        self.root.minsize(900, 600)

        self.files = []
        self.current_file = None
        self.spawn_editors = []
        self.pokemon_names = []

        self._build_ui()
        self._ensure_data()

    def _build_ui(self):
        # Left sidebar (fixed width, never collapses)
        sidebar = ttk.Frame(self.root, width=280)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        ttk.Label(sidebar, text="Pokemon", font=("", 12, "bold")).pack(padx=8, pady=(8, 4))

        ttk.Label(sidebar, text="Search:").pack(anchor="w", padx=8)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._filter_list())
        ttk.Entry(sidebar, textvariable=self.search_var).pack(fill="x", padx=8, pady=2)

        list_frame = ttk.Frame(sidebar)
        list_frame.pack(fill="both", expand=True, padx=8, pady=4)
        self.listbox = tk.Listbox(list_frame, exportselection=False)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scrollbar.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

        btn_frame = ttk.Frame(sidebar)
        btn_frame.pack(fill="x", padx=8, pady=8)
        ttk.Button(btn_frame, text="Restore to default",
                   command=self._restore_default).pack(fill="x", pady=2)
        ttk.Button(btn_frame, text="Set all to blank",
                   command=self._set_blank).pack(fill="x", pady=2)

        # Vertical separator
        ttk.Separator(self.root, orient="vertical").pack(side="left", fill="y")

        # Right editor area
        self.editor_pane = ttk.Frame(self.root)
        self.editor_pane.pack(side="left", fill="both", expand=True)

        # Header
        self.header_var = tk.StringVar(value="Select a Pokemon")
        ttk.Label(self.editor_pane, textvariable=self.header_var,
                  font=("", 14, "bold")).pack(padx=8, pady=8, anchor="w")

        # Top-level fields frame
        self.top_fields_frame = ttk.Frame(self.editor_pane)
        self.top_fields_frame.pack(fill="x", padx=8)

        # Scrollable spawns area
        self.scroll_frame = ScrollableFrame(self.editor_pane)
        self.scroll_frame.pack(fill="both", expand=True, padx=8, pady=4)

        # Bottom buttons
        bottom = ttk.Frame(self.editor_pane)
        bottom.pack(fill="x", padx=8, pady=8)
        ttk.Button(bottom, text="Add new spawn", command=self._add_spawn).pack(side="left", padx=4)
        ttk.Button(bottom, text="Save", command=self._save).pack(side="right", padx=4)

    def _ensure_data(self):
        # Ensure CWD matches the base directory so get_default_pokemons
        # saves data next to the exe / script, not in a temp folder.
        os.chdir(_BASE_DIR)
        if not os.path.isdir(SPAWN_DIR):
            self.header_var.set("Downloading spawn data...")
            self.root.update()
            self._run_background("Downloading...", reset, self._load_files)
        else:
            self._load_files()

    def _run_background(self, message, func, callback):
        progress = tk.Toplevel(self.root)
        progress.title("Please wait")
        progress.geometry("300x80")
        progress.transient(self.root)
        progress.grab_set()
        ttk.Label(progress, text=message).pack(pady=10)
        bar = ttk.Progressbar(progress, mode="indeterminate")
        bar.pack(fill="x", padx=20, pady=5)
        bar.start()

        def worker():
            try:
                func()
            finally:
                self.root.after(0, lambda: _finish(progress))

        def _finish(p):
            p.destroy()
            callback()

        threading.Thread(target=worker, daemon=True).start()

    def _load_files(self):
        self.files = load_pokemon_files()
        self.pokemon_names = load_pokemon_names()
        self._filter_list()

    def _filter_list(self):
        search = self.search_var.get().lower()
        self.listbox.delete(0, "end")
        self._filtered = []
        for fname, display in self.files:
            if not search or search in display.lower() or search in fname.lower():
                self.listbox.insert("end", display)
                self._filtered.append((fname, display))

    def _on_select(self, _event=None):
        sel = self.listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        fname, display = self._filtered[idx]
        if fname == self.current_file:
            return
        self.current_file = fname
        self._load_editor(fname, display)

    def _load_editor(self, filename, display):
        self.header_var.set(display)
        self.spawn_editors.clear()

        # Clear top fields
        for w in self.top_fields_frame.winfo_children():
            w.destroy()

        # Clear spawns area
        for w in self.scroll_frame.inner.winfo_children():
            w.destroy()

        data = load_spawn_data(filename)
        self._current_data = data

        # Top-level fields
        tf = self.top_fields_frame
        row = ttk.Frame(tf)
        row.pack(fill="x", pady=2)

        self.enabled_var = tk.BooleanVar(value=data.get("enabled", True))
        ttk.Checkbutton(row, text="Enabled", variable=self.enabled_var).pack(side="left", padx=(0, 20))

        ttk.Label(row, text="Needed installed mods:").pack(side="left")
        self.installed_var = tk.StringVar(value=", ".join(data.get("neededInstalledMods", [])))
        ttk.Entry(row, textvariable=self.installed_var, width=30).pack(side="left", padx=(2, 10))

        ttk.Label(row, text="Needed uninstalled mods:").pack(side="left")
        self.uninstalled_var = tk.StringVar(value=", ".join(data.get("neededUninstalledMods", [])))
        ttk.Entry(row, textvariable=self.uninstalled_var, width=30).pack(side="left", padx=2)

        ttk.Separator(tf, orient="horizontal").pack(fill="x", pady=4)

        # Spawn entries
        for i, spawn in enumerate(data.get("spawns", [])):
            editor = SpawnEditor(self.scroll_frame.inner, spawn, i,
                                 self.pokemon_names, self._delete_spawn)
            editor.pack(fill="x", pady=4, padx=4)
            self.spawn_editors.append(editor)

        self.root.after(50, lambda: self.scroll_frame.bind_mousewheel_recursive(self.scroll_frame.inner))

    def _delete_spawn(self, editor):
        editor.destroy()
        self.spawn_editors.remove(editor)

    def _add_spawn(self):
        if not self.current_file:
            return
        match = re.match(r"\d+_(.+)\.json", self.current_file)
        poke_name = match.group(1) if match else ""
        new_id = f"{poke_name}-{len(self.spawn_editors) + 1}"
        new_spawn = {
            "id": new_id,
            "pokemon": poke_name,
            "presets": ["natural"],
            "type": "pokemon",
            "spawnablePositionType": "grounded",
            "bucket": "common",
            "level": "1-50",
            "weight": 1.0,
            "condition": {},
        }
        editor = SpawnEditor(self.scroll_frame.inner, new_spawn, len(self.spawn_editors),
                             self.pokemon_names, self._delete_spawn)
        editor.pack(fill="x", pady=4, padx=4)
        self.spawn_editors.append(editor)
        self.root.after(50, lambda: self.scroll_frame.bind_mousewheel_recursive(editor))

    def _collect_data(self):
        data = {
            "enabled": self.enabled_var.get(),
            "neededInstalledMods": [m.strip() for m in self.installed_var.get().split(",") if m.strip()],
            "neededUninstalledMods": [m.strip() for m in self.uninstalled_var.get().split(",") if m.strip()],
            "spawns": [e.get_data() for e in self.spawn_editors],
        }
        return data

    def _save(self):
        if not self.current_file:
            return
        data = self._collect_data()
        save_spawn_data(self.current_file, data)
        messagebox.showinfo("Saved", f"Saved {self.current_file}")

    def _restore_default(self):
        if not messagebox.askyesno("Confirm", "Restore all files to default? This will re-download everything."):
            return
        self.current_file = None
        self._run_background("Restoring defaults...", reset, self._load_files)

    def _set_blank(self):
        if not messagebox.askyesno("Confirm", "Set ALL spawn files to blank?"):
            return
        self.current_file = None
        self._run_background("Setting blank...", set_blank, self._load_files)


def main():
    root = tk.Tk()
    CobblemonSpawnEditor(root)
    root.mainloop()


if __name__ == "__main__":
    main()