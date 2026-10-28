import sys
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "py_modules"))

from steam_shortcuts import (
    build_shortcut,
    is_ours,
    merge_shortcuts,
    parse_vdf,
    read_shortcuts,
    serialize_vdf,
    shortcut_id,
    synced_markers,
    write_shortcuts,
)


GOLDEN = (
    b"\x00shortcuts\x00"
    b"\x000\x00"
    b"\x02appid\x00\x00\x00\x00\x00"
    b"\x01AppName\x00Existing Game\x00"
    b"\x01Exe\x00\"/usr/bin/steam-game\"\x00"
    b"\x08\x08"
)


class VdfRoundtripTests(unittest.TestCase):
    def test_parse_golden(self):
        doc = parse_vdf(GOLDEN)
        self.assertIn("shortcuts", doc)
        entry = doc["shortcuts"]["0"]
        self.assertEqual(entry["AppName"], "Existing Game")
        self.assertEqual(entry["appid"], 0)

    def test_roundtrip(self):
        doc = read_shortcuts(GOLDEN)
        again = parse_vdf(write_shortcuts(doc))
        self.assertEqual(again, doc)

    def test_empty_input_yields_empty_doc(self):
        self.assertEqual(read_shortcuts(b""), {"shortcuts": {}})
        self.assertEqual(read_shortcuts(b"\x00" * 16), {"shortcuts": {}})

    def test_malformed_raises(self):
        with self.assertRaises(ValueError):
            parse_vdf(b"\xffnonsense\xff")

    def test_serialize_rejects_unsupported_types(self):
        with self.assertRaises(TypeError):
            serialize_vdf({"x": 1.5})


class ShortcutTests(unittest.TestCase):
    def test_shortcut_id_is_stable_and_high_bit_set(self):
        sid = shortcut_id("/usr/bin/flatpak", "Hogwarts Legacy")
        self.assertEqual(sid, shortcut_id("/usr/bin/flatpak", "Hogwarts Legacy"))
        self.assertNotEqual(sid, shortcut_id("/usr/bin/flatpak", "Mafia II"))
        self.assertEqual(sid & 0x80000000, 0x80000000)
        self.assertEqual(
            sid,
            (zlib.crc32(b"/usr/bin/flatpakHogwarts Legacy") & 0xFFFFFFFF)
            | 0x80000000,
        )

    def test_is_ours(self):
        ours = build_shortcut("X", "/bin/flatpak", "run a b", "/bin", "heroic:gog:1")
        theirs = dict(ours, DevKitGameID="")
        self.assertTrue(is_ours(ours))
        self.assertFalse(is_ours(theirs))

    def test_merge_keeps_foreign_and_is_idempotent(self):
        foreign = build_shortcut("Foreign", "/bin/x", "", "/bin", "")
        ours = build_shortcut("Mine", "/bin/flatpak", "run a b", "/bin", "heroic:epic:1")
        doc = {"shortcuts": {"0": foreign, "1": ours}}
        merged, added, removed = merge_shortcuts(doc, [ours])
        self.assertEqual(added, 1)
        self.assertEqual(removed, 1)
        entries = list(merged["shortcuts"].values())
        self.assertEqual(len(entries), 2)
        self.assertIn(foreign, entries)
        # re-running the same sync changes nothing
        merged2, added2, removed2 = merge_shortcuts(merged, [ours])
        self.assertEqual((added2, removed2), (1, 1))
        self.assertEqual(merged2, merged)

    def test_merge_on_empty(self):
        merged, added, removed = merge_shortcuts({"shortcuts": {}}, [])
        self.assertEqual((added, removed), (0, 0))
        self.assertEqual(merged, {"shortcuts": {}})

    def test_full_pipeline_roundtrip(self):
        ours = build_shortcut(
            "Hogwarts Legacy", "/usr/bin/flatpak", "run hgl url", "/usr/bin",
            "heroic:epic:fa4240",
        )
        doc, _, _ = merge_shortcuts(read_shortcuts(b""), [ours])
        data = write_shortcuts(doc)
        reparsed = read_shortcuts(data)
        self.assertEqual(reparsed["shortcuts"]["0"]["AppName"], "Hogwarts Legacy")
        self.assertTrue(is_ours(reparsed["shortcuts"]["0"]))


    def test_synced_markers_maps_to_shortcut_ids(self):
        ours = build_shortcut(
            "Hogwarts Legacy", "/usr/bin/flatpak", "run hgl url", "/usr/bin",
            "heroic:epic:fa4240",
        )
        foreign = build_shortcut("Foreign", "/bin/x", "", "/bin", "")
        doc, _, _ = merge_shortcuts(read_shortcuts(b""), [foreign, ours])
        markers = synced_markers(doc)
        self.assertEqual(list(markers.keys()), ["heroic:epic:fa4240"])
        self.assertEqual(
            markers["heroic:epic:fa4240"],
            shortcut_id("/usr/bin/flatpak", "Hogwarts Legacy"),
        )


if __name__ == "__main__":
    unittest.main()
