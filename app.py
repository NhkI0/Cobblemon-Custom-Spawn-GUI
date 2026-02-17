"""
Streamlit app to view and edit Cobblemon spawn configurations.
Made by Dopamine (@nhankio on Discord)
"""

import glob
import json
import os
import re

import streamlit as st

from get_default_pokemons import reset

SPAWN_DIR = os.path.join(os.path.dirname(__file__), ".default", "spawn_pool_world")

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


def load_pokemon_files():
    """Return sorted list of (filename, display_name) tuples."""
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


@st.cache_data
def load_pokemon_names():
    """Return sorted list of valid Pokémon names from spawn files."""
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


def _clear_editor_state(file_key):
    """Clear all widget state for a Pokémon so widgets reinitialize from file."""
    KEEP_KEYS = {"search", "pokemon_select"}
    for k in [k for k in st.session_state if k not in KEEP_KEYS]:
        if k.startswith(file_key) or k == "_prev_file":
            del st.session_state[k]


def render_condition(cond, key_prefix):
    """Render editors for a condition/anticondition dict. Returns updated dict."""
    result = {}

    cols = st.columns(2)
    with cols[0]:
        current_time = cond.get("timeRange", "")
        time_val = st.selectbox(
            "Time range", TIME_RANGES,
            index=TIME_RANGES.index(current_time) if current_time in TIME_RANGES else 0,
            key=f"{key_prefix}_timeRange",
        )
        if time_val:
            result["timeRange"] = time_val
    with cols[1]:
        current_moon = str(cond.get("moonPhase", ""))
        moon_val = st.selectbox(
            "Moon phase", MOON_PHASES,
            index=MOON_PHASES.index(current_moon) if current_moon in MOON_PHASES else 0,
            key=f"{key_prefix}_moonPhase",
        )
        if moon_val:
            result["moonPhase"] = moon_val

    cols = st.columns(3)
    for i, field in enumerate(CONDITION_BOOL_FIELDS):
        with cols[i % 3]:
            val = st.checkbox(field, value=cond.get(field, False), key=f"{key_prefix}_{field}")
            if val:
                result[field] = val

    cols = st.columns(3)
    for i, field in enumerate(CONDITION_INT_FIELDS):
        with cols[i % 3]:
            current = cond.get(field)
            val = st.number_input(
                field, value=current if current is not None else 0,
                step=1, key=f"{key_prefix}_{field}",
            )
            int_val = int(val)
            if current is not None or int_val != 0:
                result[field] = int_val

    for field in CONDITION_LIST_FIELDS:
        current = cond.get(field, [])
        val = st.text_area(
            f"{field} (one per line)",
            value="\n".join(current),
            key=f"{key_prefix}_{field}",
        )
        entries = [line.strip() for line in val.split("\n") if line.strip()]
        if entries:
            result[field] = entries

    str_cols = st.columns(2)
    for i, field in enumerate(CONDITION_STRING_FIELDS):
        with str_cols[i % 2]:
            current = cond.get(field, "")
            val = st.text_input(field, value=current, key=f"{key_prefix}_{field}")
            if val:
                result[field] = val

    return result


def render_weight_multiplier(wm, key_prefix):
    """Render editor for a single weight multiplier. Returns updated dict."""
    result = {"multiplier": st.number_input(
        "Multiplier", value=float(wm.get("multiplier", 1.0)),
        step=0.1, format="%.2f", key=f"{key_prefix}_mult",
    )}
    with st.expander("Multiplier condition", expanded=True):
        result["condition"] = render_condition(wm.get("condition", {}), f"{key_prefix}_mc")
    return result


def render_herd_pokemon(hp, key_prefix):
    """Render editor for a single herdable pokemon entry."""
    result = {}
    names = load_pokemon_names()
    cols = st.columns(2)
    with cols[0]:
        current = hp.get("pokemon", "")
        idx = names.index(current) if current in names else 0
        result["pokemon"] = st.selectbox("Pokemon", names, index=idx, key=f"{key_prefix}_poke")
    with cols[1]:
        result["levelRange"] = st.text_input("Level range", value=hp.get("levelRange", ""), key=f"{key_prefix}_lr")

    cols = st.columns(3)
    with cols[0]:
        result["weight"] = st.number_input("Weight", value=float(hp.get("weight", 1)), step=0.1, format="%.2f",
                                           key=f"{key_prefix}_w")
    with cols[1]:
        result["isLeader"] = st.checkbox("Is leader", value=hp.get("isLeader", False), key=f"{key_prefix}_leader")
    with cols[2]:
        max_times = hp.get("maxTimes")
        mt = st.number_input("Max times (0 = unlimited)", value=int(max_times) if max_times else 0, step=1,
                             key=f"{key_prefix}_mt")
        if mt > 0:
            result["maxTimes"] = mt

    lro = hp.get("levelRangeOffset", "")
    offset = st.text_input("Level range offset", value=lro, key=f"{key_prefix}_lro")
    if offset:
        result["levelRangeOffset"] = offset

    return result


def render_drops(drops, key_prefix):
    """Render editor for spawn drops. Returns updated dict or None."""
    has_drops = drops is not None
    if not st.checkbox("Enable drops", value=has_drops, key=f"{key_prefix}_has_drops"):
        return None

    if drops is None:
        drops = {"amount": 1, "entries": []}

    # Track entry count in session state so adds persist across reruns
    count_key = f"{key_prefix}_entry_count"
    file_entries = drops.get("entries", [])
    if count_key not in st.session_state:
        st.session_state[count_key] = len(file_entries)

    result = {"amount": int(st.number_input(
        "Drop amount", value=int(drops.get("amount", 1)),
        min_value=1, step=1, key=f"{key_prefix}_amount",
    ))}

    updated_entries = []
    to_delete = []
    n = st.session_state[count_key]

    for ei in range(n):
        entry = file_entries[ei] if ei < len(file_entries) else {"item": "", "percentage": 0.0}
        ek = f"{key_prefix}_entry{ei}"
        cols = st.columns([3, 2, 2, 1])
        with cols[0]:
            item = st.text_input("Item", value=entry.get("item", ""), key=f"{ek}_item")
        with cols[1]:
            qr = st.text_input("Qty range", value=entry.get("quantityRange", ""), key=f"{ek}_qr")
        with cols[2]:
            pct = st.number_input("% chance", value=float(entry.get("percentage", 0)), step=0.5,
                                  format="%.1f", key=f"{ek}_pct")
        with cols[3]:
            if st.checkbox("Del", key=f"{ek}_del"):
                to_delete.append(ei)
                continue
        if item:
            e = {"item": item}
            if qr:
                e["quantityRange"] = qr
            if pct > 0:
                e["percentage"] = pct
            updated_entries.append(e)

    if to_delete:
        st.session_state[count_key] -= len(to_delete)
        for ei in to_delete:
            for suffix in ("_item", "_qr", "_pct", "_del"):
                st.session_state.pop(f"{key_prefix}_entry{ei}{suffix}", None)
        st.rerun()

    if st.button("Add drop entry", key=f"{key_prefix}_add_entry"):
        st.session_state[count_key] += 1
        st.rerun()

    result["entries"] = updated_entries
    return result


def render_spawn(spawn, idx, key_prefix):
    """Render the full editor for one spawn entry. Returns (updated_dict, delete)."""
    col_header, col_del = st.columns([5, 1])
    with col_header:
        st.subheader(f"Spawn: {spawn.get('id', f'spawn-{idx}')}")
    with col_del:
        delete = st.checkbox("Delete", key=f"{key_prefix}_delete")

    if delete:
        return None, True

    result = {}

    # Core fields
    cols = st.columns(2)
    with cols[0]:
        result["id"] = st.text_input("ID", value=spawn.get("id", ""), key=f"{key_prefix}_id")
    with cols[1]:
        spawn_type = spawn.get("type", "pokemon")
        result["type"] = st.selectbox(
            "Type", SPAWN_TYPES,
            index=SPAWN_TYPES.index(spawn_type) if spawn_type in SPAWN_TYPES else 0,
            key=f"{key_prefix}_type",
        )

    is_herd = result["type"] == "pokemon-herd"

    if not is_herd:
        result["pokemon"] = st.text_input("Pokemon", value=spawn.get("pokemon", ""), key=f"{key_prefix}_pokemon")

    cols = st.columns(3)
    with cols[0]:
        presets = spawn.get("presets", [])
        preset_opts = list(PRESET_OPTIONS) + [p for p in presets if p not in PRESET_OPTIONS]
        result["presets"] = st.multiselect("Presets", preset_opts, default=presets, key=f"{key_prefix}_presets")
    with cols[1]:
        pos = spawn.get("spawnablePositionType", "grounded")
        result["spawnablePositionType"] = st.selectbox(
            "Position type", POSITION_TYPES,
            index=POSITION_TYPES.index(pos) if pos in POSITION_TYPES else 0,
            key=f"{key_prefix}_pos",
        )
    with cols[2]:
        bucket = spawn.get("bucket", "common")
        result["bucket"] = st.selectbox(
            "Bucket", BUCKETS,
            index=BUCKETS.index(bucket) if bucket in BUCKETS else 0,
            key=f"{key_prefix}_bucket",
        )

    cols = st.columns(2)
    with cols[0]:
        level_field = "levelRange" if is_herd else "level"
        result[level_field] = st.text_input(
            "Level range", value=spawn.get(level_field, spawn.get("level", "")),
            key=f"{key_prefix}_level",
        )
    with cols[1]:
        result["weight"] = st.number_input(
            "Weight", value=float(spawn.get("weight", 1.0)),
            step=0.1, format="%.3f", key=f"{key_prefix}_weight",
        )

    # Herd-specific fields
    if is_herd:
        cols = st.columns(2)
        with cols[0]:
            result["maxHerdSize"] = int(st.number_input(
                "Max herd size", value=int(spawn.get("maxHerdSize", 5)),
                min_value=1, step=1, key=f"{key_prefix}_herdsize",
            ))
        with cols[1]:
            result["minDistanceBetweenSpawns"] = st.number_input(
                "Min distance between spawns",
                value=float(spawn.get("minDistanceBetweenSpawns", 1.5)),
                step=0.1, format="%.1f", key=f"{key_prefix}_herddist",
            )

        st.markdown("**Herdable Pokemon**")
        herd_list = spawn.get("herdablePokemon", [])
        herd_count_key = f"{key_prefix}_herd_count"
        if herd_count_key not in st.session_state:
            st.session_state[herd_count_key] = len(herd_list)

        updated_herd = []
        to_delete_herd = []
        n_herd = st.session_state[herd_count_key]

        for hi in range(n_herd):
            hp = herd_list[hi] if hi < len(herd_list) else {"pokemon": "", "levelRange": "1-10", "weight": 1}
            hk = f"{key_prefix}_herd{hi}"
            with st.container(border=True):
                cols = st.columns([5, 1])
                with cols[1]:
                    if st.checkbox("Del", key=f"{hk}_del"):
                        to_delete_herd.append(hi)
                        continue
                updated_herd.append(render_herd_pokemon(hp, hk))

        if to_delete_herd:
            st.session_state[herd_count_key] -= len(to_delete_herd)
            st.rerun()

        if st.button("Add herd member", key=f"{key_prefix}_add_herd"):
            st.session_state[herd_count_key] += 1
            st.rerun()

        result["herdablePokemon"] = updated_herd

    # Weight multipliers
    wm = spawn.get("weightMultiplier")
    wms = spawn.get("weightMultipliers", [])
    # Normalize: convert singular to list for uniform handling
    if wm and not wms:
        wms = [wm]

    count_key = f"{key_prefix}_wm_count"
    if count_key not in st.session_state:
        st.session_state[count_key] = len(wms)

    with st.expander("Weight multipliers", expanded=False):
        updated_wms = []
        to_delete = []
        n = st.session_state[count_key]

        for wi in range(n):
            w = wms[wi] if wi < len(wms) else {"multiplier": 1.0, "condition": {}}
            wk = f"{key_prefix}_wms{wi}"
            st.markdown(f"**Multiplier {wi + 1}**")
            cols = st.columns([5, 1])
            with cols[1]:
                if st.checkbox("Del", key=f"{wk}_del"):
                    to_delete.append(wi)
                    continue
            updated_wms.append(render_weight_multiplier(w, wk))

        if to_delete:
            st.session_state[count_key] -= len(to_delete)
            st.rerun()

        if st.button("Add multiplier", key=f"{key_prefix}_add_wms"):
            st.session_state[count_key] += 1
            st.rerun()

        if updated_wms:
            result["weightMultipliers"] = updated_wms

    # Condition
    with st.expander("Condition", expanded=False):
        result["condition"] = render_condition(spawn.get("condition", {}), f"{key_prefix}_cond")

    # Anticondition
    with st.expander("Anticondition", expanded=False):
        result["anticondition"] = render_condition(spawn.get("anticondition", {}), f"{key_prefix}_anti")

    # Drops
    with st.expander("Drops", expanded=False):
        drops_result = render_drops(spawn.get("drops"), f"{key_prefix}_drops")
        if drops_result is not None:
            result["drops"] = drops_result

    # Clean up empty dicts/lists
    for k in ["condition", "anticondition"]:
        if not result.get(k):
            result.pop(k, None)
    if not result.get("presets"):
        result.pop("presets", None)

    return result, False


def main():
    st.set_page_config(page_title="Cobblemon Spawn Editor", layout="wide")
    with st.spinner("Downloading file...", show_time=True):
        st.title("Cobblemon Spawn Editor")

    if not os.path.isdir(SPAWN_DIR):
        st.error(f"Spawn directory not found: `{SPAWN_DIR}`\n\nRun `python get_default_pokemons.py` first.")
        with st.spinner("Downloading", show_time=True):
            reset()
            st.rerun()

    files = load_pokemon_files()
    if not files:
        st.warning("No spawn files found.")
        return

    # Sidebar: pokemon selector
    with st.sidebar:
        st.header("Pokemon")
        search = st.text_input("Search", key="search")
        filtered = [
            (fname, display) for fname, display in files
            if search.lower() in display.lower() or search.lower() in fname.lower()
        ] if search else files

        options = {display: fname for fname, display in filtered}
        selected_display = st.selectbox(
            "Select Pokemon", list(options.keys()),
            key="pokemon_select",
        )
        if not selected_display:
            return
        selected_file = options[selected_display]

        st.divider()
        if st.button("Restore to default", type="primary", use_container_width=True):
            with st.spinner("Downloading", show_time=True):
                reset()
                st.rerun()

    # Use selected file as key prefix so each Pokémon gets isolated widget state
    fk = selected_file.replace(".", "_")

    # Load data
    data = load_spawn_data(selected_file)

    # Top-level fields
    st.subheader(selected_display)

    cols = st.columns(3)
    with cols[0]:
        enabled_key = f"{fk}_enabled"
        if enabled_key not in st.session_state:
            st.session_state[enabled_key] = data.get("enabled", True)
        data["enabled"] = st.checkbox("Enabled", key=enabled_key)
    with cols[1]:
        installed = st.text_input(
            "Needed installed mods (comma-separated)",
            value=", ".join(data.get("neededInstalledMods", [])),
            key=f"{fk}_installed_mods",
        )
        data["neededInstalledMods"] = [m.strip() for m in installed.split(",") if m.strip()]
    with cols[2]:
        uninstalled = st.text_input(
            "Needed uninstalled mods (comma-separated)",
            value=", ".join(data.get("neededUninstalledMods", [])),
            key=f"{fk}_uninstalled_mods",
        )
        data["neededUninstalledMods"] = [m.strip() for m in uninstalled.split(",") if m.strip()]

    st.divider()

    # Spawns
    spawns = data.get("spawns", [])
    updated_spawns = []

    for i, spawn in enumerate(spawns):
        with st.container(border=True):
            result, deleted = render_spawn(spawn, i, f"{fk}_s{i}")
            if not deleted:
                updated_spawns.append(result)

    data["spawns"] = updated_spawns

    # Add new spawn
    st.divider()
    if st.button("Add new spawn", key=f"{fk}_add_spawn"):
        match = re.match(r"\d+_(.+)\.json", selected_file)
        poke_name = match.group(1) if match else ""
        new_id = f"{poke_name}-{len(data['spawns']) + 1}"
        data["spawns"].append({
            "id": new_id,
            "pokemon": poke_name,
            "presets": ["natural"],
            "type": "pokemon",
            "spawnablePositionType": "grounded",
            "bucket": "common",
            "level": "1-50",
            "weight": 1.0,
            "condition": {},
        })
        save_spawn_data(selected_file, data)
        _clear_editor_state(fk)
        st.rerun()

    # Save button
    st.divider()
    if st.button("Save", type="primary", key=f"{fk}_save"):
        save_spawn_data(selected_file, data)
        _clear_editor_state(fk)
        st.rerun()


if __name__ == "__main__":
    main()
