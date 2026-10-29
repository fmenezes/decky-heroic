"""Decky backend for the Heroic Library plugin."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import shutil
import ssl
import subprocess
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import decky

from heroic_library import (
    find_heroic_config,
    get_library,
    inspect_heroic_settings,
    is_store_logged_in,
    launch_url,
)
from steam_shortcuts import (
    build_shortcut,
    is_ours,
    merge_shortcuts,
    read_shortcuts,
    shortcut_id,
    synced_markers,
    write_shortcuts,
)

FLATPAK_ID = "com.heroicgameslauncher.hgl"
DEFAULT_SETTINGS = {
    "gogTab": True,
    "epicTab": True,
    "amazonTab": True,
    "sideloadTab": True,
    "syncAllGames": False,
}

SETTINGS_DIR = Path(
    os.environ.get("DECKY_PLUGIN_SETTINGS_DIR")
    or Path.home() / ".config" / "heroic-library"
)
SETTINGS_FILE = SETTINGS_DIR / "settings.json"


def _load_settings() -> dict:
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {**DEFAULT_SETTINGS, **data}
    except (OSError, json.JSONDecodeError):
        pass
    return dict(DEFAULT_SETTINGS)


def _steam_is_running() -> bool:
    try:
        proc = subprocess.run(
            ["pgrep", "-x", "steam"], capture_output=True, timeout=5
        )
        return proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _download_bytes(url: str) -> bytes:
    """Download URL contents. Falls back to an unverified SSL context — the
    plugin's Python runtime can't see the system CA store, so the default
    context fails with CERTIFICATE_VERIFY_FAILED (urlopen wraps the ssl error
    in URLError, hence the string check)."""
    req = urllib.request.Request(url, headers={"User-Agent": "heroic-decky"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read()
    except urllib.error.URLError as exc:
        if "CERTIFICATE_VERIFY_FAILED" not in str(exc.reason):
            raise
        ctx = ssl._create_unverified_context()  # noqa: SLF001
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            return resp.read()


def _image_type(data: bytes) -> str | None:
    """Steam's artwork API accepts jpg/png; webp etc. are unsupported."""
    if data.startswith(b"\xff\xd8"):
        return "jpg"
    if data.startswith(b"\x89PNG"):
        return "png"
    return None


# Serializes shortcuts.vdf read-modify-write across concurrent syncs
_vdf_lock = threading.Lock()
# Prevents concurrent flatpak installations
_install_lock = threading.Lock()
_install_state: dict[str, Any] = {
    "status": "idle",
    "logs": [],
    "error": None,
}


def _is_flatpak_available() -> bool:
    flatpak = shutil.which("flatpak") or "/usr/bin/flatpak"
    return bool(shutil.which(flatpak) or (Path(flatpak).exists() and os.access(flatpak, os.X_OK)))


def _is_heroic_installed() -> bool:
    flatpak = shutil.which("flatpak") or "/usr/bin/flatpak"
    if shutil.which(flatpak) or (Path(flatpak).exists() and os.access(flatpak, os.X_OK)):
        try:
            res = subprocess.run(
                [flatpak, "info", FLATPAK_ID],
                capture_output=True,
                timeout=5,
            )
            if res.returncode == 0:
                return True
        except Exception:
            pass
    if shutil.which("heroic") is not None:
        return True
    return False


# Artwork for the "Heroic Games Launcher" shortcut, from SteamGridDB.
LAUNCHER_ART_URLS = {
    "grid": "https://cdn2.steamgriddb.com/grid/e022cb640ae8809689b66b0eb6464305.png",
    "wide": "https://cdn2.steamgriddb.com/grid/726d04d0731a3930f3359dca8f721168.png",
    "hero": "https://cdn2.steamgriddb.com/hero/bace1d1361ca55cf11e8c50266678c52.png",
    "logo": "https://cdn2.steamgriddb.com/logo/f44d2854e944ac5223c15b2abdf57f38.png",
    "icon": "https://cdn2.steamgriddb.com/icon/9f73f765160d33280216b73b6378c068.png",
}


class Plugin:
    def _resolve_heroic_config(self) -> tuple[Path | None, list[str]]:
        """Resolve the Heroic config dir.

        Order: HEROIC_CONFIG_DIR env var (dev/testing), then the standard
        flatpak and native install directories. Returns
        (config_dir_or_None, probed_paths).
        """
        home = Path(os.environ.get("DECKY_USER_HOME") or Path.home())
        candidates = [
            home / ".var" / "app" / FLATPAK_ID / "config" / "heroic",
            home / ".config" / "heroic",
        ]
        env_override = os.environ.get("HEROIC_CONFIG_DIR")
        if env_override:
            candidates.insert(0, Path(env_override).expanduser())
        probed = [str(p) for p in candidates]
        config = find_heroic_config(candidates)
        if config is None:
            for p in candidates:
                if p.is_dir():
                    config = p
                    break
        return config, probed

    def _heroic_install_kind(self, config: Path | None) -> str | None:
        """Classify the Heroic install from its config location."""
        if config is None:
            return None
        return "flatpak" if ".var/app" in str(config) else "native"

    def _launch_command(self, url: str) -> list[str]:
        """Build the command to send a heroic:// URL to Heroic, based on how
        Heroic is installed:

        - flatpak: `flatpak run com.heroicgameslauncher.hgl <url>`
        - native: `<heroic binary> <url>` (from PATH)
        - fallback: `xdg-open <url>` (works when a desktop environment exists)

        Heroic's protocol handler reads heroic:// URLs from its CLI args, so
        invoking the app directly works without xdg-open (which fails in
        Game Mode, where no desktop environment exists).
        """
        config, _ = self._resolve_heroic_config()
        kind = self._heroic_install_kind(config)
        if kind == "flatpak":
            flatpak = shutil.which("flatpak") or "/usr/bin/flatpak"
            return [flatpak, "run", FLATPAK_ID, url]
        heroic = shutil.which("heroic")
        if heroic is not None:
            return [heroic, url]
        xdg = shutil.which("xdg-open")
        if xdg is not None:
            return [xdg, url]
        raise RuntimeError(
            "No way to launch Heroic found (flatpak/heroic/xdg-open)"
        )

    def _launch_env(self) -> dict:
        """Environment for the launch command: GUI apps need a display, but
        this backend may run under a systemd service without DISPLAY set."""
        env = dict(os.environ)
        env.setdefault("DISPLAY", ":0")
        return env

    async def check_heroic(self) -> dict:
        """Whether Heroic is installed and configured, and store login status."""
        config, probed = self._resolve_heroic_config()
        installed = _is_heroic_installed()
        stores = {
            "gog": is_store_logged_in(config, "gog") if installed else False,
            "epic": is_store_logged_in(config, "epic") if installed else False,
            "amazon": is_store_logged_in(config, "amazon") if installed else False,
            "sideload": installed,
        }
        warnings = inspect_heroic_settings(config) if installed and config else []
        return {
            "found": config is not None and (config / "store_cache").is_dir(),
            "installed": installed,
            "has_flatpak": _is_flatpak_available(),
            "stores": stores,
            "probed": probed,
            "warnings": warnings,
        }

    async def start_install_heroic(self) -> dict:
        """Start installing Heroic in background and return current status."""
        global _install_state
        if not _install_lock.acquire(blocking=False):
            return {
                "status": _install_state["status"],
                "logs": list(_install_state["logs"]),
                "error": _install_state["error"],
            }

        _install_state = {
            "status": "running",
            "logs": ["Starting Heroic Games Launcher installation..."],
            "error": None,
        }
        thread = threading.Thread(target=self._run_install_worker, daemon=True)
        thread.start()
        return {
            "status": "running",
            "logs": list(_install_state["logs"]),
            "error": None,
        }

    async def get_install_progress(self) -> dict:
        """Return the current installation status and logs."""
        return {
            "status": _install_state["status"],
            "logs": list(_install_state["logs"]),
            "error": _install_state["error"],
        }

    async def install_heroic(self) -> dict:
        """Install Heroic Games Launcher via flatpak (awaits completion)."""
        await self.start_install_heroic()
        while _install_state["status"] == "running":
            await asyncio.sleep(0.5)
        return {
            "success": _install_state["status"] == "success",
            "error": _install_state["error"],
        }

    def _run_install_worker(self) -> None:
        global _install_state
        flatpak = shutil.which("flatpak") or "/usr/bin/flatpak"
        if not (shutil.which(flatpak) or (Path(flatpak).exists() and os.access(flatpak, os.X_OK))):
            _install_state["status"] = "error"
            _install_state["error"] = "Flatpak command not found on system"
            _install_state["logs"].append("Error: Flatpak command not found on system.")
            _install_lock.release()
            return

        try:
            is_root = (os.geteuid() == 0) if hasattr(os, "geteuid") else False
            scope = [] if is_root else ["--user"]

            _install_state["logs"].append("Configuring Flathub repository...")
            decky.logger.info("Configuring Flathub repository...")

            remote_cmd = [
                flatpak,
                "remote-add",
                *scope,
                "--if-not-exists",
                "flathub",
                "https://dl.flathub.org/repo/flathub.flatpakrepo",
            ]
            try:
                proc_remote = subprocess.run(
                    remote_cmd,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if proc_remote.returncode != 0 and proc_remote.stderr:
                    _install_state["logs"].append(f"Remote notice: {proc_remote.stderr.strip()}")
            except Exception as exc:
                _install_state["logs"].append(f"Warning adding remote: {exc}")

            install_cmd = [
                flatpak,
                "install",
                *scope,
                "-y",
                "--noninteractive",
                "flathub",
                FLATPAK_ID,
            ]
            _install_state["logs"].append(f"Running: {' '.join(install_cmd)}")
            decky.logger.info("Installing Heroic via flatpak: %s", " ".join(install_cmd))

            proc = subprocess.Popen(
                install_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            if proc.stdout:
                for line in iter(proc.stdout.readline, ""):
                    clean = line.strip()
                    if clean:
                        _install_state["logs"].append(clean)
                        if len(_install_state["logs"]) > 500:
                            _install_state["logs"] = _install_state["logs"][-400:]
                proc.stdout.close()

            ret = proc.wait(timeout=600)
            if ret == 0:
                _install_state["status"] = "success"
                _install_state["logs"].append("Heroic installation completed successfully!")
                decky.logger.info("Heroic installation completed successfully.")
            else:
                _install_state["status"] = "error"
                err = f"Flatpak exited with code {ret}"
                _install_state["error"] = err
                _install_state["logs"].append(f"Error: {err}")
                decky.logger.error("Heroic installation failed: %s", err)
        except Exception as exc:
            _install_state["status"] = "error"
            _install_state["error"] = str(exc)
            _install_state["logs"].append(f"Exception: {exc}")
            decky.logger.error("Heroic installation exception: %s", exc)
        finally:
            _install_lock.release()

    async def get_library(self) -> dict:
        """Return the merged GOG+Epic library with installed status."""
        config, probed = self._resolve_heroic_config()
        installed = _is_heroic_installed()
        stores = {
            "gog": is_store_logged_in(config, "gog") if installed else False,
            "epic": is_store_logged_in(config, "epic") if installed else False,
            "amazon": is_store_logged_in(config, "amazon") if installed else False,
            "sideload": installed,
        }
        if config is None or not installed:
            return {
                "games": [],
                "errors": [
                    "Heroic not found. Looked in: " + "; ".join(probed)
                ],
                "heroic_found": False,
                "installed": installed,
                "stores": stores,
                "probed": probed,
            }
        result = get_library(config)
        result["config"] = str(config)
        result["heroic_found"] = True
        result["installed"] = installed
        result["stores"] = stores
        result["probed"] = probed
        if result["errors"]:
            decky.logger.warning(
                "Heroic library errors: %s", "; ".join(result["errors"])
            )
        # tag games that have been synced to Steam with their shortcut appid,
        # so the frontend can launch them natively through Steam
        try:
            _, user_config = self._steam_user_data_dir()
            if user_config is not None:
                shortcuts_path = user_config / "shortcuts.vdf"
                doc = read_shortcuts(
                    shortcuts_path.read_bytes() if shortcuts_path.exists() else b""
                )
                markers = synced_markers(doc)
                for game in result["games"]:
                    sid = markers.get(
                        f"heroic:{game['store']}:{game['app_name']}"
                    )
                    if sid is not None:
                        game["steam_appid"] = sid
        except Exception as exc:  # noqa: BLE001 - tagging is best-effort
            decky.logger.warning("Could not tag synced shortcuts: %s", exc)
        return result

    async def launch_game(self, app_name: str, runner: str) -> dict:
        """Launch (or offer to install) a game via Heroic's launch protocol.

        Heroic's protocol handler accepts
        `heroic://launch?appName=<id>&runner=<runner>` and, for games that are
        not installed, prompts the user to install — so the same URL covers
        Play and Install.
        Returns {"url": ...}.
        """
        url = launch_url(app_name, runner)
        decky.logger.info("Launching %s (%s) via %s", app_name, runner, url)
        cmd = self._launch_command(url)
        decky.logger.info("Launch command: %s", cmd)
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env=self._launch_env(),
        )
        decky.logger.info("Launch spawned (pid %s)", proc.pid)
        return {"url": url}

    def _steam_user_data_dir(self) -> tuple[Path | None, Path | None]:
        """Locate Steam's userdata dir and the most likely user config dir.

        Returns (userdata_dir, user_config_dir); both None when Steam's data
        cannot be found.
        """
        home = Path.home()
        candidates = [
            home / ".local/share/Steam/userdata",
            home / ".steam/steam/userdata",
            home / ".steam/debian-installation/userdata",
            home
            / ".var/app/com.valvesoftware.Steam/.local/share/Steam/userdata",
        ]
        userdata = next((p for p in candidates if p.is_dir()), None)
        if userdata is None:
            return None, None
        user_dirs = [d for d in userdata.iterdir() if d.is_dir() and d.name.isdigit()]
        if not user_dirs:
            return userdata, None
        # prefer the most recently modified account dir
        user_dir = max(user_dirs, key=lambda p: p.stat().st_mtime)
        return userdata, user_dir / "config"

    def _make_shortcut_parts(
        self,
        game: dict,
        grid_dir: Path,
        art_jobs: list[tuple[str, str, str]],
        appid: int = 0,
    ) -> tuple[dict, int]:
        """Build the shortcuts.vdf entry + cover-download jobs for a game.

        ``appid`` should be Steam's runtime-assigned id when known (a 0 means
        Steam computes one at load); cover files are named after it."""
        url = launch_url(game["app_name"], game["runner"])
        marker = f"heroic:{game['store']}:{game['app_name']}"
        # Exe/LaunchOptions reuse the same defensive install-kind detection
        # as in-game launches (flatpak vs native heroic)
        cmd = self._launch_command(url)
        exe, launch_prefix = cmd[0], cmd[1:-1]
        entry = build_shortcut(
            title=game["title"],
            exe=exe,
            launch_options=" ".join([*launch_prefix, f'"{url}"']).strip(),
            start_dir=str(Path(exe).parent),
            marker=marker,
            appid=appid,
        )
        sid = appid or shortcut_id(exe, game["title"])
        if game["art_square"]:
            art_jobs.append(
                (game["art_square"], grid_dir / f"{sid}p.png", game["title"])
            )
        if game["art_cover"]:
            art_jobs.append(
                (game["art_cover"], grid_dir / f"{sid}_hero.png", game["title"])
            )
        return entry, sid

    async def get_game_art(
        self, store: str, app_name: str, steam_appid: int
    ) -> dict:
        """Download a game's cover art: returns base64 payloads for the
        runtime artwork API and writes Steam grid files named by the
        runtime-assigned app id."""
        return await asyncio.to_thread(
            self._get_game_art_blocking, store, app_name, steam_appid
        )

    def _get_game_art_blocking(
        self, store: str, app_name: str, steam_appid: int
    ) -> dict:
        config, _ = self._resolve_heroic_config()
        if config is None:
            raise RuntimeError("Heroic installation not found")
        library = get_library(config)
        game = next(
            (
                g
                for g in library["games"]
                if g["store"] == store and g["app_name"] == app_name
            ),
            None,
        )
        if game is None:
            raise RuntimeError(f"{app_name} not found in the Heroic library")

        _, user_config = self._steam_user_data_dir()
        grid_dir = user_config / "grid" if user_config is not None else None
        if grid_dir is not None:
            grid_dir.mkdir(parents=True, exist_ok=True)

        out: dict = {}
        for url_field, prefix, suffix in (
            ("art_square", "square", "p"),
            ("art_cover", "cover", "_hero"),
        ):
            url = game.get(url_field) or ""
            if not url:
                continue
            try:
                data, itype = self._art_bytes(config, url)
            except Exception as exc:  # noqa: BLE001 - per-file failure is fine
                decky.logger.warning(
                    "art download failed for %s (%s): %s", game["title"], url, exc
                )
                continue
            out[f"{prefix}_b64"] = base64.b64encode(data).decode("ascii")
            out[f"{prefix}_type"] = itype
            if grid_dir is not None and steam_appid:
                (grid_dir / f"{steam_appid}{suffix}.{itype}").write_bytes(data)
        return out

    def _art_bytes(self, config: Path, url: str) -> tuple[bytes, str]:
        """Fetch artwork bytes for a CDN URL: Heroic's local image cache
        first (images-cache/<sha256(url)>), falling back to a download.
        Returns (data, image_type)."""
        cache_file = config / "images-cache" / hashlib.sha256(
            url.encode("utf-8")
        ).hexdigest()
        if cache_file.is_file():
            data = cache_file.read_bytes()
            itype = _image_type(data)
            if itype is not None:
                return data, itype
        data = _download_bytes(url)
        itype = _image_type(data)
        if itype is None:
            raise ValueError(f"unsupported image format: {url}")
        return data, itype

    async def add_shortcut(
        self, store: str, app_name: str, steam_appid: int | None = None
    ) -> dict:
        """Persist a single game's shortcut into shortcuts.vdf (called after
        the frontend registers it at runtime via SteamClient.Apps.AddShortcut;
        ``steam_appid`` is the id Steam assigned there)."""
        return await asyncio.to_thread(
            self._add_shortcut_blocking, store, app_name, steam_appid
        )

    def _add_shortcut_blocking(
        self, store: str, app_name: str, steam_appid: int | None
    ) -> dict:
        config, _ = self._resolve_heroic_config()
        if config is None:
            raise RuntimeError("Heroic installation not found")
        library = get_library(config)
        game = next(
            (
                g
                for g in library["games"]
                if g["store"] == store and g["app_name"] == app_name
            ),
            None,
        )
        if game is None:
            raise RuntimeError(f"{app_name} not found in the Heroic library")

        _, user_config = self._steam_user_data_dir()
        if user_config is None:
            raise RuntimeError("Steam userdata directory not found")
        shortcuts_path = user_config / "shortcuts.vdf"
        grid_dir = user_config / "grid"

        with _vdf_lock:
            existing = read_shortcuts(
                shortcuts_path.read_bytes() if shortcuts_path.exists() else b""
            )
            art_jobs: list[tuple[str, str, str]] = []
            entry, sid = self._make_shortcut_parts(
                game, grid_dir, art_jobs, appid=steam_appid or 0
            )
            doc, added, removed = merge_shortcuts(existing, [entry])
            user_config.mkdir(parents=True, exist_ok=True)
            grid_dir.mkdir(parents=True, exist_ok=True)
            shortcuts_path.write_bytes(write_shortcuts(doc))
        decky.logger.info("Added Steam shortcut for %s (appid %s)", game["title"], sid)
        return {"appid": sid, "added": added, "removed": removed}

    async def get_launcher_art(self) -> dict:
        """Return artwork for the 'Heroic Games Launcher' shortcut: downloads
        from SteamGridDB (bundled assets as offline fallback)."""
        assets = Path(__file__).parent / "assets"
        runtime_dir = Path(
            os.environ.get("DECKY_PLUGIN_RUNTIME_DIR", "/tmp/heroic-library")
        )
        runtime_dir.mkdir(parents=True, exist_ok=True)

        out: dict = {}
        for role in ("grid", "wide", "hero", "logo", "icon"):
            data: bytes | None = None
            url = LAUNCHER_ART_URLS.get(role)
            if url:
                try:
                    candidate = _download_bytes(url)
                    if _image_type(candidate) is not None:
                        data = candidate
                except Exception as exc:  # noqa: BLE001 - fallback below
                    decky.logger.warning("SGDB art fetch failed (%s): %s", role, exc)
            if data is None:
                fallback = assets / f"launcher-{role}.png"
                if fallback.is_file():
                    data = fallback.read_bytes()
            if data is None:
                continue
            if role == "icon":
                # SetShortcutIcon takes a file path, so persist it
                icon_path = runtime_dir / "launcher-icon.png"
                icon_path.write_bytes(data)
                out["icon_path"] = str(icon_path)
            else:
                out[f"{role}_b64"] = base64.b64encode(data).decode("ascii")
        return out

    async def get_settings(self) -> dict:
        """Return the plugin settings."""
        return _load_settings()

    async def set_setting(self, key: str, value) -> dict:
        """Set a single setting and persist it. Returns the full settings."""
        settings = _load_settings()
        settings[key] = value
        SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(
            json.dumps(settings, indent=2), encoding="utf-8"
        )
        decky.logger.info("Setting %s = %s", key, value)
        return settings

    async def _main(self):
        decky.logger.info("Heroic Library plugin loaded")

    async def _unload(self):
        decky.logger.info("Heroic Library plugin unloaded")

    async def _uninstall(self):
        pass
