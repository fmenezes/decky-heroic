"""Pure-Python parser for Heroic Games Launcher library data.

Lives in ``py_modules`` so the decky loader adds it to the plugin import path,
and so it can be unit-tested standalone without Decky.
"""

from __future__ import annotations

import json
import re
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

# Candidate Heroic config dirs, in probe order.
FLATPAK_CONFIG_PATH = Path(
    "~/.var/app/com.heroicgameslauncher.hgl/config/heroic"
).expanduser()
NATIVE_CONFIG_PATH = Path("~/.config/heroic").expanduser()
MAC_CONFIG_PATH = Path("~/Library/Application Support/heroic").expanduser()
DEFAULT_CONFIG_CANDIDATES = [FLATPAK_CONFIG_PATH, NATIVE_CONFIG_PATH, MAC_CONFIG_PATH]


def find_heroic_config(
    candidates: list[Path] | None = None,
) -> Path | None:
    """Locate a Heroic config directory.

    Probes ``candidates`` (defaults to OS-specific candidate paths).
    A candidate counts only if it contains a ``store_cache`` directory.
    Returns ``None`` when no Heroic installation is found.
    """
    if candidates is None:
        try:
            from platform_utils import get_heroic_config_candidates

            candidates = get_heroic_config_candidates()
        except ImportError:
            candidates = DEFAULT_CONFIG_CANDIDATES
    for path in candidates:
        if (path / "store_cache").is_dir():
            return path
    return None


def _clean_size(val: Any) -> str:
    """Normalize install size string, stripping out meaningless 0s."""
    s = str(val or "").strip()
    if not s or s == "0":
        return ""
    if re.match(r"^0(?:\.0+)?(?:\s*[a-zA-Z]+)?$", s):
        return ""
    return s


def _to_game_entry(entry: dict[str, Any], store: str) -> dict[str, Any] | None:
    """Normalize one library entry. Returns None for entries to skip."""
    app_name = entry.get("app_name") or ""
    if not entry.get("title") or app_name in SKIPPED_APP_NAMES:
        return None
    install = entry.get("install") or {}
    raw_size = _clean_size(install.get("install_size"))
    return {
        "title": entry["title"],
        "app_name": app_name,
        "store": store,
        "runner": entry.get("runner") or store,
        "is_installed": bool(entry.get("is_installed")),
        "art_square": entry.get("art_square") or "",
        "art_cover": entry.get("art_cover") or "",
        "install_size": raw_size,
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


def is_store_logged_in(heroic_config_dir: Path | None, store: str) -> bool:
    """Check whether a store has been logged in / initialized in Heroic.

    Sideload does not require authentication and is always considered logged in.
    Other stores check for their respective library cache file or auth credentials.
    """
    if store == "sideload":
        return True
    if heroic_config_dir is None:
        return False

    store_cache = heroic_config_dir / "store_cache"
    if store == "gog":
        return (
            (store_cache / "gog_library.json").is_file()
            or (heroic_config_dir / "gog_store" / "auth.json").is_file()
        )
    if store == "epic":
        home = Path.home()
        return (
            (store_cache / "legendary_library.json").is_file()
            or (heroic_config_dir / "legendaryConfig" / "legendary" / "user.json").is_file()
            or (home / ".config" / "legendary" / "user.json").is_file()
        )
    if store == "amazon":
        home = Path.home()
        return (
            (store_cache / "nile_library.json").is_file()
            or (heroic_config_dir / "nile_config" / "nile" / "credentials.json").is_file()
            or (home / ".config" / "nile" / "credentials.json").is_file()
        )
    return False


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


def inspect_heroic_settings(
    config_dir: Path | None = None,
    platform: str | None = None,
) -> list[dict[str, str]]:
    """Inspect Heroic configuration and return warnings for settings that
    negatively affect Steam integration, tailored per operating system.
    """
    if not config_dir:
        return []

    config_file = config_dir / "config.json"
    if not config_file.is_file():
        return []

    try:
        data = json.loads(config_file.read_text(encoding="utf-8"))
    except Exception:
        return []

    settings = data.get("defaultSettings", data)
    warnings: list[dict[str, str]] = []

    # Resolve platform (linux, macos, windows)
    if platform is None:
        try:
            from platform_utils import is_linux, is_macos, is_windows

            if is_macos():
                platform = "macos"
            elif is_windows():
                platform = "windows"
            else:
                platform = "linux"
        except Exception:
            platform = "linux"

    # 1. Check addSteamShortcuts (Duplicate Shortcuts Risk - all platforms)
    if settings.get("addSteamShortcuts") is True:
        warnings.append({
            "id": "add_steam_shortcuts",
            "level": "warning",
            "title": "Duplicate Shortcuts Risk",
            "message": "Heroic's 'Add games to Steam automatically' is enabled. We recommend turning this off in Heroic settings to prevent duplicate library entries.",
        })

    # 2. Check hideWindowOnProtocolLaunch (Window Focus / Experience)
    if settings.get("hideWindowOnProtocolLaunch") is False:
        if platform == "linux":
            msg = "Heroic is set to show its window when launching games. Enable 'Minimize/Hide window on launch' in Heroic settings for a seamless Game Mode experience."
        else:
            msg = "Heroic is set to show its window when launching games. We recommend enabling 'Minimize/Hide window on launch' in Heroic settings so games launch directly into view."
        warnings.append({
            "id": "hide_window_on_launch",
            "level": "warning",
            "title": "Heroic Window Visible on Launch",
            "message": msg,
        })

    # 3. Check Wine / Runner settings per OS
    if platform == "windows":
        # Windows runs native .exe directly without Wine/Proton. No runner warning needed.
        pass
    elif platform == "macos":
        # macOS uses Game Porting Toolkit (D3DMetal) or Wine-Crossover; not Valve Proton.
        wine_version = settings.get("wineVersion")
        if not wine_version or not isinstance(wine_version, dict) or not wine_version.get("bin"):
            warnings.append({
                "id": "missing_wine_version",
                "level": "warning",
                "title": "No Default Runner (Game Porting Toolkit / Wine) Selected",
                "message": "No default Game Porting Toolkit or Wine runner is configured in Heroic. Windows games may fail to launch on macOS until a runner is selected in Heroic.",
            })
        else:
            bin_path = Path(wine_version.get("bin", ""))
            if bin_path and not bin_path.exists():
                warnings.append({
                    "id": "broken_wine_version",
                    "level": "warning",
                    "title": "Configured Runner Missing",
                    "message": f"Default runner '{wine_version.get('name', 'Game Porting Toolkit')}' was not found on disk ({bin_path}). Games may fail to launch.",
                })

        # Check if Linux-only GameMode was enabled (e.g. from synced config)
        if settings.get("useGameMode") is True:
            warnings.append({
                "id": "gamemode_on_macos",
                "level": "warning",
                "title": "Linux GameMode Enabled on macOS",
                "message": "Heroic has 'Use GameMode' enabled, which is a Linux-only utility (gamemoderun). We recommend disabling it in Heroic on macOS to avoid launch issues.",
            })
    else:
        # Linux (SteamOS / Bazzite / Desktop)
        wine_version = settings.get("wineVersion")
        if not wine_version or not isinstance(wine_version, dict) or not wine_version.get("bin"):
            warnings.append({
                "id": "missing_wine_version",
                "level": "warning",
                "title": "No Default Wine / Proton Selected",
                "message": "No default Wine or Proton version is configured in Heroic. Windows games may fail to launch until a runner is selected in Heroic.",
            })
        else:
            bin_path = Path(wine_version.get("bin", ""))
            if bin_path and not bin_path.exists():
                warnings.append({
                    "id": "broken_wine_version",
                    "level": "warning",
                    "title": "Configured Wine / Proton Missing",
                    "message": f"Default runner '{wine_version.get('name', 'Proton')}' was not found on disk ({bin_path}). Games may fail to launch.",
                })

    return warnings

