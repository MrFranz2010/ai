"""Geometria del dock.

Tutta la matematica di posizionamento vive qui, lontano da Tk, così può essere
verificata senza un display: data la posizione scelta e il progresso
dell'espansione, il layout restituisce la finestra e i rettangoli dei widget.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .motion import magnification_factor

# Dimensioni lungo il bordo: (compatta, espansa). Il dock espandendosi allarga i
# widget informativi e lascia le icone quasi ferme.
TILE_SPANS = {
    "music": (168, 300),
    "weather": (118, 214),
    "clock": (112, 172),
    "nokk": (100, 168),
    "capture": (62, 152),
    "settings": (62, 62),
}

GAP = 8.0
PADDING = 10.0
MIN_TILE = 44.0
TIGHT_TILE = 24.0
EXPANSION_HEADROOM = 0.75

# Stile «notch»: pillola compatta in alto al centro che si srotola nel pannello.
NOTCH_WIDTH = 208.0
NOTCH_HEIGHT_RATIO = 0.55
NOTCH_REVEAL = 0.85


@dataclass(frozen=True)
class Tile:
    """Rettangolo di un widget, in coordinate finestra."""

    key: str
    x: int
    y: int
    width: int
    height: int
    magnify: float = 1.0

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    def contains(self, point_x: float, point_y: float) -> bool:
        return self.x <= point_x < self.right and self.y <= point_y < self.bottom

    def as_tuple(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.width, self.height)


@dataclass(frozen=True)
class DockLayout:
    """Geometria completa della finestra del dock."""

    x: int
    y: int
    width: int
    height: int
    tiles: tuple[Tile, ...]
    horizontal: bool
    expanded: float
    scale: float
    style: str = "dock"

    @property
    def geometry(self) -> str:
        return f"{self.width}x{self.height}+{self.x}+{self.y}"

    def tile_at(self, point_x: float, point_y: float) -> Tile | None:
        for tile in self.tiles:
            if tile.contains(point_x, point_y):
                return tile
        return None


def tile_span(key: str, expand: float, scale: float) -> float:
    """Lunghezza di un widget al progresso di espansione indicato."""
    collapsed, opened = TILE_SPANS.get(key, (80, 120))
    progress = max(0.0, min(1.0, expand))
    return max(MIN_TILE, (collapsed + (opened - collapsed) * progress) * scale)


def dock_thickness(thickness: float, expand: float, scale: float) -> float:
    """Spessore del dock: cresce del 62% quando è completamente aperto."""
    progress = max(0.0, min(1.0, expand))
    return (thickness + thickness * 0.62 * progress) * scale


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _fit(spans, gap, padding, limit):
    """Riduce spazi e widget finché il dock entra nel limite disponibile."""
    spans = list(spans)
    for _ in range(6):
        fixed = gap * (len(spans) - 1) + padding * 2
        total = sum(spans) + fixed
        if total <= limit:
            break
        if fixed > limit * 0.3:
            gap = max(2.0, gap * 0.75)
            padding = max(3.0, padding * 0.75)
            continue
        available = max(TIGHT_TILE * len(spans), limit - fixed)
        factor = available / sum(spans) if sum(spans) else 1.0
        spans = [max(TIGHT_TILE, span * factor) for span in spans]
    return spans, gap, padding


def _build_tiles(keys, spans, gap, padding, cross, horizontal, factors=None):
    """Posiziona i widget in sequenza e restituisce (tiles, lunghezza totale)."""
    tiles = []
    factors = factors if factors is not None else [1.0] * len(keys)
    cursor = padding
    for key, span, factor in zip(keys, spans, factors):
        start = int(round(cursor))
        end = int(round(cursor + span))
        span_px = max(1, end - start)
        if horizontal:
            tiles.append(Tile(key, start, 0, span_px, cross, factor))
        else:
            tiles.append(Tile(key, 0, start, cross, span_px, factor))
        cursor += span + gap
    last = tiles[-1]
    total = (last.right if horizontal else last.bottom) + int(round(padding))
    return tiles, total


def compute_layout(
    position: str,
    screen_width: int,
    screen_height: int,
    widgets,
    thickness: float = 60,
    length: float = 660,
    margin: float = 18,
    offset: float = 0.5,
    expand: float = 0.0,
    scale: float = 1.0,
    pointer: float | None = None,
    magnify: float = 1.0,
    influence: float = 120.0,
    style: str = "dock",
):
    """Calcola finestra e widget per il bordo richiesto.

    `expand` è continuo (0 = compatto, 1 = aperto) così l'animazione può
    ridisegnare la geometria a ogni fotogramma senza scatti. La lunghezza
    scelta è quella a riposo: aprendosi il dock può crescere fino al 75% in
    più, senza mai uscire dallo schermo.

    `pointer` è la coordinata dello schermo (x per le dock orizzontali, y per
    le verticali) usata per l'ingrandimento magnetico: i widget vicini al
    cursore si allargano, quelli lontani restano fermi. I centri di riferimento
    vengono calcolati sul layout a riposo, così la geometria non oscilla mentre
    il dock cresce sotto il puntatore.
    """
    keys = [key for key in widgets if key in TILE_SPANS] or list(TILE_SPANS)
    notch = str(style) == "notch"
    horizontal = True if notch else position in ("bottom", "top")
    progress = _clamp(expand, 0.0, 1.0)
    screen_length = float(screen_width if horizontal else screen_height)
    # Nel notch il contenuto è già disposto per il pannello aperto: la finestra
    # si allarga e lo rivela, invece di comprimere i widget in pochi pixel.
    span_progress = 1.0 if notch else progress
    cross = int(round(dock_thickness(thickness, span_progress, scale)))

    gap = GAP * scale
    padding = PADDING * scale
    spans = [tile_span(key, span_progress, scale) for key in keys]
    factors = [1.0] * len(keys)
    if pointer is not None and magnify > 1.0 and len(keys) > 1:
        base = compute_layout(
            position, screen_width, screen_height, widgets,
            thickness=thickness, length=length, margin=margin, offset=offset,
            expand=progress, scale=scale, style=style,
        )
        reach = max(1.0, float(influence) * scale)
        centers = [
            (base.x + tile.x + tile.width / 2) if horizontal
            else (base.y + tile.y + tile.height / 2)
            for tile in base.tiles
        ]
        for index, center in enumerate(centers):
            factors[index] = magnification_factor(
                abs(float(pointer) - center), reach, float(magnify)
            )
        spans = [span * factor for span, factor in zip(spans, factors)]

    fixed = gap * (len(spans) - 1) + padding * 2
    # L'ingrandimento può superare la lunghezza scelta: il limite reale resta
    # lo schermo, così la reazione al puntatore non viene annullata. Il notch
    # invece resta della larghezza scelta: è una pillola, non una barra.
    if notch:
        limit = min(screen_length, max(float(length), MIN_TILE * len(spans)))
    else:
        limit = min(
            screen_length,
            max(
                float(length) * (1.0 + EXPANSION_HEADROOM * progress),
                MIN_TILE * len(spans),
                sum(spans) + fixed,
            ),
        )
    spans, gap, padding = _fit(spans, gap, padding, limit)
    tiles, total_length = _build_tiles(keys, spans, gap, padding, cross, horizontal, factors)

    if total_length > screen_length:
        # Schermo molto stretto: riduce ancora una volta e ricostruisce.
        factor = max(0.3, (screen_length - 1) / max(1, total_length))
        spans = [max(TIGHT_TILE, span * factor) for span in spans]
        gap = max(2.0, gap * factor)
        padding = max(3.0, padding * factor)
        tiles, total_length = _build_tiles(keys, spans, gap, padding, cross, horizontal, factors)

    window_length = int(min(total_length, max(1, int(screen_length))))
    if horizontal:
        width, height = window_length, cross
    else:
        width, height = cross, window_length
    final_tiles = tuple(
        Tile(tile.key, tile.x, tile.y,
             min(tile.width, width) if horizontal else width,
             height if horizontal else min(tile.height, height),
             tile.magnify)
        for tile in tiles
    )

    if notch:
        reveal = 1.0 if progress >= NOTCH_REVEAL else progress / NOTCH_REVEAL
        compact_width = min(float(width), NOTCH_WIDTH * scale)
        compact_height = thickness * NOTCH_HEIGHT_RATIO * scale
        wide = int(round(compact_width + (width - compact_width) * reveal))
        tall = int(round(compact_height + (height - compact_height) * reveal))
        wide = max(1, min(wide, int(screen_width)))
        tall = max(1, min(tall, int(screen_height)))
        # agganciata al bordo alto: nessuno spazio, come il notch del portatile
        return DockLayout(
            x=int(round((screen_width - wide) / 2)),
            y=0,
            width=wide,
            height=tall,
            tiles=final_tiles,
            horizontal=True,
            expanded=progress,
            scale=scale,
            style="notch",
        )

    if position == "bottom":
        x = _clamp(screen_width - width, 0, screen_width) * offset
        y = screen_height - height - margin
    elif position == "top":
        x = _clamp(screen_width - width, 0, screen_width) * offset
        y = margin
    elif position == "left":
        x = margin
        y = _clamp(screen_height - height, 0, screen_height) * offset
    else:  # right
        x = screen_width - width - margin
        y = _clamp(screen_height - height, 0, screen_height) * offset

    x = int(round(_clamp(x, 0, max(0, screen_width - width))))
    y = int(round(_clamp(y, 0, max(0, screen_height - height))))

    return DockLayout(
        x=x,
        y=y,
        width=width,
        height=height,
        tiles=final_tiles,
        horizontal=horizontal,
        expanded=progress,
        scale=scale,
        style=str(style),
    )


def tile_content(tile: Tile, layout: DockLayout, inset: float = 14.0) -> tuple[float, float, float, float]:
    """Area interna di un widget, con padding ai lati corti."""
    pad = inset * layout.scale
    if layout.horizontal:
        return (
            tile.x + pad,
            tile.y + pad * 0.6,
            max(1.0, tile.width - pad * 2),
            max(1.0, tile.height - pad * 1.2),
        )
    return (
        tile.x + pad * 0.6,
        tile.y + pad,
        max(1.0, tile.width - pad * 1.2),
        max(1.0, tile.height - pad * 2),
    )
