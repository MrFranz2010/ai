"""Verifica del disegno del dock senza una sessione grafica.

Tkinter non è disponibile ovunque; qui viene sostituito da un piccolo stub che
registra le primitive del canvas. In questo modo i metodi che disegnano i widget
(musica, meteo, ora, NOKK, cattura, impostazioni) vengono davvero eseguiti e
ogni errore di attributo o di coordinata emerge nei test.
"""

from __future__ import annotations

import contextlib
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class FakeFont:
    def __init__(self, root=None, family="", size=10, weight="normal"):
        self.family = family
        self.size = size
        self.weight = weight

    def measure(self, text):
        return len(str(text)) * 7


class FakeCanvas:
    def __init__(self):
        self.items = []

    def _record(self, kind, args, kwargs):
        self.items.append({"kind": kind, "args": args, "kwargs": kwargs})
        return len(self.items)

    def delete(self, *_args):
        self.items.clear()

    def configure(self, **_kwargs):
        pass

    def create_polygon(self, *args, **kwargs):
        return self._record("polygon", args, kwargs)

    def create_line(self, *args, **kwargs):
        return self._record("line", args, kwargs)

    def create_text(self, *args, **kwargs):
        return self._record("text", args, kwargs)

    def create_oval(self, *args, **kwargs):
        return self._record("oval", args, kwargs)

    def create_rectangle(self, *args, **kwargs):
        return self._record("rectangle", args, kwargs)

    def create_window(self, *args, **kwargs):
        return self._record("window", args, kwargs)

    def create_arc(self, *args, **kwargs):
        return self._record("arc", args, kwargs)


class FakeRoot:
    def __init__(self, screen=(1920, 1080)):
        self.screen = screen
        self.geometry_value = ""
        self.attributes = {}

    def winfo_screenwidth(self):
        return self.screen[0]

    def winfo_screenheight(self):
        return self.screen[1]

    def geometry(self, value):
        self.geometry_value = value

    def wm_attributes(self, name, *values):
        if values:
            self.attributes[name] = values[0]
        return self.attributes.get(name)

    def winfo_pointerx(self):
        return 0

    def winfo_pointery(self):
        return 0

    def winfo_rootx(self):
        return 0

    def winfo_rooty(self):
        return 0

    def winfo_width(self):
        return 10

    def winfo_height(self):
        return 10


def _forget_dock_modules():
    """Dimentica app e pannelli (moduli e attributi del pacchetto)."""
    for name in [name for name in sys.modules if name.startswith("nokk_dock.app") or name.startswith("nokk_dock.panels")]:
        sys.modules.pop(name, None)
    package = sys.modules.get("nokk_dock")
    if package is not None:
        for attribute in ("app", "panels"):
            if hasattr(package, attribute):
                delattr(package, attribute)


@contextlib.contextmanager
def stub_tkinter():
    """Sostituisce tkinter con uno stub per importare il modulo dell'interfaccia."""
    saved = {name: sys.modules.get(name) for name in ("tkinter", "tkinter.font")}
    stub = types.ModuleType("tkinter")
    stub.TclError = RuntimeError
    stub.font = types.ModuleType("tkinter.font")
    stub.font.Font = FakeFont
    stub.font.families = lambda root=None: ["DejaVu Sans", "Ubuntu"]
    sys.modules["tkinter"] = stub
    sys.modules["tkinter.font"] = stub.font
    _forget_dock_modules()
    try:
        yield
    finally:
        _forget_dock_modules()
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


class DrawingTests(unittest.TestCase):
    def build_app(self):
        from nokk_dock import app as dock_app
        from nokk_dock import layout as dock_layout
        from nokk_dock.media import MusicState
        from nokk_dock.settings import default_config
        from nokk_dock.theme import build_theme
        from nokk_dock.weather import WeatherNow

        instance = object.__new__(dock_app.DockApp)
        instance.canvas = FakeCanvas()
        instance.root = FakeRoot()
        instance.theme = build_theme({})
        instance.config = default_config()
        instance.hits = []
        instance._font_cache = {}
        instance._alive = True
        instance._hovered = "music"
        instance.connected = True
        instance.expand = 0.0
        instance.target = 0.0
        instance.music = MusicState(
            installed=True,
            active=True,
            status="Playing",
            artist="Artista",
            title="Brano",
            album="Album",
            length_seconds=200.0,
            position_seconds=42.0,
        )
        instance.weather = WeatherNow(
            city="Torino",
            temperature=18.4,
            label="Sereno",
            icon="sun",
            minimum=12.0,
            maximum=21.0,
            updated_at=1.0,
        )
        instance.layout = dock_layout.compute_layout(
            "bottom", 1920, 1080, instance.config["widgets"],
            thickness=60, length=660, margin=18, offset=0.5, expand=0.0,
        )
        return instance

    def test_redraw_all_widgets_horizontal(self):
        with stub_tkinter():
            instance = self.build_app()
            for expand in (0.0, 0.55, 1.0):
                instance.layout = type(instance.layout)(
                    x=instance.layout.x,
                    y=instance.layout.y,
                    width=instance.layout.width,
                    height=instance.layout.height,
                    tiles=instance.layout.tiles,
                    horizontal=True,
                    expanded=expand,
                    scale=1.0,
                )
                instance._hovered = "music"
                instance._redraw()
                self.assertGreater(len(instance.canvas.items), 10)
                kinds = {item["kind"] for item in instance.canvas.items}
                self.assertIn("text", kinds)
                self.assertIn("polygon", kinds)
                for hit in instance.hits:
                    self.assertLessEqual(hit["x1"], hit["x2"])
                    self.assertLessEqual(hit["y1"], hit["y2"])

    def test_redraw_vertical(self):
        with stub_tkinter():
            from nokk_dock import layout as dock_layout

            instance = self.build_app()
            instance.layout = dock_layout.compute_layout(
                "left", 1920, 1080, instance.config["widgets"],
                thickness=60, length=660, margin=18, offset=0.5, expand=1.0,
            )
            instance._redraw()
            self.assertGreater(len(instance.canvas.items), 10)

    def test_redraw_without_player(self):
        with stub_tkinter():
            from nokk_dock.media import MusicState

            instance = self.build_app()
            instance.music = MusicState(installed=False, message="Installa playerctl")
            instance._redraw()
            labels = [
                str(item["kwargs"].get("text", ""))
                for item in instance.canvas.items
                if item["kind"] == "text"
            ]
            self.assertIn("Musica", labels)

    def test_redraw_with_weather_error(self):
        with stub_tkinter():
            from nokk_dock.weather import WeatherNow

            instance = self.build_app()
            instance.weather = WeatherNow(error="Imposta la tua città")
            instance._redraw()
            self.assertGreater(len(instance.canvas.items), 5)

    def test_apply_geometry_stays_on_screen(self):
        with stub_tkinter():
            instance = self.build_app()
            for position in ("bottom", "top", "left", "right"):
                instance.config["dock"]["position"] = position
                for expand in (0.0, 1.0):
                    instance.expand = expand
                    instance._apply_geometry(expand)
                    geometry = instance.root.geometry_value
                    size, x, y = geometry.replace("+", "|").split("|")
                    width, height = (int(part) for part in size.split("x"))
                    left, top = int(x), int(y)
                    self.assertGreaterEqual(left, 0)
                    self.assertGreaterEqual(top, 0)
                    self.assertLessEqual(left + width, 1920)
                    self.assertLessEqual(top + height, 1080)

    def test_auto_hide_pushes_dock_off_screen(self):
        with stub_tkinter():
            instance = self.build_app()
            instance.config["dock"]["auto_hide"] = True
            instance._hover_locked = False
            instance.expand = 0.0
            instance._apply_geometry(0.0)
            plan = instance.layout
            geometry = instance.root.geometry_value
            top = int(geometry.rsplit("+", 1)[1])
            self.assertGreater(top, plan.y)

    def test_ellipsize(self):
        with stub_tkinter():
            instance = self.build_app()
            font = FakeFont()
            self.assertEqual(instance._ellipsize("ciao", font, 500), "ciao")
            shortened = instance._ellipsize("parola molto lunga", font, 40)
            self.assertTrue(shortened.endswith("…"))
            self.assertLessEqual(len(shortened), len("parola molto lunga"))

    def test_motion_and_hit_handling(self):
        with stub_tkinter():
            from nokk_dock import layout as dock_layout

            instance = self.build_app()
            instance.layout = dock_layout.compute_layout(
                "bottom", 1920, 1080, instance.config["widgets"],
                thickness=60, length=660, margin=18, offset=0.5, expand=1.0,
            )
            instance._redraw()
            hit = instance.hits[0]
            event = types.SimpleNamespace(x=int(hit["x1"]) + 1, y=int(hit["y1"]) + 1)
            self.assertIsNotNone(instance._hit_at(event.x, event.y))
            instance._on_motion(event)
            outside = types.SimpleNamespace(x=-50, y=-50)
            instance._on_motion(outside)
            self.assertIsNone(instance._hovered)

    def test_dispatch_updates_state(self):
        with stub_tkinter():
            from nokk_dock.media import MusicState
            from nokk_dock.weather import WeatherNow

            instance = self.build_app()
            fresh = MusicState(installed=True, active=True, title="Nuovo")
            instance._dispatch("music", fresh)
            self.assertEqual(instance.music.title, "Nuovo")
            instance._dispatch("status", False)
            self.assertFalse(instance.connected)
            instance._dispatch("weather", WeatherNow(temperature=1.0))
            self.assertEqual(instance.weather.temperature, 1.0)

    def test_redraw_with_magnified_tiles(self):
        with stub_tkinter():
            from nokk_dock import layout as dock_layout

            instance = self.build_app()
            base = dock_layout.compute_layout(
                "bottom", 1920, 1080, instance.config["widgets"],
                thickness=60, length=660, margin=18, offset=0.5, expand=1.0,
            )
            first = base.tiles[0]
            pointer = base.x + first.x + first.width / 2
            instance.layout = dock_layout.compute_layout(
                "bottom", 1920, 1080, instance.config["widgets"],
                thickness=60, length=660, margin=18, offset=0.5, expand=1.0,
                pointer=float(pointer), magnify=1.4, influence=420.0,
            )
            self.assertTrue(any(tile.magnify > 1.0 for tile in instance.layout.tiles))
            instance._redraw()
            self.assertGreater(len(instance.canvas.items), 10)
            self.assertAlmostEqual(
                instance._tile_growth(dock_layout.Tile("clock", 0, 0, 10, 10, 1.0)), 1.0
            )
            self.assertGreater(
                instance._tile_growth(dock_layout.Tile("clock", 0, 0, 10, 10, 1.4)), 1.0
            )

    def test_hover_label_text(self):
        with stub_tkinter():
            from nokk_dock import layout as dock_layout

            instance = self.build_app()
            from nokk_dock.media import MusicState

            tile = dock_layout.Tile("music", 0, 0, 100, 60, 1.0)
            self.assertIn("Brano", instance._hover_text(tile))
            instance.music = MusicState(installed=True, active=False)
            self.assertEqual(instance._hover_text(tile), "Musica")
            instance.config["dock"]["show_labels"] = False
            self.assertIsNone(instance._schedule_hover_label(tile))


if __name__ == "__main__":
    unittest.main()
