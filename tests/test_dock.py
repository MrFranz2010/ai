"""Test del dock di NOKK (nessuna sessione grafica richiesta)."""

from __future__ import annotations

import base64
import contextlib
import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nokk_dock import capture, client as nokk_client, hotkey, icons, ipc, layout, media, settings, theme, weather

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAIAAAD8GO2jAAAAKklEQVR4nGPQsKmgKWIYtWDUglELRi0Y"
    "tWDUglELRi0YtWDUglELhooFAAS5cC7WiDFbAAAAAElFTkSuQmCC"
)


def sample_png(size=900):
    return PNG_BYTES + b"\0" * max(0, size - len(PNG_BYTES))


class SettingsTests(unittest.TestCase):
    def test_defaults_are_valid(self):
        config = settings.validate_config(settings.default_config())
        self.assertEqual(config["dock"]["position"], "bottom")
        self.assertEqual(config["widgets"], list(settings.WIDGETS))
        self.assertEqual(config["capture"]["shortcut"], "ctrl+alt+n")
        self.assertEqual(config["theme"]["preset"], "nokk")

    def test_invalid_position_rejected(self):
        config = settings.default_config()
        config["dock"]["position"] = "middle"
        with self.assertRaises(ValueError):
            settings.validate_config(config)

    def test_invalid_colour_rejected(self):
        config = settings.default_config()
        config["theme"]["accent"] = "viola"
        with self.assertRaises(ValueError):
            settings.validate_config(config)

    def test_invalid_api_key_rejected(self):
        config = settings.default_config()
        config["nokk"]["api_key"] = "nokk_corta"
        with self.assertRaises(ValueError):
            settings.validate_config(config)

    def test_numbers_are_clamped(self):
        config = settings.default_config()
        config["dock"]["opacity"] = 5
        config["dock"]["thickness"] = 10
        config["theme"]["scale"] = 9
        clean = settings.validate_config(config)
        self.assertEqual(clean["dock"]["opacity"], 1.0)
        self.assertEqual(clean["dock"]["thickness"], 44)
        self.assertEqual(clean["theme"]["scale"], 1.6)

    def test_unknown_widget_rejected(self):
        config = settings.default_config()
        config["widgets"] = ["music", "pizza"]
        with self.assertRaises(ValueError):
            settings.validate_config(config)

    def test_duplicate_widgets_collapse(self):
        config = settings.default_config()
        config["widgets"] = ["clock", "clock", "music"]
        clean = settings.validate_config(config)
        self.assertEqual(clean["widgets"], ["clock", "music"])

    def test_shortcut_normalization(self):
        self.assertEqual(settings.normalize_shortcut("Ctrl + Alt + N"), "ctrl+alt+n")
        self.assertEqual(settings.normalize_shortcut("SUPER+space"), "super+space")
        with self.assertRaises(ValueError):
            settings.normalize_shortcut("ctrl+nope")

    def test_save_and_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "nokk" / "dock.json"
            config = settings.default_config()
            config["theme"]["accent"] = "#112233"
            config["weather"]["city"] = "Torino"
            written = settings.save_config(config, path)
            self.assertEqual(written, path)
            loaded = settings.load_config(path)
            self.assertEqual(loaded["theme"]["accent"], "#112233")
            self.assertEqual(loaded["weather"]["city"], "Torino")
            if not sys.platform.startswith("win"):
                self.assertEqual(path.stat().st_mode & 0o077, 0)

    def test_corrupt_file_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "dock.json"
            path.write_text("{ rotto", encoding="utf-8")
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                loaded = settings.load_config(path)
            self.assertEqual(loaded["dock"]["position"], "bottom")
            self.assertIn("predefiniti", buffer.getvalue())

    def test_environment_override(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "custom.json"
            with mock.patch.dict("os.environ", {"NOKK_DOCK_CONFIG": str(target)}):
                self.assertEqual(settings.config_path(), target)


class LayoutTests(unittest.TestCase):
    def check_plan(self, position, screen=(1920, 1080), expand=0.0, scale=1.0, widgets=None):
        plan = layout.compute_layout(
            position,
            screen[0],
            screen[1],
            widgets or list(layout.TILE_SPANS),
            thickness=60,
            length=660,
            margin=18,
            offset=0.5,
            expand=expand,
            scale=scale,
        )
        self.assertGreater(plan.width, 0)
        self.assertGreater(plan.height, 0)
        self.assertGreaterEqual(plan.x, 0)
        self.assertGreaterEqual(plan.y, 0)
        self.assertLessEqual(plan.x + plan.width, screen[0])
        self.assertLessEqual(plan.y + plan.height, screen[1])
        previous = None
        for tile in plan.tiles:
            if plan.horizontal:
                self.assertEqual(tile.height, plan.height)
                self.assertGreaterEqual(tile.x, 0)
                self.assertLessEqual(tile.right, plan.width)
                if previous is not None:
                    self.assertGreaterEqual(tile.x, previous.right)
            else:
                self.assertEqual(tile.width, plan.width)
                self.assertGreaterEqual(tile.y, 0)
                self.assertLessEqual(tile.bottom, plan.height)
                if previous is not None:
                    self.assertGreaterEqual(tile.y, previous.bottom)
            previous = tile
        return plan

    def test_all_positions_collapsed_and_expanded(self):
        for position in ("bottom", "top", "left", "right"):
            for expand in (0.0, 0.5, 1.0):
                with self.subTest(position=position, expand=expand):
                    self.check_plan(position, expand=expand)

    def test_edges_are_respected(self):
        bottom = self.check_plan("bottom")
        self.assertEqual(bottom.y + bottom.height + 18, 1080)
        top = self.check_plan("top")
        self.assertEqual(top.y, 18)
        left = self.check_plan("left")
        self.assertEqual(left.x, 18)
        right = self.check_plan("right")
        self.assertEqual(right.x + right.width + 18, 1920)

    def test_expanded_is_thicker(self):
        collapsed = self.check_plan("bottom", expand=0.0)
        expanded = self.check_plan("bottom", expand=1.0)
        self.assertGreater(expanded.height, collapsed.height)

    def test_widget_order_is_preserved(self):
        plan = self.check_plan("bottom", widgets=["clock", "music", "settings"])
        self.assertEqual([tile.key for tile in plan.tiles], ["clock", "music", "settings"])

    def test_long_dock_fits_small_screen(self):
        plan = self.check_plan("bottom", screen=(800, 600), expand=1.0)
        self.assertLessEqual(plan.width, 800)

    def test_vertical_dock_fits_short_screen(self):
        plan = self.check_plan("left", screen=(1280, 600), expand=1.0)
        self.assertLessEqual(plan.height, 600)

    def test_tile_lookup(self):
        plan = self.check_plan("bottom")
        first = plan.tiles[0]
        self.assertEqual(plan.tile_at(first.x + 1, first.y + 1).key, first.key)
        self.assertIsNone(plan.tile_at(-5, -5))

    def test_scale_grows_the_dock(self):
        small = self.check_plan("bottom", scale=0.8)
        large = self.check_plan("bottom", scale=1.2)
        self.assertGreater(large.height, small.height)


class ThemeTests(unittest.TestCase):
    def test_mix(self):
        self.assertEqual(theme.mix("#000000", "#ffffff", 0.5), "#808080")
        self.assertEqual(theme.mix("#101010", "#ffffff", 0.0), "#101010")

    def test_readable_text(self):
        self.assertEqual(theme.readable_text("#ffffff"), "#0b0e14")
        self.assertEqual(theme.readable_text("#101010"), "#ffffff")

    def test_overrides_and_presets(self):
        built = theme.build_theme({"preset": "sand"})
        self.assertTrue(built.light)
        custom = theme.build_theme({"preset": "nokk", "accent": "#ff0000"})
        self.assertEqual(custom.accent, "#ff0000")

    def test_pick_font(self):
        self.assertEqual(theme.pick_font(["Ubuntu", "DejaVu Sans"]), "Ubuntu")
        self.assertEqual(theme.pick_font([]), theme.FONT_STACK[-1])


class ClientTests(unittest.TestCase):
    def make_client(self, responses):
        calls = []

        def transport(method, url, headers, body, timeout):
            calls.append({"method": method, "url": url, "headers": headers, "body": body})
            return responses.pop(0)

        client = nokk_client.NokkClient(
            "http://127.0.0.1:8000",
            "nokk_" + "a" * 32,
            mode="studio",
            transport=transport,
            sleep=lambda _seconds: None,
            poll_interval=0,
        )
        return client, calls

    def test_ask_completes_job(self):
        client, calls = self.make_client([
            (202, json.dumps({"job_id": "b" * 32}).encode()),
            (200, json.dumps({"status": "running", "partial_reply": "Ciao"}).encode()),
            (200, json.dumps({"status": "complete", "reply": "Tutto ok"}).encode()),
        ])
        seen = []
        result = client.ask("Riassumi", on_status=lambda partial, status: seen.append(partial))
        self.assertEqual(result["reply"], "Tutto ok")
        self.assertTrue(seen)
        self.assertEqual(calls[0]["headers"]["X-API-Key"], "nokk_" + "a" * 32)
        payload = json.loads(calls[0]["body"].decode())
        self.assertEqual(payload["mode"], "studio")
        self.assertEqual(payload["messages"][0]["role"], "user")

    def test_image_attachment_is_sent(self):
        client, calls = self.make_client([
            (202, json.dumps({"job_id": "c" * 32}).encode()),
            (200, json.dumps({"status": "complete", "reply": "Vedo una finestra"}).encode()),
        ])
        image = {"data": "AAAA", "mime_type": "image/png", "name": "screenshot.png"}
        client.ask("Cosa vedi?", image=image)
        payload = json.loads(calls[0]["body"].decode())
        attachment = payload["messages"][-1]["attachments"][0]
        self.assertEqual(attachment["kind"], "image")
        self.assertEqual(attachment["mime_type"], "image/png")
        self.assertEqual(attachment["name"], "screenshot.png")

    def test_failed_job_raises(self):
        client, _calls = self.make_client([
            (202, json.dumps({"job_id": "d" * 32}).encode()),
            (200, json.dumps({"status": "failed", "error": "Provider spento"}).encode()),
        ])
        with self.assertRaises(nokk_client.NokkError) as raised:
            client.ask("Ciao")
        self.assertIn("Provider spento", raised.exception.message)

    def test_unauthorized_message(self):
        client, _calls = self.make_client([
            (401, json.dumps({"error": "no"}).encode()),
        ])
        with self.assertRaises(nokk_client.NokkError) as raised:
            client.ask("Ciao")
        self.assertIn("Chiave API", raised.exception.message)

    def test_health_returns_none_when_unreachable(self):
        def transport(*_args, **_kwargs):
            raise urllib.error.URLError("connection refused")

        client = nokk_client.NokkClient("http://127.0.0.1:9", "", transport=transport)
        self.assertIsNone(client.health())

    def test_error_messages(self):
        self.assertIn("60", nokk_client.error_message(429))
        self.assertIn("disattivata", nokk_client.error_message(403))
        self.assertIn("provider", nokk_client.error_message(409, {"error": "Configura provider"}).lower())

    def test_history_and_limits(self):
        messages = nokk_client.build_messages(
            "x" * 20000,
            history=[
                {"role": "user", "content": "prima"},
                {"role": "assistant", "content": "risposta"},
                {"role": "system", "content": "ignorato"},
            ],
        )
        self.assertEqual(len(messages), 3)
        self.assertLessEqual(len(messages[-1]["content"]), nokk_client.MAX_MESSAGE_CHARS)


class CaptureTests(unittest.TestCase):
    def test_sniff_mime(self):
        self.assertEqual(capture.sniff_mime(PNG_BYTES), ("image/png", ".png"))
        self.assertEqual(capture.sniff_mime(b"\xff\xd8\xff\x00"), ("image/jpeg", ".jpg"))
        self.assertEqual(capture.sniff_mime(b"nope"), (None, None))

    def test_candidate_tools_prefers_wayland(self):
        def which(name):
            return f"/usr/bin/{name}" if name in ("grim", "scrot") else None

        names = [
            name for name, _builder in capture.candidate_tools(
                which=which, environ={}, platform="linux"
            )
        ]
        self.assertIn("scrot", names)
        self.assertNotIn("grim", names)
        wayland = [
            name for name, _builder in capture.candidate_tools(
                which=which, environ={"WAYLAND_DISPLAY": "wayland-0"}, platform="linux"
            )
        ]
        self.assertEqual(wayland[0], "grim")

    def test_capture_with_fake_tool(self):
        def which(name):
            return "/usr/bin/scrot" if name == "scrot" else None

        def runner(argv, **_kwargs):
            Path(argv[-1]).write_bytes(sample_png())
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        path = capture.capture_screen(
            scale=0.8, runner=runner, which=which, environ={}, platform="linux"
        )
        try:
            self.assertTrue(Path(path).exists())
            self.assertGreater(Path(path).stat().st_size, 512)
        finally:
            capture.cleanup(path)

    def test_capture_without_tools_raises(self):
        with mock.patch.object(capture, "_grab_with_pillow", return_value=None):
            with self.assertRaises(capture.CaptureError) as raised:
                capture.capture_screen(which=lambda _name: None, environ={}, platform="linux")
        self.assertIn("cattura", str(raised.exception).lower())

    def test_load_image(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "shot.png"
            path.write_bytes(sample_png())
            image = capture.load_image(path)
            self.assertEqual(image["mime_type"], "image/png")
            self.assertEqual(image["name"], "screenshot.png")
            self.assertEqual(base64.b64decode(image["data"])[:8], PNG_BYTES[:8])

    def test_load_image_rejects_unknown_format(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "shot.bin"
            path.write_bytes(b"non e un immagine")
            with self.assertRaises(capture.CaptureError):
                capture.load_image(path)


class MediaTests(unittest.TestCase):
    def test_parse_metadata(self):
        state = media.parse_metadata("\x1f".join(["Playing", "Artista", "Brano", "Album", "1500000"]))
        self.assertTrue(state.playing)
        self.assertEqual(state.title, "Brano")
        self.assertEqual(state.subtitle, "Artista — Album")
        self.assertEqual(state.length_seconds, 1.5)
        self.assertEqual(state.timecode, "0:00 / 0:01")

    def test_parse_empty(self):
        state = media.parse_metadata("")
        self.assertFalse(state.active)
        self.assertEqual(state.message, "Nessun player attivo")

    def test_missing_playerctl(self):
        controller = media.MusicController(which=lambda _name: None)
        state = controller.refresh()
        self.assertFalse(state.installed)
        self.assertIn("playerctl", state.message)
        self.assertFalse(controller.play_pause())

    def test_refresh_with_position(self):
        def runner(argv, **_kwargs):
            if "metadata" in argv:
                return SimpleNamespace(
                    returncode=0,
                    stdout="\x1f".join(["Paused", "A", "T", "Alb", "120000000"]),
                    stderr="",
                )
            if "position" in argv:
                return SimpleNamespace(returncode=0, stdout="30.0", stderr="")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        controller = media.MusicController(runner=runner, which=lambda _name: "/usr/bin/playerctl")
        state = controller.refresh()
        self.assertEqual(state.title, "T")
        self.assertEqual(state.status, "Paused")
        self.assertAlmostEqual(state.length_seconds, 120.0)
        self.assertTrue(controller.next_track())

    def test_format_seconds(self):
        self.assertEqual(media.format_seconds(0), "0:00")
        self.assertEqual(media.format_seconds(125), "2:05")


class WeatherTests(unittest.TestCase):
    def test_describe_day_and_night(self):
        self.assertEqual(weather.describe(0, True), ("Sereno", "sun"))
        self.assertEqual(weather.describe(0, False)[1], "moon")
        self.assertEqual(weather.describe(95)[1], "storm")

    def test_urls(self):
        forecast = weather.forecast_url(45.07, 7.68, "imperial")
        self.assertIn("latitude=45.0700", forecast)
        self.assertIn("temperature_unit=fahrenheit", forecast)
        geocode = weather.geocode_url("Torino")
        self.assertIn("name=Torino", geocode)

    def test_parse_geocode(self):
        payload = {"results": [{"name": "Torino", "latitude": 45.07, "longitude": 7.68, "country_code": "IT"}]}
        self.assertEqual(weather.parse_geocode(payload), ("Torino, IT", 45.07, 7.68))
        self.assertIsNone(weather.parse_geocode({"results": []}))
        self.assertIsNone(weather.parse_geocode(None))

    def test_parse_forecast(self):
        payload = {
            "current": {
                "temperature_2m": 12.4,
                "apparent_temperature": 11.0,
                "is_day": 0,
                "weather_code": 0,
                "wind_speed_10m": 7.5,
            },
            "daily": {"temperature_2m_max": [15.2], "temperature_2m_min": [6.1]},
        }
        state = weather.parse_forecast(payload, units="metric", city="Torino")
        self.assertEqual(state.temperature_text, "12°C")
        self.assertEqual(state.icon, "moon")
        self.assertEqual(state.range_text, "min 6° · max 15°")

    def test_service_without_city(self):
        service = weather.WeatherService({"units": "metric", "city": ""})
        state = service.refresh()
        self.assertIn("città", state.error)

    def test_service_uses_coordinates(self):
        calls = []

        def fetcher(url):
            calls.append(url)
            return {
                "current": {"temperature_2m": 3, "weather_code": 3, "is_day": 1},
                "daily": {"temperature_2m_max": [5], "temperature_2m_min": [1]},
            }

        service = weather.WeatherService(
            {"units": "metric", "city": "Torino", "latitude": 45.07, "longitude": 7.68},
            fetcher=fetcher,
        )
        state = service.refresh()
        self.assertEqual(state.label, "Nuvoloso")
        self.assertEqual(len(calls), 1)

    def test_service_network_error(self):
        def fetcher(_url):
            raise OSError("rete assente")

        service = weather.WeatherService(
            {"units": "metric", "latitude": 1, "longitude": 2}, fetcher=fetcher
        )
        state = service.refresh()
        self.assertIn("raggiungibile", state.error)


class HotkeyTests(unittest.TestCase):
    def test_parse_shortcut(self):
        mask, keysym = hotkey.parse_shortcut("ctrl+alt+n")
        self.assertEqual(keysym, "n")
        self.assertEqual(mask, hotkey.CONTROL_MASK | hotkey.MOD1_MASK)
        self.assertEqual(hotkey.parse_shortcut("super+space")[1], "space")

    def test_invalid_shortcuts(self):
        for value in ("", "n", "ctrl+", "ctrl+pizza"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    hotkey.parse_shortcut(value)

    def test_unavailable_without_display(self):
        grabber = hotkey.X11Hotkey("ctrl+alt+n", lambda: None, environ={})
        self.assertFalse(grabber.available())

    def test_hint(self):
        self.assertEqual(hotkey.shortcut_hint("ctrl+alt+n"), "Ctrl + Alt + N")


class IpcTests(unittest.TestCase):
    def test_roundtrip(self):
        seen = []

        def handler(action, payload):
            seen.append((action, payload))
            return {"ok": True, "echo": action}

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "dock.sock"
            server = ipc.DockServer(handler, path=path).start()
            try:
                reply = ipc.send("capture", {"n": 1}, path=path)
            finally:
                server.stop()
            self.assertTrue(reply.get("ok"))
            self.assertEqual(reply.get("echo"), "capture")
            self.assertEqual(seen, [("capture", {"n": 1})])
            self.assertFalse(path.exists())

    def test_second_server_refuses(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "dock.sock"
            first = ipc.DockServer(lambda action, payload: {"ok": True}, path=path).start()
            try:
                with self.assertRaises(OSError):
                    ipc.DockServer(lambda action, payload: {"ok": True}, path=path).start()
            finally:
                first.stop()


class IconTests(unittest.TestCase):
    class FakeCanvas:
        def __init__(self):
            self.calls = []

        def create_line(self, *args, **kwargs):
            self.calls.append("line")

        def create_polygon(self, *args, **kwargs):
            self.calls.append("polygon")

        def create_oval(self, *args, **kwargs):
            self.calls.append("oval")

        def create_rectangle(self, *args, **kwargs):
            self.calls.append("rectangle")

    def test_every_icon_draws(self):
        for name in icons.ICONS:
            with self.subTest(name=name):
                canvas = self.FakeCanvas()
                icons.draw(canvas, name, 10, 10, 20, "#ffffff", ("tag",), "#000000")
                self.assertTrue(canvas.calls)

    def test_unknown_icon_falls_back(self):
        canvas = self.FakeCanvas()
        icons.draw(canvas, "sconosciuta", 0, 0, 10, "#fff", ("tag",))
        self.assertTrue(canvas.calls)


class TrayTests(unittest.TestCase):
    def test_menu_lists_the_dock_actions(self):
        from nokk_dock import tray

        entries = tray.menu_entries()
        actions = [action for action, _label in entries if action]
        self.assertEqual(actions, ["toggle", "ask", "capture", "settings", "quit"])
        self.assertIn((None, None), entries)
        self.assertTrue(tray.ICON_ICO.exists())
        self.assertTrue(tray.ICON_PNG.exists())

    def test_missing_backend_is_not_fatal(self):
        from nokk_dock import tray

        class Broken:
            def __init__(self, _actions):
                pass

            def start(self):
                raise OSError("nessun backend")

        with mock.patch.object(tray, "is_windows", lambda platform=None: False):
            with mock.patch.object(tray, "_PystrayTray", Broken):
                self.assertIsNone(tray.create_tray({"toggle": lambda: None}))


class LauncherTests(unittest.TestCase):
    def test_parser(self):
        import dock_start

        args = dock_start.build_parser().parse_args(["--position", "top", "--capture"])
        self.assertEqual(args.position, "top")
        self.assertTrue(args.capture)

    def test_check_runs_headless(self):
        import dock_start

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            dock_start.run_check(settings.default_config(), Path("/tmp/nokk-dock-check.json"))
        output = buffer.getvalue()
        self.assertIn("NOKK Dock", output)
        self.assertIn("Config", output)


try:
    import tkinter  # noqa: F401

    TK_AVAILABLE = True
except Exception:  # noqa: BLE001 - tkinter è opzionale nei test
    TK_AVAILABLE = False


@unittest.skipUnless(TK_AVAILABLE, "tkinter non disponibile")
class DockAppImportTests(unittest.TestCase):
    def test_round_rect_is_callable(self):
        from nokk_dock import app

        self.assertTrue(callable(app.round_rect))

    def test_panels_exist(self):
        from nokk_dock import app

        self.assertTrue(callable(app.DockApp))


if __name__ == "__main__":
    unittest.main()
