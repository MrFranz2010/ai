"""Copertine dei brani per il widget musicale.

La copertina arriva dal player tramite MPRIS (`mpris:artUrl`): può essere un
file locale oppure un URL remoto (Spotify usa `https://i.scdn.co/...`). Qui
l'immagine viene validata, scaricata con limiti di dimensione e tempo, salvata
in cache e ridotta in una miniatura PNG pronta per Tk. Pillow è opzionale:
senza, si usano solo PNG/GIF già adatti alla dimensione richiesta.
"""

from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

MAX_BYTES = 2 * 1024 * 1024
TIMEOUT = 8
ALLOWED_SCHEMES = ("http", "https", "file")
THUMBNAIL_SIZES = (32, 40, 48, 56, 64, 72, 88, 96, 112, 128)


def is_windows(platform=None) -> bool:
    return str(platform or sys.platform).startswith("win")


def cache_dir(platform=None) -> Path:
    if is_windows(platform):
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if not base:
            base = str(Path.home() / "AppData" / "Local")
        return Path(base) / "nokk" / "cache" / "covers"
    base = os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache")
    return Path(base).expanduser() / "nokk" / "covers"


def url_supported(url) -> bool:
    if not isinstance(url, str) or not url.strip():
        return False
    try:
        parsed = urllib.parse.urlparse(url.strip())
    except ValueError:
        return False
    return parsed.scheme.lower() in ALLOWED_SCHEMES and bool(parsed.scheme)


def cache_key(url: str) -> str:
    return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()[:24]


def _suffix_for(url: str, data: bytes = b"") -> str:
    path = urllib.parse.urlparse(url).path if url.startswith("file:") else url
    suffix = Path(path).suffix.lower()
    if suffix in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
        return suffix
    if data.startswith(b"\x89PNG"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith(b"GIF8"):
        return ".gif"
    return ".img"


def local_path(url, directory=None, downloader=None):
    """Restituisce il file locale della copertina, scaricandola se serve."""
    if not url_supported(url):
        return None
    target_dir = Path(directory) if directory else cache_dir()
    clean = url.strip()
    parsed = urllib.parse.urlparse(clean)
    if parsed.scheme.lower() == "file":
        raw = urllib.request.url2pathname(parsed.path)
        local = Path(raw)
        try:
            size = local.stat().st_size
        except OSError:
            return None
        # Un file vuoto (scrittura interrotta) non è una copertina.
        if local.is_file() and 0 < size <= MAX_BYTES:
            return local
        return None
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    key = cache_key(clean)
    for candidate in target_dir.glob(f"{key}.*"):
        if candidate.is_file() and candidate.stat().st_size > 0:
            return candidate
    fetch = downloader or _download
    try:
        data = fetch(clean)
    except Exception:  # noqa: BLE001 - rete non disponibile: nessuna copertina
        return None
    if not data or len(data) > MAX_BYTES:
        return None
    path = target_dir / f"{key}{_suffix_for(clean, data)}"
    try:
        path.write_bytes(data)
    except OSError:
        return None
    return path


def _download(url: str) -> bytes:
    request = urllib.request.Request(
        url, headers={"User-Agent": "nokk-dock/1.0", "Accept": "image/*"}
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        chunks = []
        total = 0
        while True:
            chunk = response.read(65536)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_BYTES:
                return b""
            chunks.append(chunk)
    return b"".join(chunks)


def thumbnail_size(value, sizes=THUMBNAIL_SIZES) -> int:
    """Arrotonda la dimensione richiesta a un bucket, per riusare le miniature."""
    if not sizes:
        return max(8, int(value))
    return min(sizes, key=lambda size: abs(size - value))


def thumbnail_bytes(path, size):
    """Miniatura PNG con angoli già arrotondati; `None` se Pillow non c'è."""
    if path is None:
        return None
    bucket = thumbnail_size(size)
    try:
        from PIL import Image, ImageDraw  # type: ignore[import-not-found]
    except Exception:
        return _plain_png_bytes(path)
    try:
        with Image.open(path) as image:
            rgb = image.convert("RGB").resize((bucket, bucket), Image.LANCZOS)
            mask = Image.new("L", (bucket * 4, bucket * 4), 0)
            ImageDraw.Draw(mask).rounded_rectangle(
                (0, 0, bucket * 4 - 1, bucket * 4 - 1), radius=bucket, fill=255
            )
            mask = mask.resize((bucket, bucket), Image.LANCZOS)
            rgb.putalpha(mask)
            output = Path(tempfile.gettempdir()) / f"nokk-cover-{bucket}-{os.getpid()}.png"
            rgb.save(output, "PNG")
            return output.read_bytes()
    except Exception:
        return None


def _plain_png_bytes(path):
    """PNG/GIF già pronti: Tk li carica da solo se non serve ridimensionarli."""
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    if data.startswith(b"\x89PNG") or data.startswith(b"GIF8"):
        return data
    return None


