"""Curve di animazione del dock.

Nusa e le dock native si muovono con molle smorzate, non con interpolazioni
lineari: l'apertura parte decisa e si posa senza rimbalzare. Qui vivono le
funzioni pure (testabili senza Tk) usate dall'animazione.
"""

from __future__ import annotations

import math

# Parametri tarati su un passo di ~1/90 s e leggermente sotto-smorzati: il
# pannello scatta, supera di poco la misura e si posa, come le notch native.
STIFFNESS = 480.0
DAMPING = 31.0
FRAME_SECONDS = 1.0 / 90.0
SETTLE_EPSILON = 0.003


def spring_step(
    value: float,
    target: float,
    velocity: float,
    dt: float = FRAME_SECONDS,
    stiffness: float = STIFFNESS,
    damping: float = DAMPING,
) -> tuple[float, float]:
    """Un passo di molla smorzata: restituisce (valore, velocità)."""
    acceleration = -stiffness * (value - target) - damping * velocity
    velocity += acceleration * dt
    value += velocity * dt
    if abs(target - value) < SETTLE_EPSILON and abs(velocity) < 0.05:
        return target, 0.0
    return value, velocity


def settled(value: float, target: float, velocity: float) -> bool:
    return abs(target - value) < SETTLE_EPSILON and abs(velocity) < 0.02


def ease_out_cubic(progress: float) -> float:
    clamped = max(0.0, min(1.0, float(progress)))
    return 1.0 - (1.0 - clamped) ** 3


def magnification_factor(distance: float, reach: float, strength: float) -> float:
    """Fattore di ingrandimento con caduta cosinusoidale (stile dock macOS).

    A distanza 0 vale `strength`, a distanza `reach` vale 1.0.
    """
    if reach <= 0 or strength <= 1.0:
        return 1.0
    if distance >= reach:
        return 1.0
    weight = 0.5 * (1.0 + math.cos(math.pi * max(0.0, distance) / reach))
    return 1.0 + (strength - 1.0) * weight
