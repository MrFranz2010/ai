"""Test del supporto Windows del dock, eseguiti anche su Linux.

Le parti specifiche di Windows (RegisterHotKey, PowerShell, tasti multimediali)
vengono verificate tramite iniezione di dipendenze: qui si controlla la logica
di composizione dei comandi, i percorsi, l'IPC TCP e il parsing dei metadati.
"""

from __future__ import annotations

import base64
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nokk_dock import capture, hotkey, ipc, media, settings

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAIAAAD8GO2jAAAAKklEQVR4nGPQsKmgKWIYtWDUglELRi0Y"
    "tWDUglELRi0YtWDUglELhooFAAS5cC7WiDFbAAAAAElFTkSuQmCC"
)


def sample_png(size=900):
    return PNG_BYTES + b"\0" * max(0, size - len(PNG_BYTES))


class WindowsConfigTests(unittest.TestCase):
    def test_config_path_uses_appdata(self):
        path = settings.config_path(
            platform="win32",
            environ={"APPDATA": r"C:\Users\Mario\AppData\Roaming"},
        )
        self.assertEqual(
            str(path).replace("\\", "/"),
            "C:/Users/Mario/AppData/Roaming/nokk/dock.json",
        )

    def test_config_path_falls_back_to_home(self):
        with mock.patch.object(Path, "home", return_value=Path("C:/Users/Mario")):
            path = settings.config_path(platform="win32", environ={})
        self.assertIn("AppData", str(path).replace("\\", "/"))

    def test_explicit_override_wins(self):
        path = settings.config_path("/tmp/dock.json", platform="win32", environ={})
        self.assertEqual(Path(path), Path("/tmp/dock.json"))


class WindowsHotkeyTests(unittest.TestCase):
    def test_virtual_keys(self):
        self.assertEqual(hotkey.windows_virtual_key("n"), ord("N"))
        self.assertEqual(hotkey.windows_virtual_key("7"), ord("7"))
        self.assertEqual(hotkey.windows_virtual_key("f9"), 0x78)
        self.assertEqual(hotkey.windows_virtual_key("f24"), 0x87)
        self.assertEqual(hotkey.windows_virtual_key("space"), 0x20)
        with self.assertRaises(ValueError):
            hotkey.windows_virtual_key("f25")
        with self.assertRaises(ValueError):
            hotkey.windows_virtual_key("nope")

    def test_modifier_flags(self):
        flags = hotkey.windows_modifier_flags(("ctrl", "alt"))
        self.assertEqual(flags, hotkey.MOD_CONTROL | hotkey.MOD_ALT)
        self.assertEqual(hotkey.windows_modifier_flags(("super",)), hotkey.MOD_WIN)
        with self.assertRaises(ValueError):
            hotkey.windows_modifier_flags(("hyper",))

    def test_split_shortcut(self):
        self.assertEqual(hotkey.split_shortcut("Ctrl+Alt+N"), (("ctrl", "alt"), "n"))
        with self.assertRaises(ValueError):
            hotkey.split_shortcut("n")

    def test_windows_hotkey_unavailable_elsewhere(self):
        grabber = hotkey.WindowsHotkey("ctrl+alt+n", lambda: None, platform="linux")
        self.assertFalse(grabber.available())
        self.assertFalse(grabber.start())

    def test_factory_picks_backend(self):
        self.assertIsInstance(
            hotkey.create_hotkey("ctrl+alt+n", lambda: None, platform="win32"),
            hotkey.WindowsHotkey,
        )
        self.assertIsInstance(
            hotkey.create_hotkey("ctrl+alt+n", lambda: None, platform="linux", environ={}),
            hotkey.X11Hotkey,
        )
        self.assertIn("Windows", hotkey.backend_name("win32"))
        self.assertIn("X11", hotkey.backend_name("linux"))


class WindowsCaptureTests(unittest.TestCase):
    def test_no_external_tools_on_windows(self):
        self.assertEqual(capture.candidate_tools(platform="win32", which=lambda _n: "/bin/x"), [])

    def test_script_contains_path_and_scale(self):
        script = capture.windows_screenshot_script(r"C:\Temp\shot.png", scale=0.8)
        self.assertIn(r"C:\Temp\shot.png", script)
        self.assertIn("0.800", script)
        self.assertIn("CopyFromScreen", script)

    def test_script_escapes_quotes(self):
        script = capture.windows_screenshot_script(r"C:\Temp\o'brien.png", scale=1.0)
        self.assertIn("o''brien", script)
        self.assertIn("1.000", script)

    def test_capture_uses_powershell(self):
        seen = []

        def which(name):
            return "powershell.exe" if name == "powershell" else None

        def runner(argv, **kwargs):
            seen.append((argv, kwargs))
            # Il runner finto legge dallo script il percorso del PNG da creare.
            script = Path(argv[-1]).read_text(encoding="utf-8")
            marker = "$full.Save('"
            start = script.index(marker) + len(marker)
            target = Path(script[start:script.index("'", start)].replace("''", "'"))
            target.write_bytes(sample_png())
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

        path = capture.capture_screen(platform="win32", runner=runner, which=which)
        self.assertTrue(Path(path).exists())
        self.assertTrue(seen)
        argv, kwargs = seen[0]
        self.assertEqual(argv[0], "powershell.exe")
        self.assertIn("-NoProfile", argv)
        self.assertIn("-File", argv)
        self.assertTrue(argv[-1].endswith(".ps1"))
        self.assertEqual(kwargs.get("creationflags"), capture.CREATE_NO_WINDOW)
        capture.cleanup(path)

    def test_capture_without_powershell(self):
        with mock.patch.object(capture, "_grab_with_pillow", return_value=None):
            with self.assertRaises(capture.CaptureError) as raised:
                capture.capture_screen(platform="win32", which=lambda _n: None)
        self.assertIn("PowerShell", str(raised.exception))

    def test_capture_failure_reports_powershell_error(self):
        def which(name):
            return "powershell.exe" if name == "powershell" else None

        def runner(argv, **kwargs):
            return SimpleNamespace(returncode=1, stdout=b"", stderr=b"Eccezione: accesso negato")

        with mock.patch.object(capture, "_grab_with_pillow", return_value=None):
            with self.assertRaises(capture.CaptureError) as raised:
                capture.capture_screen(platform="win32", runner=runner, which=which)
        self.assertIn("accesso negato", str(raised.exception))


class WindowsIpcTests(unittest.TestCase):
    def test_tcp_roundtrip_and_token(self):
        seen = []

        def handler(action, payload):
            seen.append(action)
            return {"ok": True, "echo": action}

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "endpoint.json"
            server = ipc.DockServer(handler, path=path, platform="win32", token="abc123").start()
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self.assertIn("port", data)
                self.assertEqual(data["token"], "abc123")
                reply = ipc.send("capture", {"x": 1}, path=path, platform="win32")
                self.assertTrue(reply.get("ok"))
                self.assertEqual(reply.get("echo"), "capture")
                # Token errato: il comando viene rifiutato senza arrivare all'handler.
                with mock.patch.object(ipc, "_read_endpoint", return_value=(data["port"], "sbagliato")):
                    rejected = ipc.send("capture", path=path, platform="win32")
                self.assertFalse(rejected.get("ok"))
            finally:
                server.stop()
            self.assertFalse(path.exists())
            self.assertEqual(seen, ["capture"])

    def test_missing_endpoint_raises(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(OSError):
                ipc.send("capture", path=Path(temporary) / "nope.json", platform="win32")


class WindowsMediaTests(unittest.TestCase):
    def test_media_key_codes(self):
        self.assertEqual(media.WINDOWS_MEDIA_KEYS["play_pause"], 0xB3)
        self.assertEqual(media.WINDOWS_MEDIA_KEYS["next"], 0xB0)
        self.assertEqual(media.WINDOWS_MEDIA_KEYS["previous"], 0xB1)

    def test_parse_active_line(self):
        line = json.dumps({
            "active": True,
            "status": "Playing",
            "title": "Brano",
            "artist": "Artista",
            "album": "Album",
        })
        state = media.parse_windows_media_line(line)
        self.assertTrue(state.playing)
        self.assertEqual(state.title, "Brano")
        self.assertEqual(state.subtitle, "Artista — Album")
        self.assertEqual(state.art_url, "")

    def test_parse_line_with_cover(self):
        line = json.dumps({
            "active": True,
            "status": "Playing",
            "title": "Brano",
            "artist": "Artista",
            "album": "Album",
            "art": r"C:\Users\Anna\AppData\Local\Temp\nokk-art-1234.png",
        })
        state = media.parse_windows_media_line(line)
        self.assertEqual(
            state.art_url,
            "file:///C:/Users/Anna/AppData/Local/Temp/nokk-art-1234.png",
        )

    def test_cover_paths_become_file_urls(self):
        self.assertEqual(media.windows_file_url(""), "")
        self.assertEqual(media.windows_file_url(None), "")
        self.assertEqual(
            media.windows_file_url(r"C:\Temp\nokk-art-abc.png"),
            "file:///C:/Temp/nokk-art-abc.png",
        )
        self.assertEqual(
            media.windows_file_url("https://i.scdn.co/image/x.jpg"),
            "https://i.scdn.co/image/x.jpg",
        )

    def test_helper_saves_the_cover_even_if_the_file_exists(self):
        script = media.WINDOWS_HELPER_SCRIPT
        # Lo stream WinRT non è ricercabile: i byte si leggono in memoria.
        self.assertIn("DataReader", script)
        self.assertIn("MemoryStream", script)
        # GDI+ non sovrascrive un file esistente: va tolto prima di salvare.
        self.assertIn("Remove-Item $target -Force", script)
        self.assertIn("256, 256", script)

    def test_helper_retries_a_missing_cover(self):
        script = media.WINDOWS_HELPER_SCRIPT
        self.assertIn("$artTries", script)
        self.assertIn("$artTries -lt 5", script)

    def test_parse_inactive_and_invalid(self):
        inactive = media.parse_windows_media_line('{"active": false}')
        self.assertFalse(inactive.active)
        self.assertEqual(inactive.art_url, "")
        self.assertIsNone(media.parse_windows_media_line("non json"))

    def test_controller_without_powershell(self):
        controller = media.WindowsMusicController(
            which=lambda _name: None, platform="win32", key_sender=lambda _code: False
        )
        state = controller.refresh()
        self.assertFalse(state.installed)
        self.assertIn("PowerShell", state.message)
        self.assertFalse(controller.play_pause())

    def test_controller_reads_helper_output(self):
        payload = json.dumps({"active": True, "status": "Paused", "title": "Titolo", "artist": "Art"})

        class FakeProcess:
            def __init__(self, lines):
                self.stdout = lines
                self.terminated = False

            def poll(self):
                return None

            def terminate(self):
                self.terminated = True

        process = FakeProcess([payload + "\n"])
        pressed = []
        controller = media.WindowsMusicController(
            which=lambda _name: "powershell.exe",
            popen=lambda *args, **kwargs: process,
            platform="win32",
            key_sender=lambda code: pressed.append(code) or True,
        )
        self.assertTrue(controller.refresh().installed)
        deadline = time.time() + 2
        state = controller.refresh()
        while not state.title and time.time() < deadline:
            time.sleep(0.01)
            state = controller.refresh()
        self.assertEqual(state.title, "Titolo")
        self.assertEqual(state.status, "Paused")
        controller.stop()
        self.assertTrue(process.terminated)
        self.assertTrue(controller.play_pause())
        self.assertIn(media.WINDOWS_MEDIA_KEYS["play_pause"], pressed)

    def test_send_media_key_is_noop_off_windows(self):
        self.assertFalse(media.send_media_key(0xB3, platform="linux"))

    def test_factory(self):
        self.assertIsInstance(media.create_controller(platform="win32"), media.WindowsMusicController)
        self.assertIsInstance(media.create_controller(platform="linux"), media.MusicController)


if __name__ == "__main__":
    unittest.main()
