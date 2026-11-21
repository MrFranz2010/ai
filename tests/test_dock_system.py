"""Batteria e appunti: funzioni pure verificate senza Tk."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nokk_dock import settings, system


class BatteryTests(unittest.TestCase):
    def test_no_battery_means_mains_power(self):
        with tempfile.TemporaryDirectory() as folder:
            state = system.read_battery(platform="linux", root=folder)
        self.assertFalse(state.present)
        self.assertEqual(state.label, "Rete elettrica")

    def test_charging_battery_is_read_from_sysfs(self):
        with tempfile.TemporaryDirectory() as folder:
            battery = Path(folder) / "BAT0"
            battery.mkdir()
            (battery / "capacity").write_text("82\n")
            (battery / "status").write_text("Charging\n")
            state = system.read_battery(platform="linux", root=folder)
        self.assertTrue(state.present)
        self.assertEqual(state.percent, 82.0)
        self.assertTrue(state.charging)
        self.assertTrue(state.plugged)
        self.assertEqual(state.label, "82% · in carica")

    def test_discharging_battery(self):
        with tempfile.TemporaryDirectory() as folder:
            battery = Path(folder) / "BAT1"
            battery.mkdir()
            (battery / "capacity").write_text("41")
            (battery / "status").write_text("Discharging")
            state = system.read_battery(platform="linux", root=folder)
        self.assertEqual(state.label, "41% · batteria")
        self.assertFalse(state.plugged)

    def test_broken_battery_file_is_ignored(self):
        with tempfile.TemporaryDirectory() as folder:
            battery = Path(folder) / "BAT0"
            battery.mkdir()
            (battery / "capacity").write_text("n/d")
            state = system.read_battery(platform="linux", root=folder)
        self.assertFalse(state.present)


class ClipboardTests(unittest.TestCase):
    def test_preview_collapses_newlines(self):
        self.assertEqual(
            system.clipboard_preview("  prima\n\nseconda\t riga  "),
            "prima seconda riga",
        )

    def test_preview_is_truncated(self):
        self.assertEqual(system.clipboard_preview("abcdefghij", limit=5), "abcd…")

    def test_preview_of_empty_text(self):
        self.assertEqual(system.clipboard_preview(""), "")
        self.assertEqual(system.clipboard_preview(None), "")


class MigrationTests(unittest.TestCase):
    def test_old_configs_gain_the_clipboard_page(self):
        config = settings.default_config()
        config["version"] = 1
        config["widgets"] = ["music", "weather", "clock", "nokk", "capture", "settings"]
        clean = settings.validate_config(config)
        self.assertEqual(
            clean["widgets"],
            ["music", "weather", "clock", "clipboard", "nokk", "capture", "settings"],
        )
        self.assertEqual(clean["version"], 2)


if __name__ == "__main__":
    unittest.main()
