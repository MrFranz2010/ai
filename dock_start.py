#!/usr/bin/env python3
"""Avvia il dock da scrivania di NOKK.

Esempi:

    python dock_start.py                 # avvia il dock
    python dock_start.py --check         # diagnostica senza aprire finestre
    python dock_start.py --capture       # cattura schermo dal dock già avviato
    python dock_start.py --position top  # cambia bordo e salva
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nokk_dock.settings import (  # noqa: E402
    POSITIONS,
    config_path,
    default_config,
    load_config,
    save_config,
    validate_config,
)

CHECK = "ok  "
MISSING = "--  "


def build_parser():
    parser = argparse.ArgumentParser(
        prog="dock_start.py",
        description="Dock da scrivania per NOKK: musica, meteo, ora e domande sullo schermo.",
    )
    parser.add_argument("--config", metavar="FILE", help="file di configurazione alternativo")
    parser.add_argument("--capture", action="store_true", help="chiede al dock di catturare lo schermo")
    parser.add_argument("--ask", metavar="TESTO", help="apre «Chiedi a NOKK» con una domanda")
    parser.add_argument("--settings", action="store_true", help="apre le impostazioni del dock in esecuzione")
    parser.add_argument("--position", choices=POSITIONS, help="sposta il dock su questo bordo")
    parser.add_argument("--reset", action="store_true", help="ripristina la configurazione predefinita")
    parser.add_argument("--print-config", action="store_true", help="mostra il percorso e il contenuto della configurazione")
    parser.add_argument("--check", action="store_true", help="diagnostica ambiente e collegamento a NOKK")
    return parser


def _send(action, payload=None, timeout=2.0):
    from nokk_dock.ipc import send

    return send(action, payload, timeout=timeout)


def _ping_running():
    try:
        return bool(_send("ping", timeout=0.6).get("ok"))
    except OSError:
        return False


def run_check(config, config_file):
    """Stampa lo stato dell'ambiente: utile quando il dock non parte."""
    import platform

    print("NOKK Dock — diagnostica")
    print(f"Python      : {platform.python_version()}")
    print(f"Config      : {config_file}")
    print()

    lines = []
    lines.append((CHECK if sys.version_info >= (3, 10) else MISSING, "Python 3.10 o successivo"))

    try:
        import tkinter  # noqa: F401

        lines.append((CHECK, "tkinter disponibile"))
    except Exception:
        if sys.platform.startswith("win"):
            lines.append((MISSING, "tkinter manca: reinstalla Python da python.org con Tcl/Tk"))
        else:
            lines.append((MISSING, "tkinter manca: installa python3-tk"))

    import os

    if sys.platform.startswith("win"):
        lines.append((CHECK, f"Windows {platform.release()} ({platform.machine()})"))
        from nokk_dock.capture import windows_powershell

        powershell = windows_powershell()
        lines.append((
            CHECK if powershell else MISSING,
            f"PowerShell: {powershell}" if powershell else "PowerShell manca: serve per lo screenshot",
        ))
        lines.append((CHECK, "Cattura schermo: PowerShell + System.Drawing"))
        lines.append((CHECK, "Widget musica: tasti multimediali di Windows"))
    else:
        display = os.environ.get("DISPLAY")
        wayland = os.environ.get("WAYLAND_DISPLAY")
        if display:
            lines.append((CHECK, f"DISPLAY={display}"))
        elif wayland:
            lines.append((CHECK, f"WAYLAND_DISPLAY={wayland}"))
        else:
            lines.append((MISSING, "Nessuna sessione grafica (DISPLAY/WAYLAND_DISPLAY)"))

        playerctl = shutil.which("playerctl")
        lines.append((
            CHECK if playerctl else MISSING,
            f"playerctl: {playerctl}" if playerctl else "playerctl manca: sudo apt install playerctl",
        ))

        from nokk_dock.capture import candidate_tools

        tools = candidate_tools(environ=os.environ)
        if tools:
            lines.append((CHECK, "Cattura schermo: " + ", ".join(name for name, _ in tools)))
        else:
            lines.append((MISSING, "Nessuno strumento di cattura (grim, scrot, gnome-screenshot, Pillow)"))

    try:
        from nokk_dock import hotkey as hotkey_module

        hotkey = hotkey_module.create_hotkey(config["capture"]["shortcut"], lambda: None)
        if hotkey.available():
            lines.append((
                CHECK,
                f"Scorciatoia globale ({hotkey_module.backend_name()}): "
                f"{config['capture']['shortcut']}",
            ))
        else:
            lines.append((MISSING, "Scorciatoia globale non disponibile: usa --capture dal desktop"))
    except Exception:
        lines.append((MISSING, "Scorciatoia globale non verificabile"))

    lines.append((
        CHECK if _ping_running() else MISSING,
        "Dock in esecuzione" if _ping_running() else "Dock non in esecuzione",
    ))

    from nokk_dock.client import NokkClient

    health = NokkClient(config["nokk"]["base_url"], config["nokk"]["api_key"], timeout=5).health()
    lines.append((
        CHECK if health else MISSING,
        f"NOKK risponde su {config['nokk']['base_url']}"
        if health else f"NOKK non risponde su {config['nokk']['base_url']}",
    ))

    for status, text in lines:
        print(f"[{status}] {text}")
    print()
    print("Le voci con [--] non bloccano il dock: i widget corrispondenti lo segnalano.")


def run_standalone_capture(config):
    """Cattura senza dock: salva lo scatto e spiega come usarlo."""
    from nokk_dock.capture import CaptureError, capture_screen, cleanup, load_image

    try:
        path = capture_screen(scale=config["capture"]["scale"])
    except CaptureError as error:
        print(f"Cattura non riuscita: {error}")
        return 1
    try:
        image = load_image(path, config["capture"]["max_bytes"])
    finally:
        cleanup(path)
    print(
        "Screenshot pronto "
        f"({image['bytes'] // 1024} KB, {image['mime_type']}). "
        "Avvia il dock con `python dock_start.py` per inviarlo a NOKK con la scorciatoia."
    )
    return 0


def main(argv=None):
    args = build_parser().parse_args(argv)
    target = config_path(args.config)

    if args.reset:
        save_config(default_config(), target)
        print(f"Configurazione ripristinata: {target}")
        if _ping_running():
            _send("reload")
        return 0

    config = load_config(target)

    if args.print_config:
        import json

        print(f"Configurazione: {target}")
        print(json.dumps(config, ensure_ascii=False, indent=2))
        return 0

    if args.check:
        run_check(config, target)
        return 0

    if args.position:
        config["dock"]["position"] = args.position
        config = validate_config(config)
        save_config(config, target)
        if _ping_running():
            _send("reload")
            print(f"Dock spostato: {args.position}")
        else:
            print(f"Posizione salvata: {args.position}. Avvia il dock con `python dock_start.py`.")
        return 0

    if args.capture:
        if _ping_running():
            _send("capture")
            print("Cattura richiesta al dock.")
            return 0
        print("Il dock non è in esecuzione: avvialo con `python dock_start.py`.")
        return run_standalone_capture(config)

    if args.ask is not None:
        if _ping_running():
            _send("ask", {"question": args.ask})
            print("Domanda inviata al dock.")
            return 0
        print("Il dock non è in esecuzione: avvialo con `python dock_start.py`.")
        return 1

    if args.settings:
        if _ping_running():
            _send("settings")
            return 0
        print("Il dock non è in esecuzione: avvialo con `python dock_start.py`.")
        return 1

    from nokk_dock.app import main as run_dock

    try:
        run_dock(config, target)
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
