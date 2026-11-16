"""Aggiornamenti di NOKK dal repository Git, senza merge automatici.

Il controllo confronta HEAD con il branch remoto, applica solo fast-forward e
rifiuta di toccare un worktree con modifiche locali. Non gestisce credenziali:
usa quelle già configurate per Git e non apre prompt interattivi.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

DEFAULT_REMOTE = "origin"
DEFAULT_BRANCH = "main"
FETCH_TIMEOUT = 8
GIT_TIMEOUT = 15
DEPENDENCY_FILES = {"requirements.txt", "requirements-tui.txt"}


class UpdateError(RuntimeError):
    """Errore mostrabile all'utente durante il controllo o l'aggiornamento."""


@dataclass(frozen=True)
class UpdateStatus:
    root: str
    branch: str
    remote: str
    local_sha: str
    remote_sha: str
    behind: int
    ahead: int
    dirty: bool
    changed_files: tuple[str, ...]
    commits: tuple[str, ...]

    @property
    def available(self):
        return self.behind > 0

    @property
    def requirements_changed(self):
        return any(
            name in DEPENDENCY_FILES for name in self.changed_files
        )


@dataclass(frozen=True)
class UpdateResult:
    branch: str
    previous_sha: str
    new_sha: str
    changed_files: tuple[str, ...]
    requirements_changed: bool


def _git(root, *arguments, timeout=GIT_TIMEOUT):
    environment = os.environ.copy()
    environment["GIT_TERMINAL_PROMPT"] = "0"
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=environment,
            check=False,
        )
    except FileNotFoundError:
        raise UpdateError("Git non è installato: impossibile aggiornare NOKK.") from None
    except subprocess.TimeoutExpired:
        raise UpdateError("Git non ha risposto in tempo.") from None
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        detail = detail.splitlines()[-1] if detail else "errore sconosciuto"
        raise UpdateError(f"Git non ha completato l'operazione: {detail}")
    return completed.stdout.strip()


def find_repository(start=None):
    """Restituisce la radice del repository Git che contiene NOKK."""
    base = Path(start or Path(__file__).resolve().parent)
    try:
        root = _git(base, "rev-parse", "--show-toplevel")
    except UpdateError:
        raise UpdateError(
            "NOKK non è dentro un repository Git: aggiornamento non disponibile."
        ) from None
    if not root:
        raise UpdateError("Radice del repository Git non trovata.")
    return root


def current_branch(root):
    try:
        branch = _git(root, "symbolic-ref", "--quiet", "--short", "HEAD")
    except UpdateError:
        raise UpdateError(
            "HEAD non è su un branch: aggiornamento automatico non disponibile."
        ) from None
    if not branch:
        raise UpdateError(
            "HEAD non è su un branch: aggiornamento automatico non disponibile."
        )
    return branch


def current_sha(root):
    return _git(root, "rev-parse", "HEAD")


def _remote_exists(root, remote):
    try:
        _git(root, "remote", "get-url", remote)
    except UpdateError:
        raise UpdateError(
            f"Il remote Git «{remote}» non è configurato."
        ) from None


def _fetch(root, remote, branch):
    _git(
        root,
        "fetch",
        "--quiet",
        "--no-tags",
        remote,
        branch,
        timeout=FETCH_TIMEOUT,
    )
    return _git(root, "rev-parse", "FETCH_HEAD")


def check_for_update(start=None, remote=DEFAULT_REMOTE, branch=None):
    """Confronta la copia locale con il branch remoto senza modificarla."""
    root = find_repository(start)
    _remote_exists(root, remote)
    branch = branch or current_branch(root)
    local_sha = current_sha(root)
    dirty = bool(_git(root, "status", "--porcelain", "--untracked-files=no"))
    remote_sha = _fetch(root, remote, branch)
    counts = _git(
        root, "rev-list", "--left-right", "--count",
        f"HEAD...{remote_sha}",
    ).split()
    if len(counts) != 2:
        raise UpdateError("Git ha restituito un confronto non valido.")
    ahead, behind = (int(counts[0]), int(counts[1]))
    changed = _git(
        root, "diff", "--name-only", f"HEAD..{remote_sha}",
    )
    log = _git(
        root, "log", "--format=%h%x09%s", "-n", "8", f"HEAD..{remote_sha}",
    )
    return UpdateStatus(
        root=root,
        branch=branch,
        remote=remote,
        local_sha=local_sha,
        remote_sha=remote_sha,
        behind=behind,
        ahead=ahead,
        dirty=dirty,
        changed_files=tuple(
            line for line in changed.splitlines() if line.strip()
        ),
        commits=tuple(
            line for line in log.splitlines() if line.strip()
        ),
    )


def apply_update(status, repo=None):
    """Applica un fast-forward già verificato, senza creare merge."""
    if not isinstance(status, UpdateStatus):
        raise UpdateError("Stato dell'aggiornamento non valido.")
    if status.dirty:
        raise UpdateError(
            "Ci sono modifiche locali non salvate: aggiornamento annullato."
        )
    if status.ahead:
        raise UpdateError(
            "Il branch locale ha commit che non sono sul remoto: "
            "aggiornamento annullato per non perdere lavoro."
        )
    if not status.available:
        raise UpdateError("Nessun aggiornamento da applicare.")
    root = find_repository(repo or status.root)
    if current_sha(root) != status.local_sha:
        raise UpdateError(
            "Il repository è cambiato durante il controllo: riprova."
        )
    _git(root, "merge", "--ff-only", status.remote_sha)
    return UpdateResult(
        branch=status.branch,
        previous_sha=status.local_sha,
        new_sha=current_sha(root),
        changed_files=status.changed_files,
        requirements_changed=status.requirements_changed,
    )


def auto_update(
    notify=None, start=None, remote=DEFAULT_REMOTE, branch=None,
    restart_required=True,
):
    """Controlla e applica un aggiornamento sicuro all'avvio.

    Disattivabile con ``NOKK_AUTO_UPDATE=0``. Gli errori di rete non bloccano
    l'avvio e non vengono mostrati come errori fatali.
    """
    notify = notify or (lambda _message: None)
    if os.environ.get("NOKK_AUTO_UPDATE", "").lower() in {"0", "false", "off", "no"}:
        return None
    try:
        status = check_for_update(start, remote=remote, branch=branch)
    except UpdateError:
        return None
    if not status.available:
        return status
    if status.dirty:
        notify(
            "Aggiornamento NOKK disponibile, ma ci sono modifiche locali: "
            "salta. Usa /update dopo averle messe da parte."
        )
        return status
    if status.ahead:
        notify(
            "Aggiornamento NOKK disponibile, ma il branch locale ha commit "
            "non pubblicati: salta per non perdere lavoro."
        )
        return status
    if status.requirements_changed:
        notify(
            "Aggiornamento NOKK disponibile, ma cambia le dipendenze: "
            "salta. Usa /update, reinstalla i requirements e riavvia."
        )
        return status
    try:
        result = apply_update(status)
    except UpdateError as error:
        notify(f"Aggiornamento NOKK non riuscito: {error}")
        return status
    notify(
        f"NOKK aggiornato da {result.previous_sha[:8]} a "
        f"{result.new_sha[:8]} ({len(result.changed_files)} file)."
    )
    if result.requirements_changed:
        notify(
            "Le dipendenze sono cambiate: esegui "
            "python -m pip install -r requirements.txt "
            "(e requirements-tui.txt per la TUI)."
        )
    if restart_required:
        notify("Riavvia NOKK per usare la nuova versione.")
    return result
