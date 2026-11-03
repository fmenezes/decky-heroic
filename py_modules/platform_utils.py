"""Platform detection and OS-specific paths for Decky Heroic.

Provides structured OS checks (Linux, macOS, Windows) and centralizes
path resolution for Heroic configs, Steam userdata, and launch commands.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

FLATPAK_HEROIC_ID = "com.heroicgameslauncher.hgl"
FLATPAK_STEAM_ID = "com.valvesoftware.Steam"


def is_macos() -> bool:
    """Return True if running on macOS (Darwin)."""
    return sys.platform == "darwin"


def is_linux() -> bool:
    """Return True if running on Linux (SteamOS, Bazzite, generic distro)."""
    return sys.platform.startswith("linux")


def is_windows() -> bool:
    """Return True if running on Windows."""
    return sys.platform in ("win32", "cygwin")


def get_heroic_config_candidates(home: Path | None = None) -> list[Path]:
    """Return ordered list of candidate directories where Heroic config may live."""
    if home is None:
        home = Path(os.environ.get("DECKY_USER_HOME") or Path.home())

    candidates: list[Path] = []
    env_override = os.environ.get("HEROIC_CONFIG_DIR")
    if env_override:
        candidates.append(Path(env_override).expanduser())

    if is_macos():
        candidates.append(home / "Library" / "Application Support" / "heroic")
    elif is_windows():
        appdata = os.environ.get("APPDATA")
        if appdata:
            candidates.append(Path(appdata) / "heroic")
        candidates.append(home / "AppData" / "Roaming" / "heroic")
    else:  # Linux default
        candidates.append(
            home / ".var" / "app" / FLATPAK_HEROIC_ID / "config" / "heroic"
        )
        candidates.append(home / ".config" / "heroic")

    # Universal fallbacks in case cross-platform folders exist (e.g. testing)
    fallback_linux = home / ".config" / "heroic"
    fallback_mac = home / "Library" / "Application Support" / "heroic"
    if fallback_linux not in candidates:
        candidates.append(fallback_linux)
    if fallback_mac not in candidates:
        candidates.append(fallback_mac)

    return candidates


def get_heroic_app_path() -> Path | None:
    """Return the path to the Heroic app bundle (macOS) or executable (Windows/Linux)."""
    if is_macos():
        for p in (
            "/Applications/Heroic.app",
            str(Path.home() / "Applications" / "Heroic.app"),
        ):
            if Path(p).is_dir():
                return Path(p)
    elif is_windows():
        for env_key in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            base = os.environ.get(env_key)
            if base:
                for candidate in (
                    Path(base) / "Heroic" / "Heroic.exe",
                    Path(base) / "Programs" / "heroic" / "Heroic.exe",
                ):
                    if candidate.is_file():
                        return candidate
    else:  # Linux
        flatpak = shutil.which("flatpak") or "/usr/bin/flatpak"
        if shutil.which(flatpak) or (
            Path(flatpak).exists() and os.access(flatpak, os.X_OK)
        ):
            try:
                res = subprocess.run(
                    [flatpak, "info", FLATPAK_HEROIC_ID],
                    capture_output=True,
                    timeout=5,
                )
                if res.returncode == 0:
                    return Path(flatpak)
            except Exception:
                pass
        h = shutil.which("heroic")
        if h:
            return Path(h)
    return None


def is_heroic_installed() -> bool:
    """Check if Heroic is installed on the current operating system."""
    if get_heroic_app_path() is not None:
        return True

    # Generic check on PATH
    if shutil.which("heroic") is not None:
        return True

    # If Heroic has a config directory with store_cache, it is initialized
    from heroic_library import find_heroic_config

    cfg = find_heroic_config()
    return cfg is not None and (cfg / "store_cache").is_dir()


def get_steam_userdata_candidates(home: Path | None = None) -> list[Path]:
    """Return candidate directories where Steam's userdata folder may live."""
    if home is None:
        home = Path(os.environ.get("DECKY_USER_HOME") or Path.home())

    candidates: list[Path] = []
    if is_macos():
        candidates.append(
            home / "Library" / "Application Support" / "Steam" / "userdata"
        )
    elif is_windows():
        for env_key in ("ProgramFiles(x86)", "ProgramFiles"):
            pf = os.environ.get(env_key)
            if pf:
                candidates.append(Path(pf) / "Steam" / "userdata")
    else:  # Linux
        candidates.append(home / ".local" / "share" / "Steam" / "userdata")
        candidates.append(home / ".steam" / "steam" / "userdata")
        candidates.append(home / ".steam" / "debian-installation" / "userdata")
        candidates.append(
            home
            / ".var"
            / "app"
            / FLATPAK_STEAM_ID
            / ".local"
            / "share"
            / "Steam"
            / "userdata"
        )

    return candidates


def get_heroic_cli_command(cli_type: str) -> list[str]:
    """Return the command list to execute a Heroic CLI helper (gogdl, legendary, nile)."""
    bin_name = {
        "gog": "gogdl",
        "epic": "legendary",
        "amazon": "nile",
    }.get(cli_type.lower(), cli_type)

    # 1. Native PATH check
    for candidate in (bin_name, cli_type):
        native = shutil.which(candidate)
        if native:
            return [native]

    # 2. macOS app bundle binaries
    if is_macos():
        for arch in ("arm64", "x64"):
            for candidate in (bin_name, cli_type):
                mac_bin = Path(
                    f"/Applications/Heroic.app/Contents/Resources/app.asar.unpacked/build/bin/{arch}/darwin/{candidate}"
                )
                if mac_bin.is_file():
                    return [str(mac_bin)]

    # 3. Linux Flatpak
    if is_linux():
        flatpak_bin = shutil.which("flatpak") or "/usr/bin/flatpak"
        if shutil.which(flatpak_bin) or (
            Path(flatpak_bin).exists() and os.access(flatpak_bin, os.X_OK)
        ):
            rel_map = {
                "gog": "/app/bin/heroic/resources/app.asar.unpacked/build/bin/x64/linux/gogdl",
                "gogdl": "/app/bin/heroic/resources/app.asar.unpacked/build/bin/x64/linux/gogdl",
                "legendary": "/app/bin/heroic/resources/app.asar.unpacked/build/bin/x64/linux/legendary",
                "epic": "/app/bin/heroic/resources/app.asar.unpacked/build/bin/x64/linux/legendary",
                "nile": "/app/bin/heroic/resources/app.asar.unpacked/build/bin/x64/linux/nile",
                "amazon": "/app/bin/heroic/resources/app.asar.unpacked/build/bin/x64/linux/nile",
            }
            rel_path = rel_map.get(cli_type) or rel_map.get(bin_name)
            if rel_path:
                return [flatpak_bin, "run", f"--command={rel_path}", FLATPAK_HEROIC_ID]

    return []


def get_heroic_launch_command(
    url: str, heroic_config: Path | None = None
) -> list[str]:
    """Return command list to trigger heroic:// launch URL on current OS."""
    if is_macos():
        return ["open", url]
    elif is_windows():
        return ["cmd.exe", "/c", "start", "", url]

    # Linux: Check Flatpak vs Native
    is_flatpak = heroic_config is not None and ".var/app" in str(heroic_config)
    if is_flatpak:
        flatpak = shutil.which("flatpak") or "/usr/bin/flatpak"
        return [flatpak, "run", FLATPAK_HEROIC_ID, url]
    heroic = shutil.which("heroic")
    if heroic is not None:
        return [heroic, url]
    xdg = shutil.which("xdg-open")
    if xdg is not None:
        return [xdg, url]
    return ["xdg-open", url]


def get_steam_shortcut_params(
    url: str = "", heroic_config: Path | None = None
) -> tuple[str, str, str]:
    """Return (exe, start_dir, launch_options) for creating a Steam shortcut.

    This represents what Steam itself must execute.
    On macOS: /Applications/Heroic.app (Steam requires an .app bundle)
    On Linux Flatpak: /usr/bin/flatpak with args `run com.heroicgameslauncher.hgl "<url>"`
    On Linux Native: /usr/bin/heroic with args `"<url>"`
    On Windows: Heroic.exe with args `"<url>"`
    """
    if is_macos():
        app_path = get_heroic_app_path() or Path("/Applications/Heroic.app")
        exe = str(app_path)
        start_dir = str(app_path.parent)
        launch_options = f'"{url}"' if url else "--console"
        return exe, start_dir, launch_options

    if is_windows():
        app_path = get_heroic_app_path()
        if app_path:
            exe = str(app_path)
            start_dir = str(app_path.parent)
        else:
            exe = "Heroic.exe"
            start_dir = ""
        launch_options = f'"{url}"' if url else "--console"
        return exe, start_dir, launch_options

    # Linux: Check Flatpak vs Native
    is_flatpak = heroic_config is not None and ".var/app" in str(heroic_config)
    flatpak = shutil.which("flatpak") or "/usr/bin/flatpak"
    if is_flatpak or shutil.which("heroic") is None:
        exe = flatpak
        start_dir = str(Path(flatpak).parent)
        launch_options = (
            f'run {FLATPAK_HEROIC_ID} "{url}"'
            if url
            else f"run {FLATPAK_HEROIC_ID} --console"
        )
        return exe, start_dir, launch_options

    heroic = shutil.which("heroic") or "/usr/bin/heroic"
    exe = heroic
    start_dir = str(Path(heroic).parent)
    launch_options = f'"{url}"' if url else "--console"
    return exe, start_dir, launch_options

