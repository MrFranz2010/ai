"""Test delle aggiunte ispirate alle dock native (nessun display richiesto).

Coprono la molla dell'animazione, l'ingrandimento magnetico del layout, la
gestione delle copertine e le nuove chiavi di configurazione.
"""

from __future__ import annotations

import base64
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nokk_dock import artwork, layout, media, motion, settings, theme

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg=="
)


class SpringTests(unittest.TestCase):
    def test_converges_without_overshooting_wildly(self):
        value, velocity, target = 0.0, 0.0, 1.0
        peak = 0.0
        for _ in range(240):
            value, velocity = motion.spring_step(value, target, velocity)
            peak = max(peak, value)
        self.assertAlmostEqual(value, target, places=3)
        self.assertLess(peak, target + 0.05)

    def test_rises_without_reversing_before_the_target(self):
        value, velocity = 0.0, 0.0
        previous = value
        for _ in range(200):
            value, velocity = motion.spring_step(value, 1.0, velocity)
            if previous < 0.98:
                self.assertGreaterEqual(value, previous - 1e-9)
            previous = value

    def test_overshoots_like_a_native_notch_but_only_slightly(self):
        value, velocity, peak = 0.0, 0.0, 0.0
        for _ in range(200):
            value, velocity = motion.spring_step(value, 1.0, velocity)
            peak = max(peak, value)
        self.assertGreater(peak, 1.0)
        self.assertLess(peak, 1.05)
        self.assertAlmostEqual(value, 1.0, places=3)

    def test_settled(self):
        self.assertTrue(motion.settled(1.0, 1.0, 0.0))
        self.assertFalse(motion.settled(0.0, 1.0, 0.0))

    def test_ease_out_cubic(self):
        self.assertAlmostEqual(motion.ease_out_cubic(0.0), 0.0)
        self.assertAlmostEqual(motion.ease_out_cubic(1.0), 1.0)
        self.assertGreater(motion.ease_out_cubic(0.5), 0.5)


class MagnificationTests(unittest.TestCase):
    def test_curve_falls_off(self):
        self.assertAlmostEqual(motion.magnification_factor(0.0, 120.0, 1.25), 1.25)
        self.assertAlmostEqual(motion.magnification_factor(120.0, 120.0, 1.25), 1.0)
        self.assertAlmostEqual(motion.magnification_factor(400.0, 120.0, 1.25), 1.0)
        middle = motion.magnification_factor(60.0, 120.0, 1.25)
        self.assertGreater(middle, 1.0)
        self.assertLess(middle, 1.25)

    def test_disabled_when_strength_is_one(self):
        self.assertEqual(motion.magnification_factor(0.0, 120.0, 1.0), 1.0)

    def test_curve_is_monotonic(self):
        distances = [step * 10.0 for step in range(0, 14)]
        factors = [motion.magnification_factor(d, 120.0, 1.4) for d in distances]
        for previous, current in zip(factors, factors[1:]):
            self.assertLessEqual(current, previous + 1e-9)


class LayoutMagnificationTests(unittest.TestCase):
    widgets = ["music", "weather", "clock", "nokk", "capture", "settings"]

    def layout(self, **kwargs):
        options = dict(
            position="bottom",
            screen_width=1920,
            screen_height=1080,
            widgets=self.widgets,
            thickness=60,
            length=660,
            margin=18,
            offset=0.5,
            expand=1.0,
            scale=1.0,
        )
        options.update(kwargs)
        return layout.compute_layout(**options)

    def test_default_layout_keeps_tiles_flat(self):
        plan = self.layout()
        self.assertTrue(all(tile.magnify == 1.0 for tile in plan.tiles))

    def test_pointer_grows_nearest_tile_most(self):
        base = self.layout()
        first = base.tiles[0]
        pointer = base.x + first.x + first.width / 2
        plan = self.layout(pointer=float(pointer), magnify=1.4, influence=420.0)
        factors = [tile.magnify for tile in plan.tiles]
        self.assertAlmostEqual(factors[0], 1.4, places=1)
        self.assertGreater(factors[1], 1.0)
        self.assertLess(factors[1], factors[0])
        self.assertAlmostEqual(factors[-1], 1.0, places=1)

    def test_influence_limits_the_reach(self):
        base = self.layout()
        first = base.tiles[0]
        pointer = base.x + first.x + first.width / 2
        plan = self.layout(pointer=float(pointer), magnify=1.4)
        factors = [tile.magnify for tile in plan.tiles]
        self.assertAlmostEqual(factors[0], 1.4, places=1)
        self.assertEqual(factors[1:], [1.0] * (len(factors) - 1))

    def test_magnified_dock_stays_on_screen(self):
        plan = self.layout(pointer=700.0, magnify=1.6)
        self.assertGreaterEqual(plan.x, 0)
        self.assertGreaterEqual(plan.y, 0)
        self.assertLessEqual(plan.x + plan.width, 1920)
        self.assertLessEqual(plan.y + plan.height, 1080)

    def test_vertical_dock_magnifies_on_y_axis(self):
        base = self.layout(position="left")
        tile = base.tiles[1]
        pointer = base.y + tile.y + tile.height / 2
        plan = self.layout(position="left", pointer=float(pointer), magnify=1.4)
        self.assertFalse(plan.horizontal)
        self.assertGreater(plan.tiles[1].magnify, plan.tiles[0].magnify)
        self.assertLessEqual(plan.y + plan.height, 1080)


class NotchLayoutTests(unittest.TestCase):
    widgets = LayoutMagnificationTests.widgets

    def build(self, expand, **kwargs):
        options = dict(
            position="bottom",
            screen_width=1920,
            screen_height=1080,
            widgets=self.widgets,
            thickness=60,
            length=660,
            margin=18,
            offset=0.0,
            expand=expand,
            scale=1.0,
            style="notch",
        )
        options.update(kwargs)
        return layout.compute_layout(**options)

    def test_collapsed_is_a_compact_pill_at_top_centre(self):
        plan = self.build(0.0)
        self.assertEqual(plan.style, "notch")
        self.assertTrue(plan.horizontal)
        self.assertLessEqual(plan.width, int(layout.NOTCH_WIDTH) + 1)
        self.assertLess(plan.height, 45)
        self.assertEqual(plan.y, 0)
        self.assertAlmostEqual(plan.x + plan.width / 2, 960, delta=1)

    def test_opening_reveals_the_full_panel(self):
        collapsed = self.build(0.0)
        opened = self.build(1.0)
        self.assertGreater(opened.width, collapsed.width * 2)
        self.assertGreater(opened.height, collapsed.height)
        self.assertLessEqual(opened.x + opened.width, 1920)
        self.assertLessEqual(opened.y + opened.height, 1080)
        # il contenuto non viene compresso: si svela crescendo
        self.assertEqual(opened.tiles[0].width, collapsed.tiles[0].width)

    def test_notch_is_glued_to_the_top_edge(self):
        for margin in (0, 18, 60):
            with self.subTest(margin=margin):
                self.assertEqual(self.build(0.0, margin=margin).y, 0)

    def test_offset_does_not_move_the_notch(self):
        self.assertEqual(self.build(1.0, offset=0.0).x, self.build(1.0, offset=1.0).x)

    def test_dock_style_keeps_the_edge_bar(self):
        plan = self.build(0.0, style="dock")
        self.assertEqual(plan.style, "dock")
        self.assertGreater(plan.width, 300)


class ThemeTests(unittest.TestCase):
    def test_default_palette_is_black_and_white(self):
        palette = theme.build_theme({})
        self.assertEqual(palette.preset, "nokk")
        self.assertEqual(palette.background, "#000000")
        self.assertEqual(palette.accent, "#ffffff")
        self.assertGreater(theme.luminance(palette.text), 0.85)
        self.assertLess(theme.luminance(palette.muted), theme.luminance(palette.text))
        self.assertEqual(palette.on_accent, "#0b0e14")


class SettingsMagnifyTests(unittest.TestCase):
    def test_style_default_and_validation(self):
        config = settings.default_config()
        self.assertEqual(config["dock"]["style"], "notch")
        config["dock"]["style"] = "Dock"
        self.assertEqual(settings.validate_config(config)["dock"]["style"], "dock")
        config["dock"]["style"] = "boh"
        with self.assertRaises(ValueError):
            settings.validate_config(config)

    def test_defaults(self):
        config = settings.default_config()
        self.assertAlmostEqual(config["dock"]["magnify"], 1.25)
        self.assertTrue(config["dock"]["show_labels"])

    def test_magnify_is_clamped(self):
        for value, expected in ((9.0, 1.6), (0.2, 1.0), (1.3, 1.3)):
            with self.subTest(value=value):
                config = settings.default_config()
                config["dock"]["magnify"] = value
                clean = settings.validate_config(config)
                self.assertAlmostEqual(clean["dock"]["magnify"], expected)

    def test_labels_accept_boolean(self):
        config = settings.default_config()
        config["dock"]["show_labels"] = False
        self.assertFalse(settings.validate_config(config)["dock"]["show_labels"])


class ArtworkTests(unittest.TestCase):
    def test_url_support(self):
        self.assertTrue(artwork.url_supported("https://i.scdn.co/image/abc.jpg"))
        self.assertTrue(artwork.url_supported("file:///tmp/cover.png"))
        self.assertFalse(artwork.url_supported("ftp://example.com/cover.png"))
        self.assertFalse(artwork.url_supported(""))
        self.assertFalse(artwork.url_supported(None))

    def test_cache_key_is_stable(self):
        self.assertEqual(
            artwork.cache_key("https://example.test/a.png"),
            artwork.cache_key(" https://example.test/a.png "),
        )
        self.assertNotEqual(
            artwork.cache_key("https://example.test/a.png"),
            artwork.cache_key("https://example.test/b.png"),
        )

    def test_download_then_reuse_cache(self):
        calls = []

        def downloader(url):
            calls.append(url)
            return PNG_BYTES

        with tempfile.TemporaryDirectory() as temporary:
            first = artwork.local_path(
                "https://example.test/cover.png", directory=temporary, downloader=downloader
            )
            self.assertIsNotNone(first)
            self.assertTrue(Path(first).exists())
            self.assertEqual(Path(first).suffix, ".png")
            second = artwork.local_path(
                "https://example.test/cover.png", directory=temporary, downloader=downloader
            )
            self.assertEqual(Path(second), Path(first))
            self.assertEqual(len(calls), 1)

    def test_oversized_download_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = artwork.local_path(
                "https://example.test/big.png",
                directory=temporary,
                downloader=lambda _url: b"x" * (artwork.MAX_BYTES + 1),
            )
            self.assertIsNone(path)

    def test_local_file_scheme(self):
        with tempfile.TemporaryDirectory() as temporary:
            cover = Path(temporary) / "cover.png"
            cover.write_bytes(PNG_BYTES)
            resolved = artwork.local_path(cover.as_uri())
            self.assertIsNotNone(resolved)
            self.assertEqual(Path(resolved), cover)

    def test_missing_local_file(self):
        self.assertIsNone(artwork.local_path("file:///nonexistent/nokk/cover.png"))

    def test_thumbnail_buckets(self):
        self.assertEqual(artwork.thumbnail_size(38), 40)
        self.assertEqual(artwork.thumbnail_size(64), 64)
        self.assertEqual(artwork.thumbnail_size(1000), max(artwork.THUMBNAIL_SIZES))

    def test_thumbnail_and_accent(self):
        with tempfile.TemporaryDirectory() as temporary:
            cover = Path(temporary) / "cover.png"
            cover.write_bytes(PNG_BYTES)
            data = artwork.thumbnail_bytes(cover, 40)
            self.assertIsNotNone(data)
            self.assertTrue(data.startswith(b"\x89PNG"))
            accent = artwork.accent_color(cover)
            if accent is not None:
                self.assertRegex(accent, r"^#[0-9a-f]{6}$")

    def test_thumbnail_without_path(self):
        self.assertIsNone(artwork.thumbnail_bytes(None, 40))
        self.assertIsNone(artwork.accent_color(None))


class MediaArtTests(unittest.TestCase):
    def test_parse_metadata_with_art_url(self):
        payload = "\x1f".join(
            ["Playing", "Artista", "Brano", "Album", "1500000", "https://i.scdn.co/image/x.jpg"]
        )
        state = media.parse_metadata(payload)
        self.assertEqual(state.art_url, "https://i.scdn.co/image/x.jpg")
        self.assertEqual(state.title, "Brano")

    def test_parse_metadata_without_art_url(self):
        state = media.parse_metadata("\x1f".join(["Paused", "A", "T", "Alb", "1000"]))
        self.assertEqual(state.art_url, "")


if __name__ == "__main__":
    unittest.main()
