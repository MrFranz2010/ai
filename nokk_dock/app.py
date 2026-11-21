"""Finestra del dock di NOKK.

Il dock è una finestra senza cornice ancorata a un bordo dello schermo: resta
sopra le altre finestre, si espande al passaggio del mouse e mostra i widget
scelti. Tutto il disegno passa da un canvas, così colori, raggi e scala seguono
il tema senza ricostruire l'interfaccia.
"""

from __future__ import annotations

import base64
import queue
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import webbrowser
from datetime import datetime

from . import artwork, icons
from . import layout as dock_layout
from .motion import settled, spring_step
from .capture import CaptureError, capture_screen, cleanup, load_image
from .client import NokkClient, NokkError
from .hotkey import backend_name, create_hotkey, shortcut_hint
from .ipc import DockServer, send as ipc_send
from .media import INSTALL_HINT, MusicState, create_controller
from .panels import AskPanel, SettingsPanel
from .settings import (
    POSITION_LABELS,
    WIDGET_LABELS,
    config_path,
    save_config,
    validate_config,
)
from .theme import Theme, build_theme, mix, pick_font, readable_text
from .weather import WeatherNow, WeatherService

AMBER = "#f0b429"
WINDOWS = sys.platform.startswith("win")
# Colore chiave usato su Windows per rendere trasparenti gli angoli arrotondati.
TRANSPARENT_KEY = "#010203"


def enable_dpi_awareness():
    """Rende nitido il dock su Windows con il ridimensionamento dello schermo."""
    if not WINDOWS:
        return False
    try:
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
            return True
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()
            return True
    except Exception:  # noqa: BLE001 - il dock funziona anche senza
        return False


def round_rect(canvas, x1, y1, x2, y2, radius, **kwargs):
    """Rettangolo con angoli arrotondati disegnato come poligono morbido."""
    limit = min(abs(x2 - x1), abs(y2 - y1)) / 2
    r = max(0.0, min(float(radius), limit))
    points = (
        x1 + r, y1,
        x2 - r, y1,
        x2, y1,
        x2, y1 + r,
        x2, y2 - r,
        x2, y2,
        x2 - r, y2,
        x1 + r, y2,
        x1, y2,
        x1, y2 - r,
        x1, y1 + r,
        x1, y1,
    )
    return canvas.create_polygon(points, smooth=True, splinesteps=14, **kwargs)


class DockApp:
    """Dock completo: finestra, widget, scorciatoia e collegamento a NOKK."""

    # Valori di default validi anche per istanze create senza __init__ (test).
    _velocity = 0.0
    _pointer = None
    _hover_label = None
    _hover_label_text = None
    _hover_label_job = None
    _art_path = None
    _art_source = ""
    _art_pending = ""
    _art_accent = None
    _art_variants = None

    def __init__(self, config, config_file=None):
        self.config = validate_config(config)
        self.config_file = config_file or config_path()
        self.font_family = None
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("NOKK Dock")
        self.root.overrideredirect(True)
        try:
            self.root.wm_attributes("-type", "dock")
        except tk.TclError:
            pass
        self.canvas = tk.Canvas(self.root, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.queue: queue.Queue = queue.Queue()
        self.hits: list[dict] = []
        self.layout: dock_layout.DockLayout | None = None
        self.expand = 0.0
        self.target = 0.0
        self._anim_job = None
        self._expand_job = None
        self._collapse_job = None
        self._pump_job = None
        self._clock_job = None
        self._alive = True
        self._hovered: str | None = None
        self._hover_locked = False
        self._panels = 0
        self._font_cache: dict = {}
        self.stop_event = threading.Event()
        self.music = MusicState(installed=False, message="Ricerca del player…")
        self.weather = WeatherNow()
        self.connected: bool | None = None
        self._music_thread = None
        self._status_thread = None
        self._hotkey = None
        self._server: DockServer | None = None
        self._toast: tk.Toplevel | None = None
        self._toast_job = None
        self._last_draw = 0.0
        self._velocity = 0.0
        self._pointer: float | None = None
        self._hover_label = None
        self._hover_label_text = None
        self._hover_label_job = None
        self._art_path = None
        self._art_source = ""
        self._art_pending = ""
        self._art_accent = None
        self._art_variants = {}

        self.font_family = pick_font(tkfont.families(self.root))
        self._bind_events()
        self._apply_config(self.config, persist=False)
        self._install_ipc()
        self._install_hotkey()
        self._start_threads()
        self.root.deiconify()
        self._apply_geometry(self.expand)
        self._schedule_clock()
        self._pump_job = self.root.after(80, self._pump)
        self.root.protocol("WM_DELETE_WINDOW", self.shutdown)

    # ---------------------------------------------------------------- setup
    def _bind_events(self):
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<Button-3>", self._on_context_menu)
        self.canvas.bind("<Enter>", self._on_enter)
        self.canvas.bind("<Leave>", self._on_leave)

    def _apply_config(self, config, persist=True):
        """Applica una configurazione (tema, widget, servizi, geometria)."""
        clean = validate_config(config)
        self.config = clean
        self.theme: Theme = build_theme(clean["theme"], self.font_family)
        self._font_cache = {}
        dock = clean["dock"]
        try:
            self.root.wm_attributes("-topmost", bool(dock["always_on_top"]))
            self.root.wm_attributes("-alpha", float(dock["opacity"]))
        except tk.TclError:
            pass
        self._apply_window_background()
        self.client = NokkClient(
            clean["nokk"]["base_url"],
            clean["nokk"]["api_key"],
            mode=clean["nokk"]["mode"],
            timeout=clean["nokk"]["timeout"],
        )
        previous = getattr(self, "music_controller", None)
        if previous is not None and hasattr(previous, "stop"):
            try:
                previous.stop()
            except Exception:  # noqa: BLE001 - il controller non blocca il salvataggio
                pass
        self.music_controller = create_controller(clean["music"]["player"])
        self._restart_weather()
        if persist:
            try:
                save_config(clean, self.config_file)
            except (OSError, ValueError) as error:
                print(f"Impossibile salvare la configurazione del dock: {error}")
        self._apply_geometry(self.expand)
        self._redraw()

    def _apply_window_background(self):
        """Su Windows rende trasparenti gli angoli con un colore chiave."""
        background = self.theme.background
        if WINDOWS:
            try:
                self.root.configure(bg=TRANSPARENT_KEY)
                self.root.wm_attributes("-transparentcolor", TRANSPARENT_KEY)
                background = TRANSPARENT_KEY
            except tk.TclError:
                background = self.theme.background
                try:
                    self.root.configure(bg=background)
                except tk.TclError:
                    pass
        self.canvas.configure(bg=background)

    def _restart_weather(self):
        if getattr(self, "weather_service", None) is not None:
            self.weather_service.stop()
        self.weather_service = WeatherService(self.config["weather"])
        self.weather_service.start(
            lambda state: self.post("weather", state),
            interval_minutes=self.config["weather"]["refresh_minutes"],
        )

    def _install_ipc(self):
        try:
            self._server = DockServer(self._ipc_command).start()
        except OSError as error:
            if "già in esecuzione" in str(error):
                raise SystemExit("Il dock è già in esecuzione.") from None
            print(f"IPC del dock non disponibile: {error}")

    def _install_hotkey(self):
        if self._hotkey is not None:
            self._hotkey.stop()
            self._hotkey = None
        shortcut = self.config["capture"]["shortcut"]
        hotkey = create_hotkey(shortcut, lambda: self.post("capture", None))
        if hotkey.start():
            self._hotkey = hotkey
        else:
            print(f"Scorciatoia globale ({backend_name()}) non attiva: {hotkey.error}")

    def _start_threads(self):
        self.stop_event.clear()
        self._music_thread = threading.Thread(
            target=self._music_loop, name="nokk-dock-music", daemon=True
        )
        self._music_thread.start()
        self._status_thread = threading.Thread(
            target=self._status_loop, name="nokk-dock-status", daemon=True
        )
        self._status_thread.start()

    # ---------------------------------------------------------- main loop
    def run(self):
        self.root.mainloop()

    def post(self, kind, payload):
        """Consegna un evento al thread dell'interfaccia."""
        self.queue.put((kind, payload))

    def _pump(self):
        if not self._alive:
            return
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                self._dispatch(kind, payload)
        except queue.Empty:
            pass
        finally:
            self._pump_job = self.root.after(60, self._pump)

    def _dispatch(self, kind, payload):
        if kind == "music":
            if payload != self.music:
                previous_art = self.music.art_url
                self.music = payload
                if payload.art_url != previous_art:
                    self._request_art(payload.art_url)
                self._redraw()
        elif kind == "art":
            self._apply_art(*payload)
        elif kind == "weather":
            self.weather = payload
            self._redraw()
        elif kind == "status":
            self.connected = bool(payload)
            self._redraw()
        elif kind == "capture":
            self.request_capture()
        elif kind == "capture_ready":
            self.open_ask(image=payload, question=self.config["ask"]["prompt"])
        elif kind == "error":
            self.toast(str(payload))
        elif kind == "toast":
            self.toast(str(payload))
        elif kind == "ask":
            self.open_ask(question=str(payload))
        elif kind == "settings":
            self.open_settings()
        elif kind == "reload":
            self._reload_from_disk()
        elif kind == "toggle":
            self._animate(1.0 if self.target < 0.5 else 0.0)
        elif kind == "quit":
            self.shutdown()

    def _music_loop(self):
        while not self.stop_event.is_set():
            try:
                state = self.music_controller.refresh(with_position=self.expand > 0.4)
            except Exception:  # noqa: BLE001 - playerctl non deve fermare il dock
                state = MusicState(installed=False, message=INSTALL_HINT)
            self.post("music", state)
            self.stop_event.wait(1.6 if self.expand > 0.4 else 3.0)

    def _status_loop(self):
        while not self.stop_event.is_set():
            client = self.client
            healthy = client.health() is not None
            self.post("status", healthy)
            self.stop_event.wait(40)

    def _schedule_clock(self):
        if not self._alive:
            return
        self._redraw()
        self._clock_job = self.root.after(1000, self._schedule_clock)

    # ------------------------------------------------------------ geometry
    def _apply_geometry(self, expand):
        dock = self.config["dock"]
        width = self.root.winfo_screenwidth()
        height = self.root.winfo_screenheight()
        plan = dock_layout.compute_layout(
            position=dock["position"],
            screen_width=width,
            screen_height=height,
            widgets=self.config["widgets"],
            thickness=dock["thickness"],
            length=dock["length"],
            margin=dock["margin"],
            offset=dock["offset"],
            expand=expand,
            scale=self.theme.scale,
            pointer=self._pointer,
            magnify=dock["magnify"],
            style=dock["style"],
        )
        self.layout = plan
        offset_x = 0
        offset_y = 0
        if dock["auto_hide"] and self.expand <= 0.02 and not self._hover_locked:
            peek = int(round(8 * self.theme.scale))
            if dock["position"] == "bottom":
                offset_y = plan.height - peek
            elif dock["position"] == "top":
                offset_y = -(plan.height - peek)
            elif dock["position"] == "left":
                offset_x = -(plan.width - peek)
            else:
                offset_x = plan.width - peek
        self.root.geometry(
            f"{plan.width}x{plan.height}+{plan.x + offset_x}+{plan.y + offset_y}"
        )
        self.canvas.configure(width=plan.width, height=plan.height)

    def _animate(self, target):
        self.target = max(0.0, min(1.0, float(target)))
        if self._anim_job is None:
            self._anim_job = self.root.after(8, self._anim_step)

    def _anim_step(self):
        self._anim_job = None
        if not self._alive:
            return
        if settled(self.expand, self.target, self._velocity):
            self.expand = self.target
            self._velocity = 0.0
            self._apply_geometry(self.expand)
            self._redraw()
            return
        self.expand, self._velocity = spring_step(
            self.expand, self.target, self._velocity
        )
        self._apply_geometry(self.expand)
        self._redraw()
        self._anim_job = self.root.after(11, self._anim_step)

    # --------------------------------------------------------------- hover
    def _on_enter(self, _event=None):
        self._hover_locked = True
        self._cancel(self._collapse_job)
        self._collapse_job = None
        delay = 0 if self.expand > 0 else self.config["dock"]["hover_delay_ms"]
        self._cancel(self._expand_job)
        self._expand_job = self.root.after(max(0, int(delay)), lambda: self._animate(1.0))

    def _on_leave(self, _event=None):
        self._cancel(self._expand_job)
        self._expand_job = None
        self._hide_hover_label()
        delay = int(self.config["dock"]["collapse_delay_ms"])
        self._collapse_job = self.root.after(delay, self._maybe_collapse)

    def _maybe_collapse(self):
        self._collapse_job = None
        if not self._alive or self._panels:
            return
        if self._pointer_inside():
            self._collapse_job = self.root.after(220, self._maybe_collapse)
            return
        self._hover_locked = False
        self._hovered = None
        self._pointer = None
        self._hide_hover_label()
        self._animate(0.0)

    def _pointer_inside(self):
        try:
            pointer_x = self.root.winfo_pointerx()
            pointer_y = self.root.winfo_pointery()
            root_x = self.root.winfo_rootx()
            root_y = self.root.winfo_rooty()
        except tk.TclError:
            return False
        return (
            root_x <= pointer_x <= root_x + self.root.winfo_width()
            and root_y <= pointer_y <= root_y + self.root.winfo_height()
        )

    def _on_motion(self, event):
        hit = self._hit_at(event.x, event.y)
        self.canvas.configure(cursor="hand2" if hit is not None else "")
        axis = "x_root" if (self.layout and self.layout.horizontal) else "y_root"
        pointer = getattr(event, axis, None)
        if pointer is not None and pointer != self._pointer:
            self._pointer = pointer
            self._apply_geometry(self.expand)
        tile = self.layout.tile_at(event.x, event.y) if self.layout else None
        key = tile.key if tile else None
        if key != self._hovered:
            self._hovered = key
            self._schedule_hover_label(tile)
            self._redraw()
        elif tile is not None and self._hover_label is not None:
            self._place_hover_label(tile)

    def _on_click(self, event):
        hit = self._hit_at(event.x, event.y)
        if hit is not None:
            hit["command"]()
            return
        if not self.layout:
            return
        if self.layout.style == "notch" and self.expand < 0.85:
            return
        tile = self.layout.tile_at(event.x, event.y)
        if tile is not None:
            self._activate(tile.key)

    def _on_context_menu(self, event):
        menu = tk.Menu(
            self.root,
            tearoff=0,
            bg=self.theme.panel,
            fg=self.theme.text,
            activebackground=self.theme.accent,
            activeforeground=self.theme.on_accent,
            bd=0,
        )
        menu.add_command(label="Chiedi a NOKK", command=lambda: self.open_ask())
        menu.add_command(label="Cattura schermo e chiedi", command=self.request_capture)
        menu.add_separator()
        for position, label in POSITION_LABELS.items():
            menu.add_command(
                label=f"Posizione: {label}",
                command=lambda value=position: self.set_position(value),
            )
        menu.add_separator()
        menu.add_command(label="Impostazioni del dock", command=self.open_settings)
        menu.add_command(
            label="Apri NOKK nel browser",
            command=lambda: webbrowser.open(self.config["nokk"]["base_url"]),
        )
        menu.add_separator()
        menu.add_command(label="Chiudi il dock", command=self.shutdown)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _hit_at(self, x, y):
        for hit in reversed(self.hits):
            if hit["x1"] <= x <= hit["x2"] and hit["y1"] <= y <= hit["y2"]:
                return hit
        return None

    # ------------------------------------------------------------- actions
    def _activate(self, key):
        if key == "music":
            self.toggle_music()
        elif key == "weather":
            self.refresh_weather()
        elif key == "clock":
            self.open_ask(question="Che ore sono e che giorno è?")
        elif key == "nokk":
            self.open_ask()
        elif key == "capture":
            self.request_capture()
        elif key == "settings":
            self.open_settings()

    def toggle_music(self):
        def worker():
            self.music_controller.play_pause()
            time.sleep(0.25)
            self.post("music", self.music_controller.refresh(with_position=True))

        threading.Thread(target=worker, daemon=True).start()
        self._animate(1.0)

    def next_track(self):
        threading.Thread(target=self._music_action, args=("next",), daemon=True).start()

    def previous_track(self):
        threading.Thread(target=self._music_action, args=("previous",), daemon=True).start()

    def _music_action(self, action):
        controller = self.music_controller
        if action == "next":
            controller.next_track()
        else:
            controller.previous_track()
        time.sleep(0.3)
        self.post("music", controller.refresh(with_position=True))

    def refresh_weather(self):
        threading.Thread(target=self._weather_worker, daemon=True).start()

    def _weather_worker(self):
        state = self.weather_service.refresh()
        self.post("weather", state)

    def set_position(self, position):
        if position not in POSITION_LABELS:
            return
        updated = dict(self.config)
        updated["dock"] = dict(self.config["dock"])
        updated["dock"]["position"] = position
        self._apply_config(updated)
        self.toast(f"Dock spostato: {POSITION_LABELS[position]}")

    # -------------------------------------------------------------- ask UI
    def open_ask(self, image=None, question=None):
        panel = AskPanel(self, image=image, question=question)
        return panel

    def request_capture(self):
        self._hover_locked = True
        self._animate(1.0)
        self.toast("Cattura dello schermo…", seconds=2)
        threading.Thread(target=self._capture_worker, daemon=True).start()

    def _capture_worker(self):
        try:
            path = capture_screen(scale=self.config["capture"]["scale"])
            image = load_image(path, self.config["capture"]["max_bytes"])
            cleanup(path)
        except CaptureError as error:
            self.post("error", str(error))
            return
        except Exception as error:  # noqa: BLE001 - lo screenshot non deve chiudere il dock
            self.post("error", f"Cattura non riuscita: {error}")
            return
        self.post("capture_ready", image)

    def open_settings(self):
        return SettingsPanel(self)

    def panel_opened(self):
        self._panels += 1
        self._hover_locked = True
        self._animate(1.0)

    def panel_closed(self):
        self._panels = max(0, self._panels - 1)
        if not self._panels:
            self._hover_locked = self._pointer_inside()

    # --------------------------------------------------------------- toast
    def toast(self, message, seconds=5):
        if not message:
            return
        self._close_toast()
        theme = self.theme
        window = tk.Toplevel(self.root)
        window.overrideredirect(True)
        try:
            window.wm_attributes("-topmost", True)
        except tk.TclError:
            pass
        window.configure(bg=theme.border)
        label = tk.Label(
            window,
            text=message,
            justify="left",
            wraplength=int(320 * theme.scale),
            bg=theme.panel,
            fg=theme.text,
            font=theme.font(10),
            padx=int(14 * theme.scale),
            pady=int(10 * theme.scale),
        )
        label.pack(padx=1, pady=1)
        window.update_idletasks()
        width = window.winfo_reqwidth()
        height = window.winfo_reqheight()
        plan = self.layout
        if plan is not None:
            if self.config["dock"]["position"] in ("bottom",):
                x = plan.x + (plan.width - width) // 2
                y = plan.y - height - 10
            elif self.config["dock"]["position"] == "top":
                x = plan.x + (plan.width - width) // 2
                y = plan.y + plan.height + 10
            else:
                x = plan.x + plan.width + 10
                y = plan.y
        else:
            x = 40
            y = 40
        x = max(0, min(self.root.winfo_screenwidth() - width, x))
        y = max(0, min(self.root.winfo_screenheight() - height, y))
        window.geometry(f"+{x}+{y}")
        self._toast = window
        self._toast_job = self.root.after(int(seconds * 1000), self._close_toast)

    def _close_toast(self):
        self._cancel(self._toast_job)
        self._toast_job = None
        if self._toast is not None:
            try:
                self._toast.destroy()
            except tk.TclError:
                pass
            self._toast = None

    # ------------------------------------------------------------- drawing
    def _font(self, size, weight="normal"):
        key = (round(float(size), 1), weight)
        font = self._font_cache.get(key)
        if font is None:
            font = tkfont.Font(
                root=self.root,
                family=self.theme.font_family,
                size=max(6, int(round(float(size) * self.theme.scale))),
                weight=weight,
            )
            self._font_cache[key] = font
        return font

    def _ellipsize(self, text, font, width):
        if width <= 10:
            return ""
        if font.measure(text) <= width:
            return text
        ellipsis = "…"
        trimmed = text
        while trimmed and font.measure(trimmed + ellipsis) > width:
            trimmed = trimmed[:-1]
        return (trimmed + ellipsis) if trimmed else ""

    def _text(self, x, y, text, size, weight="normal", fill=None, anchor="w", width=None):
        font = self._font(size, weight)
        if width is not None:
            text = self._ellipsize(text, font, width)
        if not text:
            return
        self.canvas.create_text(
            int(x), int(y),
            text=text,
            anchor=anchor,
            fill=fill or self.theme.text,
            font=font,
        )

    # ------------------------------------------------------------ cover art
    def _request_art(self, url):
        """Risolve la copertina del brano in un thread (file locale o rete)."""
        if url == self._art_source or url == self._art_pending:
            return
        self._art_pending = url or ""
        if not url:
            self._apply_art("", "", None)
            return
        threading.Thread(
            target=self._art_worker, args=(url,), name="nokk-dock-art", daemon=True
        ).start()

    def _art_worker(self, url):
        path = ""
        accent = None
        try:
            resolved = artwork.local_path(url)
            if resolved is not None:
                path = str(resolved)
                accent = artwork.accent_color(resolved)
        except Exception:  # noqa: BLE001 - la copertina non deve fermare il dock
            path, accent = "", None
        self.post("art", (url, path, accent))

    def _apply_art(self, url, path, accent):
        self._art_pending = ""
        if url != self.music.art_url:
            return
        self._art_source = url
        if (path or None) != self._art_path:
            self._art_path = path or None
            self._art_variants = {}
        self._art_accent = accent or None
        self._redraw()

    def _art_photo_for(self, size):
        path = self._art_path
        if not path:
            return None
        bucket = artwork.thumbnail_size(int(size))
        key = (path, bucket)
        variants = self._art_variants
        if variants is None:
            variants = self._art_variants = {}
        photo = variants.get(key)
        if photo is not None:
            return photo
        data = artwork.thumbnail_bytes(path, bucket)
        if not data:
            return None
        try:
            photo = tk.PhotoImage(data=base64.b64encode(data).decode("ascii"))
        except tk.TclError:
            return None
        if len(variants) > 12:
            variants.clear()
        variants[key] = photo
        return photo

    def _cover_for(self, expanded):
        if not self._art_path:
            return None
        photo = self._art_photo_for(64 if expanded > 0.5 else 40)
        if photo is None:
            photo = self._art_photo_for(40 if expanded > 0.5 else 64)
        return photo

    # ------------------------------------------------------- hover labels
    def _hover_text(self, tile):
        text = WIDGET_LABELS.get(tile.key, tile.key)
        if tile.key == "music" and self.music.title:
            return f"{text} · {self.music.title}"
        if tile.key == "weather" and self.weather.city and self.weather.updated_at:
            return f"{text} · {self.weather.city}"
        if tile.key == "nokk":
            return "Chiedi a NOKK"
        if tile.key == "capture":
            return (
                "Schermo → NOKK · "
                + shortcut_hint(self.config["capture"]["shortcut"])
            )
        return text

    def _schedule_hover_label(self, tile):
        self._cancel(self._hover_label_job)
        self._hover_label_job = None
        plan = self.layout
        if plan is not None and plan.style == "notch" and self.expand < 0.85:
            self._hide_hover_label()
            return
        if tile is None:
            self._hide_hover_label()
            return
        if not self.config["dock"]["show_labels"]:
            return
        self._hover_label_job = self.root.after(
            320, lambda: self._show_hover_label(tile)
        )

    def _show_hover_label(self, tile):
        self._hover_label_job = None
        if not self._alive or not self.config["dock"]["show_labels"]:
            return
        theme = self.theme
        try:
            if self._hover_label is None:
                window = tk.Toplevel(self.root)
                window.overrideredirect(True)
                try:
                    window.wm_attributes("-topmost", True)
                except tk.TclError:
                    pass
                window.configure(bg=theme.border)
                label = tk.Label(window, bg=theme.panel, fg=theme.text, padx=10, pady=5)
                label.pack(padx=1, pady=1)
                self._hover_label = window
                self._hover_label_text = label
            self._hover_label_text.configure(
                text=self._hover_text(tile), bg=theme.panel, fg=theme.text,
                font=theme.font(8.8),
            )
            self._place_hover_label(tile)
        except tk.TclError:
            self._hover_label = None

    def _place_hover_label(self, tile):
        window = self._hover_label
        plan = self.layout
        if window is None or plan is None:
            return
        try:
            window.update_idletasks()
            width = window.winfo_reqwidth()
            height = window.winfo_reqheight()
            position = self.config["dock"]["position"]
            if plan.horizontal:
                x = plan.x + tile.x + tile.width // 2 - width // 2
                y = plan.y - height - 8 if position == "bottom" else plan.y + plan.height + 8
            else:
                y = plan.y + tile.y + tile.height // 2 - height // 2
                x = plan.x + plan.width + 8 if position == "left" else plan.x - width - 8
            x = max(0, min(self.root.winfo_screenwidth() - width, x))
            y = max(0, min(self.root.winfo_screenheight() - height, y))
            window.geometry(f"+{int(x)}+{int(y)}")
            window.deiconify()
            window.lift()
        except tk.TclError:
            self._hover_label = None

    def _hide_hover_label(self):
        self._cancel(self._hover_label_job)
        self._hover_label_job = None
        if self._hover_label is not None:
            try:
                self._hover_label.withdraw()
            except tk.TclError:
                self._hover_label = None

    def _tile_growth(self, tile):
        """Quanto cresce il contenuto di un widget con l'ingrandimento magnetico."""
        return 1.0 + max(0.0, float(tile.magnify) - 1.0) * 0.55

    def _redraw(self):
        if not self._alive or self.layout is None:
            return
        self._last_draw = time.monotonic()
        canvas = self.canvas
        canvas.delete("all")
        self.hits = []
        plan = self.layout
        theme = self.theme
        expanded = plan.expanded
        radius = min(
            plan.height / 2 if plan.horizontal else plan.width / 2,
            max(10.0, theme.radius),
        )
        # alone esterno: dà profondità al pannello senza bisogno di trasparenza
        round_rect(
            canvas, 0, 0, plan.width, plan.height, radius,
            fill=mix(theme.background, theme.panel, 0.65), outline="",
        )
        round_rect(
            canvas, 1.5, 1.5, plan.width - 1.5, plan.height - 1.5, radius,
            fill=theme.panel, outline=theme.border, width=1,
        )
        # riflesso superiore e ombra interna: effetto vetro
        if plan.width - radius * 2 > 12:
            canvas.create_line(
                radius, 2.4, plan.width - radius, 2.4,
                fill=mix(theme.panel, theme.text, 0.14 if not theme.light else 0.08),
                width=1,
            )
            canvas.create_line(
                radius, plan.height - 2.4, plan.width - radius, plan.height - 2.4,
                fill=mix(theme.panel, theme.background, 0.55), width=1,
            )
        if getattr(plan, "style", "dock") == "notch" and expanded < 0.85:
            self._draw_notch(plan)
            return
        for tile in plan.tiles:
            area = dock_layout.tile_content(tile, plan)
            hovered = tile.key == self._hovered
            if hovered:
                round_rect(
                    canvas,
                    tile.x + 3, tile.y + 3, tile.right - 3, tile.bottom - 3,
                    max(8.0, radius * 0.6),
                    fill=theme.panel_hover,
                    outline=mix(theme.accent, theme.panel_hover, 0.4),
                    width=1,
                )
            painter = getattr(self, f"_draw_{tile.key}", None)
            if painter is not None:
                painter(tile, area, expanded)

    def _draw_notch(self, plan):
        """Pillola a riposo: stato di NOKK, ora e indicatore musicale."""
        theme = self.theme
        canvas = self.canvas
        scale = theme.scale
        width, height = plan.width, plan.height
        center_x, center_y = width / 2, height / 2
        color = theme.accent if self.connected else (
            AMBER if self.connected is False else theme.muted
        )
        radius = max(2.0, 2.6 * scale)
        dot_x = max(radius + 8 * scale, 16 * scale)
        canvas.create_oval(
            dot_x - radius, center_y - radius, dot_x + radius, center_y + radius,
            fill=color, outline="",
        )
        if width > 90 * scale:
            self._text(
                center_x, center_y, datetime.now().strftime("%H:%M"), 11.0,
                "bold", fill=theme.text, anchor="center",
            )
        if self.music.active and width > 60 * scale:
            icons.draw(
                canvas, "pause" if self.music.playing else "play",
                width - dot_x, center_y, 10.5 * scale, theme.muted, ("icon",),
            )

    def _draw_music(self, tile, area, expanded):
        theme = self.theme
        state = self.music
        x, y, width, height = area
        horizontal = self.layout.horizontal if self.layout else True
        scale = theme.scale
        growth = self._tile_growth(tile)
        accent = self._art_accent or theme.accent
        button = min(34 * scale * growth, height * 0.6)
        cover = self._cover_for(expanded) if state.installed else None
        if cover is not None:
            button = min(button, height * 0.52)
        if not state.installed:
            self._draw_placeholder(tile, area, "music", "Musica", INSTALL_HINT)
            return
        if horizontal:
            center_y = y + height / 2 - (5 * scale if expanded > 0.6 else 0)
            cursor = x + 2
            if cover is not None:
                self.canvas.create_image(
                    cursor + cover.width() / 2, center_y, image=cover
                )
                cursor += cover.width() + 9 * scale
            if expanded > 0.55:
                prev_cx = cursor + button * 0.42
                play_cx = prev_cx + button * 1.28
                next_cx = play_cx + button * 1.28
                self._mini_button(prev_cx, center_y, button * 0.8, "previous",
                                  self.previous_track)
                self._play_button(play_cx, center_y, button, state, accent)
                self._mini_button(next_cx, center_y, button * 0.8, "next",
                                  self.next_track)
                text_x = next_cx + button * 0.5
            else:
                play_cx = cursor + button * 0.62
                self._play_button(play_cx, center_y, button, state, accent)
                text_x = play_cx + button * 0.68
            available = tile.right - 12 - text_x
            if available > 24:
                title_y = center_y - (7 * scale if expanded > 0.6 else 0)
                self._text(text_x, title_y, state.label, 10.5 * growth, "bold",
                           fill=theme.text, width=available)
                subtitle = state.subtitle if state.active else state.message
                if expanded > 0.7 and subtitle:
                    self._text(text_x, title_y + 17 * scale, subtitle, 8.6 * growth,
                               fill=theme.muted, width=available)
            if expanded > 0.75 and state.length_seconds > 0:
                bar_y = y + height - 8 * scale
                canvas = self.canvas
                canvas.create_line(x, bar_y, x + width, bar_y,
                                   fill=theme.divider, width=3, capstyle="round")
                progress_x = x + max(2.0, width * state.progress)
                canvas.create_line(x, bar_y, progress_x, bar_y,
                                   fill=accent, width=3, capstyle="round")
                timecode = state.timecode
                if timecode:
                    self._text(tile.right - 12, bar_y - 9 * scale, timecode, 7.6,
                               fill=theme.muted, anchor="e")
        else:
            icon_center = (x + width / 2, y + 30 * scale)
            if cover is not None:
                self.canvas.create_image(icon_center[0], icon_center[1], image=cover)
            else:
                self._play_button(
                    icon_center[0], icon_center[1], button * 0.9, state, accent
                )
            text_width = width - 8
            self._text(x + width / 2, y + 30 * scale + button * 0.62,
                       state.label, 9.0 * growth, "bold", fill=theme.text,
                       anchor="n", width=text_width)
            if expanded > 0.7 and state.subtitle:
                self._text(x + width / 2, y + 30 * scale + button * 0.62 + 16 * scale,
                           state.subtitle, 8.0 * growth, fill=theme.muted, anchor="n",
                           width=text_width)

    def _play_button(self, cx, cy, size, state, accent=None):
        theme = self.theme
        fill = accent or theme.accent
        radius = size / 2
        self.canvas.create_oval(
            cx - radius, cy - radius, cx + radius, cy + radius,
            fill=fill, outline="",
        )
        icons.draw(
            self.canvas,
            "pause" if state.playing else "play",
            cx, cy, size * 0.5, readable_text(fill), ("icon",),
        )
        self._register_hit(cx - radius, cy - radius, cx + radius, cy + radius, self.toggle_music)

    def _mini_button(self, cx, cy, size, icon_name, command):
        icons.draw(self.canvas, icon_name, cx, cy, size * 0.9, self.theme.muted, ("icon",))
        radius = size / 2
        self._register_hit(cx - radius, cy - radius, cx + radius, cy + radius, command)

    def _register_hit(self, x1, y1, x2, y2, command):
        self.hits.append({"x1": x1, "y1": y1, "x2": x2, "y2": y2, "command": command})

    def _draw_weather(self, tile, area, expanded):
        theme = self.theme
        state = self.weather
        x, y, width, height = area
        horizontal = self.layout.horizontal if self.layout else True
        scale = theme.scale
        icon_name = state.icon if state.updated_at else "cloud"
        if state.error:
            icon_name = "cloud"
        icon_bg = theme.panel_hover if tile.key == self._hovered else theme.panel
        growth = self._tile_growth(tile)
        if horizontal:
            icon_size = min(26 * scale * growth, height * 0.5)
            icon_cx = x + icon_size * 0.62
            icon_cy = y + height / 2 - (5 * scale if expanded > 0.6 else 0)
            icons.draw(self.canvas, icon_name, icon_cx, icon_cy, icon_size,
                       theme.accent if not state.error else theme.muted, ("icon",), icon_bg)
            text_x = icon_cx + icon_size * 0.66
            available = tile.right - 12 - text_x
            value = state.temperature_text if not state.error else "—"
            self._text(text_x, icon_cy, value, 12.5 * growth, "bold", fill=theme.text, width=available)
            if expanded > 0.7:
                detail = state.label if not state.error else state.error
                self._text(text_x, icon_cy + 17 * scale, detail, 8.4 * growth,
                           fill=theme.muted, width=available)
        else:
            icon_cy = y + 34 * scale
            icons.draw(self.canvas, icon_name, x + width / 2, icon_cy,
                       min(30 * scale * growth, width * 0.42),
                       theme.accent if not state.error else theme.muted, ("icon",), icon_bg)
            self._text(x + width / 2, icon_cy + 26 * scale,
                       state.temperature_text if not state.error else "—",
                       11.5 * growth, "bold", fill=theme.text, anchor="n")
            if expanded > 0.7 and state.city:
                self._text(x + width / 2, icon_cy + 46 * scale, state.city,
                           7.8 * growth, fill=theme.muted, anchor="n", width=width - 8)

    def _draw_clock(self, tile, area, expanded):
        theme = self.theme
        x, y, width, height = area
        now = datetime.now()
        horizontal = self.layout.horizontal if self.layout else True
        scale = theme.scale
        growth = self._tile_growth(tile)
        time_text = now.strftime("%H:%M")
        if horizontal:
            center_y = y + height / 2 - (5 * scale if expanded > 0.6 else 0)
            self._text(x + 2, center_y, time_text, 13.5 * growth, "bold", fill=theme.text,
                       width=width - 6)
            if expanded > 0.7:
                self._text(x + 2, center_y + 18 * scale,
                           now.strftime("%a %d %b"), 8.4 * growth, fill=theme.muted,
                           width=width - 6)
        else:
            self._text(x + width / 2, y + height / 2 - 10 * scale, time_text,
                       13.0 * growth, "bold", fill=theme.text, anchor="center")
            if expanded > 0.7:
                self._text(x + width / 2, y + height / 2 + 12 * scale,
                           now.strftime("%d/%m"), 8.0 * growth, fill=theme.muted, anchor="n")

    def _draw_nokk(self, tile, area, expanded):
        theme = self.theme
        x, y, width, height = area
        horizontal = self.layout.horizontal if self.layout else True
        scale = theme.scale
        growth = self._tile_growth(tile)
        color = theme.accent if self.connected else (
            AMBER if self.connected is False else theme.muted
        )
        if horizontal:
            center_y = y + height / 2 - (5 * scale if expanded > 0.6 else 0)
            icons.draw(self.canvas, "spark", x + 10 * scale, center_y, 20 * scale * growth,
                       color, ("icon",), theme.panel)
            text_x = x + 24 * scale
            available = tile.right - 12 - text_x
            self._text(text_x, center_y - (7 * scale if expanded > 0.6 else 0),
                       "NOKK", 10.5 * growth, "bold", fill=theme.text, width=available)
            if expanded > 0.7:
                status = "Connesso" if self.connected else (
                    "Non raggiungibile" if self.connected is False else "Verifica…"
                )
                self._text(text_x, center_y + 13 * scale, status, 8.2 * growth,
                           fill=theme.muted, width=available)
            self.canvas.create_oval(
                tile.right - 13, center_y - 3, tile.right - 7, center_y + 3,
                fill=color, outline="",
            )
        else:
            icons.draw(self.canvas, "spark", x + width / 2, y + 34 * scale,
                       24 * scale * growth, color, ("icon",), theme.panel)
            self._text(x + width / 2, y + 52 * scale, "NOKK", 9.5 * growth, "bold",
                       fill=theme.text, anchor="n")

    def _draw_capture(self, tile, area, expanded):
        theme = self.theme
        x, y, width, height = area
        horizontal = self.layout.horizontal if self.layout else True
        scale = theme.scale
        growth = self._tile_growth(tile)
        if horizontal:
            center_y = y + height / 2 - (5 * scale if expanded > 0.6 else 0)
            icons.draw(self.canvas, "camera", x + 12 * scale, center_y, 21 * scale * growth,
                       theme.text, ("icon",), theme.panel)
            if expanded > 0.65:
                text_x = x + 26 * scale
                available = tile.right - 10 - text_x
                self._text(text_x, center_y - 7 * scale, "Schermo", 9.4 * growth, "bold",
                           fill=theme.text, width=available)
                self._text(text_x, center_y + 11 * scale,
                           shortcut_hint(self.config["capture"]["shortcut"]),
                           7.6 * growth, fill=theme.muted, width=available)
        else:
            icons.draw(self.canvas, "camera", x + width / 2, y + 30 * scale,
                       22 * scale * growth, theme.text, ("icon",), theme.panel)
            if expanded > 0.7:
                self._text(x + width / 2, y + 46 * scale, "Schermo", 8.4 * growth,
                           fill=theme.muted, anchor="n")

    def _draw_settings(self, tile, area, expanded):
        theme = self.theme
        x, y, width, height = area
        icons.draw(self.canvas, "gear", x + width / 2, y + height / 2,
                   min(21 * theme.scale * self._tile_growth(tile), height * 0.42),
                   theme.muted, ("icon",), theme.panel)

    def _draw_placeholder(self, tile, area, icon_name, title, hint):
        theme = self.theme
        x, y, width, height = area
        horizontal = self.layout.horizontal if self.layout else True
        scale = theme.scale
        if horizontal:
            center_y = y + height / 2
            icons.draw(self.canvas, icon_name, x + 10 * scale, center_y,
                       19 * scale, theme.muted, ("icon",), theme.panel)
            available = tile.right - 12 - (x + 24 * scale)
            self._text(x + 24 * scale, center_y, title, 9.4, "bold",
                       fill=theme.text, width=available)
        else:
            icons.draw(self.canvas, icon_name, x + width / 2, y + 30 * scale,
                       20 * scale, theme.muted, ("icon",), theme.panel)
            self._text(x + width / 2, y + 46 * scale, title, 8.4,
                       fill=theme.muted, anchor="n")

    # -------------------------------------------------------------- system
    def _ipc_command(self, action, payload):
        if action == "capture":
            self.post("capture", None)
            return {"ok": True}
        if action == "ask":
            self.post("ask", str(payload.get("question") or ""))
            return {"ok": True}
        if action in ("settings", "toggle", "reload", "quit"):
            self.post(action, None)
            return {"ok": True}
        return {"ok": True}

    def _reload_from_disk(self):
        from .settings import load_config

        self._apply_config(load_config(self.config_file))
        self._install_hotkey()

    def _cancel(self, job):
        if job is not None:
            try:
                self.root.after_cancel(job)
            except (tk.TclError, ValueError):
                pass

    def shutdown(self):
        if not self._alive:
            return
        self._alive = False
        self.stop_event.set()
        for job in (self._anim_job, self._expand_job, self._collapse_job,
                    self._pump_job, self._clock_job, self._toast_job):
            self._cancel(job)
        if self._hotkey is not None:
            self._hotkey.stop()
        if self._server is not None:
            self._server.stop()
        weather_service = getattr(self, "weather_service", None)
        if weather_service is not None:
            weather_service.stop()
        if self._hover_label is not None:
            try:
                self._hover_label.destroy()
            except tk.TclError:
                pass
            self._hover_label = None
        controller = getattr(self, "music_controller", None)
        if controller is not None and hasattr(controller, "stop"):
            try:
                controller.stop()
            except Exception:  # noqa: BLE001
                pass
        self._close_toast()
        try:
            self.root.destroy()
        except tk.TclError:
            pass


def trigger_running_capture():
    """Chiede al dock già avviato di fare la cattura schermo."""
    try:
        reply = ipc_send("capture")
    except OSError:
        return False
    return bool(reply.get("ok"))


def main(config, config_file):
    """Avvia il dock; solleva SystemExit con un messaggio chiaro se manca Tk."""
    enable_dpi_awareness()
    try:
        app = DockApp(config, config_file)
    except tk.TclError as error:
        raise SystemExit(
            "Il dock ha bisogno di una sessione grafica (DISPLAY o WAYLAND_DISPLAY). "
            f"Dettaglio: {error}"
        ) from None
    except OSError as error:
        raise SystemExit(f"Impossibile aprire il dock: {error}") from None
    app.run()


__all__ = ["DockApp", "main", "trigger_running_capture", "mix", "NokkError", "WIDGET_LABELS"]
