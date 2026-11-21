"""Cattura dello schermo per il dock (Linux e Windows).

Su Linux prova prima gli strumenti nativi della sessione grafica (Wayland con
`grim`, X11 con `gnome-screenshot`, `spectacle`, `scrot` o ImageMagick). Su
Windows usa PowerShell e `System.Drawing`, che sono presenti in ogni
installazione. Pillow resta un ripiego facoltativo su entrambe le piattaforme e
serve anche a ridurre gli scatti oltre il limite di NOKK.
"""

from __future__ import annotations

import base64
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

MAX_NOKK_IMAGE_BYTES = 4 * 1024 * 1024
CREATE_NO_WINDOW = 0x08000000

# (comando, costruttore argv, ambiente). L'ordine conta: prima le sessioni
# Wayland, poi gli strumenti X11, infine ImageMagick.
TOOLS = (
    ("grim", lambda path, scale: ["grim", "-s", f"{scale:g}", path], "wayland"),
    ("gnome-screenshot", lambda path, scale: ["gnome-screenshot", "-f", path], "any"),
    ("spectacle", lambda path, scale: ["spectacle", "-b", "-n", "-o", path], "any"),
    ("scrot", lambda path, scale: ["scrot", "-o", path], "x11"),
    ("import", lambda path, scale: ["import", "-window", "root", path], "x11"),
)

WINDOWS_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$bounds = [System.Windows.Forms.SystemInformation]::VirtualScreen
$full = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
$graphics = [System.Drawing.Graphics]::FromImage($full)
$graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
$scale = $SCALE$
if ($scale -lt 1) {
  $w = [int]($bounds.Width * $scale)
  $h = [int]($bounds.Height * $scale)
  $small = New-Object System.Drawing.Bitmap $w, $h
  $g2 = [System.Drawing.Graphics]::FromImage($small)
  $g2.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
  $g2.DrawImage($full, 0, 0, $w, $h)
  $small.Save('$PATH$', [System.Drawing.Imaging.ImageFormat]::Png)
  $g2.Dispose()
  $small.Dispose()
} else {
  $full.Save('$PATH$', [System.Drawing.Imaging.ImageFormat]::Png)
}
$graphics.Dispose()
$full.Dispose()
"""

MAGIC = (
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
    (b"GIF87a", "image/gif", ".gif"),
    (b"GIF89a", "image/gif", ".gif"),
)


class CaptureError(Exception):
    """Errore di cattura mostrato all'utente."""


def sniff_mime(data: bytes):
    for magic, mime_type, suffix in MAGIC:
        if data.startswith(magic):
            return mime_type, suffix
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", ".webp"
    return None, None


def is_wayland(environ) -> bool:
    return bool(environ.get("WAYLAND_DISPLAY"))


def is_windows(platform=None) -> bool:
    return str(platform or sys.platform).startswith("win")


def candidate_tools(which=shutil.which, environ=None, platform=None):
    """Elenca gli strumenti disponibili, ordinati per sessione grafica."""
    if is_windows(platform):
        return []
    env = environ if environ is not None else {}
    names = []
    for name, builder, target in TOOLS:
        if target == "wayland" and not is_wayland(env):
            continue
        if target == "x11" and is_wayland(env) and name == "scrot":
            continue
        if which(name):
            names.append((name, builder))
    return names


def windows_powershell(which=shutil.which):
    """Percorso di PowerShell (o di PowerShell 7) su Windows."""
    return which("powershell") or which("pwsh") or which("powershell.exe")


def windows_screenshot_script(path, scale=1.0):
    """Script PowerShell che cattura tutti i monitor e salva un PNG."""
    safe_path = str(path).replace("'", "''")
    factor = max(0.25, min(1.0, float(scale)))
    return (
        WINDOWS_SCRIPT
        .replace("$SCALE$", f"{factor:.3f}")
        .replace("$PATH$", safe_path)
    )


def _run_tool(runner, argv, timeout, platform):
    """Esegue uno strumento esterno senza aprire console su Windows."""
    kwargs = {"timeout": timeout, "capture_output": True}
    if is_windows(platform):
        kwargs["creationflags"] = CREATE_NO_WINDOW
    return runner(argv, **kwargs)


def _capture_windows(path, scale, runner, which, platform):
    powershell = windows_powershell(which)
    if not powershell:
        raise CaptureError(
            "PowerShell non trovato: serve per catturare lo schermo su Windows."
        )
    script = Path(tempfile.gettempdir()) / f"nokk-shot-{uuid.uuid4().hex}.ps1"
    script.write_text(windows_screenshot_script(path, scale), encoding="utf-8")
    try:
        completed = _run_tool(
            runner,
            [
                powershell, "-NoProfile", "-NonInteractive",
                "-ExecutionPolicy", "Bypass", "-File", str(script),
            ],
            45,
            platform,
        )
    finally:
        script.unlink(missing_ok=True)
    target = Path(path)
    if getattr(completed, "returncode", 1) != 0 or not target.exists() or target.stat().st_size < 512:
        detail = (getattr(completed, "stderr", b"") or b"")
        if isinstance(detail, bytes):
            detail = detail.decode("utf-8", "replace")
        detail = str(detail).strip().splitlines()[:1]
        message = "Cattura dello schermo non riuscita su Windows."
        if detail:
            message += f" PowerShell: {detail[0][:200]}"
        raise CaptureError(message)
    return path


def capture_screen(
    scale=1.0,
    runner=None,
    which=shutil.which,
    environ=None,
    grabber=None,
    platform=None,
):
    """Esegue lo screenshot e restituisce il percorso del file temporaneo."""
    runner = runner or subprocess.run
    env = environ if environ is not None else {}
    current = platform or sys.platform
    path = str(Path(tempfile.gettempdir()) / f"nokk-dock-{uuid.uuid4().hex}.png")
    attempts = []

    if is_windows(current):
        try:
            return _capture_windows(path, scale, runner, which, current)
        except CaptureError as error:
            attempts.append(str(error))
    else:
        for name, builder in candidate_tools(which=which, environ=env, platform=current):
            argv = builder(path, scale)
            try:
                completed = _run_tool(runner, argv, 25, current)
            except (OSError, subprocess.SubprocessError) as error:
                attempts.append(f"{name}: {error}")
                continue
            if (
                getattr(completed, "returncode", 1) == 0
                and Path(path).exists()
                and Path(path).stat().st_size > 512
            ):
                return path
            attempts.append(f"{name}: uscita {getattr(completed, 'returncode', '?')}")

    grab_path = _grab_with_pillow(path, grabber)
    if grab_path:
        return grab_path

    hint = (
        "Nessuno strumento di cattura disponibile. Su Windows serve PowerShell; "
        "su Linux installa grim (Wayland) o scrot/gnome-screenshot (X11). "
        "In alternativa: `pip install pillow`."
    )
    if attempts:
        hint += " Tentativi: " + "; ".join(attempts[:3]) + "."
    raise CaptureError(hint)


def _grab_with_pillow(path, grabber=None):
    try:
        from PIL import ImageGrab  # type: ignore[import-not-found]
    except Exception:
        return None
    try:
        image = (grabber or ImageGrab).grab()
        image.save(path, "PNG")
        return path if Path(path).exists() and Path(path).stat().st_size > 512 else None
    except Exception:
        return None


def _shrink(path, max_bytes, quality_steps=(82, 72, 62, 52)):
    """Riduce lo scatto sotto `max_bytes` conservando la risoluzione leggibile."""
    try:
        from PIL import Image  # type: ignore[import-not-found]
    except Exception:
        Image = None
    if Image is not None:
        try:
            with Image.open(path) as image:
                rgb = image.convert("RGB")
                for factor in (1.0, 0.85, 0.7, 0.55):
                    resized = rgb if factor == 1.0 else rgb.resize(
                        (max(1, int(rgb.width * factor)), max(1, int(rgb.height * factor)))
                    )
                    for quality in quality_steps:
                        buffer = Path(tempfile.gettempdir()) / f"nokk-dock-{uuid.uuid4().hex}.jpg"
                        resized.save(buffer, "JPEG", quality=quality, optimize=True)
                        if buffer.stat().st_size <= max_bytes:
                            return buffer, "image/jpeg"
                        buffer.unlink(missing_ok=True)
                resized = rgb.resize((max(1, int(rgb.width * 0.4)), max(1, int(rgb.height * 0.4))))
                buffer = Path(tempfile.gettempdir()) / f"nokk-dock-{uuid.uuid4().hex}.jpg"
                resized.save(buffer, "JPEG", quality=45, optimize=True)
                if buffer.stat().st_size <= max_bytes:
                    return buffer, "image/jpeg"
                buffer.unlink(missing_ok=True)
        except Exception:
            pass

    for name, argv in (
        ("magick", ["magick", path, "-resize", "60%", "-quality", "72", "-"]),
        ("convert", ["convert", path, "-resize", "60%", "-quality", "72", "-"]),
    ):
        if not shutil.which(name):
            continue
        try:
            completed = subprocess.run(argv, timeout=25, capture_output=True)
        except (OSError, subprocess.SubprocessError):
            continue
        if completed.returncode == 0 and completed.stdout and len(completed.stdout) <= max_bytes:
            return _memory_jpeg(completed.stdout), "image/jpeg"
    return None, None


def _memory_jpeg(data: bytes) -> Path:
    """Salva in un file temporaneo un JPEG già codificato in memoria."""
    path = Path(tempfile.gettempdir()) / f"nokk-dock-{uuid.uuid4().hex}.jpg"
    path.write_bytes(data)
    return path


def load_image(path, max_bytes=MAX_NOKK_IMAGE_BYTES):
    """Legge lo scatto e lo prepara per l'API di NOKK (base64 + mime)."""
    source = Path(path)
    try:
        data = source.read_bytes()
    except OSError as error:
        raise CaptureError(f"Lo screenshot non è leggibile ({error}).") from None
    if not data:
        raise CaptureError("Lo screenshot è vuoto.")
    mime_type, suffix = sniff_mime(data)
    if mime_type is None:
        raise CaptureError("Il formato dello screenshot non è supportato.")
    if len(data) > max_bytes:
        shrunk, shrunk_mime = _shrink(source, max_bytes)
        if shrunk is None:
            raise CaptureError(
                "Lo screenshot supera il limite di 4 MB di NOKK. "
                "Installa Pillow (`pip install pillow`) per ridurlo automaticamente."
            )
        data = shrunk.read_bytes()
        mime_type, suffix = shrunk_mime, shrunk.suffix
        shrunk.unlink(missing_ok=True)
    if len(data) > MAX_NOKK_IMAGE_BYTES:
        raise CaptureError("Lo screenshot supera il limite di 4 MB di NOKK.")
    return {
        "data": base64.b64encode(data).decode("ascii"),
        "mime_type": mime_type,
        "name": f"screenshot{suffix or '.png'}",
        "bytes": len(data),
    }


def cleanup(path):
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass
