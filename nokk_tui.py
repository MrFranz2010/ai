#!/usr/bin/env python3
"""Interfaccia a pannelli per il terminale NOKK.

Questa è la modalità predefinita quando Textual è installato e il terminale è
interattivo. Il client HTTP e le regole dei comandi restano in ``nokk_cli.py``:
qui c'è solo la UI, con la chat a sinistra e la barra laterale a destra.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.markdown import Markdown as RichMarkdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    RichLog,
    Select,
    Static,
    Switch,
)

from nokk_cli import (
    AGENT_RULES,
    CONTINUE_RULES,
    DEFAULT_BASE_URL,
    JOB_TIMEOUT,
    MAX_AGENT_ROUNDS,
    MAX_COMMANDS_PER_REPLY,
    POLL_INTERVAL,
    CliError,
    Config,
    LocalResult,
    NokkClient,
    extract_run_commands,
    mask_key,
    infer_profile,
    normalize_base_url,
    normalize_mode,
    run_local,
    save_config,
    truncate,
)

SIDEBAR_MIN_WIDTH = 96
MAX_SESSIONS = 30
MAX_SESSION_MESSAGES = 400


@dataclass
class ChatSession:
    title: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


def load_sessions(path):
    """Load the small session store used by the TUI."""
    try:
        saved = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return []
    items = saved.get("chats") if isinstance(saved, dict) else saved
    if not isinstance(items, list):
        return []
    sessions = []
    for item in items[:MAX_SESSIONS]:
        if not isinstance(item, dict):
            continue
        title = item.get("title")
        if not isinstance(title, str) or not title.strip():
            title = "Chat"
        messages = []
        raw_messages = item.get("messages")
        if isinstance(raw_messages, list):
            for message in raw_messages[-MAX_SESSION_MESSAGES:]:
                if not isinstance(message, dict):
                    continue
                role = message.get("role")
                content = message.get("content")
                if role not in {"user", "assistant"} or not isinstance(content, str):
                    continue
                clean = {"role": role, "content": content}
                if message.get("hidden"):
                    clean["hidden"] = True
                messages.append(clean)
        created_at = item.get("created_at")
        if not isinstance(created_at, (int, float)):
            created_at = time.time()
        sessions.append(ChatSession(title.strip()[:80], messages, float(created_at)))
    return sessions


def save_sessions(path, chats):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = {
        "version": 1,
        "chats": [
            {
                "title": chat.title,
                "created_at": chat.created_at,
                "messages": chat.messages[-MAX_SESSION_MESSAGES:],
            }
            for chat in chats[:MAX_SESSIONS]
        ],
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


FILE_CONTEXT_LIMIT = 40_000
FILE_CONTEXT_TOTAL = 100_000
FILE_MENTION_RE = re.compile(r"(?<![\w@])@([^\s@]+)")


def collect_file_context(text, cwd):
    """Read @file mentions into context for the next request."""
    cwd = Path(cwd).expanduser().resolve()
    seen = set()
    blocks = []
    total = 0
    for match in FILE_MENTION_RE.finditer(text or ""):
        raw = match.group(1).rstrip(".,;:!?)]}")
        if not raw:
            continue
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = cwd / path
        try:
            path = path.resolve()
        except OSError:
            continue
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        try:
            size = path.stat().st_size
            if size > FILE_CONTEXT_LIMIT:
                blocks.append(f"File: {path}\n(file troppo grande, non incluso)")
                continue
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError as error:
            blocks.append(f"File: {path}\n(impossibile leggerlo: {error})")
            continue
        if "\x00" in content:
            blocks.append(f"File: {path}\n(file binario, non incluso)")
            continue
        if total + len(content) > FILE_CONTEXT_TOTAL:
            blocks.append("(limite complessivo del contesto file raggiunto)")
            break
        total += len(content)
        try:
            label = str(path.relative_to(cwd))
        except ValueError:
            label = str(path)
        blocks.append(f"File: {label}\n```\n{content.rstrip()}\n```")
    if not blocks:
        return ""
    return "Contesto dei file citati dall'utente:\n\n" + "\n\n".join(blocks)


def git_output(cwd, args, timeout=8):
    try:
        completed = subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return 1, f"git non disponibile: {error}"
    output = (completed.stdout or completed.stderr or "").strip()
    return completed.returncode, output


def _memory_usage():
    try:
        info = {}
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition(":")
            if value.strip():
                info[key] = int(value.split()[0])
        total = info.get("MemTotal")
        available = info.get("MemAvailable", info.get("MemFree"))
        if not total or available is None:
            return None, None
        used = max(0, total - available)
        return used / total * 100, used / 1024 / 1024
    except (OSError, ValueError):
        return None, None


def resource_snapshot(cwd):
    cpu = None
    try:
        load = os.getloadavg()[0]
        cpu = min(100.0, load / (os.cpu_count() or 1) * 100)
    except (AttributeError, OSError):
        pass
    memory_percent, memory_used_mb = _memory_usage()
    disk_percent = None
    disk_free_gb = None
    try:
        usage = shutil.disk_usage(cwd)
        disk_percent = usage.used / usage.total * 100 if usage.total else None
        disk_free_gb = usage.free / 1024**3
    except OSError:
        pass
    process_mb = None
    try:
        import resource

        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        process_mb = value / 1024 / 1024 if sys.platform == "darwin" else value / 1024
    except (ImportError, OSError):
        pass
    return {
        "cpu": cpu,
        "memory": memory_percent,
        "memory_used_mb": memory_used_mb,
        "disk": disk_percent,
        "disk_free_gb": disk_free_gb,
        "process_mb": process_mb,
    }


def meter(percent, width=10):
    if percent is None:
        return "░" * width
    filled = max(0, min(width, round(percent / 100 * width)))
    return "█" * filled + "░" * (width - filled)


def short_path(path, limit=34):
    text = str(path)
    home = str(Path.home())
    if text.startswith(home):
        text = "~" + text[len(home):]
    if len(text) <= limit:
        return text
    return "…" + text[-(limit - 1):]


def native_clipboard_copy(text):
    """Best-effort copy through the desktop clipboard tools."""
    if sys.platform == "darwin":
        commands = [["pbcopy"]]
    elif os.name == "nt":
        commands = [["clip"]]
    elif os.environ.get("WAYLAND_DISPLAY"):
        commands = [["wl-copy"], ["xclip", "-selection", "clipboard"]]
    else:
        commands = [
            ["xclip", "-selection", "clipboard"],
            ["xsel", "--clipboard", "--input"],
        ]
    for command in commands:
        if shutil.which(command[0]) is None:
            continue
        try:
            subprocess.run(
                command,
                input=text,
                text=True,
                timeout=1.5,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except (OSError, subprocess.SubprocessError):
            continue
    return False


def git_branch(cwd):
    try:
        completed = subprocess.run(
            ["git", "-C", str(cwd), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=1.5,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    branch = completed.stdout.strip()
    return branch if completed.returncode == 0 and branch else None


class ConfirmScreen(ModalScreen[bool]):
    """Conferma un comando locale o un'azione richiesta dal server."""

    BINDINGS = [
        Binding("escape", "no", "Annulla"),
        Binding("n", "no", "No"),
        Binding("y", "yes", "Sì"),
    ]

    def __init__(self, title, detail, yes_label="Esegui"):
        super().__init__()
        self.dialog_title = title
        self.dialog_detail = detail
        self.yes_label = yes_label

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(self.dialog_title, id="dialog-title")
            yield Static(
                Panel(
                    Text(self.dialog_detail),
                    border_style="#30363d",
                    padding=(0, 1),
                ),
                id="dialog-text",
            )
            with Horizontal(classes="dialog-buttons"):
                yield Button(self.yes_label, id="yes", variant="success")
                yield Button("Rifiuta", id="no", variant="error")

    def on_button_pressed(self, event: Button.Pressed):
        self.dismiss(event.button.id == "yes")

    def action_yes(self):
        self.dismiss(True)

    def action_no(self):
        self.dismiss(False)


class SecretScreen(ModalScreen[str | None]):
    """Chiede una chiave API senza mostrarla nel transcript."""

    BINDINGS = [Binding("escape", "cancel", "Annulla")]

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static("Chiave API NOKK", id="dialog-title")
            yield Static(
                "Incolla la chiave creata in Impostazioni → API. "
                "Lascia vuoto e premi Salva per rimuoverla.",
                id="dialog-text",
            )
            yield Input(placeholder="nokk_…", password=True, id="secret")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Salva", id="save", variant="primary")
                yield Button("Annulla", id="cancel", variant="default")

    def on_mount(self):
        self.query_one("#secret", Input).focus()

    def on_input_submitted(self, event: Input.Submitted):
        self.dismiss(event.value.strip())

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "save":
            self.dismiss(self.query_one("#secret", Input).value.strip())
        else:
            self.dismiss(None)

    def action_cancel(self):
        self.dismiss(None)


HELP_TEXT = """\
## Terminale NOKK

Scrivi un messaggio e premi Invio. I comandi che NOKK propone nel blocco
`nokk-run` vengono eseguiti **sul computer locale**, dopo la tua conferma.
I comandi che NOKK vuole eseguire sul server passano da una conferma separata.

### Comandi

| Comando | Azione |
| --- | --- |
| `/new` | nuova chat |
| `/cd [cartella]` | cambia directory locale |
| `/run <comando>` | esegue un comando locale |
| `/agent [on\\|off]` | abilita i comandi locali proposti |
| `/mode [codice\\|studio\\|analista\\|off]` | modalità di risposta |
| `/url [indirizzo]` | cambia server |
| `/key` | imposta la chiave API |
| `/server` | stato del server |
| `/status` | sessione, connessione e configurazione |
| `/config` | configurazione attuale |
| `/settings` | profili locale/hosting e chiavi |
| `/export [file]` | esporta la chat in Markdown |
| `/copy [n|all]` | copia l'ultima risposta, una precedente o tutto |
| `/retry` | ripete l'ultima domanda |
| `/sessions` | elenca le sessioni salvate |
| `/resume <n>` | riapre una sessione salvata |
| `/rename <titolo>` | rinomina la sessione attiva |
| `/model [provider/modello]` | cambia modello per questa sessione |
| `/diff`, `/git status` | mostra modifiche e stato Git |
| `/cancel` | annulla il job in corso |
| `/clear` | pulisce il transcript |

`!comando` esegue subito un comando locale. `Ctrl+Q` esce, `Ctrl+N` apre una
nuova chat, `Ctrl+B` mostra o nasconde la barra laterale, `Ctrl+E` esporta la
chat, `Ctrl+Y` copia l'ultima risposta, `Ctrl+R` ripete l'ultima domanda,
`F1` apre l'aiuto e `F2` le impostazioni.
"""


class HelpScreen(ModalScreen[None]):
    BINDINGS = [Binding("escape", "close", "Chiudi")]

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="dialog", classes="help-dialog"):
            yield Static(RichMarkdown(HELP_TEXT))
            with Horizontal(classes="dialog-buttons"):
                yield Button("Chiudi", id="close", variant="primary")

    def on_button_pressed(self, _event: Button.Pressed):
        self.dismiss(None)

    def action_close(self):
        self.dismiss(None)


MODE_OPTIONS = [
    ("Predefinita", ""),
    ("Codice", "codice"),
    ("Studio", "studio"),
    ("Analista", "analista"),
]


class SettingsScreen(ModalScreen[dict | None]):
    """Impostazioni comuni per il profilo locale e quello hosting."""

    BINDINGS = [
        Binding("escape", "cancel", "Annulla"),
        Binding("ctrl+s", "save", "Salva"),
    ]

    def __init__(self, profile, profiles, mode, agent):
        super().__init__()
        self.profile = profile if profile in {"local", "hosting"} else "local"
        self.profiles = {
            name: {
                "url": str(values.get("url") or ""),
                "key": str(values.get("key") or ""),
            }
            for name, values in profiles.items()
            if name in {"local", "hosting"}
        }
        self.profiles.setdefault("local", {"url": DEFAULT_BASE_URL, "key": ""})
        self.profiles.setdefault("hosting", {"url": "", "key": ""})
        self.mode = mode
        self.agent = bool(agent)
        self._ready = False

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="dialog", classes="settings-dialog"):
            yield Static("Impostazioni", id="dialog-title")
            yield Static(
                "Scegli il profilo, poi modifica server e chiave. "
                "Le due configurazioni restano salvate separatamente.",
                id="dialog-text",
            )
            yield Label("Profilo")
            yield Select(
                [("Locale", "local"), ("Hosting", "hosting")],
                value=self.profile,
                allow_blank=False,
                compact=True,
                id="settings-profile",
            )
            yield Label("Server")
            yield Input(
                value=self.profiles[self.profile]["url"],
                placeholder="http://127.0.0.1:8000",
                compact=True,
                id="settings-url",
            )
            yield Label("Chiave API")
            yield Input(
                value=self.profiles[self.profile]["key"],
                placeholder="nokk_… (serve per l'hosting)",
                password=True,
                compact=True,
                id="settings-key",
            )
            yield Label("Modalità")
            yield Select(
                MODE_OPTIONS,
                value=self.mode or "",
                allow_blank=True,
                compact=True,
                id="settings-mode",
            )
            yield Label("Comandi locali proposti dall'agente")
            yield Switch(value=self.agent, id="settings-agent")
            yield Static(id="settings-status")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Prova connessione", id="settings-test", variant="default")
                yield Button("Salva", id="settings-save", variant="primary")
                yield Button("Annulla", id="settings-cancel", variant="default")

    def on_mount(self):
        self._ready = True
        self.query_one("#settings-url", Input).focus()

    def _capture_current(self):
        self.profiles[self.profile] = {
            "url": self.query_one("#settings-url", Input).value.strip(),
            "key": self.query_one("#settings-key", Input).value.strip(),
        }

    def _load_profile(self):
        values = self.profiles[self.profile]
        self.query_one("#settings-url", Input).value = values["url"]
        self.query_one("#settings-key", Input).value = values["key"]
        self.query_one("#settings-profile", Select).value = self.profile

    def on_select_changed(self, event: Select.Changed):
        if event.select.id != "settings-profile" or not self._ready:
            return
        if event.value not in {"local", "hosting"} or event.value == self.profile:
            return
        self._capture_current()
        self.profile = event.value
        self._load_profile()
        self.query_one("#settings-url", Input).focus()

    def collect(self):
        self._capture_current()
        values = self.profiles[self.profile]
        url = normalize_base_url(values["url"])
        key = values["key"]
        mode_value = self.query_one("#settings-mode", Select).value
        mode = normalize_mode(mode_value if mode_value not in (None, Select.BLANK) else None)
        agent = self.query_one("#settings-agent", Switch).value
        self.profiles[self.profile] = {"url": url, "key": key}
        return {
            "profile": self.profile,
            "profiles": {
                name: dict(profile) for name, profile in self.profiles.items()
            },
            "mode": mode,
            "agent": bool(agent),
        }

    def _set_status(self, text, color="#7d8b9a"):
        self.query_one("#settings-status", Static).update(
            Text(text, style=color)
        )

    async def test_connection(self):
        try:
            data = self.collect()
            profile = data["profiles"][self.profile]
            client = NokkClient(profile["url"], profile["key"])
            health = await asyncio.to_thread(client.health)
        except CliError as error:
            self._set_status(f"Errore: {error}", "#f85149")
            return
        provider = health.get("provider") or "NOKK"
        self._set_status(f"Connessione riuscita · {provider}", "#3fb950")

    def save(self):
        try:
            data = self.collect()
        except CliError as error:
            self._set_status(f"Errore: {error}", "#f85149")
            return
        self.dismiss(data)

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "settings-test":
            self.run_worker(
                self.test_connection(), group="settings-test", exclusive=True,
            )
        elif event.button.id == "settings-save":
            self.save()
        elif event.button.id == "settings-cancel":
            self.dismiss(None)

    def action_save(self):
        self.save()

    def action_cancel(self):
        self.dismiss(None)


class NokkTuiApp(App):
    """Layout: chat a sinistra, barra con widget e agenti a destra."""

    TITLE = "NOKK"
    SUB_TITLE = "terminale"
    CSS = """
    Screen {
        background: #0b0f14;
        color: #d7e0ea;
    }
    Header {
        background: #111820;
        color: #d7e0ea;
    }
    Footer {
        background: #111820;
        color: #7d8b9a;
    }
    #main {
        height: 1fr;
    }
    #left {
        width: 1fr;
    }
    #transcript {
        height: 1fr;
        padding: 0 1;
        background: #0b0f14;
    }
    #streamline {
        height: auto;
        max-height: 4;
        padding: 0 1;
        background: #0d1319;
        color: #8b949e;
    }
    #statusline {
        height: 1;
        padding: 0 1;
        background: #111820;
        color: #7d8b9a;
    }
    #prompt {
        height: 3;
        margin: 0 1 1 1;
        border: tall #2f81f7;
        background: #0f141a;
    }
    #sidebar {
        width: 42;
        padding: 0 1;
        background: #0f141a;
        border-left: solid #263241;
    }
    .section-title {
        color: #58a6ff;
        text-style: bold;
        margin-top: 1;
    }
    #agents, #resources, #widgets {
        height: auto;
    }
    #chats {
        height: 3;
        background: #0f141a;
        border: none;
    }
    #chats > ListItem {
        padding: 0 1;
        color: #d7e0ea;
    }
    #activity {
        height: 6;
        background: #0f141a;
        border: none;
    }
    Screen.narrow #sidebar {
        display: none;
    }
    ConfirmScreen, SecretScreen, HelpScreen {
        align: center middle;
        background: #000000 65%;
    }
    #dialog {
        width: 76;
        max-width: 92%;
        height: auto;
        max-height: 82%;
        border: thick #2f81f7;
        background: #111820;
        padding: 1 2;
    }
    #dialog-title {
        color: #58a6ff;
        text-style: bold;
        margin-bottom: 1;
    }
    #dialog-text {
        height: auto;
        margin-bottom: 1;
    }
    .dialog-buttons {
        height: auto;
        align-horizontal: right;
    }
    .dialog-buttons Button {
        margin-left: 1;
    }
    .settings-dialog {
        width: 84;
    }
    .settings-dialog Label {
        color: #7d8b9a;
        margin-top: 1;
    }
    .settings-dialog Input, .settings-dialog Select {
        margin-bottom: 0;
    }
    #settings-status {
        height: 2;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Esci", show=True),
        Binding("ctrl+n", "new_chat", "Nuova chat", show=True),
        Binding("ctrl+b", "toggle_sidebar", "Sidebar", show=True),
        Binding("ctrl+e", "export_chat", "Esporta", show=True, priority=True),
        Binding("ctrl+y", "copy_last", "Copia", show=True, priority=True),
        Binding("ctrl+r", "retry", "Riprova", show=True, priority=True),
        Binding("ctrl+x", "cancel_job", "Annulla", show=True, priority=True),
        Binding("ctrl+l", "clear_view", "Pulisci", show=True),
        Binding("f1", "help", "Aiuto", show=True),
        Binding("f2", "settings", "Impostazioni", show=True),
    ]

    def __init__(
        self,
        config,
        config_path,
        *,
        client=None,
        auto_yes=False,
        job_timeout=JOB_TIMEOUT,
        cwd=None,
        session_path=None,
    ):
        super().__init__()
        self.client = client or NokkClient(config.base_url, config.api_key)
        self.config_path = Path(config_path)
        self.session_path = (
            Path(session_path)
            if session_path
            else self.config_path.with_name("sessions.json")
        )
        self.profile = config.profile if config.profile in {"local", "hosting"} else infer_profile(config.base_url)
        self.profiles = {
            "local": {
                "url": config.local_url or DEFAULT_BASE_URL,
                "key": config.local_api_key,
            },
            "hosting": {
                "url": config.hosting_url or "",
                "key": config.hosting_api_key,
            },
        }
        self.profiles[self.profile] = {
            "url": self.client.base_url,
            "key": self.client.api_key,
        }
        self.mode = normalize_mode(config.mode)
        self.agent = bool(config.agent)
        self.auto_yes = bool(auto_yes)
        self.job_timeout = job_timeout
        self.cwd = Path(cwd or Path.cwd()).expanduser().resolve()
        self.model_override = None
        self.current_job_id = None
        saved_chats = load_sessions(self.session_path)
        self.chats = saved_chats or [ChatSession("Chat 1")]
        self.active_index = len(self.chats) - 1 if saved_chats else 0
        self.messages: list[dict[str, Any]] = self.active_chat.messages
        self.busy = False
        self.online = None
        self.health: dict[str, Any] = {}
        self.status_detail = "pronto"
        self.requests = 0
        self.last_latency = None
        self.started_at = time.time()
        self._sidebar_hidden = False
        self._branch = git_branch(self.cwd)

    # ------------------------------------------------------------------ layout
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main"):
            with Vertical(id="left"):
                yield RichLog(
                    id="transcript",
                    wrap=True,
                    highlight=False,
                    markup=True,
                    min_width=1,
                    max_lines=2000,
                )
                yield Static("", id="streamline")
                yield Static(id="statusline")
                yield Input(
                    placeholder=(
                        "Scrivi a NOKK…   !comando per il terminale locale   /help"
                    ),
                    id="prompt",
                )
            with VerticalScroll(id="sidebar"):
                yield Static("AGENTI", classes="section-title")
                yield Static(id="agents")
                yield Static("CHAT", classes="section-title")
                yield ListView(id="chats")
                yield Static("RISORSE", classes="section-title")
                yield Static(id="resources")
                yield Static("WIDGET", classes="section-title")
                yield Static(id="widgets")
                yield Static("ATTIVITÀ", classes="section-title")
                yield RichLog(
                    id="activity",
                    max_lines=100,
                    min_width=1,
                    wrap=True,
                    markup=True,
                )
        yield Footer()

    def on_mount(self):
        self.query_one("#streamline", Static).display = False
        self.query_one("#prompt", Input).focus()
        self.refresh_chat_list()
        self.refresh_sidebar()
        self.refresh_widgets()
        self.set_interval(2.0, self.refresh_widgets)
        self.write_banner()
        self.activity_log().write(Text("sessione avviata", style="dim"))
        self.run_worker(self.check_health(), group="health")

    def on_resize(self, event):
        self._apply_sidebar_visibility(event.size.width)

    def _apply_sidebar_visibility(self, width=None):
        width = self.size.width if width is None else width
        self.screen.set_class(
            self._sidebar_hidden or width < SIDEBAR_MIN_WIDTH,
            "narrow",
        )

    def action_toggle_sidebar(self):
        self._sidebar_hidden = not self._sidebar_hidden
        self._apply_sidebar_visibility()
        self.query_one("#prompt", Input).focus()

    def action_new_chat(self):
        if self.busy:
            self.notify("Attendi la risposta di NOKK.", severity="warning")
            return
        self.new_chat()

    def action_clear_view(self):
        self.query_one("#transcript", RichLog).clear()
        self.notify("Transcript pulito.")

    def action_help(self):
        self.push_screen(HelpScreen())

    def action_settings(self):
        if self.busy:
            self.notify("Attendi la risposta di NOKK.", severity="warning")
            return
        self.push_screen(
            SettingsScreen(self.profile, self.profiles, self.mode, self.agent),
            callback=self.apply_settings,
        )

    def action_export_chat(self):
        self.export_chat("")

    def action_copy_last(self):
        self.copy_message("")

    def action_retry(self):
        if self.busy:
            self.notify("Attendi la risposta di NOKK.", severity="warning")
            return
        self.run_worker(
            self.retry_last(),
            group="chat",
            name="chat",
            exclusive=True,
        )

    def action_cancel_job(self):
        if not self.busy or not self.current_job_id:
            self.notify("Nessuna attività da annullare.")
            return
        self.run_worker(
            self.cancel_job(),
            group="cancel",
            name="cancel",
            exclusive=True,
        )

    async def cancel_job(self):
        job_id = self.current_job_id
        if not job_id:
            return
        try:
            await asyncio.to_thread(self.client.cancel, job_id)
        except CliError as error:
            self.write_error(error)
            return
        self.write_system("Richiesta di annullamento inviata.")
        self.activity_log().write(Text("annullamento richiesto", style="#d29922"))

    def apply_settings(self, data):
        if not data:
            return
        self.profile = data["profile"]
        self.profiles = data["profiles"]
        self.mode = data["mode"]
        self.agent = bool(data["agent"])
        self.model_override = None
        active = self.profiles[self.profile]
        self.client.base_url = active["url"]
        self.client.api_key = active["key"]
        self.save()
        self.write_system(
            f"Profilo {self.profile} · {self.client.base_url}"
        )
        self.refresh_widgets()
        self.run_worker(self.check_health(), group="health")

    # ------------------------------------------------------------------ output
    def transcript(self) -> RichLog:
        return self.query_one("#transcript", RichLog)

    def activity_log(self) -> RichLog:
        return self.query_one("#activity", RichLog)

    def write_banner(self):
        banner = Text()
        banner.append("NOKK", style="bold #58a6ff")
        banner.append("  terminale\n", style="bold #d7e0ea")
        banner.append(
            "Chat a sinistra, agenti e risorse a destra. "
            "I comandi locali chiedono conferma.\n",
            style="#7d8b9a",
        )
        banner.append("!comando", style="bold")
        banner.append(" esegue qui · ", style="#7d8b9a")
        banner.append("/help", style="bold")
        banner.append(" mostra i comandi · ", style="#7d8b9a")
        banner.append("F1", style="bold")
        banner.append(" aiuto", style="#7d8b9a")
        self.transcript().write(
            Panel(
                banner,
                title="benvenuto",
                border_style="#263241",
                padding=(0, 1),
            )
        )

    def write_user(self, text):
        self.transcript().write(
            Panel(
                Text(text),
                title="tu",
                title_align="left",
                border_style="#2f81f7",
                padding=(0, 1),
            )
        )

    def write_assistant(self, text):
        renderable = RichMarkdown(text) if text.strip() else Text("(nessun testo)")
        self.transcript().write(
            Panel(
                renderable,
                title="NOKK",
                title_align="left",
                border_style="#238636",
                padding=(0, 1),
            )
        )

    def write_system(self, text):
        self.transcript().write(
            Text.assemble(("· ", "dim"), (text, "dim"))
        )

    def write_error(self, error):
        body = Text(str(error), style="bold #f85149")
        hint = getattr(error, "hint", None)
        if hint:
            body.append("\n" + str(hint), style="dim")
        self.transcript().write(
            Panel(body, title="errore", border_style="#f85149", padding=(0, 1))
        )
        self.activity_log().write(Text(f"errore: {error}", style="#f85149"))

    def write_command(self, result: LocalResult):
        color = "#3fb950" if result.exit_code == 0 else "#f85149"
        output = result.output.rstrip() or "(nessun output)"
        self.transcript().write(
            Panel(
                Text(truncate(output, 6000)),
                title=f"shell · exit {result.exit_code}",
                title_align="left",
                border_style=color,
                padding=(0, 1),
            )
        )
        self.activity_log().write(
            Text.assemble(
                ("shell ", f"bold {color}"),
                (f"exit {result.exit_code} · ", "dim"),
                (result.command, ""),
            )
        )

    def write_tool_event(self, event):
        command = event.get("command") or event.get("tool") or "strumento"
        exit_code = event.get("exit_code")
        executed = event.get("executed")
        color = "#3fb950" if executed is not False and exit_code in (0, None) else "#f85149"
        line = Text.assemble(
            ("server ", f"bold {color}"),
            (f"· exit {exit_code} · " if exit_code is not None else "· ", "dim"),
            (str(command), ""),
        )
        self.transcript().write(line)
        output = event.get("output")
        if isinstance(output, str) and output.strip():
            self.transcript().write(
                Text(truncate(output.rstrip(), 1500), style="dim")
            )
        self.activity_log().write(line)

    # ------------------------------------------------------------------ status
    def set_busy(self, busy, detail=None):
        self.busy = busy
        if detail:
            self.status_detail = detail
        try:
            prompt = self.query_one("#prompt", Input)
            prompt.disabled = busy
            if not busy:
                prompt.focus()
        except Exception:
            pass
        self.refresh_sidebar()
        self.refresh_widgets()

    def refresh_widgets(self):
        resources = resource_snapshot(self.cwd)
        uptime = int(time.time() - self.started_at)
        minutes, seconds = divmod(uptime, 60)
        hours, minutes = divmod(minutes, 60)
        cpu = resources["cpu"]
        memory = resources["memory"]
        disk = resources["disk"]
        visible_messages = sum(
            1 for message in self.active_chat.messages if not message.get("hidden")
        )
        turns = sum(
            1 for message in self.active_chat.messages
            if message.get("role") == "user" and not message.get("hidden")
        )
        context_chars = sum(
            len(message.get("content", ""))
            for message in self.active_chat.messages
            if isinstance(message.get("content"), str)
        )
        context_tokens = context_chars // 4

        resources_text = Text()
        resources_text.append("CPU   ")
        resources_text.append(meter(cpu, 8), style="#58a6ff")
        resources_text.append(f" {cpu:3.0f}%\n" if cpu is not None else " n/d\n")
        resources_text.append("RAM   ")
        resources_text.append(meter(memory, 8), style="#bc8cff")
        if memory is not None and resources.get("memory_used_mb"):
            used = resources["memory_used_mb"]
            amount = f"{used / 1024:.1f}G" if used >= 1024 else f"{used:.0f}M"
            resources_text.append(f" {memory:3.0f}% · {amount}\n")
        else:
            resources_text.append(" n/d\n")
        resources_text.append("Disco ")
        resources_text.append(meter(disk, 8), style="#3fb950")
        if disk is not None:
            resources_text.append(
                f" {disk:3.0f}% · {resources.get('disk_free_gb', 0):.1f}G\n"
            )
        else:
            resources_text.append(" n/d\n")
        resources_text.append(
            f"Ctx   {context_tokens / 1000:.1f}k token\n"
            if context_tokens >= 1000
            else f"Ctx   {context_tokens} token\n",
            style="dim",
        )
        resources_text.append(
            f"Req   {self.requests} · "
            + (f"{self.last_latency * 1000:.0f}ms\n" if self.last_latency else "—\n"),
            style="dim",
        )
        resources_text.append(
            f"Proc  {resources.get('process_mb') or 0:.0f}M · "
            f"{hours:02d}:{minutes:02d}:{seconds:02d}",
            style="dim",
        )
        self.query_one("#resources", Static).update(resources_text)

        title = self.active_chat.title
        if len(title) > 28:
            title = title[:27] + "…"
        widgets = Text()
        widgets.append("Profilo ", style="dim")
        widgets.append(("locale" if self.profile == "local" else "hosting") + "\n")
        widgets.append("Chat    ", style="dim")
        widgets.append(f"{title} · {visible_messages} msg\n")
        widgets.append("Turni   ", style="dim")
        widgets.append(f"{turns}\n")
        widgets.append("API key ", style="dim")
        widgets.append(("configurata" if self.client.api_key else "assente") + "\n")
        widgets.append("Mode    ", style="dim")
        widgets.append(f"{self.mode or 'predefinita'}\n")
        widgets.append("Modello ", style="dim")
        if self.model_override:
            widgets.append(
                f"{self.model_override['provider']}/{self.model_override['model']}\n"
            )
        else:
            widgets.append(
                f"{self.health.get('provider') or '—'}/"
                f"{self.health.get('model') or '—'}\n"
            )
        widgets.append("Agente  ", style="dim")
        widgets.append(("on" if self.agent else "off") + "\n")
        widgets.append("CWD     ", style="dim")
        widgets.append(short_path(self.cwd, 30) + "\n")
        widgets.append("Git     ", style="dim")
        widgets.append(self._branch or "—")
        self.query_one("#widgets", Static).update(widgets)

        self.refresh_statusline()
        self.refresh_sidebar()

    def show_stream(self, text):
        line = self.query_one("#streamline", Static)
        text = (text or "").strip()
        if not text:
            line.display = False
            line.update("")
            return
        line.display = True
        line.update(Text(text[-1200:], style="#8b949e"))

    def refresh_statusline(self):
        color = "#3fb950" if self.online else ("#f85149" if self.online is False else "#8b949e")
        label = "online" if self.online else ("offline" if self.online is False else "connessione…")
        status = Text.assemble(
            ("● ", color),
            (label, color),
            (" · ", "dim"),
            (self.client.base_url, "dim"),
            (" · ", "dim"),
            (self.mode or "predefinita", ""),
            (" · ", "dim"),
            (self.status_detail, "#d7e0ea"),
        )
        if self.busy:
            status.append("  ⏳", style="#d29922")
        self.query_one("#statusline", Static).update(status)

    def refresh_sidebar(self):
        agents = Text()
        for name, detail, color in (
            (
                "NOKK API",
                "online" if self.online else ("offline" if self.online is False else "connessione…"),
                "#3fb950" if self.online else ("#f85149" if self.online is False else "#d29922"),
            ),
            (
                "Agente",
                "al lavoro" if self.busy else "pronto",
                "#d29922" if self.busy else "#3fb950",
            ),
            (
                "Terminale",
                "conferma",
                "#58a6ff",
            ),
            (
                "Approvazioni",
                "automatiche" if self.auto_yes else "manuali",
                "#d29922" if self.auto_yes else "#3fb950",
            ),
        ):
            agents.append("● ", style=color)
            agents.append(f"{name}  ", style="bold #d7e0ea")
            agents.append(detail + "\n", style=color)
        provider = self.health.get("provider")
        if provider:
            agents.append(
                f"  {provider} · {self.health.get('model') or '—'}\n",
                style="dim",
            )
        self.query_one("#agents", Static).update(agents)

    def refresh_chat_list(self):
        listview = self.query_one("#chats", ListView)
        listview.clear()
        for chat in self.chats:
            listview.append(ListItem(Label(chat.title, markup=False)))
        try:
            listview.index = self.active_index
        except Exception:
            pass

    # ------------------------------------------------------------------ chat
    @property
    def active_chat(self):
        return self.chats[self.active_index]

    def _persist_sessions(self):
        try:
            save_sessions(self.session_path, self.chats)
        except OSError as error:
            self.notify(f"Sessioni non salvate: {error}", severity="warning")

    def new_chat(self):
        if self.active_chat.messages:
            self.chats.append(ChatSession(f"Chat {len(self.chats) + 1}"))
            self.active_index = len(self.chats) - 1
        self.messages = self.active_chat.messages
        self.refresh_chat_list()
        self.query_one("#transcript", RichLog).clear()
        self.write_banner()
        self.refresh_widgets()
        self.query_one("#prompt", Input).focus()
        self._persist_sessions()

    def select_chat(self, index):
        if index is None or not 0 <= index < len(self.chats) or index == self.active_index:
            return
        self.active_index = index
        self.messages = self.active_chat.messages
        self.render_chat()
        self.refresh_chat_list()
        self.refresh_widgets()
        self.query_one("#prompt", Input).focus()
        self._persist_sessions()

    def on_list_view_selected(self, event: ListView.Selected):
        self.select_chat(event.index)

    def render_chat(self):
        log = self.query_one("#transcript", RichLog)
        log.clear()
        if not self.active_chat.messages:
            self.write_banner()
            return
        for message in self.active_chat.messages:
            if message.get("hidden"):
                continue
            content = message.get("content")
            if not isinstance(content, str):
                continue
            if message.get("role") == "user":
                self.write_user(content)
            elif message.get("role") == "assistant":
                self.write_assistant(content)

    def _wire(self, text):
        if not self.agent:
            return text
        return f"{text}\n\n---\n{AGENT_RULES.format(cwd=self.cwd)}"

    def wire_messages(self, extra_context=""):
        wire = []
        for message in self.active_chat.messages[-38:]:
            role = message.get("role")
            content = message.get("content")
            if role not in {"user", "assistant"} or not isinstance(content, str):
                continue
            wire.append({"role": role, "content": truncate(content, 12_000)})
        if wire and wire[-1]["role"] == "user":
            content = wire[-1]["content"]
            if extra_context:
                content = truncate(extra_context, 100_000) + "\n\n" + content
            wire[-1]["content"] = self._wire(content) if self.agent else content
        return wire

    async def ask(self, text):
        chat = self.active_chat
        if not chat.messages:
            chat.title = text if len(text) <= 30 else text[:29] + "…"
            self.refresh_chat_list()
        file_context = collect_file_context(text, self.cwd)
        if file_context:
            self.write_system("Contesto file incluso nella richiesta.")
        self.write_user(text)
        chat.messages.append({"role": "user", "content": text})
        self.set_busy(True, "NOKK sta pensando…")
        try:
            for round_number in range(MAX_AGENT_ROUNDS + 1):
                job = await self.run_job(self.wire_messages(file_context))
                reply = job.get("reply")
                reply = reply.strip() if isinstance(reply, str) else ""
                self.write_assistant(reply)
                chat.messages.append({"role": "assistant", "content": reply})
                commands = extract_run_commands(reply) if self.agent else []
                if not commands:
                    self.set_busy(False, "pronto")
                    return
                if round_number >= MAX_AGENT_ROUNDS:
                    self.write_system("Limite di comandi locali raggiunto.")
                    self.set_busy(False, "pronto")
                    return
                for command in commands[:MAX_COMMANDS_PER_REPLY]:
                    approved = self.auto_yes or await self.confirm_local(command)
                    if not approved:
                        self.write_system("Comando locale rifiutato.")
                        self.activity_log().write(
                            Text(f"rifiutato: {command}", style="#d29922")
                        )
                        self.set_busy(False, "comando rifiutato")
                        return
                    result = await asyncio.to_thread(run_local, command, self.cwd)
                    self.write_command(result)
                    chat.messages.append({
                        "role": "user",
                        "content": self.result_context(result),
                        "hidden": True,
                    })
                self.set_busy(True, "NOKK sta pensando…")
        except CliError as error:
            self.write_error(error)
            self.set_busy(False, "errore")
            return
        except asyncio.CancelledError:
            self.set_busy(False, "annullato")
            raise
        finally:
            self.current_job_id = None
            self.show_stream("")
            if self.busy:
                self.set_busy(False, "pronto")
            self.refresh_widgets()
            self._persist_sessions()

    def result_context(self, result: LocalResult):
        output = truncate(result.output.strip(), 10_000)
        return (
            "Ho eseguito questo comando sulla macchina locale:\n"
            f"comando: {result.command}\n"
            f"directory: {self.cwd}\n"
            f"exit code: {result.exit_code}\n"
            f"output:\n{output or '(nessun output)'}"
        )

    async def run_local_command(self, command):
        command = (command or "").strip()
        if not command:
            self.write_system("Uso: !comando")
            return
        self.set_busy(True, "comando locale…")
        try:
            result = await asyncio.to_thread(run_local, command, self.cwd)
            self.write_command(result)
            self.active_chat.messages.append({
                "role": "user",
                "content": self.result_context(result),
                "hidden": True,
            })
        except CliError as error:
            self.write_error(error)
        finally:
            self.set_busy(False, "pronto")
            self.refresh_widgets()
            self._persist_sessions()

    async def run_job(self, messages):
        started = time.monotonic()
        self.requests += 1
        model = self.model_override or {}
        job_id = await asyncio.to_thread(
            self.client.start_chat,
            messages,
            self.mode,
            model.get("provider"),
            model.get("model"),
            stream=True,
        )
        self.current_job_id = job_id
        self.last_latency = time.monotonic() - started
        seen_events = 0
        deadline = time.monotonic() + self.job_timeout
        while time.monotonic() < deadline:
            job = await asyncio.to_thread(self.client.job, job_id)
            self.requests += 1
            self.last_latency = time.monotonic() - started
            events = job.get("tool_events")
            if isinstance(events, list):
                for event in events[seen_events:]:
                    self.write_tool_event(event)
                seen_events = len(events)
            partial = job.get("partial_reply")
            if isinstance(partial, str) and partial:
                self.show_stream(partial)
                self.set_busy(True, f"NOKK sta scrivendo… {len(partial)} caratteri")
            status = job.get("status")
            if status == "complete":
                self.show_stream("")
                self.current_job_id = None
                return job
            if status == "cancelled":
                self.current_job_id = None
                raise CliError("Attività annullata.")
            if status == "failed":
                self.current_job_id = None
                raise CliError(
                    job.get("error") or "Attività fallita sul server.",
                    job.get("hint") or job.get("details"),
                )
            if status == "awaiting_approval":
                action = job.get("action") or {}
                action_id = action.get("id") if isinstance(action, dict) else None
                command = action.get("command") if isinstance(action, dict) else ""
                workspace = action.get("workspace") if isinstance(action, dict) else ""
                approved = self.auto_yes or await self.confirm_server(
                    command, workspace,
                )
                await asyncio.to_thread(
                    self.client.approve, job_id, action_id, approved,
                )
                self.write_system(
                    "Comando del server approvato." if approved
                    else "Comando del server rifiutato."
                )
                self.activity_log().write(
                    Text(
                        ("approvato" if approved else "rifiutato")
                        + f": {command}",
                        style="#3fb950" if approved else "#d29922",
                    )
                )
                continue
            await asyncio.sleep(POLL_INTERVAL)
        raise CliError(
            f"Attività non conclusa entro {self.job_timeout} secondi.",
        )

    async def _ask_screen(self, screen):
        """Aspetta la chiusura di una modale anche da un event handler."""
        future = asyncio.get_running_loop().create_future()

        def finish(result):
            if not future.done():
                future.set_result(result)

        self.push_screen(screen, callback=finish)
        try:
            return await future
        except asyncio.CancelledError:
            if not future.done():
                future.cancel()
            raise

    async def confirm_local(self, command):
        result = await self._ask_screen(ConfirmScreen(
            "Eseguire questo comando sul computer?",
            command,
            yes_label="Esegui",
        ))
        return bool(result)

    async def confirm_server(self, command, workspace):
        detail = command or "(comando non specificato)"
        if workspace:
            detail += f"\n\ndirectory: {workspace}"
        result = await self._ask_screen(ConfirmScreen(
            "NOKK vuole eseguire un comando sul server",
            detail,
            yes_label="Approva",
        ))
        return bool(result)

    # ------------------------------------------------------------------ comandi
    def on_input_submitted(self, event: Input.Submitted):
        value = event.value.strip()
        event.input.value = ""
        if not value or self.busy:
            return
        # Non bloccare il message pump: la richiesta può durare a lungo e
        # deve poter mostrare la modale di conferma mentre è in corso.
        self.run_worker(
            self.dispatch_input(value),
            group="chat",
            name="chat",
            exclusive=True,
        )

    async def dispatch_input(self, value):
        if value.startswith("/"):
            await self.handle_command(value)
        elif value.startswith("!"):
            await self.run_local_command(value[1:])
        else:
            await self.ask(value)

    async def handle_command(self, line):
        name, _, argument = line.partition(" ")
        name = name.lower()
        argument = argument.strip()
        if name in {"/exit", "/quit", "/q"}:
            self.exit()
        elif name in {"/help", "/?"}:
            self.push_screen(HelpScreen())
        elif name == "/new":
            self.new_chat()
        elif name == "/clear":
            self.query_one("#transcript", RichLog).clear()
        elif name == "/pwd":
            self.write_system(str(self.cwd))
        elif name == "/cd":
            await self.change_directory(argument)
        elif name in {"/run", "/sh"}:
            await self.run_local_command(argument)
        elif name == "/agent":
            if argument.lower() in {"on", "off"}:
                self.agent = argument.lower() == "on"
            else:
                self.agent = not self.agent
            self.save()
            self.write_system("Agente locale " + ("attivo." if self.agent else "disattivato."))
            self.refresh_widgets()
        elif name == "/mode":
            await self.change_mode(argument)
        elif name == "/url":
            self.change_url(argument)
        elif name == "/key":
            await self.change_key()
        elif name == "/settings":
            self.action_settings()
        elif name == "/server":
            await self.show_server()
        elif name == "/status":
            self.show_status()
        elif name == "/sessions":
            self.list_sessions()
        elif name == "/resume":
            self.resume_session(argument)
        elif name == "/rename":
            self.rename_session(argument)
        elif name == "/model":
            self.change_model(argument)
        elif name in {"/diff", "/git"}:
            self.show_git("diff" if name == "/diff" else argument)
        elif name == "/cancel":
            self.action_cancel_job()
        elif name == "/config":
            self.show_config()
        elif name == "/export":
            self.export_chat(argument)
        elif name == "/copy":
            self.copy_message(argument)
        elif name in {"/retry", "/again"}:
            await self.retry_last()
        else:
            self.write_system(f"Comando sconosciuto: {name}. Premi F1 per l'aiuto.")

    async def change_directory(self, argument):
        if not argument:
            self.write_system(str(self.cwd))
            return
        target = Path(argument).expanduser()
        if not target.is_absolute():
            target = self.cwd / target
        try:
            target = target.resolve()
        except OSError as error:
            self.write_error(CliError(str(error)))
            return
        if not target.is_dir():
            self.write_error(CliError(f"Directory non trovata: {target}"))
            return
        self.cwd = target
        self._branch = git_branch(self.cwd)
        self.write_system(f"Directory locale: {self.cwd}")
        self.refresh_widgets()

    async def change_mode(self, argument):
        if not argument:
            self.write_system(f"Modalità: {self.mode or 'predefinita'}")
            return
        try:
            self.mode = normalize_mode(argument)
        except CliError as error:
            self.write_error(error)
            return
        self.save()
        self.write_system(f"Modalità: {self.mode or 'predefinita'}")
        self.refresh_widgets()

    def change_url(self, argument):
        if not argument:
            self.write_system(self.client.base_url)
            return
        try:
            self.client.base_url = normalize_base_url(argument)
        except CliError as error:
            self.write_error(error)
            return
        self.profiles[self.profile] = {
            "url": self.client.base_url,
            "key": self.client.api_key,
        }
        self.save()
        self.write_system(f"Server: {self.client.base_url}")
        self.run_worker(self.check_health(), group="health")

    async def change_key(self):
        key = await self._ask_screen(SecretScreen())
        if key is None:
            return
        self.client.api_key = key
        self.profiles[self.profile]["key"] = key
        self.save()
        self.write_system(
            "Chiave aggiornata." if key else "Chiave rimossa: uso le rotte locali."
        )
        await self.check_health()

    async def show_server(self):
        try:
            data = await asyncio.to_thread(self.client.health)
        except CliError as error:
            self.write_error(error)
            return
        lines = "\n".join(f"{key}: {value}" for key, value in data.items())
        self.write_system("Stato del server\n" + lines)

    def show_config(self):
        self.write_system(
            f"server: {self.client.base_url}\n"
            f"api key: {mask_key(self.client.api_key)}\n"
            f"modalità: {self.mode or 'predefinita'}\n"
            f"agente: {'on' if self.agent else 'off'}\n"
            f"cwd: {self.cwd}\n"
            f"config: {self.config_path}"
        )

    def list_sessions(self):
        lines = []
        for index, chat in enumerate(self.chats[:MAX_SESSIONS], start=1):
            marker = "→" if index - 1 == self.active_index else " "
            count = sum(
                1 for message in chat.messages if not message.get("hidden")
            )
            when = time.strftime("%d/%m %H:%M", time.localtime(chat.created_at))
            lines.append(f"{marker} {index}. {chat.title} · {count} msg · {when}")
        self.write_system(
            "Sessioni salvate\n" + "\n".join(lines)
            + "\n\nUsa /resume <numero> per riaprirne una."
        )

    def resume_session(self, argument):
        try:
            number = int(argument)
        except (TypeError, ValueError):
            self.write_system("Uso: /resume <numero> (vedi /sessions)")
            return
        if not 1 <= number <= len(self.chats):
            self.write_system("Numero di sessione non valido.")
            return
        self.select_chat(number - 1)
        self.write_system(f"Sessione: {self.active_chat.title}")

    def rename_session(self, argument):
        title = (argument or "").strip()
        if not title:
            self.write_system("Uso: /rename <titolo>")
            return
        self.active_chat.title = title[:60]
        self.refresh_chat_list()
        self._persist_sessions()
        self.write_system(f"Sessione rinominata: {self.active_chat.title}")

    def change_model(self, argument):
        argument = (argument or "").strip()
        if not argument:
            current = self.model_override
            if current:
                self.write_system(
                    f"Modello sessione: {current['provider']}/{current['model']}\n"
                    "Usa /model reset per tornare al modello del server."
                )
            else:
                self.write_system(
                    "Modello del server: "
                    f"{self.health.get('provider') or '—'}/"
                    f"{self.health.get('model') or '—'}\n"
                    "Uso: /model <provider>/<modello>"
                )
            return
        if argument.lower() in {"reset", "auto", "server"}:
            self.model_override = None
            self.write_system("Modello della sessione: quello configurato sul server.")
            self.refresh_widgets()
            return
        provider, separator, model = argument.partition("/")
        provider, model = provider.strip(), model.strip()
        if not separator or not provider or not model:
            self.write_system("Uso: /model <provider>/<modello>")
            return
        self.model_override = {"provider": provider, "model": model}
        self.write_system(f"Modello della sessione: {provider}/{model}")
        self.refresh_widgets()

    def show_git(self, argument):
        mode = (argument or "").strip().lower()
        if mode in {"", "status", "st"}:
            code, output = git_output(self.cwd, ["status", "--short", "--branch"])
            title = "git status"
        elif mode in {"diff", "d", "staged", "--staged", "--cached"}:
            staged = mode in {"staged", "--staged", "--cached"}
            extra = ["--cached"] if staged else []
            code, summary = git_output(self.cwd, ["diff", "--stat", *extra])
            _, patch = git_output(self.cwd, ["diff", *extra])
            output = "\n".join(part for part in (summary, patch) if part)
            title = "git diff"
        elif mode == "log":
            code, output = git_output(self.cwd, ["log", "--oneline", "-10"])
            title = "git log"
        else:
            self.write_system("Uso: /diff [--staged] oppure /git status|diff|log")
            return
        if code != 0:
            self.write_error(CliError(output or "Comando Git non riuscito."))
            return
        self.transcript().write(
            Panel(
                Text(truncate(output or "(nessuna modifica)", 6000)),
                title=title,
                title_align="left",
                border_style="#8b949e",
                padding=(0, 1),
            )
        )

    def show_status(self):
        connection = "online" if self.online else ("offline" if self.online is False else "connessione…")
        turns = sum(
            1 for message in self.active_chat.messages
            if message.get("role") == "user" and not message.get("hidden")
        )
        latency = f"{self.last_latency * 1000:.0f} ms" if self.last_latency else "—"
        self.write_system(
            "Stato sessione\n"
            f"profilo: {self.profile}\n"
            f"server: {self.client.base_url} · {connection}\n"
            f"provider: {self.health.get('provider') or '—'}\n"
            f"modello: {self.health.get('model') or '—'}\n"
            f"api key: {mask_key(self.client.api_key) or '—'}\n"
            f"modalità: {self.mode or 'predefinita'}\n"
            f"agente: {'on' if self.agent else 'off'}\n"
            f"turni: {turns} · richieste: {self.requests} · latenza: {latency}\n"
            f"cwd: {self.cwd}\n"
            f"git: {self._branch or '—'}\n"
            f"config: {self.config_path}"
        )

    def chat_markdown(self):
        chat = self.active_chat
        lines = [
            f"# NOKK · {chat.title}",
            "",
            f"- Data: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"- Profilo: {self.profile}",
            f"- Server: {self.client.base_url}",
            f"- Modalità: {self.mode or 'predefinita'}",
            f"- Directory: {self.cwd}",
            "",
        ]
        for message in chat.messages:
            if message.get("hidden"):
                continue
            content = message.get("content")
            if not isinstance(content, str):
                continue
            if message.get("role") == "user":
                heading = "Tu"
            elif message.get("role") == "assistant":
                heading = "NOKK"
            else:
                continue
            lines.extend([f"## {heading}", "", content.rstrip() or "(vuoto)", ""])
        return "\n".join(lines).rstrip() + "\n"

    def copy_message(self, argument):
        argument = (argument or "").strip().lower()
        answers = [
            message.get("content") for message in self.active_chat.messages
            if message.get("role") == "assistant"
            and not message.get("hidden")
            and isinstance(message.get("content"), str)
            and message.get("content").strip()
        ]
        if argument == "all":
            text = self.chat_markdown()
            label = "transcript"
        else:
            if argument:
                try:
                    position = int(argument)
                except ValueError:
                    self.write_system("Uso: /copy [numero|all]")
                    return
                if position < 1:
                    self.write_system("Uso: /copy [numero|all]")
                    return
            else:
                position = 1
            if position > len(answers):
                self.write_system(
                    "Non c'è una risposta così vecchia da copiare."
                )
                return
            text = answers[-position]
            label = "risposta" if position == 1 else f"risposta {position}"
        native = native_clipboard_copy(text)
        try:
            self.copy_to_clipboard(text)
        except Exception as error:  # noqa: BLE001 - clipboard is terminal-specific
            if not native:
                self.write_error(CliError(f"Copia non riuscita: {error}"))
                return
        self.write_system(f"{label.capitalize()} copiato negli appunti.")
        self.activity_log().write(
            Text(f"copia: {label}", style="#3fb950")
        )

    def export_chat(self, argument):
        visible = [
            message for message in self.active_chat.messages
            if not message.get("hidden")
            and isinstance(message.get("content"), str)
            and message.get("role") in {"user", "assistant"}
        ]
        if not visible:
            self.write_system("Non c'è ancora niente da esportare.")
            return
        if argument:
            target = Path(argument).expanduser()
        else:
            target = Path(f"nokk-chat-{time.strftime('%Y%m%d-%H%M%S')}.md")
        if not target.is_absolute():
            target = self.cwd / target
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(self.chat_markdown(), encoding="utf-8")
        except OSError as error:
            self.write_error(CliError(f"Esportazione non riuscita: {error}"))
            return
        self.write_system(f"Chat esportata in {target}")
        self.activity_log().write(
            Text(f"export: {target}", style="#3fb950")
        )

    async def retry_last(self):
        if self.busy:
            self.notify("Attendi la risposta di NOKK.", severity="warning")
            return
        chat = self.active_chat
        index = None
        for position in range(len(chat.messages) - 1, -1, -1):
            message = chat.messages[position]
            if message.get("role") == "user" and not message.get("hidden"):
                index = position
                break
        if index is None:
            self.write_system("Nessuna domanda da ripetere.")
            return
        text = chat.messages[index].get("content") or ""
        if not text.strip():
            self.write_system("L'ultima domanda è vuota.")
            return
        del chat.messages[index:]
        self.messages = chat.messages
        self.render_chat()
        self.write_system("Ripeto l'ultima domanda…")
        self.activity_log().write(Text("retry dell'ultima domanda", style="#58a6ff"))
        await self.ask(text)

    def save(self):
        try:
            save_config(Config(
                base_url=self.client.base_url,
                api_key=self.client.api_key,
                mode=self.mode,
                agent=self.agent,
                profile=self.profile,
                local_url=self.profiles["local"]["url"],
                local_api_key=self.profiles["local"]["key"],
                hosting_url=self.profiles["hosting"]["url"],
                hosting_api_key=self.profiles["hosting"]["key"],
            ), self.config_path)
        except CliError as error:
            self.write_error(error)

    async def check_health(self):
        try:
            data = await asyncio.to_thread(self.client.health)
        except CliError as error:
            self.online = False
            self.health = {}
            self.write_system(f"Server non raggiungibile: {error}")
            self.refresh_widgets()
            return
        self.online = True
        self.health = data
        self.refresh_widgets()
        provider = data.get("provider")
        if provider:
            self.write_system(
                f"Connesso a {self.client.base_url} · {provider}"
                + (f" · {data.get('model')}" if data.get("model") else "")
            )

    def action_quit(self):
        self.exit()


def run_tui(config, config_path, *, auto_yes=False, job_timeout=JOB_TIMEOUT, cwd=None):
    app = NokkTuiApp(
        config,
        config_path,
        auto_yes=auto_yes,
        job_timeout=job_timeout,
        cwd=cwd,
    )
    app.run()
    return 0
