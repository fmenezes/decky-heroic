import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "py_modules"))

from platform_utils import (
    get_heroic_app_path,
    get_heroic_config_candidates,
    get_steam_shortcut_params,
    get_steam_userdata_candidates,
    is_linux,
    is_macos,
    is_windows,
)


class PlatformUtilsTests(unittest.TestCase):
    def test_os_checks_are_boolean(self):
        self.assertIsInstance(is_macos(), bool)
        self.assertIsInstance(is_linux(), bool)
        self.assertIsInstance(is_windows(), bool)

    def test_get_heroic_config_candidates_returns_paths(self):
        home = Path("/mock/home")
        candidates = get_heroic_config_candidates(home)
        self.assertTrue(len(candidates) >= 2)
        self.assertTrue(all(isinstance(p, Path) for p in candidates))

    @patch("platform_utils.is_macos", return_value=True)
    def test_macos_candidate_order(self, mock_mac):
        home = Path("/mock/home")
        candidates = get_heroic_config_candidates(home)
        self.assertEqual(candidates[0], home / "Library" / "Application Support" / "heroic")

    @patch("platform_utils.is_linux", return_value=True)
    @patch("platform_utils.is_macos", return_value=False)
    @patch("platform_utils.is_windows", return_value=False)
    def test_linux_candidate_order(self, mock_win, mock_mac, mock_lin):
        home = Path("/mock/home")
        candidates = get_heroic_config_candidates(home)
        self.assertEqual(candidates[0], home / ".var" / "app" / "com.heroicgameslauncher.hgl" / "config" / "heroic")
        self.assertEqual(candidates[1], home / ".config" / "heroic")

    @patch("platform_utils.is_macos", return_value=True)
    def test_macos_steam_userdata(self, mock_mac):
        home = Path("/mock/home")
        candidates = get_steam_userdata_candidates(home)
        self.assertEqual(candidates[0], home / "Library" / "Application Support" / "Steam" / "userdata")

    @patch("platform_utils.is_macos", return_value=True)
    def test_macos_shortcut_params(self, mock_mac):
        exe, start_dir, launch_options = get_steam_shortcut_params("heroic://test")
        self.assertIn("Heroic.app", exe)
        self.assertEqual(launch_options, '"heroic://test"')

        exe_launcher, _, opts_launcher = get_steam_shortcut_params("")
        self.assertEqual(opts_launcher, "--console")

    @patch("platform_utils.is_linux", return_value=True)
    @patch("platform_utils.is_macos", return_value=False)
    @patch("platform_utils.is_windows", return_value=False)
    def test_linux_flatpak_shortcut_params(self, mock_win, mock_mac, mock_lin):
        exe, start_dir, launch_options = get_steam_shortcut_params(
            "heroic://test", heroic_config=Path("/mock/.var/app/com.heroicgameslauncher.hgl/config/heroic")
        )
        self.assertIn("flatpak", exe)
        self.assertIn("run com.heroicgameslauncher.hgl", launch_options)

        _, _, opts_launcher = get_steam_shortcut_params(
            "", heroic_config=Path("/mock/.var/app/com.heroicgameslauncher.hgl/config/heroic")
        )
        self.assertIn("--console", opts_launcher)


if __name__ == "__main__":
    unittest.main()
