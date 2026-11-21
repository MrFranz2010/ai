"""Icona nella system tray del dock.

Su Windows l'icona usa solo ctypes e le API di sistema (`Shell_NotifyIcon`),
quindi il dock non aggiunge dipendenze. Altrove si usa `pystray` se è
installato; senza, il dock continua a funzionare e si riporta a schermo con
`python dock_start.py --settings` o con la scorciatoia della cattura.
"""

from __future__ import annotations

import ctypes
import sys
import threading
import types
from pathlib import Path

ASSET_DIR = Path(__file__).resolve().parent / "assets"
ICON_ICO = ASSET_DIR / "nokk.ico"
ICON_PNG = ASSET_DIR / "nokk.png"
TOOLTIP = "NOKK Dock"

# (azione, etichetta); `None` inserisce un separatore.
MENU = (
    ("toggle", "Mostra / nascondi il dock"),
    ("ask", "Chiedi a NOKK"),
    ("capture", "Cattura schermo e chiedi"),
    ("settings", "Impostazioni del dock"),
    (None, None),
    ("quit", "Esci"),
)

WM_APP = 0x8000
CALLBACK_MESSAGE = WM_APP + 1


def is_windows(platform=None):
    return str(platform or sys.platform).startswith("win")


def menu_entries():
    """Voci del menu della tray: `(azione, etichetta)`, azione `None` = separatore."""
    return tuple(MENU)


def create_tray(actions):
    """Avvia l'icona e restituisce l'oggetto con `stop()`, oppure `None`."""
    backend = _WindowsTray(actions) if is_windows() else _PystrayTray(actions)
    try:
        return backend.start()
    except Exception:  # noqa: BLE001 - la tray non deve impedire l'avvio del dock
        return None


def _run_action(actions, action):
    callback = actions.get(action)
    if callback is None:
        return
    try:
        callback()
    except Exception:  # noqa: BLE001 - un'azione non deve fermare il ciclo della tray
        pass


def _win32():
    """Carica le API e definisce le strutture Win32 solo quando servono."""
    from ctypes import wintypes

    WNDPROC = ctypes.WINFUNCTYPE(
        ctypes.c_ssize_t,
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    )

    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", wintypes.DWORD),
            ("Data2", wintypes.WORD),
            ("Data3", wintypes.WORD),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    class NOTIFYICONDATAW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("hWnd", wintypes.HWND),
            ("uID", wintypes.UINT),
            ("uFlags", wintypes.UINT),
            ("uCallbackMessage", wintypes.UINT),
            ("hIcon", wintypes.HICON),
            ("szTip", wintypes.WCHAR * 128),
            ("dwState", wintypes.DWORD),
            ("dwStateMask", wintypes.DWORD),
            ("szInfo", wintypes.WCHAR * 256),
            ("uVersion", wintypes.UINT),
            ("szInfoTitle", wintypes.WCHAR * 64),
            ("dwInfoFlags", wintypes.DWORD),
            ("guidItem", GUID),
            ("hBalloonIcon", wintypes.HICON),
        ]

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [
            ("style", wintypes.UINT),
            ("lpfnWndProc", WNDPROC),
            ("cbClsExtra", ctypes.c_int),
            ("cbWndExtra", ctypes.c_int),
            ("hInstance", wintypes.HINSTANCE),
            ("hIcon", wintypes.HICON),
            ("hCursor", ctypes.c_void_p),
            ("hbrBackground", wintypes.HBRUSH),
            ("lpszMenuName", wintypes.LPCWSTR),
            ("lpszClassName", wintypes.LPCWSTR),
        ]

    class POINT(ctypes.Structure):
        _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

    class MSG(ctypes.Structure):
        _fields_ = [
            ("hWnd", wintypes.HWND),
            ("message", wintypes.UINT),
            ("wParam", wintypes.WPARAM),
            ("lParam", wintypes.LPARAM),
            ("time", wintypes.DWORD),
            ("pt", POINT),
        ]

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE

    user32.RegisterClassW.argtypes = (ctypes.POINTER(WNDCLASSW),)
    user32.RegisterClassW.restype = wintypes.WORD
    user32.CreateWindowExW.argtypes = (
        wintypes.DWORD,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HWND,
        wintypes.HMENU,
        wintypes.HINSTANCE,
        wintypes.LPVOID,
    )
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.DefWindowProcW.argtypes = (
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    )
    user32.DefWindowProcW.restype = ctypes.c_ssize_t
    user32.DestroyWindow.argtypes = (wintypes.HWND,)
    user32.DestroyWindow.restype = wintypes.BOOL
    user32.GetMessageW.argtypes = (
        ctypes.POINTER(MSG),
        wintypes.HWND,
        wintypes.UINT,
        wintypes.UINT,
    )
    user32.GetMessageW.restype = wintypes.BOOL
    user32.TranslateMessage.argtypes = (ctypes.POINTER(MSG),)
    user32.TranslateMessage.restype = wintypes.BOOL
    user32.DispatchMessageW.argtypes = (ctypes.POINTER(MSG),)
    user32.DispatchMessageW.restype = ctypes.c_ssize_t
    user32.PostMessageW.argtypes = (
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    )
    user32.PostMessageW.restype = wintypes.BOOL
    user32.PostQuitMessage.argtypes = (ctypes.c_int,)
    user32.LoadImageW.argtypes = (
        wintypes.HINSTANCE,
        wintypes.LPCWSTR,
        wintypes.UINT,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    )
    user32.LoadImageW.restype = wintypes.HANDLE
    user32.LoadIconW.argtypes = (wintypes.HINSTANCE, wintypes.LPCWSTR)
    user32.LoadIconW.restype = wintypes.HICON
    user32.DestroyIcon.argtypes = (wintypes.HICON,)
    user32.DestroyIcon.restype = wintypes.BOOL
    user32.GetSystemMetrics.argtypes = (ctypes.c_int,)
    user32.GetSystemMetrics.restype = ctypes.c_int
    user32.CreatePopupMenu.argtypes = ()
    user32.CreatePopupMenu.restype = wintypes.HMENU
    user32.AppendMenuW.argtypes = (
        wintypes.HMENU,
        wintypes.UINT,
        wintypes.UINT,
        wintypes.LPCWSTR,
    )
    user32.AppendMenuW.restype = wintypes.BOOL
    user32.TrackPopupMenu.argtypes = (
        wintypes.HMENU,
        wintypes.UINT,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HWND,
        wintypes.LPVOID,
    )
    user32.TrackPopupMenu.restype = ctypes.c_int
    user32.DestroyMenu.argtypes = (wintypes.HMENU,)
    user32.DestroyMenu.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.GetCursorPos.argtypes = (ctypes.POINTER(POINT),)
    user32.GetCursorPos.restype = wintypes.BOOL
    user32.RegisterWindowMessageW.argtypes = (wintypes.LPCWSTR,)
    user32.RegisterWindowMessageW.restype = wintypes.UINT
    shell32.Shell_NotifyIconW.argtypes = (
        wintypes.DWORD,
        ctypes.POINTER(NOTIFYICONDATAW),
    )
    shell32.Shell_NotifyIconW.restype = wintypes.BOOL

    return types.SimpleNamespace(
        WNDPROC=WNDPROC,
        NOTIFYICONDATAW=NOTIFYICONDATAW,
        WNDCLASSW=WNDCLASSW,
        POINT=POINT,
        MSG=MSG,
        user32=user32,
        shell32=shell32,
        kernel32=kernel32,
        CALLBACK=CALLBACK_MESSAGE,
        TASKBAR_CREATED=user32.RegisterWindowMessageW("TaskbarCreated"),
        WM_CLOSE=0x0010,
        WM_DESTROY=0x0002,
        WM_NULL=0x0000,
        WM_CONTEXTMENU=0x007B,
        WM_RBUTTONUP=0x0205,
        WM_LBUTTONUP=0x0202,
        NIN_SELECT=0x0400,
        NIN_KEYSELECT=0x0401,
        NIM_ADD=0,
        NIM_DELETE=2,
        NIM_SETVERSION=4,
        NOTIFYICON_VERSION_4=4,
        NIF_MESSAGE=0x00000001,
        NIF_ICON=0x00000002,
        NIF_TIP=0x00000004,
        IMAGE_ICON=1,
        LR_LOADFROMFILE=0x00000010,
        SM_CXSMICON=49,
        SM_CYSMICON=50,
        IDI_APPLICATION=32512,
        MF_STRING=0x00000000,
        MF_SEPARATOR=0x00000800,
        TPM_RETURNCMD=0x0100,
        TPM_RIGHTBUTTON=0x0002,
    )


class _WindowsTray:
    """Icona nativa su Windows: finestra nascosta, ciclo messaggi e menu."""

    _own_icon = False

    def __init__(self, actions):
        self.actions = actions
        self._api = None
        self._hwnd = None
        self._data = None
        self._icon = None
        self._wndproc = None
        self._ready = threading.Event()

    # -- ciclo di vita ----------------------------------------------------
    def start(self):
        try:
            self._api = _win32()
        except (AttributeError, OSError, ImportError):
            return None
        threading.Thread(
            target=self._run, name="nokk-dock-tray", daemon=True
        ).start()
        self._ready.wait(2.0)
        return self if self._hwnd is not None else None

    def stop(self):
        api = self._api
        hwnd, self._hwnd = self._hwnd, None
        if api is None or not hwnd:
            return
        try:
            api.user32.PostMessageW(hwnd, api.WM_CLOSE, 0, 0)
        except Exception:  # noqa: BLE001 - chiusura già avvenuta
            pass

    # -- thread della tray ------------------------------------------------
    def _run(self):
        api = self._api
        hwnd = None
        try:
            self._wndproc = api.WNDPROC(self._on_message)
            instance = api.kernel32.GetModuleHandleW(None)
            window_class = api.WNDCLASSW()
            window_class.lpfnWndProc = self._wndproc
            window_class.hInstance = instance
            window_class.lpszClassName = "NokkDockTrayWindow"
            # Se la classe esiste già (dock riavviato) va bene lo stesso.
            api.user32.RegisterClassW(ctypes.byref(window_class))
            hwnd = api.user32.CreateWindowExW(
                0, "NokkDockTrayWindow", "NOKK Dock", 0,
                0, 0, 0, 0, None, None, instance, None,
            )
            if not hwnd:
                raise OSError("finestra della tray non creata")
            data = api.NOTIFYICONDATAW()
            data.cbSize = ctypes.sizeof(api.NOTIFYICONDATAW)
            data.hWnd = hwnd
            data.uID = 1
            data.uFlags = api.NIF_MESSAGE | api.NIF_ICON | api.NIF_TIP
            data.uCallbackMessage = api.CALLBACK
            data.hIcon = self._load_icon(api)
            data.szTip = TOOLTIP
            if not api.shell32.Shell_NotifyIconW(api.NIM_ADD, ctypes.byref(data)):
                raise OSError("Shell_NotifyIcon non ha aggiunto l'icona")
            self._data = data
            # Versione 4: un solo evento per clic e per menu contestuale.
            data.uVersion = api.NOTIFYICON_VERSION_4
            api.shell32.Shell_NotifyIconW(api.NIM_SETVERSION, ctypes.byref(data))
        except Exception:  # noqa: BLE001 - niente tray: il dock resta usabile
            if hwnd:
                api.user32.DestroyWindow(hwnd)
            self._hwnd = None
            self._ready.set()
            return
        self._hwnd = hwnd
        self._ready.set()
        message = api.MSG()
        while api.user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            api.user32.TranslateMessage(ctypes.byref(message))
            api.user32.DispatchMessageW(ctypes.byref(message))
        if self._own_icon and self._icon:
            api.user32.DestroyIcon(self._icon)

    def _load_icon(self, api):
        self._icon = None
        size = api.user32.GetSystemMetrics(api.SM_CXSMICON) or 16
        if ICON_ICO.exists():
            handle = api.user32.LoadImageW(
                None, str(ICON_ICO), api.IMAGE_ICON, size, size, api.LR_LOADFROMFILE
            )
            if handle:
                self._icon = handle
                self._own_icon = True
                return handle
        fallback = ctypes.cast(
            ctypes.c_void_p(api.IDI_APPLICATION), ctypes.c_wchar_p
        )
        self._icon = api.user32.LoadIconW(None, fallback)
        return self._icon

    # -- messaggi ---------------------------------------------------------
    def _on_message(self, hwnd, message, wparam, lparam):
        api = self._api
        try:
            if message == api.WM_DESTROY:
                if self._data is not None:
                    api.shell32.Shell_NotifyIconW(
                        api.NIM_DELETE, ctypes.byref(self._data)
                    )
                    self._data = None
                api.user32.PostQuitMessage(0)
                return 0
            if message == api.TASKBAR_CREATED:
                # Explorer riavviato: la tray perde le icone, si rimette la nostra.
                if self._data is not None:
                    api.shell32.Shell_NotifyIconW(
                        api.NIM_ADD, ctypes.byref(self._data)
                    )
                return 0
            if message == api.CALLBACK:
                event = int(lparam) & 0xFFFF
                if event in (api.NIN_SELECT, api.NIN_KEYSELECT, api.WM_LBUTTONUP):
                    _run_action(self.actions, "toggle")
                elif event in (api.WM_CONTEXTMENU, api.WM_RBUTTONUP):
                    self._show_menu()
                return 0
        except Exception:  # noqa: BLE001 - una callback rotta non chiude la tray
            return 0
        return api.user32.DefWindowProcW(hwnd, message, wparam, lparam)

    def _show_menu(self):
        api = self._api
        menu = api.user32.CreatePopupMenu()
        if not menu:
            return
        commands = {}
        try:
            for action, label in MENU:
                if action is None:
                    api.user32.AppendMenuW(menu, api.MF_SEPARATOR, 0, None)
                    continue
                command = 100 + len(commands)
                commands[command] = action
                api.user32.AppendMenuW(menu, api.MF_STRING, command, label)
            point = api.POINT()
            api.user32.GetCursorPos(ctypes.byref(point))
            api.user32.SetForegroundWindow(self._hwnd)
            chosen = api.user32.TrackPopupMenu(
                menu,
                api.TPM_RETURNCMD | api.TPM_RIGHTBUTTON,
                point.x,
                point.y,
                0,
                self._hwnd,
                None,
            )
            api.user32.PostMessageW(self._hwnd, api.WM_NULL, 0, 0)
            if chosen in commands:
                _run_action(self.actions, commands[chosen])
        finally:
            api.user32.DestroyMenu(menu)


class _PystrayTray:
    """Tray per Linux e macOS tramite pystray, se l'utente lo installa."""

    def __init__(self, actions):
        self.actions = actions
        self.icon = None

    def start(self):
        try:
            import pystray  # type: ignore[import-not-found]
            from PIL import Image  # type: ignore[import-not-found]
        except Exception:  # noqa: BLE001 - pystray è facoltativo
            return None
        if not ICON_PNG.exists():
            return None
        try:
            image = Image.open(ICON_PNG)
            image.load()
            items = []
            for action, label in MENU:
                if action is None:
                    items.append(pystray.Menu.SEPARATOR)
                else:
                    items.append(
                        pystray.MenuItem(
                            label,
                            self._handler(action),
                            default=action == "toggle",
                        )
                    )
            self.icon = pystray.Icon(
                "nokk-dock", image, TOOLTIP, pystray.Menu(*items)
            )
            threading.Thread(
                target=self.icon.run, name="nokk-dock-tray", daemon=True
            ).start()
        except Exception:  # noqa: BLE001 - backend grafico non disponibile
            self.icon = None
            return None
        return self

    def stop(self):
        icon, self.icon = self.icon, None
        if icon is None:
            return
        try:
            icon.stop()
        except Exception:  # noqa: BLE001 - già fermata
            pass

    def _handler(self, action):
        def call(_icon=None, _item=None):
            _run_action(self.actions, action)

        return call


__all__ = [
    "MENU",
    "TOOLTIP",
    "create_tray",
    "is_windows",
    "menu_entries",
]
