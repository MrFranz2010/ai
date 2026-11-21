"""Client HTTP per l'API pubblica di NOKK.

Usa solo la libreria standard: il dock non aggiunge dipendenze al repository.
Le funzioni di composizione del payload e di traduzione degli errori sono pure,
così i test possono verificarle senza rete.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

API_PREFIX = "/api/v1"
MAX_MESSAGE_CHARS = 12_000
IMAGE_MIME_TYPES = ("image/png", "image/jpeg", "image/webp", "image/gif")


class NokkError(Exception):
    """Errore leggibile mostrato nel dock."""

    def __init__(self, message, status=None):
        super().__init__(message)
        self.message = message
        self.status = status


def build_messages(text, image=None, history=None):
    """Compone la lista `messages` accettata da `POST /api/v1/chat`."""
    messages = []
    for turn in history or []:
        role = turn.get("role")
        content = turn.get("content")
        if role in ("user", "assistant") and isinstance(content, str) and content.strip():
            messages.append({"role": role, "content": content[:MAX_MESSAGE_CHARS]})
    question = (text or "").strip() or "Descrivi questa immagine."
    user_message = {"role": "user", "content": question[:MAX_MESSAGE_CHARS]}
    if image:
        mime_type = image.get("mime_type") or "image/png"
        if mime_type not in IMAGE_MIME_TYPES:
            raise NokkError("Formato immagine non supportato da NOKK.")
        user_message["attachments"] = [{
            "kind": "image",
            "name": image.get("name") or "screenshot.png",
            "mime_type": mime_type,
            "data": image.get("data") or "",
        }]
    messages.append(user_message)
    return messages


def error_message(status, payload=None):
    """Traduce lo stato HTTP e il corpo JSON in un messaggio per l'utente."""
    detail = ""
    if isinstance(payload, dict):
        detail = str(payload.get("error") or payload.get("detail") or "").strip()
    if status == 401:
        return "Chiave API non valida. Creala in NOKK → Impostazioni → API."
    if status == 403:
        return "L'API di NOKK è disattivata. Attivala in NOKK → Impostazioni → API."
    if status == 404:
        return detail or "Richiesta non trovata su NOKK."
    if status == 409:
        return detail or "Configura provider e chiave AI in NOKK prima di chiedere."
    if status == 429:
        return "Troppe richieste: NOKK accetta 60 chiamate al minuto. Riprova tra poco."
    if status in (502, 503):
        return detail or "Il provider AI di NOKK non è disponibile in questo momento."
    if status == 400:
        return detail or "La richiesta non è valida."
    if status >= 500:
        return detail or f"NOKK ha risposto con un errore interno ({status})."
    return detail or f"NOKK ha risposto {status}."


def default_transport(method, url, headers, body, timeout):
    """Esegue la richiesta HTTP e restituisce (stato, corpo)."""
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status), response.read()
    except urllib.error.HTTPError as error:
        try:
            return int(error.code), error.read()
        finally:
            error.close()


class NokkClient:
    """Client sincrono; il dock lo chiama da un thread secondario."""

    def __init__(
        self,
        base_url,
        api_key,
        mode="",
        timeout=240,
        transport=None,
        poll_interval=0.7,
        sleep=time.sleep,
        clock=time.monotonic,
    ):
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key or ""
        self.mode = mode or ""
        self.timeout = timeout
        self.transport = transport or default_transport
        self.poll_interval = poll_interval
        self.sleep = sleep
        self.clock = clock

    # -- interni ---------------------------------------------------------
    def _url(self, path):
        if not self.base_url:
            raise NokkError("Indica l'indirizzo di NOKK nelle impostazioni del dock.")
        return f"{self.base_url}{API_PREFIX}{path}"

    def _request(self, method, path, payload=None, timeout=None, authenticated=True):
        url = self._url(path)
        headers = {"Accept": "application/json", "User-Agent": "nokk-dock/1.0"}
        body = None
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if authenticated and self.api_key:
            headers["X-API-Key"] = self.api_key
        try:
            status, raw = self.transport(
                method, url, headers, body, timeout or min(30, self.timeout)
            )
        except urllib.error.URLError as error:
            reason = getattr(error, "reason", error)
            raise NokkError(
                f"NOKK non è raggiungibile su {self.base_url} ({reason}). "
                "Avvia NOKK con «python linux_start.py»."
            ) from None
        except TimeoutError:
            raise NokkError("NOKK non ha risposto in tempo.") from None
        except OSError as error:
            raise NokkError(f"Connessione a NOKK non riuscita ({error}).") from None
        try:
            data = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            data = {}
        if status >= 400:
            raise NokkError(error_message(status, data), status=status)
        return data if isinstance(data, dict) else {}

    # -- API -------------------------------------------------------------
    def health(self):
        """Stato del servizio; `None` se non raggiungibile."""
        try:
            return self._request("GET", "/health", authenticated=False, timeout=6)
        except NokkError:
            return None

    def ask(self, text, image=None, history=None, on_status=None):
        """Invia la domanda e attende la risposta completa del job."""
        messages = build_messages(text, image=image, history=history)
        payload = {"messages": messages}
        if self.mode:
            payload["mode"] = self.mode
        started = self.clock()
        response = self._request("POST", "/chat", payload=payload, timeout=min(30, self.timeout))
        job_id = response.get("job_id")
        if not job_id:
            reply = response.get("reply")
            if reply:
                return {"reply": reply, "tool_events": response.get("tool_events") or []}
            raise NokkError("NOKK non ha avviato la richiesta.")
        return self.wait_job(job_id, on_status=on_status, deadline=started + self.timeout)

    def wait_job(self, job_id, on_status=None, deadline=None, cancelled=None):
        deadline = deadline or (self.clock() + self.timeout)
        last_partial = ""
        while self.clock() < deadline:
            if cancelled is not None and cancelled():
                raise NokkError("Richiesta annullata.")
            job = self._request("GET", f"/jobs/{job_id}", timeout=20)
            status = job.get("status")
            if status == "complete":
                return {
                    "reply": job.get("reply") or "",
                    "tool_events": job.get("tool_events") or [],
                }
            if status == "failed":
                raise NokkError(job.get("error") or "NOKK non è riuscito a rispondere.")
            if status == "cancelled":
                raise NokkError("Richiesta annullata.")
            if status == "awaiting_approval":
                raise NokkError(
                    "NOKK attende l'approvazione di un comando: aprilo nel browser "
                    "per confermare, poi riprova."
                )
            partial = job.get("partial_reply") or ""
            if partial and partial != last_partial:
                last_partial = partial
                if on_status:
                    on_status(partial, status)
            elif on_status and status == "running":
                on_status(last_partial, status)
            self.sleep(self.poll_interval)
        raise NokkError(
            "NOKK non ha risposto entro il tempo massimo. "
            "Controlla la pagina di NOKK per lo stato dell'attività."
        )

    def cancel(self, job_id):
        try:
            self._request("POST", f"/jobs/{job_id}/cancel", payload={})
        except NokkError:
            pass
