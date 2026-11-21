"""Piccolo canale IPC fra istanze del dock.

Su Linux usa un socket Unix in `XDG_RUNTIME_DIR`. Su Windows usa un socket TCP
in ascolto solo su 127.0.0.1: la porta e un token casuale finiscono in
`%LOCALAPPDATA%\\nokk\\dock-endpoint.json`, con permessi riservati all'utente.

Serve a due cose: una sola istanza del dock alla volta e il comando esterno
`python dock_start.py --capture`, che permette di assegnare la cattura schermo
alla scorciatoia globale del desktop anche su Wayland.
"""

from __future__ import annotations

import json
import os
import secrets
import socket
import sys
import tempfile
import threading
from pathlib import Path


def is_windows(platform=None) -> bool:
    return str(platform or sys.platform).startswith("win")


def socket_path() -> Path:
    base = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    return Path(base) / f"nokk-dock-{getattr(os, 'getuid', lambda: 0)()}.sock"


def windows_endpoint_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if not base:
        base = str(Path.home() / "AppData" / "Local")
    return Path(base) / "nokk" / "dock-endpoint.json"


def endpoint_path(platform=None) -> Path:
    """Percorso del file che descrive l'endpoint del dock."""
    return windows_endpoint_path() if is_windows(platform) else socket_path()


def _read_endpoint(path: Path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    port = data.get("port")
    token = data.get("token")
    if not isinstance(port, int) or not 0 < port < 65536:
        return None
    return port, token if isinstance(token, str) else ""


def send(action, payload=None, timeout=2.0, path=None, platform=None):
    """Invia un comando al dock in esecuzione; solleva OSError se non c'è."""
    target = Path(path) if path else endpoint_path(platform)
    message = {"action": action, "payload": payload or {}}
    if is_windows(platform):
        endpoint = _read_endpoint(target)
        if endpoint is None:
            raise OSError("Il dock non è in ascolto.")
        port, token = endpoint
        message["token"] = token
        raw = json.dumps(message).encode("utf-8")
        with socket.create_connection(("127.0.0.1", port), timeout=timeout) as client:
            client.settimeout(timeout)
            client.sendall(raw + b"\n")
            data = b""
            while True:
                chunk = client.recv(4096)
                if not chunk:
                    break
                data += chunk
                if b"\n" in data:
                    break
    else:
        raw = json.dumps(message).encode("utf-8")
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(timeout)
            client.connect(str(target))
            client.sendall(raw + b"\n")
            data = b""
            while True:
                chunk = client.recv(4096)
                if not chunk:
                    break
                data += chunk
                if b"\n" in data:
                    break
    try:
        return json.loads(data.decode("utf-8").strip() or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}


class DockServer:
    """Server locale che consegna i comandi al dock."""

    def __init__(self, handler, path=None, platform=None, token=None):
        self.handler = handler
        self.platform = platform or sys.platform
        self.windows = is_windows(self.platform)
        self.path = Path(path) if path else endpoint_path(self.platform)
        self.token = token or secrets.token_hex(16)
        self.socket = None
        self.thread = None
        self.stop_event = threading.Event()

    @property
    def address(self):
        if self.socket is None:
            return None
        try:
            return self.socket.getsockname()
        except OSError:
            return None

    def start(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            try:
                send("ping", timeout=0.4, path=self.path, platform=self.platform)
            except OSError:
                self.path.unlink(missing_ok=True)
            else:
                raise OSError("Un'altra istanza del dock è già in esecuzione.")
        if self.windows:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(("127.0.0.1", 0))
            server.listen(4)
            port = server.getsockname()[1]
            try:
                self.path.write_text(
                    json.dumps({"port": port, "token": self.token}),
                    encoding="utf-8",
                )
                os.chmod(self.path, 0o600)
            except OSError as error:
                server.close()
                raise OSError(f"Impossibile scrivere l'endpoint del dock: {error}") from None
            server.settimeout(0.5)
            self.socket = server
        else:
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind(str(self.path))
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass
            server.listen(4)
            server.settimeout(0.5)
            self.socket = server
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._loop, name="nokk-dock-ipc", daemon=True)
        self.thread.start()
        return self

    def _loop(self):
        while not self.stop_event.is_set():
            try:
                client, _address = self.socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with client:
                try:
                    client.settimeout(2.0)
                    raw = client.recv(65536)
                except OSError:
                    continue
                try:
                    message = json.loads(raw.decode("utf-8").strip() or "{}")
                except (UnicodeDecodeError, json.JSONDecodeError):
                    message = {}
                action = message.get("action")
                payload = message.get("payload") or {}
                reply = {"ok": True}
                if self.windows and message.get("token") != self.token:
                    reply = {"ok": False, "error": "Token IPC non valido."}
                elif isinstance(action, str) and action:
                    try:
                        result = self.handler(action, payload if isinstance(payload, dict) else {})
                        if isinstance(result, dict):
                            reply.update(result)
                    except Exception as error:  # noqa: BLE001 - risposta sempre JSON
                        reply = {"ok": False, "error": str(error)}
                try:
                    client.sendall((json.dumps(reply) + "\n").encode("utf-8"))
                except OSError:
                    pass

    def stop(self):
        self.stop_event.set()
        if self.socket is not None:
            try:
                self.socket.close()
            except OSError:
                pass
            self.socket = None
        self.path.unlink(missing_ok=True)
