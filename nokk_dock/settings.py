"""Configurazione del dock.

Il file vive fuori dal repository (`$XDG_CONFIG_HOME/nokk/dock.json`) così le
preferenze personali e la chiave API non finiscono mai nel codice versionato.
La chiave non viene mai scritta nei log.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

from .theme import DEFAULT_PRESET, PRESETS

POSITIONS = ("bottom", "top", "left", "right")
POSITION_LABELS = {
    "bottom": "Basso",
    "top": "Alto",
    "left": "Sinistra",
    "right": "Destra",
}
WIDGETS = ("music", "weather", "clock", "nokk", "capture", "settings")
STYLES = ("notch", "dock")
STYLE_LABELS = {"notch": "Notch", "dock": "Dock"}


def _style(value):
    """Forma del dock: «notch» (pillola in alto) o «dock» (barra sul bordo)."""
    if value is None:
        return "notch"
    style = str(value).strip().lower()
    if style not in STYLES:
        raise ValueError(
            f"dock.style non valido: {value!r} (usa {', '.join(STYLES)})"
        )
    return style
WIDGET_LABELS = {
    "music": "Musica",
    "weather": "Meteo",
    "clock": "Ora",
    "nokk": "NOKK",
    "capture": "Schermo",
    "settings": "Impostazioni",
}
MODES = ("", "codice", "studio", "analista")
API_KEY_PATTERN = re.compile(r"^nokk_[A-Za-z0-9_-]{32}$")
URL_PATTERN = re.compile(r"^https?://[^\s/]+(?::\d+)?(?:/[^\s]*)?$")
MODIFIERS = {"ctrl", "alt", "shift", "super", "meta"}
KEY_PATTERN = re.compile(
    r"^(?:[a-z0-9]|f(?:[1-9]|1[0-9]|2[0-4])|space|enter|return|tab|esc|escape|"
    r"print|backspace|delete|home|end|pageup|pagedown|up|down|left|right)$"
)

DEFAULT_SHORTCUT = "ctrl+alt+n"
DEFAULT_PROMPT = (
    "Guarda lo screenshot del mio schermo e dimmi cosa vedi, "
    "segnalando eventuali errori o la prossima cosa da fare."
)


def config_path(
    override: str | os.PathLike | None = None,
    platform: str | None = None,
    environ=None,
) -> Path:
    """Percorso del file di configurazione: XDG su Linux, APPDATA su Windows."""
    if override:
        return Path(override).expanduser()
    env = os.environ if environ is None else environ
    explicit = env.get("NOKK_DOCK_CONFIG")
    if explicit:
        return Path(explicit).expanduser()
    current = platform or sys.platform
    if str(current).startswith("win"):
        base = env.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base).expanduser() / "nokk" / "dock.json"
    base = env.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
    return Path(base).expanduser() / "nokk" / "dock.json"


def default_config() -> dict:
    return {
        "version": 1,
        "nokk": {
            "base_url": "http://127.0.0.1:8000",
            "api_key": "",
            "mode": "",
            "timeout": 240,
        },
        "dock": {
            "position": "bottom",
            "offset": 0.5,
            "margin": 18,
            "thickness": 60,
            "length": 660,
            "auto_hide": False,
            "always_on_top": True,
            "opacity": 1.0,
            "hover_delay_ms": 30,
            "collapse_delay_ms": 160,
            "magnify": 1.25,
            "show_labels": True,
            "style": "notch",
        },
        "theme": {
            "preset": DEFAULT_PRESET,
            "accent": "",
            "background": "",
            "panel": "",
            "border": "",
            "text": "",
            "muted": "",
            "font": "",
            "radius": 20.0,
            "scale": 1.0,
        },
        "widgets": list(WIDGETS),
        "weather": {
            "city": "",
            "latitude": None,
            "longitude": None,
            "units": "metric",
            "refresh_minutes": 20,
        },
        "music": {"player": ""},
        "capture": {
            "shortcut": DEFAULT_SHORTCUT,
            "scale": 1.0,
            "max_bytes": 3_800_000,
        },
        "ask": {"prompt": DEFAULT_PROMPT},
    }


def _number(value, name, low, high, default, integer=False):
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Il valore «{name}» deve essere un numero.")
    number = int(value) if integer else float(value)
    return max(low, min(high, number))


def _boolean(value, name, default):
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ValueError(f"Il valore «{name}» deve essere vero o falso.")
    return value


def _text(value, name, max_length, default=""):
    if value is None:
        return default
    if not isinstance(value, str):
        raise ValueError(f"Il valore «{name}» deve essere testo.")
    clean = value.strip()
    if len(clean) > max_length:
        raise ValueError(f"Il valore «{name}» supera {max_length} caratteri.")
    return clean


def normalize_shortcut(value: str) -> str:
    """Normalizza una scorciatoia tipo `Ctrl+Alt+N` in `ctrl+alt+n`."""
    parts = [part.strip().lower() for part in (value or "").split("+") if part.strip()]
    if not parts:
        raise ValueError("La scorciatoia non può essere vuota.")
    key = parts[-1]
    modifiers = parts[:-1]
    if not KEY_PATTERN.fullmatch(key):
        raise ValueError(
            "Tasto non riconosciuto: usa una lettera, un numero, F1–F24 o un nome "
            "come space, tab, enter, esc."
        )
    if not modifiers:
        raise ValueError("La scorciatoia deve avere almeno un modificatore.")
    for modifier in modifiers:
        if modifier not in MODIFIERS:
            raise ValueError(
                "Modificatori ammessi: ctrl, alt, shift, super (separati da «+»)."
            )
    if len(set(modifiers)) != len(modifiers):
        raise ValueError("La scorciatoia ripete un modificatore.")
    return "+".join(modifiers + [key])


def validate_config(saved) -> dict:
    """Ripulisce e valida la configurazione, riempiendo i valori mancanti."""
    if saved is None:
        return default_config()
    if not isinstance(saved, dict):
        raise ValueError("La configurazione del dock deve essere un oggetto JSON.")
    defaults = default_config()

    nokk = saved.get("nokk") or {}
    if not isinstance(nokk, dict):
        raise ValueError("La sezione «nokk» non è valida.")
    base_url = _text(nokk.get("base_url"), "nokk.base_url", 300, defaults["nokk"]["base_url"])
    base_url = base_url.rstrip("/")
    if not URL_PATTERN.fullmatch(base_url):
        raise ValueError("L'indirizzo di NOKK deve iniziare con http:// o https://.")
    api_key = _text(nokk.get("api_key"), "nokk.api_key", 80, "")
    if api_key and not API_KEY_PATTERN.fullmatch(api_key):
        raise ValueError("La chiave API deve iniziare con «nokk_» e avere 32 caratteri.")
    mode = _text(nokk.get("mode"), "nokk.mode", 20, "")
    if mode not in MODES:
        raise ValueError("Modalità di risposta non supportata.")

    dock = saved.get("dock") or {}
    if not isinstance(dock, dict):
        raise ValueError("La sezione «dock» non è valida.")
    position = _text(dock.get("position"), "dock.position", 10, defaults["dock"]["position"])
    if position not in POSITIONS:
        raise ValueError(
            "La posizione deve essere una tra: " + ", ".join(POSITIONS) + "."
        )

    theme = saved.get("theme") or {}
    if not isinstance(theme, dict):
        raise ValueError("La sezione «theme» non è valida.")
    preset = _text(theme.get("preset"), "theme.preset", 20, DEFAULT_PRESET)
    if preset not in PRESETS:
        preset = DEFAULT_PRESET
    colors = {}
    for key in ("accent", "background", "panel", "border", "text", "muted"):
        raw = _text(theme.get(key), f"theme.{key}", 9, "")
        if raw and not re.fullmatch(r"#[0-9A-Fa-f]{6}", raw):
            raise ValueError(f"Il colore «{key}» deve essere nel formato #rrggbb.")
        colors[key] = raw.lower()

    widgets = saved.get("widgets", defaults["widgets"])
    if not isinstance(widgets, list) or not widgets:
        raise ValueError("Il dock deve mostrare almeno un widget.")
    clean_widgets = []
    for widget in widgets:
        if widget not in WIDGETS:
            raise ValueError(f"Widget sconosciuto: {widget!r}.")
        if widget in clean_widgets:
            continue
        clean_widgets.append(widget)

    weather = saved.get("weather") or {}
    if not isinstance(weather, dict):
        raise ValueError("La sezione «weather» non è valida.")
    latitude = weather.get("latitude")
    longitude = weather.get("longitude")
    for value, name in ((latitude, "weather.latitude"), (longitude, "weather.longitude")):
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, (int, float))
            or not -180 <= float(value) <= 180
        ):
            raise ValueError(f"Il valore «{name}» deve essere una coordinata valida.")
    units = _text(weather.get("units"), "weather.units", 12, "metric")
    if units not in ("metric", "imperial"):
        raise ValueError("L'unità del meteo deve essere «metric» o «imperial».")

    music = saved.get("music") or {}
    if not isinstance(music, dict):
        raise ValueError("La sezione «music» non è valida.")

    capture = saved.get("capture") or {}
    if not isinstance(capture, dict):
        raise ValueError("La sezione «capture» non è valida.")

    ask = saved.get("ask") or {}
    if not isinstance(ask, dict):
        raise ValueError("La sezione «ask» non è valida.")

    clean = {
        "version": 1,
        "nokk": {
            "base_url": base_url,
            "api_key": api_key,
            "mode": mode,
            "timeout": _number(nokk.get("timeout"), "nokk.timeout", 30, 900, 240, integer=True),
        },
        "dock": {
            "position": position,
            "offset": _number(dock.get("offset"), "dock.offset", 0.0, 1.0, 0.5),
            "margin": _number(dock.get("margin"), "dock.margin", 0, 400, 18, integer=True),
            "thickness": _number(dock.get("thickness"), "dock.thickness", 44, 110, 60, integer=True),
            "length": _number(dock.get("length"), "dock.length", 240, 4000, 660, integer=True),
            "auto_hide": _boolean(dock.get("auto_hide"), "dock.auto_hide", False),
            "always_on_top": _boolean(dock.get("always_on_top"), "dock.always_on_top", True),
            "opacity": _number(dock.get("opacity"), "dock.opacity", 0.4, 1.0, 1.0),
            "hover_delay_ms": _number(dock.get("hover_delay_ms"), "dock.hover_delay_ms", 0, 1000, 30, integer=True),
            "collapse_delay_ms": _number(
                dock.get("collapse_delay_ms"), "dock.collapse_delay_ms", 0, 2000, 160, integer=True
            ),
            "magnify": _number(dock.get("magnify"), "dock.magnify", 1.0, 1.6, 1.25),
            "show_labels": _boolean(dock.get("show_labels"), "dock.show_labels", True),
            "style": _style(dock.get("style")),
        },
        "theme": {
            "preset": preset,
            "accent": colors["accent"],
            "background": colors["background"],
            "panel": colors["panel"],
            "border": colors["border"],
            "text": colors["text"],
            "muted": colors["muted"],
            "font": _text(theme.get("font"), "theme.font", 60, ""),
            "radius": _number(theme.get("radius"), "theme.radius", 0, 40, 20.0),
            "scale": _number(theme.get("scale"), "theme.scale", 0.7, 1.6, 1.0),
        },
        "widgets": clean_widgets,
        "weather": {
            "city": _text(weather.get("city"), "weather.city", 80, ""),
            "latitude": None if latitude is None else float(latitude),
            "longitude": None if longitude is None else float(longitude),
            "units": units,
            "refresh_minutes": _number(
                weather.get("refresh_minutes"), "weather.refresh_minutes", 5, 180, 20, integer=True
            ),
        },
        "music": {
            "player": _text(music.get("player"), "music.player", 80, ""),
        },
        "capture": {
            "shortcut": normalize_shortcut(
                _text(capture.get("shortcut"), "capture.shortcut", 40, DEFAULT_SHORTCUT)
            ),
            "scale": _number(capture.get("scale"), "capture.scale", 0.25, 1.0, 1.0),
            "max_bytes": _number(
                capture.get("max_bytes"), "capture.max_bytes", 500_000, 3_900_000, 3_800_000, integer=True
            ),
        },
        "ask": {
            "prompt": _text(ask.get("prompt"), "ask.prompt", 600, DEFAULT_PROMPT),
        },
    }
    return clean


def load_config(path: str | os.PathLike | None = None) -> dict:
    """Legge la configurazione; se il file non esiste o è corrotto usa i default."""
    target = config_path(path)
    try:
        with target.open("r", encoding="utf-8") as handle:
            saved = json.load(handle)
    except FileNotFoundError:
        return default_config()
    except (OSError, json.JSONDecodeError) as error:
        print(f"Configurazione del dock non leggibile ({error}); uso i valori predefiniti.")
        return default_config()
    try:
        return validate_config(saved)
    except ValueError as error:
        print(f"Configurazione del dock non valida ({error}); uso i valori predefiniti.")
        return default_config()


def save_config(config: dict, path: str | os.PathLike | None = None) -> Path:
    """Valida e salva la configurazione con scrittura atomica e permessi ristretti."""
    clean = validate_config(config)
    target = config_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=str(target.parent),
        prefix=".dock-",
        suffix=".json",
        delete=False,
    )
    temporary = Path(handle.name)
    try:
        with handle:
            json.dump(clean, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        os.replace(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return target
