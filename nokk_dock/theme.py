"""Palette e tipografia del dock.

I preset riprendono i colori dell'interfaccia web di NOKK (`web/style.css`) così
il dock sembra parte della stessa applicazione. Ogni valore può essere
sovrascritto dalla configurazione, quindi il tema resta personalizzabile.
"""

from __future__ import annotations

from dataclasses import dataclass

FONT_STACK = (
    "Inter",
    "SF Pro Display",
    "Segoe UI Variable Display",
    "Segoe UI",
    "Cantarell",
    "Ubuntu",
    "Noto Sans",
    "DejaVu Sans",
)

DEFAULT_PRESET = "nokk"

PRESETS = {
    "nokk": {
        "background": "#10131b",
        "panel": "#181c27",
        "border": "#282d3b",
        "text": "#e9ebf2",
        "muted": "#8c93a4",
        "accent": "#9b8cff",
        "light": False,
    },
    "midnight": {
        "background": "#070a10",
        "panel": "#0f141d",
        "border": "#1d2532",
        "text": "#eef2f8",
        "muted": "#7d8798",
        "accent": "#4f9dff",
        "light": False,
    },
    "graphite": {
        "background": "#15161a",
        "panel": "#1e2026",
        "border": "#2b2e36",
        "text": "#eceef2",
        "muted": "#8b8f9a",
        "accent": "#f0b429",
        "light": False,
    },
    "mint": {
        "background": "#0b1512",
        "panel": "#14211c",
        "border": "#21342c",
        "text": "#e6f2ec",
        "muted": "#87a294",
        "accent": "#4fd1a5",
        "light": False,
    },
    "sand": {
        "background": "#efe9dd",
        "panel": "#fbf8f2",
        "border": "#ddd5c6",
        "text": "#221f1a",
        "muted": "#6d675c",
        "accent": "#b4643a",
        "light": True,
    },
}

PRESET_LABELS = {
    "nokk": "NOKK",
    "midnight": "Midnight",
    "graphite": "Graphite",
    "mint": "Mint",
    "sand": "Sand",
}

HEX_PATTERN_HINT = "#rrggbb"


def _clamp_channel(value: float) -> int:
    return max(0, min(255, int(round(value))))


def parse_hex(value: str, fallback: str = "#000000") -> tuple[int, int, int]:
    """Converte `#rrggbb` in una tupla RGB, tornando al fallback se non valida."""
    text = (value or "").strip()
    if len(text) == 4 and text.startswith("#"):
        text = "#" + "".join(char * 2 for char in text[1:])
    if len(text) != 7 or not text.startswith("#"):
        return parse_hex(fallback, "#000000")
    try:
        return (
            int(text[1:3], 16),
            int(text[3:5], 16),
            int(text[5:7], 16),
        )
    except ValueError:
        return parse_hex(fallback, "#000000")


def to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*(_clamp_channel(part) for part in rgb))


def mix(color_a: str, color_b: str, amount: float) -> str:
    """Mescola due colori; `amount` 0 restituisce `color_a`, 1 restituisce `color_b`."""
    ratio = max(0.0, min(1.0, float(amount)))
    first = parse_hex(color_a)
    second = parse_hex(color_b)
    return to_hex(tuple(
        first[index] + (second[index] - first[index]) * ratio for index in range(3)
    ))


def luminance(color: str) -> float:
    red, green, blue = parse_hex(color)
    return (0.2126 * red + 0.7152 * green + 0.0722 * blue) / 255


def readable_text(color: str) -> str:
    """Testo leggibile sopra un colore pieno (usato per i bottoni accentati)."""
    return "#0b0e14" if luminance(color) > 0.62 else "#ffffff"


@dataclass(frozen=True)
class Theme:
    preset: str
    background: str
    panel: str
    border: str
    text: str
    muted: str
    accent: str
    radius: float
    scale: float
    font_family: str
    light: bool

    @property
    def panel_hover(self) -> str:
        return mix(self.panel, self.accent, 0.14 if not self.light else 0.10)

    @property
    def panel_soft(self) -> str:
        return mix(self.panel, self.text, 0.045 if not self.light else 0.03)

    @property
    def on_accent(self) -> str:
        return readable_text(self.accent)

    @property
    def shadow(self) -> str:
        return mix(self.background, "#000000", 0.28 if not self.light else 0.08)

    @property
    def divider(self) -> str:
        return mix(self.panel, self.text, 0.10 if not self.light else 0.08)

    def font(self, size: float, weight: str = "normal") -> tuple:
        return (self.font_family, max(7, int(round(size * self.scale))), weight)


def build_theme(saved: dict, font_family: str | None = None) -> Theme:
    """Costruisce il tema effettivo unendo preset e sovrascritture dell'utente."""
    preset_name = saved.get("preset") or DEFAULT_PRESET
    base = PRESETS.get(preset_name, PRESETS[DEFAULT_PRESET])
    colors = {}
    for key in ("background", "panel", "border", "text", "muted", "accent"):
        override = saved.get(key)
        colors[key] = override if isinstance(override, str) and override.strip() else base[key]
    family = (saved.get("font") or "").strip() or (font_family or FONT_STACK[-1])
    radius = float(saved.get("radius") or 20)
    scale = float(saved.get("scale") or 1.0)
    return Theme(
        preset=preset_name,
        background=colors["background"],
        panel=colors["panel"],
        border=colors["border"],
        text=colors["text"],
        muted=colors["muted"],
        accent=colors["accent"],
        radius=max(0.0, min(40.0, radius)),
        scale=max(0.7, min(1.6, scale)),
        font_family=family,
        light=bool(base.get("light")),
    )


def pick_font(available) -> str:
    """Sceglie il primo font della pila presente nel sistema."""
    names = {str(name).strip().lower() for name in available}
    for candidate in FONT_STACK:
        if candidate.lower() in names:
            return candidate
    return FONT_STACK[-1]
