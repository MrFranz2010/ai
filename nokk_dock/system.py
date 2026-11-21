"""Stato della macchina per il dock: batteria e appunti, senza dipendenze.

Windows espone la carica con `GetSystemPowerStatus`, Linux la legge dai file di
`/sys/class/power_supply`. Quando la batteria non c'è (un desktop) lo stato
resta valido e il dock scrive «Rete elettrica».
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

POWER_SUPPLY = "/sys/class/power_supply"
CLIPBOARD_HISTORY = 8


@dataclass(frozen=True)
class BatteryState:
    """Carica residua e alimentazione; `percent` è None senza batteria."""

    percent: float | None = None
    plugged: bool = True
    charging: bool = False

    @property
    def present(self) -> bool:
        return self.percent is not None

    @property
    def label(self) -> str:
        if self.percent is None:
            return "Rete elettrica"
        value = f"{int(round(self.percent))}%"
        if self.charging:
            return f"{value} · in carica"
        if not self.plugged:
            return f"{value} · batteria"
        return value


def _windows_battery() -> BatteryState:
    try:
        import ctypes

        class PowerStatus(ctypes.Structure):
            _fields_ = [
                ("ACLineStatus", ctypes.c_byte),
                ("BatteryFlag", ctypes.c_byte),
                ("BatteryLifePercent", ctypes.c_byte),
                ("Reserved", ctypes.c_byte),
                ("BatteryLifeTime", ctypes.c_uint32),
                ("BatteryFullLifeTime", ctypes.c_uint32),
            ]

        status = PowerStatus()
        if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
            return BatteryState()
        percent = None
        if status.BatteryLifePercent != 255:
            percent = float(status.BatteryLifePercent)
        return BatteryState(
            percent=percent,
            plugged=status.ACLineStatus == 1,
            charging=bool(status.BatteryFlag & 8),
        )
    except Exception:  # noqa: BLE001 - lo stato è solo informativo
        return BatteryState()


def _linux_battery(root) -> BatteryState:
    try:
        batteries = sorted(Path(root).glob("BAT*"))
    except OSError:
        return BatteryState()
    for battery in batteries:
        try:
            capacity = int((battery / "capacity").read_text().strip())
        except (OSError, ValueError):
            continue
        try:
            status = (battery / "status").read_text().strip().lower()
        except OSError:
            status = ""
        return BatteryState(
            percent=max(0.0, min(100.0, float(capacity))),
            plugged=status in ("charging", "full", "not charging"),
            charging=status == "charging",
        )
    return BatteryState()


def read_battery(platform=None, root=POWER_SUPPLY) -> BatteryState:
    """Legge la batteria: percentuale, alimentazione e ricarica."""
    current = sys.platform if platform is None else str(platform)
    if current.startswith("win"):
        return _windows_battery()
    return _linux_battery(root)


def clipboard_preview(text, limit: int = 180) -> str:
    """Anteprima su una riga sola del testo copiato."""
    if not text:
        return ""
    cleaned = " ".join(str(text).split())
    if limit > 1 and len(cleaned) > limit:
        return cleaned[: limit - 1].rstrip() + "…"
    return cleaned
