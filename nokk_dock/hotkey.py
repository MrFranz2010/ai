"""Scorciatoia globale per la cattura schermo.

Su Windows il dock usa `RegisterHotKey` (user32): la combinazione viene
consumata a livello di sistema e non richiede finestre né pacchetti esterni.
Su X11 registra il tasto sul server grafico tramite `ctypes` e libX11. Wayland
non consente scorciatoie globali alle applicazioni: lì resta il comando
`python dock_start.py --capture`, da assegnare alla scorciatoia del desktop.
"""

from __future__ import annotations

import ctypes
import os
import sys
import threading
import time

from .settings import KEY_PATTERN

KEY_PRESS = 2
SHIFT_MASK = 1
CONTROL_MASK = 4
MOD1_MASK = 8
MOD4_MASK = 64
MODIFIER_MASKS = {
    "shift": SHIFT_MASK,
    "ctrl": CONTROL_MASK,
    "alt": MOD1_MASK,
    "super": MOD4_MASK,
    "meta": MOD4_MASK,
}
LOCK_MASKS = (0, 2, 16)  # nessun lock, caps lock, num lock
KEYSYM_NAMES = {
    "space": "space",
    "enter": "Return",
    "return": "Return",
    "tab": "Tab",
    "esc": "Escape",
    "escape": "Escape",
    "print": "Print",
    "backspace": "BackSpace",
}

# Windows: RegisterHotKey / GetAsyncKeyState
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
PM_REMOVE = 0x0001
WINDOWS_MODIFIERS = {
    "alt": MOD_ALT,
    "ctrl": MOD_CONTROL,
    "shift": MOD_SHIFT,
    "super": MOD_WIN,
    "meta": MOD_WIN,
}
WINDOWS_KEYS = {
    "space": 0x20,
    "enter": 0x0D,
    "return": 0x0D,
    "tab": 0x09,
    "esc": 0x1B,
    "escape": 0x1B,
    "print": 0x2C,
    "backspace": 0x08,
    "delete": 0x2E,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
}


def split_shortcut(shortcut):
    """Divide `ctrl+alt+n` in (modificatori, tasto) dopo la validazione."""
    parts = [part.strip().lower() for part in (shortcut or "").split("+") if part.strip()]
    if not parts:
        raise ValueError("La scorciatoia è vuota.")
    key = parts[-1]
    modifiers = parts[:-1]
    for modifier in modifiers:
        if modifier not in MODIFIER_MASKS:
            raise ValueError(f"Modificatore sconosciuto: {modifier}.")
    if not modifiers:
        raise ValueError("La scorciatoia deve avere almeno un modificatore.")
    if not KEY_PATTERN.fullmatch(key):
        raise ValueError(
            "Tasto non riconosciuto: usa una lettera, un numero, F1–F24 o un nome "
            "come space, tab, enter, esc."
        )
    return tuple(modifiers), key


def parse_shortcut(shortcut):
    """Restituisce (maschera modificatori X11, nome keysym) da `ctrl+alt+n`."""
    modifiers, key = split_shortcut(shortcut)
    mask = 0
    for modifier in modifiers:
        mask |= MODIFIER_MASKS[modifier]
    if len(key) == 1 and key.isalpha():
        keysym = key
    else:
        keysym = KEYSYM_NAMES.get(key, key)
    return mask, keysym


def windows_virtual_key(key):
    """Codice virtuale Windows per un tasto della scorciatoia."""
    clean = (key or "").strip().lower()
    if clean in WINDOWS_KEYS:
        return WINDOWS_KEYS[clean]
    if len(clean) == 1 and clean.isalnum():
        return ord(clean.upper())
    if clean.startswith("f") and clean[1:].isdigit():
        number = int(clean[1:])
        if 1 <= number <= 24:
            return 0x70 + number - 1
    raise ValueError(f"Tasto non supportato su Windows: {key}.")


def windows_modifier_flags(modifiers):
    """Maschera MOD_* per RegisterHotKey."""
    flags = 0
    for modifier in modifiers:
        if modifier not in WINDOWS_MODIFIERS:
            raise ValueError(f"Modificatore sconosciuto: {modifier}.")
        flags |= WINDOWS_MODIFIERS[modifier]
    return flags


def is_windows(platform=None):
    return str(platform or sys.platform).startswith("win")


class _X11:
    """Binding minimale di libX11 fatto a mano, senza python-xlib."""

    def __init__(self):
        self.lib = ctypes.CDLL("libX11.so.6")
        self.lib.XOpenDisplay.argtypes = [ctypes.c_char_p]
        self.lib.XOpenDisplay.restype = ctypes.c_void_p
        self.lib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        self.lib.XDefaultRootWindow.restype = ctypes.c_ulong
        self.lib.XStringToKeysym.argtypes = [ctypes.c_char_p]
        self.lib.XStringToKeysym.restype = ctypes.c_ulong
        self.lib.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        self.lib.XKeysymToKeycode.restype = ctypes.c_ubyte
        self.lib.XGrabKey.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_ulong,
            ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ]
        self.lib.XGrabKey.restype = ctypes.c_int
        self.lib.XUngrabKey.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_ulong]
        self.lib.XPending.argtypes = [ctypes.c_void_p]
        self.lib.XPending.restype = ctypes.c_int
        self.lib.XNextEvent.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self.lib.XNextEvent.restype = ctypes.c_int
        self.lib.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.lib.XCloseDisplay.argtypes = [ctypes.c_void_p]


class X11Hotkey:
    """Registra una scorciatoia globale X11 e chiama `on_trigger`."""

    def __init__(self, shortcut, on_trigger, environ=None):
        self.shortcut = shortcut
        self.on_trigger = on_trigger
        self.environ = environ if environ is not None else os.environ
        self.thread = None
        self.stop_event = threading.Event()
        self.error = ""
        self._display = None
        self._x11 = None
        self._keycode = 0
        self._mask = 0

    def available(self) -> bool:
        if not self.environ.get("DISPLAY"):
            return False
        try:
            _X11()
        except OSError:
            return False
        return True

    def start(self) -> bool:
        if not self.available():
            self.error = "DISPLAY non disponibile: usa la scorciatoia del desktop."
            return False
        try:
            mask, keysym = parse_shortcut(self.shortcut)
        except ValueError as error:
            self.error = str(error)
            return False
        try:
            x11 = _X11()
            display = x11.lib.XOpenDisplay(None)
            if not display:
                self.error = "Impossibile aprire il display X11."
                return False
            sym = x11.lib.XStringToKeysym(keysym.encode("ascii"))
            if not sym:
                self.error = f"Tasto non riconosciuto: {keysym}."
                x11.lib.XCloseDisplay(display)
                return False
            keycode = x11.lib.XKeysymToKeycode(display, sym)
            if not keycode:
                self.error = f"Tasto non disponibile: {keysym}."
                x11.lib.XCloseDisplay(display)
                return False
            root = x11.lib.XDefaultRootWindow(display)
            grabbed = False
            for lock in LOCK_MASKS:
                result = x11.lib.XGrabKey(
                    display, int(keycode), int(mask | lock), root, 1, 1, 1
                )
                grabbed = grabbed or result != 0
            x11.lib.XSync(display, 0)
        except Exception as error:  # noqa: BLE001 - binding X11 non disponibile
            self.error = f"Scorciatoia globale non attiva ({error})."
            return False
        if not grabbed:
            self.error = "La scorciatoia è già usata da un altro programma."
            try:
                x11.lib.XCloseDisplay(display)
            except Exception:  # noqa: BLE001
                pass
            return False
        self._x11 = x11
        self._display = display
        self._keycode = int(keycode)
        self._mask = int(mask)
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._listen, name="nokk-dock-hotkey", daemon=True)
        self.thread.start()
        return True

    def _listen(self):
        x11 = self._x11
        display = self._display
        event = ctypes.create_string_buffer(192)
        while not self.stop_event.is_set():
            try:
                pending = x11.lib.XPending(display)
            except Exception:  # noqa: BLE001
                break
            if pending <= 0:
                time.sleep(0.03)
                continue
            try:
                x11.lib.XNextEvent(display, ctypes.byref(event))
            except Exception:  # noqa: BLE001
                break
            event_type = ctypes.cast(event, ctypes.POINTER(ctypes.c_int))[0]
            if event_type == KEY_PRESS:
                try:
                    self.on_trigger()
                except Exception:  # noqa: BLE001 - il callback non ferma il thread
                    pass

    def stop(self):
        self.stop_event.set()
        # Attende il thread prima di chiudere il display: chiuderlo mentre
        # XPending è in corso renderebbe il puntatore non valido.
        if self.thread is not None and self.thread.is_alive():
            self.thread.join(timeout=0.6)
        display = self._display
        if display and self._x11 and self._keycode:
            try:
                for lock in LOCK_MASKS:
                    self._x11.lib.XUngrabKey(display, self._keycode, self._mask | lock,
                                             self._x11.lib.XDefaultRootWindow(display))
                self._x11.lib.XSync(display, 0)
                self._x11.lib.XCloseDisplay(display)
            except Exception:  # noqa: BLE001
                pass
        self._display = None
        self._keycode = 0


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.c_void_p),
        ("message", ctypes.c_uint),
        ("wParam", ctypes.c_size_t),
        ("lParam", ctypes.c_ssize_t),
        ("time", ctypes.c_uint),
        ("pt", _POINT),
    ]


def _windows_user32():
    return ctypes.WinDLL("user32", use_last_error=True)


class WindowsHotkey:
    """Scorciatoia globale Windows via RegisterHotKey."""

    IDENTIFIER = 0x4E4F4B4B

    def __init__(self, shortcut, on_trigger, platform=None):
        self.shortcut = shortcut
        self.on_trigger = on_trigger
        self.platform = platform or sys.platform
        self.thread = None
        self.stop_event = threading.Event()
        self.error = ""
        self._ready = threading.Event()
        self._registered = False

    def available(self) -> bool:
        if not is_windows(self.platform):
            return False
        try:
            _windows_user32()
        except OSError:
            return False
        return True

    def start(self) -> bool:
        if not self.available():
            self.error = "Scorciatoia globale Windows non disponibile."
            return False
        try:
            modifiers, key = split_shortcut(self.shortcut)
            flags = windows_modifier_flags(modifiers) | MOD_NOREPEAT
            virtual_key = windows_virtual_key(key)
        except ValueError as error:
            self.error = str(error)
            return False
        self.stop_event.clear()
        self._ready.clear()
        self._registered = False
        self.thread = threading.Thread(
            target=self._listen,
            args=(flags, virtual_key),
            name="nokk-dock-hotkey",
            daemon=True,
        )
        self.thread.start()
        self._ready.wait(timeout=1.5)
        return self._registered

    def _listen(self, flags, virtual_key):
        try:
            user32 = _windows_user32()
        except OSError as error:
            self.error = f"user32 non disponibile ({error})."
            self._ready.set()
            return
        user32.RegisterHotKey.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_uint,
        ]
        user32.RegisterHotKey.restype = ctypes.c_int
        user32.UnregisterHotKey.argtypes = [ctypes.c_void_p, ctypes.c_int]
        user32.PeekMessageW.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint,
        ]
        try:
            registered = user32.RegisterHotKey(
                None, self.IDENTIFIER, int(flags), int(virtual_key)
            )
        except Exception as error:  # noqa: BLE001 - binding Windows non disponibile
            self.error = f"Scorciatoia globale non attiva ({error})."
            self._ready.set()
            return
        if not registered:
            self.error = "La scorciatoia è già usata da un altro programma."
            self._ready.set()
            return
        self._registered = True
        self._ready.set()
        message = _MSG()
        try:
            while not self.stop_event.is_set():
                found = user32.PeekMessageW(
                    ctypes.byref(message), None, 0, 0, PM_REMOVE
                )
                if not found:
                    time.sleep(0.04)
                    continue
                if message.message == WM_HOTKEY:
                    try:
                        self.on_trigger()
                    except Exception:  # noqa: BLE001
                        pass
        finally:
            try:
                user32.UnregisterHotKey(None, self.IDENTIFIER)
            except Exception:  # noqa: BLE001
                pass

    def stop(self):
        self.stop_event.set()
        if self.thread is not None and self.thread.is_alive():
            self.thread.join(timeout=0.8)
        self._registered = False


def create_hotkey(shortcut, on_trigger, platform=None, environ=None):
    """Restituisce il backend di scorciatoia adatto alla piattaforma."""
    if is_windows(platform):
        return WindowsHotkey(shortcut, on_trigger, platform=platform)
    return X11Hotkey(shortcut, on_trigger, environ=environ)


def shortcut_hint(shortcut: str) -> str:
    """Versione leggibile della scorciatoia, per l'interfaccia."""
    return " + ".join(part.capitalize() for part in (shortcut or "").split("+") if part)


def backend_name(platform=None) -> str:
    """Nome del backend di scorciatoia, per la diagnostica."""
    return "Windows RegisterHotKey" if is_windows(platform) else "X11 XGrabKey"
