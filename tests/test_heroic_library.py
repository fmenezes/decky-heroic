import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "py_modules"))

from heroic_library import (
    find_heroic_config,
    get_library,
    inspect_heroic_settings,
    is_store_logged_in,
    launch_url,
    parse_library_file,
    parse_sideloads,
)

FIXTURES = Path(__file__).parent / "fixtures"


class ParseLibraryFileTests(unittest.TestCase):
    def test_gog_fixture(self):
        games = parse_library_file(FIXTURES / "gog_library.json", "gog", "games")
        titles = [g["title"] for g in games]
        # gog-redist must be filtered out
        self.assertNotIn("Galaxy Common Redistributables", titles)
        self.assertEqual(len(games), 2)
        rebel = next(g for g in games if g["app_name"] == "1435582019")
        self.assertTrue(rebel["is_installed"])
        self.assertEqual(rebel["install_size"], "2.5 GiB")
        self.assertTrue(rebel["cloud_saves"])
        self.assertEqual(rebel["store"], "gog")

    def test_epic_fixture(self):
        games = parse_library_file(
            FIXTURES / "legendary_library.json", "epic", "library"
        )
        self.assertEqual(len(games), 3)
        hlp = next(g for g in games if g["app_name"].startswith("fa4240"))
        self.assertTrue(hlp["is_installed"])
        self.assertEqual(hlp["runner"], "legendary")
        self.assertEqual(hlp["install_size"], "71.2 GiB")
        # empty art string must be preserved as "", not None
        sleeper = next(g for g in games if "Citizen" in g["title"])
        self.assertEqual(sleeper["art_square"], "")

    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            parse_library_file(FIXTURES / "nope.json", "gog", "games")


class GetLibraryTests(unittest.TestCase):
    def _make_config_dir(self, tmp: str, copy_fixtures: bool) -> Path:
        """Build a Heroic config dir in tmp, optionally seeding store_cache
        with the fixture library files."""
        config = Path(tmp)
        store_cache = config / "store_cache"
        store_cache.mkdir()
        if copy_fixtures:
            for fixture in FIXTURES.glob("*_library.json"):
                shutil.copy(fixture, store_cache / fixture.name)
        return config

    def test_merges_stores_and_sorts(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = self._make_config_dir(tmp, copy_fixtures=True)
            result = get_library(config)
            self.assertEqual(result["errors"], [])
            installed = [g["title"] for g in result["games"] if g["is_installed"]]
            not_installed = [g["title"] for g in result["games"] if not g["is_installed"]]
            # installed games all come first, alphabetical within each group
            self.assertEqual(
                [g["is_installed"] for g in result["games"]],
                [True] * len(installed) + [False] * len(not_installed),
            )
            self.assertEqual(len(result["games"]), 7)

    def test_missing_store_is_skipped_silently(self):
        """A store that was never synced (no library file) is not an error."""
        with tempfile.TemporaryDirectory() as tmp:
            config = self._make_config_dir(tmp, copy_fixtures=False)
            config.joinpath("store_cache", "gog_library.json").write_text(
                json.dumps({"games": []}), encoding="utf-8"
            )
            result = get_library(config)
            self.assertEqual(result["games"], [])
            self.assertEqual(result["errors"], [])

    def test_corrupt_store_reports_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = self._make_config_dir(tmp, copy_fixtures=False)
            store_cache = config / "store_cache"
            store_cache.joinpath("gog_library.json").write_text(
                "{not json", encoding="utf-8"
            )
            shutil.copy(
                FIXTURES / "legendary_library.json",
                store_cache / "legendary_library.json",
            )
            result = get_library(config)
            self.assertEqual(len(result["errors"]), 1)
            self.assertIn("gog", result["errors"][0])
            # the other store's games are still returned
            self.assertEqual(len(result["games"]), 3)


class FindHeroicConfigTests(unittest.TestCase):
    def _candidate(self, tmp: str) -> Path:
        path = Path(tmp) / "heroic-config"
        path.joinpath("store_cache").mkdir(parents=True)
        return path

    def test_finds_first_candidate_with_store_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = self._candidate(tmp)
            bad = Path(tmp) / "no-store-cache"
            bad.mkdir()
            self.assertEqual(
                find_heroic_config(candidates=[bad, good]), good
            )

    def test_candidate_order_takes_precedence(self):
        with tempfile.TemporaryDirectory() as tmp1, tempfile.TemporaryDirectory() as tmp2:
            first = self._candidate(tmp1)
            second = self._candidate(tmp2)
            self.assertEqual(
                find_heroic_config(candidates=[first, second]),
                first,
            )

    def test_returns_none_when_nothing_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(
                find_heroic_config(candidates=[Path(tmp) / "missing"])
            )

    def test_ignores_candidate_without_store_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "heroic-config"
            path.mkdir()
            self.assertIsNone(find_heroic_config(candidates=[path]))


class LaunchUrlTests(unittest.TestCase):
    def test_epic_url(self):
        self.assertEqual(
            launch_url("fa4240e57a3c46b39f169041b7811293", "legendary"),
            "heroic://launch?appName=fa4240e57a3c46b39f169041b7811293"
            "&runner=legendary",
        )

    def test_gog_url(self):
        self.assertEqual(
            launch_url("1449710114", "gog"),
            "heroic://launch?appName=1449710114&runner=gog",
        )

    def test_amazon_url(self):
        self.assertEqual(
            launch_url("amzn1.adg.product.9f8a01b5", "nile"),
            "heroic://launch?appName=amzn1.adg.product.9f8a01b5&runner=nile",
        )

    def test_sideload_url(self):
        self.assertEqual(
            launch_url("my-game", "sideload"),
            "heroic://launch?appName=my-game&runner=sideload",
        )

    def test_app_name_is_urlencoded(self):
        self.assertEqual(
            launch_url("my game", "sideload"),
            "heroic://launch?appName=my%20game&runner=sideload",
        )


class AmazonAndSideloadTests(unittest.TestCase):
    def test_amazon_fixture(self):
        games = parse_library_file(
            FIXTURES / "nile_library.json", "amazon", "library"
        )
        self.assertEqual(len(games), 2)
        installed = next(g for g in games if g["is_installed"])
        self.assertEqual(installed["store"], "amazon")
        self.assertEqual(installed["install_size"], "14.1 GiB")
        self.assertTrue(installed["cloud_saves"])

    def test_sideloads_parsed_from_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            sideload_dir = Path(tmp) / "sideload_apps"
            sideload_dir.mkdir()
            (sideload_dir / "my-game.json").write_text(
                json.dumps(
                    {
                        "title": "My Game",
                        "app_name": "sideload-my-game",
                        "runner": "sideload",
                        "is_installed": False,
                    }
                ),
                encoding="utf-8",
            )
            # invalid json files are ignored
            (sideload_dir / "broken.json").write_text("{nope", encoding="utf-8")
            games = parse_sideloads(sideload_dir)
            self.assertEqual(len(games), 1)
            self.assertEqual(games[0]["title"], "My Game")
            self.assertTrue(games[0]["is_installed"])
            self.assertEqual(games[0]["store"], "sideload")

    def test_missing_sideload_dir_yields_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(parse_sideloads(Path(tmp) / "sideload_apps"), [])

    def test_get_library_includes_sideloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp)
            store_cache = config / "store_cache"
            store_cache.mkdir()
            store_cache.joinpath("gog_library.json").write_text(
                json.dumps({"games": []}), encoding="utf-8"
            )
            sideload_dir = config / "sideload_apps"
            sideload_dir.mkdir()
            (sideload_dir / "x.json").write_text(
                json.dumps({"title": "X", "app_name": "sideload-x"}),
                encoding="utf-8",
            )
            result = get_library(config)
            self.assertEqual(
                [g["title"] for g in result["games"]], ["X"]
            )
            # missing nile/legendary libraries are not errors anymore
            self.assertEqual(result["errors"], [])


class StoreLoggedInTests(unittest.TestCase):
    def test_sideload_always_logged_in(self):
        self.assertTrue(is_store_logged_in(None, "sideload"))

    def test_missing_config_returns_false(self):
        self.assertFalse(is_store_logged_in(None, "gog"))
        self.assertFalse(is_store_logged_in(None, "epic"))
        self.assertFalse(is_store_logged_in(None, "amazon"))

    def test_detects_library_cache_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp)
            store_cache = config / "store_cache"
            store_cache.mkdir()
            self.assertFalse(is_store_logged_in(config, "gog"))
            (store_cache / "gog_library.json").write_text("{}", encoding="utf-8")
            self.assertTrue(is_store_logged_in(config, "gog"))

    def test_detects_auth_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp)
            gog_store = config / "gog_store"
            gog_store.mkdir()
            (gog_store / "auth.json").write_text("{}", encoding="utf-8")
            self.assertTrue(is_store_logged_in(config, "gog"))


class InspectHeroicSettingsTests(unittest.TestCase):
    def test_none_or_missing_config_returns_empty(self):
        self.assertEqual(inspect_heroic_settings(None), [])
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(inspect_heroic_settings(Path(tmp)), [])

    def test_optimal_settings_has_no_warnings(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp)
            wine_bin = config / "wine"
            wine_bin.write_text("fake binary")
            cfg_data = {
                "defaultSettings": {
                    "addSteamShortcuts": False,
                    "hideWindowOnProtocolLaunch": True,
                    "wineVersion": {
                        "bin": str(wine_bin),
                        "name": "Proton Test",
                    },
                }
            }
            (config / "config.json").write_text(json.dumps(cfg_data), encoding="utf-8")
            warnings = inspect_heroic_settings(config)
            self.assertEqual(warnings, [])

    def test_warns_on_add_steam_shortcuts(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp)
            wine_bin = config / "wine"
            wine_bin.write_text("fake binary")
            cfg_data = {
                "defaultSettings": {
                    "addSteamShortcuts": True,
                    "hideWindowOnProtocolLaunch": True,
                    "wineVersion": {"bin": str(wine_bin), "name": "Proton"},
                }
            }
            (config / "config.json").write_text(json.dumps(cfg_data), encoding="utf-8")
            warnings = inspect_heroic_settings(config)
            self.assertEqual(len(warnings), 1)
            self.assertEqual(warnings[0]["id"], "add_steam_shortcuts")

    def test_warns_on_show_window_on_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp)
            wine_bin = config / "wine"
            wine_bin.write_text("fake binary")
            cfg_data = {
                "defaultSettings": {
                    "addSteamShortcuts": False,
                    "hideWindowOnProtocolLaunch": False,
                    "wineVersion": {"bin": str(wine_bin), "name": "Proton"},
                }
            }
            (config / "config.json").write_text(json.dumps(cfg_data), encoding="utf-8")
            warnings = inspect_heroic_settings(config)
            self.assertEqual(len(warnings), 1)
            self.assertEqual(warnings[0]["id"], "hide_window_on_launch")

    def test_warns_on_missing_wine_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp)
            cfg_data = {
                "defaultSettings": {
                    "addSteamShortcuts": False,
                    "hideWindowOnProtocolLaunch": True,
                    "wineVersion": None,
                }
            }
            (config / "config.json").write_text(json.dumps(cfg_data), encoding="utf-8")
            warnings = inspect_heroic_settings(config)
            self.assertEqual(len(warnings), 1)
            self.assertEqual(warnings[0]["id"], "missing_wine_version")

    def test_warns_on_broken_wine_version_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp)
            cfg_data = {
                "defaultSettings": {
                    "addSteamShortcuts": False,
                    "hideWindowOnProtocolLaunch": True,
                    "wineVersion": {
                        "bin": "/nonexistent/path/to/proton",
                        "name": "Missing Proton",
                    },
                }
            }
            (config / "config.json").write_text(json.dumps(cfg_data), encoding="utf-8")
            warnings = inspect_heroic_settings(config)
            self.assertEqual(len(warnings), 1)
            self.assertEqual(warnings[0]["id"], "broken_wine_version")



if __name__ == "__main__":
    unittest.main()
