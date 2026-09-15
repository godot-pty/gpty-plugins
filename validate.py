#!/usr/bin/env python3
"""Validate the gpty plugin registry index.

Two layers:

* Structure (always): the index parses, each entry carries exactly the
  documented keys, every value is in range, and no id or repo repeats.
* Manifest agreement (``--check-repos``, needs network): each entry's
  ``gpty-plugin.toml`` is fetched from its repo at HEAD and must agree with
  what the index states, so the catalog cannot drift from the plugin it
  points at (id, name, version floor, platforms).

Run locally before pushing: ``python3 validate.py --check-repos``.
Exit codes: 0 clean, 1 problems (each printed).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "registry.json"

MAX_PLUGINS = 256
MAX_ID_PART = 63
MAX_NAME = 64
MAX_DESCRIPTION = 200
CATEGORIES = ("agent", "editor", "git", "multiplexer", "utility")
PLATFORMS = ("linux", "macos", "windows")
KEYS = (
    "id",
    "repo",
    "name",
    "description",
    "category",
    "min_gpty_version",
    "platforms",
)
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
ID = re.compile(r"^[a-z0-9-]+/[a-z0-9-]+$")
MANIFEST_URL = "https://raw.githubusercontent.com/{pid}/HEAD/gpty-plugin.toml"
# What makes a manifest a plugin rather than a manifest that ships nothing.
SHIPPED_SECTIONS = ("profiles", "actions", "events", "concepts", "link_handlers")


def check_structure(index) -> list[str]:
    """Every rule the index itself must hold, with no network."""
    problems: list[str] = []
    if not isinstance(index, dict):
        return ["registry.json must be an object"]
    if index.get("version") != 1:
        problems.append(f"version must be 1, got {index.get('version')!r}")
    plugins = index.get("plugins")
    if not isinstance(plugins, list):
        return problems + ["plugins must be an array"]
    if len(plugins) > MAX_PLUGINS:
        problems.append(
            f"plugins must hold at most {MAX_PLUGINS} entries, got {len(plugins)}"
        )
    seen_ids: set[str] = set()
    seen_repos: set[str] = set()
    for i, entry in enumerate(plugins):
        where = f"plugins[{i}]"
        if not isinstance(entry, dict):
            problems.append(f"{where} must be an object")
            continue
        unknown = sorted(set(entry) - set(KEYS))
        missing = sorted(set(KEYS) - set(entry))
        if unknown:
            problems.append(f"{where} has unknown keys: {', '.join(unknown)}")
        if missing:
            problems.append(f"{where} is missing: {', '.join(missing)}")

        pid = entry.get("id")
        if (
            not isinstance(pid, str)
            or not ID.match(pid)
            or any(len(part) > MAX_ID_PART for part in pid.split("/"))
        ):
            problems.append(
                f"{where}.id must be owner/name of [a-z0-9-] parts"
                f" ≤ {MAX_ID_PART}: {pid!r}"
            )
            # The remaining rules are keyed on a usable id.
            continue
        if pid in seen_ids:
            problems.append(f"{where}.id repeats {pid}")
        seen_ids.add(pid)

        repo = entry.get("repo")
        if isinstance(repo, str):
            if repo in seen_repos:
                problems.append(f"{where}.repo repeats {repo}")
            seen_repos.add(repo)
        if repo != f"https://github.com/{pid}":
            problems.append(
                f"{where}.repo must be https://github.com/{pid}, got {repo!r}"
            )

        name = entry.get("name")
        if (
            not isinstance(name, str)
            or not 1 <= len(name) <= MAX_NAME
            or "\n" in name
        ):
            problems.append(
                f"{where}.name must be one line of 1–{MAX_NAME} characters: {name!r}"
            )

        description = entry.get("description")
        if (
            not isinstance(description, str)
            or not 1 <= len(description) <= MAX_DESCRIPTION
            or "\n" in description
        ):
            problems.append(
                f"{where}.description must be one line of"
                f" 1–{MAX_DESCRIPTION} characters: {description!r}"
            )

        category = entry.get("category")
        if category not in CATEGORIES:
            problems.append(
                f"{where}.category must be one of {', '.join(CATEGORIES)}:"
                f" {category!r}"
            )

        floor = entry.get("min_gpty_version")
        if not isinstance(floor, str) or not SEMVER.match(floor):
            problems.append(f"{where}.min_gpty_version must be X.Y.Z: {floor!r}")

        platforms = entry.get("platforms")
        if (
            not isinstance(platforms, list)
            or not platforms
            or len(set(platforms)) != len(platforms)
            or any(p not in PLATFORMS for p in platforms)
        ):
            problems.append(
                f"{where}.platforms must be a non-empty subset of"
                f" {', '.join(PLATFORMS)}: {platforms!r}"
            )
    return problems


def check_manifest(entry: dict) -> list[str]:
    """Fetch the plugin's manifest at HEAD and require agreement with the entry."""
    pid = entry["id"]
    where = f"plugins[{pid}]"
    try:
        with urllib.request.urlopen(MANIFEST_URL.format(pid=pid), timeout=30) as resp:
            manifest = tomllib.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, tomllib.TOMLDecodeError) as error:
        return [f"{where}: cannot read gpty-plugin.toml at HEAD: {error}"]

    problems: list[str] = []
    if manifest.get("id") != pid:
        problems.append(
            f"{where}: the manifest's id is {manifest.get('id')!r}, not {pid!r}"
        )
    if manifest.get("name") != entry.get("name"):
        problems.append(
            f"{where}: manifest name {manifest.get('name')!r} does not match the"
            f" index ({entry.get('name')!r})"
        )
    if manifest.get("min_gpty_version") != entry.get("min_gpty_version"):
        problems.append(
            f"{where}: manifest floor {manifest.get('min_gpty_version')!r} does not"
            f" match the index ({entry.get('min_gpty_version')!r})"
        )
    # An absent platforms list means every platform, the manifest's default.
    manifest_platforms = manifest.get("platforms", list(PLATFORMS))
    if sorted(manifest_platforms) != sorted(entry.get("platforms", [])):
        problems.append(
            f"{where}: manifest platforms {manifest_platforms!r} do not match the"
            f" index ({entry.get('platforms')!r})"
        )
    version = manifest.get("version")
    if not isinstance(version, str) or not SEMVER.match(version):
        problems.append(f"{where}: the manifest's version must be X.Y.Z: {version!r}")
    if not any(manifest.get(section) for section in SHIPPED_SECTIONS):
        problems.append(
            f"{where}: the manifest ships nothing"
            f" ({'/'.join(SHIPPED_SECTIONS)} all absent or empty)"
        )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate registry.json.")
    parser.add_argument(
        "--check-repos",
        action="store_true",
        help="also fetch every plugin's manifest at HEAD (needs network)",
    )
    args = parser.parse_args()

    try:
        index = json.loads(INDEX.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"registry.json: {error}", file=sys.stderr)
        return 1

    problems = check_structure(index)
    if args.check_repos and not problems:
        for entry in index.get("plugins", []):
            problems += check_manifest(entry)

    if problems:
        print(f"registry invalid — {len(problems)} problem(s):", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1

    count = len(index.get("plugins", []))
    scope = "manifests checked" if args.check_repos else "structure only"
    print(f"registry ok: {count} plugin(s), {scope}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
