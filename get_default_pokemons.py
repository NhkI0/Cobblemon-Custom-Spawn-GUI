"""Download the Cobblemon spawn_pool_world folder from GitLab and create
blank spawn files for any Pokémon that don't have spawns defined.
Made by Dopamine (@nhankio on Discord)
"""

import io
import json
import os
import re
import sys
import tarfile
from shutil import rmtree

try:
    import requests
except ImportError:
    print("Missing dependency. Install with: pip install requests")
    sys.exit(1)

BASE_URL = "https://gitlab.com"
PROJECT_ID = "cable-mc%2Fcobblemon"
SPAWN_FOLDER = "common/src/main/resources/data/cobblemon/spawn_pool_world"
SPECIES_FOLDER = "common/src/main/resources/data/cobblemon/species"
REF = "main"
OUTPUT_DIR = ".default/spawn_pool_world"

BLANK_SPAWN = {
    "enabled": True,
    "neededInstalledMods": [],
    "neededUninstalledMods": [],
    "spawns": [],
}


def download_spawn_pool(output):
    """Download existing spawn pool files and return set of filenames."""
    print("Downloading spawn_pool_world...")

    resp = requests.get(
        f"{BASE_URL}/api/v4/projects/{PROJECT_ID}/repository/archive.tar.gz",
        params={"sha": REF, "path": SPAWN_FOLDER},
        stream=True,
    )
    resp.raise_for_status()

    data = io.BytesIO(resp.content)
    count = 0
    existing = set()

    with tarfile.open(fileobj=data, mode="r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            parts = member.name.split("/")
            try:
                idx = parts.index("spawn_pool_world")
            except ValueError:
                continue
            relative = os.path.join(*parts[idx + 1:]) if len(parts) > idx + 1 else parts[idx]
            local_path = os.path.join(output, relative)
            os.makedirs(os.path.dirname(local_path), exist_ok=True)

            with tar.extractfile(member) as src, open(local_path, "wb") as dst:
                dst.write(src.read())
            count += 1
            existing.add(os.path.basename(relative))

    print(f"\t{count} spawn file(s) downloaded.")
    return existing


def fetch_all_species():
    """Fetch every species from all generation folders and return a list of
    (nationalPokedexNumber, name) tuples."""
    print("Fetching species list...")

    # Get generation folders
    resp = requests.get(
        f"{BASE_URL}/api/v4/projects/{PROJECT_ID}/repository/tree",
        params={"path": SPECIES_FOLDER, "ref": REF, "per_page": 100},
    )
    resp.raise_for_status()
    generations = [item["name"] for item in resp.json() if item["type"] == "tree"]

    print(f"\tDownloading species data ({len(generations)} generations)...")
    resp = requests.get(
        f"{BASE_URL}/api/v4/projects/{PROJECT_ID}/repository/archive.tar.gz",
        params={"sha": REF, "path": SPECIES_FOLDER},
        stream=True,
    )
    resp.raise_for_status()

    data = io.BytesIO(resp.content)
    species = []

    with tarfile.open(fileobj=data, mode="r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile() or not member.name.endswith(".json"):
                continue
            with tar.extractfile(member) as f:
                try:
                    info = json.load(f)
                except (json.JSONDecodeError, ValueError):
                    continue
                dex = info.get("nationalPokedexNumber")
                name = info.get("name")
                if dex is not None and name:
                    species.append((dex, name.lower()))

    print(f"\t{len(species)} species found.")
    return species


def create_blank_spawns(output, existing_files, species):
    """Create blank spawn files for species missing from spawn_pool_world."""
    existing_dex = set()
    pattern = re.compile(r"^(\d+)_")
    for fname in existing_files:
        m = pattern.match(fname)
        if m:
            existing_dex.add(int(m.group(1)))

    count = 0
    for dex, name in sorted(species):
        if dex in existing_dex:
            continue
        filename = f"{dex:04d}_{name}.json"
        filepath = os.path.join(output, filename)
        if not os.path.exists(filepath):
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(BLANK_SPAWN, f, indent=4)
                f.write("\n")
            count += 1

    print(f"\t{count} blank spawn file(s) created for missing Pokémon.")


def get_default():
    """Get all the default spawn pools and species. Generate blanks for the ones that don't already exist."""
    output = os.path.abspath(OUTPUT_DIR)
    print(f"Output directory: {output}\n")

    existing_files = download_spawn_pool(output)
    species = fetch_all_species()
    create_blank_spawns(output, existing_files, species)

    total = len(os.listdir(output))
    print(f"\nDone! {total} total file(s) in {output}")


def reset():
    """Reset all existing spawn pools to their initial state."""
    rmtree(OUTPUT_DIR, ignore_errors=True)
    get_default()


if __name__ == "__main__":
    reset()
