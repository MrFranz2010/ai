"""Icone vettoriali disegnate sul canvas.

Nessuna dipendenza esterna: le icone sono primitive Tk (linee, poligoni, ovali)
disegnate a coordinate relative, così restano nitide a ogni scala e cambiano
colore con il tema.
"""

from __future__ import annotations

import math


def _stroke(size: float) -> int:
    return max(1, int(round(size * 0.085)))


def _line(canvas, points, color, width, tag):
    canvas.create_line(
        *points,
        fill=color,
        width=width,
        capstyle="round",
        joinstyle="round",
        tags=tag,
    )


def _poly(canvas, points, color, tag):
    canvas.create_polygon(*points, fill=color, outline="", tags=tag)


def _oval(canvas, cx, cy, rx, ry, color, tag, outline=""):
    canvas.create_oval(
        cx - rx, cy - ry, cx + rx, cy + ry,
        fill=color, outline=outline, width=0, tags=tag,
    )


def play(canvas, cx, cy, size, color, tag, bg=None):
    _poly(canvas, [
        cx - size * 0.22, cy - size * 0.32,
        cx + size * 0.32, cy,
        cx - size * 0.22, cy + size * 0.32,
    ], color, tag)


def pause(canvas, cx, cy, size, color, tag, bg=None):
    width = size * 0.13
    height = size * 0.62
    for offset in (-size * 0.16, size * 0.16):
        canvas.create_rectangle(
            cx + offset - width / 2, cy - height / 2,
            cx + offset + width / 2, cy + height / 2,
            fill=color, outline="", tags=tag,
        )


def previous(canvas, cx, cy, size, color, tag, bg=None):
    _poly(canvas, [
        cx + size * 0.28, cy - size * 0.28,
        cx - size * 0.08, cy,
        cx + size * 0.28, cy + size * 0.28,
    ], color, tag)
    _line(canvas, [cx - size * 0.26, cy - size * 0.28, cx - size * 0.26, cy + size * 0.28],
          color, _stroke(size), tag)


def next_(canvas, cx, cy, size, color, tag, bg=None):
    _poly(canvas, [
        cx - size * 0.28, cy - size * 0.28,
        cx + size * 0.08, cy,
        cx - size * 0.28, cy + size * 0.28,
    ], color, tag)
    _line(canvas, [cx + size * 0.26, cy - size * 0.28, cx + size * 0.26, cy + size * 0.28],
          color, _stroke(size), tag)


def music(canvas, cx, cy, size, color, tag, bg=None):
    _oval(canvas, cx - size * 0.16, cy + size * 0.2, size * 0.15, size * 0.12, color, tag)
    _line(canvas, [
        cx + size * 0.0, cy + size * 0.2,
        cx + size * 0.0, cy - size * 0.3,
    ], color, _stroke(size), tag)
    _line(canvas, [
        cx + size * 0.0, cy - size * 0.3,
        cx + size * 0.26, cy - size * 0.16,
    ], color, _stroke(size), tag)


def clock(canvas, cx, cy, size, color, tag, bg=None):
    width = _stroke(size)
    canvas.create_oval(
        cx - size * 0.36, cy - size * 0.36, cx + size * 0.36, cy + size * 0.36,
        outline=color, width=width, tags=tag,
    )
    _line(canvas, [cx, cy, cx, cy - size * 0.2], color, width, tag)
    _line(canvas, [cx, cy, cx + size * 0.17, cy + size * 0.06], color, width, tag)


def sun(canvas, cx, cy, size, color, tag, bg=None):
    _oval(canvas, cx, cy, size * 0.19, size * 0.19, color, tag)
    width = _stroke(size)
    for index in range(8):
        angle = math.pi * index / 4
        _line(canvas, [
            cx + math.cos(angle) * size * 0.3, cy + math.sin(angle) * size * 0.3,
            cx + math.cos(angle) * size * 0.44, cy + math.sin(angle) * size * 0.44,
        ], color, width, tag)


def moon(canvas, cx, cy, size, color, tag, bg=None):
    _oval(canvas, cx, cy, size * 0.36, size * 0.36, color, tag)
    _oval(canvas, cx + size * 0.17, cy - size * 0.11, size * 0.32, size * 0.32, bg or color, tag)


def _cloud(canvas, cx, cy, size, color, tag):
    _oval(canvas, cx - size * 0.1, cy + size * 0.02, size * 0.2, size * 0.16, color, tag)
    _oval(canvas, cx + size * 0.1, cy + size * 0.05, size * 0.16, size * 0.13, color, tag)
    _oval(canvas, cx + size * 0.0, cy - size * 0.1, size * 0.23, size * 0.19, color, tag)
    canvas.create_rectangle(
        cx - size * 0.28, cy + size * 0.03, cx + size * 0.26, cy + size * 0.17,
        fill=color, outline="", tags=tag,
    )


def cloud(canvas, cx, cy, size, color, tag, bg=None):
    _cloud(canvas, cx, cy - size * 0.04, size, color, tag)


def rain(canvas, cx, cy, size, color, tag, bg=None):
    _cloud(canvas, cx, cy - size * 0.1, size, color, tag)
    width = _stroke(size)
    for offset in (-0.16, 0.0, 0.16):
        _line(canvas, [
            cx + size * offset, cy + size * 0.24,
            cx + size * (offset - 0.05), cy + size * 0.38,
        ], color, width, tag)


def snow(canvas, cx, cy, size, color, tag, bg=None):
    _cloud(canvas, cx, cy - size * 0.1, size, color, tag)
    for offset in (-0.16, 0.0, 0.16):
        _oval(canvas, cx + size * offset, cy + size * 0.3, size * 0.04, size * 0.04, color, tag)


def storm(canvas, cx, cy, size, color, tag, bg=None):
    _cloud(canvas, cx, cy - size * 0.12, size, color, tag)
    _poly(canvas, [
        cx + size * 0.02, cy + size * 0.14,
        cx - size * 0.1, cy + size * 0.14,
        cx, cy + size * 0.36,
        cx - size * 0.05, cy + size * 0.36,
        cx + size * 0.12, cy + size * 0.1,
        cx + size * 0.01, cy + size * 0.1,
    ], color, tag)


def fog(canvas, cx, cy, size, color, tag, bg=None):
    width = _stroke(size)
    for index, offset in enumerate((-0.16, 0.0, 0.16)):
        shrink = size * (0.32 if index == 1 else 0.24)
        _line(canvas, [cx - shrink, cy + size * offset, cx + shrink, cy + size * offset],
              color, width, tag)


def spark(canvas, cx, cy, size, color, tag, bg=None):
    _poly(canvas, [
        cx, cy - size * 0.42,
        cx + size * 0.11, cy - size * 0.11,
        cx + size * 0.42, cy,
        cx + size * 0.11, cy + size * 0.11,
        cx, cy + size * 0.42,
        cx - size * 0.11, cy + size * 0.11,
        cx - size * 0.42, cy,
        cx - size * 0.11, cy - size * 0.11,
    ], color, tag)


def camera(canvas, cx, cy, size, color, tag, bg=None):
    width = _stroke(size)
    canvas.create_rectangle(
        cx - size * 0.38, cy - size * 0.24, cx + size * 0.38, cy + size * 0.3,
        outline=color, width=width, tags=tag,
    )
    canvas.create_rectangle(
        cx - size * 0.14, cy - size * 0.34, cx + size * 0.14, cy - size * 0.2,
        outline=color, width=width, tags=tag,
    )
    canvas.create_oval(
        cx - size * 0.15, cy - size * 0.05, cx + size * 0.15, cy + size * 0.25,
        outline=color, width=width, tags=tag,
    )


def search(canvas, cx, cy, size, color, tag, bg=None):
    width = _stroke(size)
    canvas.create_oval(
        cx - size * 0.36, cy - size * 0.36, cx + size * 0.12, cy + size * 0.12,
        outline=color, width=width, tags=tag,
    )
    _line(canvas, [
        cx + size * 0.1, cy + size * 0.1,
        cx + size * 0.4, cy + size * 0.4,
    ], color, width, tag)


def clipboard(canvas, cx, cy, size, color, tag, bg=None):
    width = _stroke(size)
    canvas.create_rectangle(
        cx - size * 0.3, cy - size * 0.32, cx + size * 0.3, cy + size * 0.38,
        outline=color, width=width, tags=tag,
    )
    canvas.create_rectangle(
        cx - size * 0.13, cy - size * 0.42, cx + size * 0.13, cy - size * 0.26,
        outline=color, width=width, tags=tag,
    )
    for offset in (-0.02, 0.16):
        _line(canvas, [
            cx - size * 0.16, cy + size * offset,
            cx + size * 0.16, cy + size * offset,
        ], color, width, tag)


def gear(canvas, cx, cy, size, color, tag, bg=None):
    width = _stroke(size)
    canvas.create_oval(
        cx - size * 0.22, cy - size * 0.22, cx + size * 0.22, cy + size * 0.22,
        outline=color, width=width, tags=tag,
    )
    for index in range(8):
        angle = math.pi * index / 4
        _line(canvas, [
            cx + math.cos(angle) * size * 0.26, cy + math.sin(angle) * size * 0.26,
            cx + math.cos(angle) * size * 0.4, cy + math.sin(angle) * size * 0.4,
        ], color, width, tag)


def chevron_left(canvas, cx, cy, size, color, tag, bg=None):
    _line(canvas, [
        cx + size * 0.12, cy - size * 0.22,
        cx - size * 0.1, cy,
        cx + size * 0.12, cy + size * 0.22,
    ], color, _stroke(size) + 1, tag)


def chevron_right(canvas, cx, cy, size, color, tag, bg=None):
    _line(canvas, [
        cx - size * 0.12, cy - size * 0.22,
        cx + size * 0.1, cy,
        cx - size * 0.12, cy + size * 0.22,
    ], color, _stroke(size) + 1, tag)


def chevron_down(canvas, cx, cy, size, color, tag, bg=None):
    _line(canvas, [
        cx - size * 0.22, cy - size * 0.1,
        cx, cy + size * 0.12,
        cx + size * 0.22, cy - size * 0.1,
    ], color, _stroke(size) + 1, tag)


def close(canvas, cx, cy, size, color, tag, bg=None):
    width = _stroke(size) + 1
    _line(canvas, [cx - size * 0.2, cy - size * 0.2, cx + size * 0.2, cy + size * 0.2], color, width, tag)
    _line(canvas, [cx + size * 0.2, cy - size * 0.2, cx - size * 0.2, cy + size * 0.2], color, width, tag)


def check(canvas, cx, cy, size, color, tag, bg=None):
    _line(canvas, [
        cx - size * 0.24, cy,
        cx - size * 0.06, cy + size * 0.18,
        cx + size * 0.26, cy - size * 0.18,
    ], color, _stroke(size) + 1, tag)


def dot(canvas, cx, cy, size, color, tag, bg=None):
    _oval(canvas, cx, cy, size * 0.16, size * 0.16, color, tag)


def external(canvas, cx, cy, size, color, tag, bg=None):
    width = _stroke(size)
    _line(canvas, [
        cx - size * 0.24, cy + size * 0.24,
        cx + size * 0.2, cy - size * 0.2,
    ], color, width, tag)
    _line(canvas, [
        cx + size * 0.02, cy - size * 0.24,
        cx + size * 0.26, cy - size * 0.24,
        cx + size * 0.26, cy + size * 0.0,
    ], color, width, tag)


ICONS = {
    "play": play,
    "pause": pause,
    "previous": previous,
    "next": next_,
    "music": music,
    "clock": clock,
    "sun": sun,
    "moon": moon,
    "cloud": cloud,
    "rain": rain,
    "snow": snow,
    "storm": storm,
    "fog": fog,
    "spark": spark,
    "camera": camera,
    "clipboard": clipboard,
    "search": search,
    "gear": gear,
    "chevron_left": chevron_left,
    "chevron_right": chevron_right,
    "chevron_down": chevron_down,
    "close": close,
    "check": check,
    "dot": dot,
    "external": external,
}


def draw(canvas, name, cx, cy, size, color, tag, bg=None):
    """Disegna l'icona `name` centrata in (cx, cy)."""
    painter = ICONS.get(name)
    if painter is None:
        painter = ICONS["dot"]
    painter(canvas, cx, cy, size, color, tag, bg)
