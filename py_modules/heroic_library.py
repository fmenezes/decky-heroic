"""Pure-Python parser for Heroic Games Launcher library data.

Lives in ``py_modules`` so the decky loader adds it to the plugin import path,
and so it can be unit-tested standalone without Decky.
"""

from __future__ import annotations

import json
import urllib.parse
from pathlib import Path
from typing import Any

# store id -> (library file, key holding the game list)
STORES = {
    "gog": ("gog_library.json", "games"),
    "epic": ("legendary_library.json", "library"),
    "amazon": ("nile_library.json", "library"),
}

# store id -> heroic runner name (as Heroic expects in the protocol URL)
STORE_TO_RUNNER = {
    "gog": "gog",
    "epic": "legendary",
    "amazon": "nile",
    "sideload": "sideload",
}

# Non-game entries to hide.
SKIPPED_APP_NAMES = {"gog-redist"}

# Candidate Heroic config dirs, in probe order (after any custom path).
FLATPAK_CONFIG_PATH = Path(
    "~/.var/app/com.heroicgameslauncher.hgl/config/heroic"
).expanduser()
NATIVE_CONFIG_PATH = Path("~/.config/heroic").expanduser()
DEFAULT_CONFIG_CANDIDATES = [FLATPAK_CONFIG_PATH, NATIVE_CONFIG_PATH]


def find_heroic_config(
    custom_path: str | None = None,
    candidates: list[Path] | None = None,
) -> Path | None:
    """Locate a Heroic config directory.

    Probes, in order: ``custom_path`` (if given), then ``candidates``
    (defaults to the flatpak config dir followed by the native install one).
    A candidate counts only if it contains a ``store_cache`` directory.
    Returns ``None`` when no Heroic installation is found.
    """
    if candidates is None:
        candidates = DEFAULT_CONFIG_CANDIDATES
    ordered: list[Path] = []
    if custom_path:
        ordered.append(Path(custom_path).expanduser())
    ordered.extend(candidates)
    for path in ordered:
        if (path / "store_cache").is_dir():
            return path
    return None


def _to_game_entry(entry: dict[str, Any], store: str) -> dict[str, Any] | None:
    """Normalize one library entry. Returns None for entries to skip."""
    app_name = entry.get("app_name") or ""
    if not entry.get("title") or app_name in SKIPPED_APP_NAMES:
        return None
    install = entry.get("install") or {}
    return {
        "title": entry["title"],
        "app_name": app_name,
        "store": store,
        "runner": entry.get("runner") or store,
        "is_installed": bool(entry.get("is_installed")),
        "art_square": entry.get("art_square") or "",
        "art_cover": entry.get("art_cover") or "",
        "install_size": install.get("install_size") or "",
        "cloud_saves": bool(entry.get("cloud_save_enabled")),
    }


def parse_library_file(path: Path, store: str, list_key: str) -> list[dict[str, Any]]:
    """Parse one store's library JSON into normalized game entries."""
    data = json.loads(path.read_text(encoding="utf-8"))
    games: list[dict[str, Any]] = []
    for entry in data.get(list_key, []):
        game = _to_game_entry(entry, store)
        if game is not None:
            games.append(game)
    return games


def parse_sideloads(sideload_dir: Path) -> list[dict[str, Any]]:
    """Parse Heroic's sideload_apps directory (one JSON file per game).

    Sideloaded games are local executables, so they are always installed.
    A missing directory yields an empty list.
    """
    games: list[dict[str, Any]] = []
    if not sideload_dir.is_dir():
        return games
    for file in sorted(sideload_dir.glob("*.json")):
        try:
            entry = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        game = _to_game_entry({**entry, "is_installed": True}, "sideload")
        if game is not None:
            games.append(game)
    return games


def get_library(heroic_config_dir: Path) -> dict[str, Any]:
    """Read all store libraries under ``heroic_config_dir``.

    Returns ``{"games": [...], "errors": [...]}``. A missing or corrupt store
    file is reported in ``errors``; the other stores are still returned.
    Games are sorted installed-first, then alphabetically by title.
    """
    store_cache_dir = heroic_config_dir / "store_cache"
    games: list[dict[str, Any]] = []
    errors: list[str] = []
    for store, (filename, list_key) in STORES.items():
        path = store_cache_dir / filename
        try:
            games.extend(parse_library_file(path, store, list_key))
        except FileNotFoundError:
            continue  # store not logged in / never synced: not an error
        except json.JSONDecodeError as exc:
            errors.append(f"{store}: could not parse library file ({exc})")
    games.extend(parse_sideloads(heroic_config_dir / "sideload_apps"))
    games.sort(key=lambda g: (not g["is_installed"], g["title"].casefold()))
    return {"games": games, "errors": errors}


def launch_url(app_name: str, runner: str) -> str:
    """Build the heroic:// launch URL for a game.

    Heroic (>= 2.22) only handles the `launch` protocol action, as
    `heroic://launch?appName=<id>&runner=<runner>` — runner being one of
    legendary/gog/nile/sideload. Not-installed games launched this way make
    Heroic offer to install them, so the same URL drives both Play and
    Install flows.
    """
    runner = STORE_TO_RUNNER.get(runner, runner)
    return (
        f"heroic://launch?appName={urllib.parse.quote(app_name)}"
        f"&runner={urllib.parse.quote(runner)}"
    )
