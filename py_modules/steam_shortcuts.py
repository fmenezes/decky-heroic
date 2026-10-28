"""Steam shortcuts.vdf handling for syncing Heroic games into Steam.

Pure-Python, no Decky imports so it can be unit-tested standalone.

shortcuts.vdf is a Source-engine binary VDF file:
  0x00 name\\0 <children...> 0x08   -> dict node
  0x01 name\\0 value\\0            -> string node
  0x02 name\\0 <int32 LE>          -> int node
The root is a dict named "shortcuts" whose children are dicts named
"0", "1", ... (one per non-Steam shortcut).
"""

from __future__ import annotations

import struct
import urllib.parse
import zlib
from typing import Any

OUR_TAG_PREFIX = "heroic:"
OUR_LAUNCH_MARKER = "heroic://launch"


def parse_vdf(data: bytes) -> dict[str, Any]:
    """Parse a binary VDF document. Raises ValueError on malformed input.

    Tolerates Steam's quirks: the client writes an extra end-of-dict marker
    after the root node, so trailing 0x08 bytes are skipped.
    """
    obj, pos = _parse_node(data, 0)
    while pos < len(data) and data[pos] == 0x08:
        pos += 1
    if pos != len(data):
        raise ValueError(f"trailing bytes after VDF document at {pos}")
    return obj


def _parse_node(data: bytes, pos: int) -> tuple[dict[str, Any] | str | int, int]:
    kind = data[pos]
    if kind == 0x08:
        raise ValueError("unexpected end-of-dict marker")
    if kind not in (0x00, 0x01, 0x02):
        raise ValueError(f"unknown node type 0x{kind:02x} at {pos}")
    raw_name, pos = _read_cstring(data, pos + 1)
    name = raw_name.decode("utf-8", "replace")
    if kind == 0x00:
        children: dict[str, Any] = {}
        while data[pos] != 0x08:
            child, pos = _parse_child(data, pos)
            children.update(child)
        return {name: children}, pos + 1
    if kind == 0x01:
        value, pos = _read_cstring(data, pos)
        return {name: value.decode("utf-8", "replace")}, pos
    if len(data) - pos < 4:
        raise ValueError("truncated int value")
    value = struct.unpack("<i", data[pos : pos + 4])[0]
    return {name: value}, pos + 4


def _parse_child(data: bytes, pos: int) -> tuple[dict[str, Any], int]:
    kind = data[pos]
    if kind == 0x08:
        raise ValueError("unexpected end-of-dict inside document")
    return _parse_node(data, pos)  # type: ignore[return-value]


def _read_cstring(data: bytes, pos: int) -> tuple[bytes, int]:
    end = data.find(b"\x00", pos)
    if end == -1:
        raise ValueError("unterminated string in VDF")
    return data[pos:end], end + 1


def serialize_vdf(obj: dict[str, Any]) -> bytes:
    """Serialize a dict/str/int tree back into binary VDF."""
    return _serialize_dict(obj)


def _serialize_dict(obj: dict[str, Any]) -> bytes:
    out = bytearray()
    for name, value in obj.items():
        n = str(name).encode()
        if isinstance(value, dict):
            out += b"\x00" + n + b"\x00" + _serialize_dict(value) + b"\x08"
        elif isinstance(value, bool):
            out += b"\x02" + n + b"\x00" + struct.pack("<i", int(value))
        elif isinstance(value, int):
            out += b"\x02" + n + b"\x00" + struct.pack("<i", value)
        elif isinstance(value, str):
            out += b"\x01" + n + b"\x00" + value.encode() + b"\x00"
        else:
            raise TypeError(f"unsupported VDF value type: {type(value)}")
    return bytes(out)


def shortcut_id(exe: str, app_name: str) -> int:
    """Steam's non-Steam shortcut id: crc32(exe + appname) | 0x80000000.

    Grid images are named after this id (e.g. ``<id>p.png`` for the portrait).
    """
    return (zlib.crc32((exe + app_name).encode()) & 0xFFFFFFFF) | 0x80000000


def is_ours(entry: dict[str, Any]) -> bool:
    """Whether a shortcut entry was created by this plugin."""
    return str(entry.get("DevKitGameID", "")).startswith(OUR_TAG_PREFIX)


def build_shortcut(
    title: str,
    exe: str,
    launch_options: str,
    start_dir: str,
    marker: str,
    hidden: bool = False,
    appid: int = 0,
) -> dict[str, Any]:
    """Build one shortcuts.vdf entry dict (values mirror SRM/Heroic).

    ``appid`` should be Steam's runtime-assigned shortcut id when known
    (see SteamClient.Apps.AddShortcut); 0 lets Steam compute one at load.
    ``hidden=True`` hides the shortcut from Steam's library tabs; its app
    page still exists, so it can be linked to (and launched) from elsewhere.
    """
    return {
        "appid": appid,
        "AppName": title,
        "Exe": f'"{exe}"',
        "StartDir": f'"{start_dir}"',
        "icon": "",
        "ShortcutPath": "",
        "LaunchOptions": launch_options,
        "IsHidden": 1 if hidden else 0,
        "AllowDesktopConfig": 1,
        "AllowOverlay": 1,
        "openvr": 0,
        "DevKit": 0,
        "DevKitGameID": marker,
        "LastPlayTime": 0,
    }


def merge_shortcuts(
    existing: dict[str, Any], new_entries: list[dict[str, Any]]
) -> tuple[dict[str, Any], int, int]:
    """Merge our shortcuts into a parsed shortcuts.vdf document.

    Removes every entry previously created by this plugin (idempotent re-sync),
    keeps all other shortcuts untouched, and appends the new entries.

    Returns (document, number_added, number_removed).
    """
    shortcuts = existing.get("shortcuts", {})
    kept = {
        idx: entry for idx, entry in shortcuts.items() if not is_ours(entry)
    }
    removed = len(shortcuts) - len(kept)
    result: dict[str, Any] = {}
    for i, entry in enumerate(kept.values()):
        result[str(i)] = entry
    for i, entry in enumerate(new_entries, start=len(result)):
        result[str(i)] = entry
    return {"shortcuts": result}, len(new_entries), removed


def synced_markers(doc: dict[str, Any]) -> dict[str, int]:
    """Map this plugin's game markers (``heroic:store:app_name``) to Steam
    shortcut app ids.

    Detection is launch-command based (entries whose LaunchOptions point at a
    heroic://launch URL) because Steam rewrites shortcuts.vdf on exit with
    its in-memory state — an entry created at runtime by Steam keeps its
    LaunchOptions but loses the DevKitGameID marker. The stored ``appid``
    field wins when present (it is Steam's own assigned id); otherwise the
    id is derived from Exe+AppName.
    """
    out: dict[str, int] = {}
    for entry in doc.get("shortcuts", {}).values():
        if not isinstance(entry, dict):
            continue
        marker = None
        devkit = str(entry.get("DevKitGameID", ""))
        if devkit.startswith(OUR_TAG_PREFIX):
            marker = devkit
        else:
            options = str(entry.get("LaunchOptions", ""))
            if OUR_LAUNCH_MARKER in options:
                m = re_search_appname(options)
                if m:
                    store = {
                        "gog": "gog",
                        "legendary": "epic",
                        "nile": "amazon",
                        "sideload": "sideload",
                    }.get(m[1], m[1])
                    marker = f"{OUR_TAG_PREFIX}{store}:{m[0]}"
        if marker is None:
            continue
        appid = entry.get("appid")
        if not appid:
            exe = str(entry.get("Exe", "")).strip('"')
            name = str(entry.get("AppName", ""))
            appid = shortcut_id(exe, name)
        out[marker] = int(appid)
    return out


def re_search_appname(options: str) -> tuple[str, str] | None:
    """Extract (app_name, runner) from LaunchOptions containing a
    heroic://launch?appName=..&runner=.. URL."""
    import re

    m = re.search(
        r"heroic://launch\?appName=([^&\s\"]+)&runner=([a-z]+)", options
    )
    if not m:
        return None
    return urllib.parse.unquote(m.group(1)), m.group(2)


def read_shortcuts(data: bytes) -> dict[str, Any]:
    """Parse shortcuts.vdf bytes; empty/blank input yields an empty doc."""
    if not data.strip(b"\x00 \n\r\t"):
        return {"shortcuts": {}}
    return parse_vdf(data)


def write_shortcuts(doc: dict[str, Any]) -> bytes:
    """Serialize a shortcuts.vdf document back to bytes.

    Mirrors Steam's own writer, which appends an extra end-of-dict marker
    after the root node.
    """
    return serialize_vdf(doc) + b"\x08"
