"""Controlli musicali.

Su Linux si usa `playerctl` (MPRIS) e funziona con Spotify, Firefox, VLC, mpv,
Rhythmbox e così via. Su Windows si usano i tasti multimediali di sistema
(VK_MEDIA_*) e, quando possibile, i metadati della sessione corrente tramite
WinRT letto da PowerShell. Se i metadati non sono disponibili i controlli
restano attivi: il widget mostra che il titolo non è leggibile.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

SEPARATOR = "\x1f"
FORMAT = SEPARATOR.join((
    "{{status}}",
    "{{artist}}",
    "{{title}}",
    "{{album}}",
    "{{mpris:length}}",
    "{{mpris:artUrl}}",
))

INSTALL_HINT = "Installa playerctl: sudo apt install playerctl"
WINDOWS_HINT = "PowerShell non trovato: i controlli musicali non sono disponibili."
WINDOWS_NO_METADATA = "Controlli multimediali attivi"

CREATE_NO_WINDOW = 0x08000000
WINDOWS_MEDIA_KEYS = {
    "play_pause": 0xB3,
    "next": 0xB0,
    "previous": 0xB1,
    "stop": 0xB2,
}
WINDOWS_STATUS = {
    "playing": "Playing",
    "paused": "Paused",
    "stopped": "Stopped",
}

WINDOWS_HELPER_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
Add-Type -AssemblyName System.Runtime.WindowsRuntime
Add-Type -AssemblyName System.Drawing
$managerType = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager, Windows.Media.Control, ContentType = WindowsRuntime]
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
})[0]
function Await($operation, $type) {
    $task = $asTask.MakeGenericMethod($type).Invoke($null, @($operation))
    $task.Wait(-1) | Out-Null
    $task.Result
}
$artKey = ''
$artPath = ''
$artTries = 0
try {
    Get-ChildItem ([System.IO.Path]::GetTempPath()) -Filter 'nokk-art-*.png' -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -lt (Get-Date).AddHours(-2) } |
        Remove-Item -Force -ErrorAction SilentlyContinue
} catch { }
function Save-Art($thumbnail, $key) {
    try {
        if ($null -eq $thumbnail) { return '' }
        $stream = Await ($thumbnail.OpenReadAsync()) ([Windows.Storage.Streams.IRandomAccessStreamWithContentType])
        # I byte vengono letti in memoria: lo stream WinRT non è sempre
        # ricercabile e System.Drawing lo rifiuterebbe.
        $size = [uint32]$stream.Size
        $reader = [Windows.Storage.Streams.DataReader]::new($stream.GetInputStreamAt(0))
        $loaded = Await ($reader.LoadAsync($size)) ([uint32])
        $bytes = New-Object byte[] $loaded
        $reader.ReadBytes($bytes)
        $reader.Dispose()
        $stream.Dispose()
        $sha = [System.Security.Cryptography.SHA1]::Create()
        $hash = [System.BitConverter]::ToString($sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($key))).Replace('-', '').ToLower()
        $target = Join-Path ([System.IO.Path]::GetTempPath()) ("nokk-art-$hash.png")
        # GDI+ non sovrascrive un file esistente: va tolto prima, altrimenti
        # dopo un riavvio la copertina non viene più salvata.
        if (Test-Path $target) { Remove-Item $target -Force -ErrorAction SilentlyContinue }
        try {
            $memory = New-Object System.IO.MemoryStream
            $memory.Write($bytes, 0, $bytes.Length)
            $memory.Position = 0
            $image = [System.Drawing.Image]::FromStream($memory)
            $bitmap = New-Object System.Drawing.Bitmap 256, 256
            $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
            $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
            $graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
            $graphics.DrawImage($image, 0, 0, 256, 256)
            $bitmap.Save($target, [System.Drawing.Imaging.ImageFormat]::Png)
            $graphics.Dispose()
            $bitmap.Dispose()
            $image.Dispose()
            $memory.Dispose()
            return $target
        } catch { }
        # Ripiego: i byte originali, se il ridimensionamento non riesce.
        $suffix = 'img'
        if ($bytes.Length -gt 3 -and $bytes[0] -eq 0x89) { $suffix = 'png' }
        elseif ($bytes.Length -gt 2 -and $bytes[0] -eq 0xFF -and $bytes[1] -eq 0xD8) { $suffix = 'jpg' }
        $raw = Join-Path ([System.IO.Path]::GetTempPath()) ("nokk-art-$hash.$suffix")
        if (Test-Path $raw) { Remove-Item $raw -Force -ErrorAction SilentlyContinue }
        [System.IO.File]::WriteAllBytes($raw, $bytes)
        return $raw
    } catch {
        return ''
    }
}
while ($true) {
    try {
        $manager = Await ($managerType::RequestAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager])
        $session = $manager.GetCurrentSession()
        if ($null -eq $session) {
            $artKey = ''
            @{ active = $false } | ConvertTo-Json -Compress
        } else {
            $properties = Await ($session.TryGetMediaPropertiesAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties])
            $info = $session.GetPlaybackInfo()
            $key = "$($properties.Artist)|$($properties.Title)|$($properties.AlbumTitle)"
            # Se la copertina non si salva si riprova nei cicli successivi,
            # invece di restare senza immagine per tutto il brano.
            if ($key -ne $artKey) { $artTries = 0 }
            if ($key -ne $artKey -or (-not $artPath -and $artTries -lt 5)) {
                $artPath = Save-Art $properties.Thumbnail $key
                if ($artPath) {
                    $artKey = $key
                    $artTries = 0
                } else {
                    $artPath = ''
                    $artTries = $artTries + 1
                }
            }
            @{
                active = $true
                status = [string]$info.PlaybackStatus
                title = [string]$properties.Title
                artist = [string]$properties.Artist
                album = [string]$properties.AlbumTitle
                art = $artPath
            } | ConvertTo-Json -Compress
        }
    } catch {
        $artKey = ''
        @{ active = $false; error = $true } | ConvertTo-Json -Compress
    }
    Start-Sleep -Milliseconds 1500
}
"""


@dataclass(frozen=True)
class MusicState:
    installed: bool = False
    active: bool = False
    status: str = "stopped"
    artist: str = ""
    title: str = ""
    album: str = ""
    length_seconds: float = 0.0
    position_seconds: float = 0.0
    art_url: str = ""
    message: str = ""

    @property
    def playing(self) -> bool:
        return self.status.lower() == "playing"

    @property
    def label(self) -> str:
        if self.title:
            return self.title
        return self.message or "Nessun brano"

    @property
    def subtitle(self) -> str:
        if self.artist and self.album:
            return f"{self.artist} — {self.album}"
        return self.artist or self.album or ""

    @property
    def progress(self) -> float:
        if self.length_seconds <= 0:
            return 0.0
        return max(0.0, min(1.0, self.position_seconds / self.length_seconds))

    @property
    def timecode(self) -> str:
        if self.length_seconds <= 0:
            return ""
        return f"{format_seconds(self.position_seconds)} / {format_seconds(self.length_seconds)}"


def format_seconds(value: float) -> str:
    total = max(0, int(value))
    return f"{total // 60}:{total % 60:02d}"


def is_windows(platform=None) -> bool:
    return str(platform or sys.platform).startswith("win")


def parse_metadata(text: str) -> MusicState:
    """Trasforma l'uscita di `playerctl metadata --format` in uno stato."""
    if not text or not text.strip():
        return MusicState(installed=True, message="Nessun player attivo")
    parts = text.strip("\n").split(SEPARATOR)
    while len(parts) < 6:
        parts.append("")

    def clean(value: str) -> str:
        return value.strip()

    def number(value: str) -> float:
        try:
            return float(clean(value))
        except ValueError:
            return 0.0

    length_us = number(parts[4])
    status = clean(parts[0]) or "stopped"
    return MusicState(
        installed=True,
        active=bool(clean(parts[2]) or clean(parts[1])),
        status=status,
        artist=clean(parts[1]),
        title=clean(parts[2]),
        album=clean(parts[3]),
        length_seconds=length_us / 1_000_000 if length_us > 0 else 0.0,
        art_url=clean(parts[5]),
    )


def windows_file_url(path) -> str:
    """Trasforma il percorso di un file in un URL `file:///` per le copertine."""
    value = str(path or "").strip().replace("\\", "/")
    if not value:
        return ""
    if "://" in value:
        return value
    if not value.startswith("/"):
        value = "/" + value
    return "file://" + value


def parse_windows_media_line(line: str):
    """Legge una riga JSON emessa dall'helper PowerShell di Windows."""
    if not line or not line.strip():
        return None
    try:
        data = json.loads(line.strip())
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    if not data.get("active"):
        return MusicState(installed=True, message="Nessun player attivo")
    status = str(data.get("status") or "").strip()
    return MusicState(
        installed=True,
        active=True,
        status=WINDOWS_STATUS.get(status.lower(), status or "Stopped"),
        title=str(data.get("title") or "").strip(),
        artist=str(data.get("artist") or "").strip(),
        album=str(data.get("album") or "").strip(),
        art_url=windows_file_url(data.get("art")),
    )


def send_media_key(virtual_key, platform=None) -> bool:
    """Premere un tasto multimediale su Windows tramite user32."""
    if not is_windows(platform):
        return False
    try:
        import ctypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.keybd_event(int(virtual_key), 0, 0, 0)
        user32.keybd_event(int(virtual_key), 0, 2, 0)
        return True
    except Exception:  # noqa: BLE001 - nessun controllo disponibile
        return False


class MusicController:
    """Piccolo wrapper su playerctl (Linux), con runner iniettabile per i test."""

    def __init__(self, player="", runner=None, which=shutil.which):
        self.player = (player or "").strip()
        self.runner = runner or subprocess.run
        self.which = which

    def available(self) -> bool:
        return bool(self.which("playerctl"))

    def _argv(self, *args):
        argv = ["playerctl"]
        if self.player:
            argv += ["--player", self.player]
        return argv + list(args)

    def _run(self, *args, timeout=6):
        try:
            completed = self.runner(
                self._argv(*args), timeout=timeout, capture_output=True, text=True
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return completed

    def refresh(self, with_position=True) -> MusicState:
        if not self.available():
            return MusicState(installed=False, message=INSTALL_HINT)
        completed = self._run("metadata", "--format", FORMAT)
        if completed is None or getattr(completed, "returncode", 1) != 0:
            detail = (getattr(completed, "stderr", "") or "").strip().lower()
            message = "Nessun player attivo"
            if "playerctl" in detail and "not found" in detail:
                message = INSTALL_HINT
            return MusicState(installed=True, message=message)
        state = parse_metadata(completed.stdout or "")
        if with_position and state.length_seconds > 0 and state.playing:
            position = self._run("position", timeout=4)
            if position is not None and getattr(position, "returncode", 1) == 0:
                try:
                    state = MusicState(
                        installed=state.installed,
                        active=state.active,
                        status=state.status,
                        artist=state.artist,
                        title=state.title,
                        album=state.album,
                        length_seconds=state.length_seconds,
                        position_seconds=float((position.stdout or "0").strip() or 0),
                        art_url=state.art_url,
                        message=state.message,
                    )
                except ValueError:
                    pass
        return state

    def play_pause(self) -> bool:
        return self._succeeded("play-pause")

    def next_track(self) -> bool:
        return self._succeeded("next")

    def previous_track(self) -> bool:
        return self._succeeded("previous")

    def _succeeded(self, command) -> bool:
        if not self.available():
            return False
        completed = self._run(command, timeout=5)
        return completed is not None and getattr(completed, "returncode", 1) == 0

    def stop(self):
        """Nessun processo da chiudere: esiste per uniformità con Windows."""
        return None


class WindowsMusicController:
    """Controlli con i tasti multimediali e metadati WinRT via PowerShell."""

    def __init__(self, player="", which=shutil.which, popen=None, platform=None, key_sender=None):
        self.player = (player or "").strip()
        self.which = which
        self.popen = popen or subprocess.Popen
        self.platform = platform or sys.platform
        self.key_sender = key_sender or (lambda code: send_media_key(code, self.platform))
        self._process = None
        self._reader = None
        self._script = None
        self._lock = threading.Lock()
        self._state = MusicState(installed=True, message=WINDOWS_NO_METADATA)

    def _powershell(self):
        return self.which("powershell") or self.which("pwsh") or self.which("powershell.exe")

    def available(self) -> bool:
        return bool(self._powershell())

    def refresh(self, with_position=True) -> MusicState:
        if not self.available():
            return MusicState(installed=False, message=WINDOWS_HINT)
        self._ensure_helper()
        with self._lock:
            return self._state

    def _ensure_helper(self):
        if self._process is not None and self._process.poll() is None:
            return
        powershell = self._powershell()
        if not powershell:
            return
        script = Path(tempfile.gettempdir()) / "nokk-media.ps1"
        try:
            script.write_text(WINDOWS_HELPER_SCRIPT, encoding="utf-8")
        except OSError:
            return
        self._script = script
        try:
            process = self.popen(
                [
                    powershell, "-NoProfile", "-NonInteractive",
                    "-ExecutionPolicy", "Bypass", "-File", str(script),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=CREATE_NO_WINDOW,
            )
        except (OSError, ValueError):
            self._process = None
            return
        self._process = process
        self._reader = threading.Thread(
            target=self._read_lines, args=(process,), name="nokk-dock-windows-media", daemon=True
        )
        self._reader.start()

    def _read_lines(self, process):
        stdout = getattr(process, "stdout", None)
        if stdout is None:
            return
        try:
            for line in stdout:
                state = parse_windows_media_line(line)
                if state is None:
                    continue
                with self._lock:
                    self._state = state
        except (OSError, ValueError):
            return

    def play_pause(self) -> bool:
        return self._press("play_pause")

    def next_track(self) -> bool:
        return self._press("next")

    def previous_track(self) -> bool:
        return self._press("previous")

    def _press(self, action) -> bool:
        code = WINDOWS_MEDIA_KEYS.get(action)
        if code is None:
            return False
        try:
            return bool(self.key_sender(code))
        except Exception:  # noqa: BLE001
            return False

    def stop(self):
        process = self._process
        self._process = None
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except (OSError, ValueError):
                pass
        if self._script is not None:
            try:
                self._script.unlink(missing_ok=True)
            except OSError:
                pass
            self._script = None


def create_controller(player="", platform=None):
    """Restituisce il controller musicale adatto alla piattaforma."""
    if is_windows(platform):
        return WindowsMusicController(player, platform=platform)
    return MusicController(player)
