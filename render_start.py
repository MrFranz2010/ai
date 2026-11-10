import base64
import binascii
import hmac
import json
import os
import re
import threading
from http.server import ThreadingHTTPServer

import app
import user_memory
from search import make_document
from supabase_store import MISSING, SupabaseJSONStore


USERNAME = os.environ.get("APP_USERNAME", "")
PASSWORD = os.environ.get("APP_PASSWORD", "")
CHAT_FILE = app.CONFIG_FILE.with_name("chats.json")
MEMORY_FILE = app.CONFIG_FILE.with_name("memories.json")
CHAT_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")
CHAT_LOCK = threading.Lock()

if not USERNAME or ":" in USERNAME:
    raise SystemExit("Set APP_USERNAME to a non-empty name without ':'.")
if len(PASSWORD) < 16:
    raise SystemExit("Set APP_PASSWORD to a password of at least 16 characters.")


def config_from_state(saved):
    """Validate the configuration document stored in Supabase."""
    if not isinstance(saved, dict):
        raise RuntimeError("Supabase config.json must contain a JSON object.")
    workspace = saved.get("workspace", str(app.APP_DIR))
    if not isinstance(workspace, str) or not os.path.isdir(os.path.expanduser(workspace)):
        workspace = str(app.APP_DIR)
    try:
        return app.validate_config(
            saved.get("provider"), saved.get("model"), saved.get("api_key"),
            saved.get("terminal_enabled", False),
            saved.get("approval_mode", "manual"), workspace,
            saved.get("system_prompt", ""), saved.get("wake_phrase", "Nok"),
            saved.get("transcribe_model", ""),
            saved.get("wake_window_seconds", app.WAKE_WINDOW_DEFAULT),
            saved.get("tts_auto_play", False),
            saved.get("api_keys", {}),
            saved.get("notifications_enabled", False),
            base_url=saved.get("base_url", ""),
            models=saved.get("models", {}),
            weather_enabled=saved.get("weather_enabled", False),
            weather_city=saved.get("weather_city", ""),
            alerts_enabled=saved.get("alerts_enabled", False),
            alerts_disk_percent=saved.get("alerts_disk_percent", 90),
            alerts_memory_percent=saved.get("alerts_memory_percent", 92),
        )
    except ValueError as error:
        raise RuntimeError(f"Supabase configuration is invalid: {error}") from error


def _configure_supabase_storage():
    storage = SupabaseJSONStore.from_environment()
    if storage is None:
        print("Supabase storage is not configured; using local JSON files.")
        return None

    def load_json(path):
        value = storage.load(path.name)
        if value is not MISSING:
            return value
        try:
            with path.open("r", encoding="utf-8") as state_file:
                value = json.load(state_file)
        except FileNotFoundError:
            return MISSING
        storage.save(path.name, value)
        print(f"Imported existing {path.name} into Supabase.")
        return value

    def save_json(path, data):
        storage.save(path.name, data)

    def load_config():
        saved = load_json(app.CONFIG_FILE)
        if saved is MISSING:
            return app.default_config()
        return config_from_state(saved)

    def load_workflows():
        saved = load_json(app.WORKFLOWS_FILE)
        if saved is MISSING:
            return []
        try:
            return app.validate_workflows(saved)
        except ValueError as error:
            raise RuntimeError(f"Supabase workflows are invalid: {error}") from error

    def load_planner():
        saved = load_json(app.PLANNER_FILE)
        if saved is MISSING:
            return app.default_planner()
        try:
            return app.validate_planner(saved)
        except ValueError as error:
            raise RuntimeError(f"Supabase planner data is invalid: {error}") from error

    def load_api():
        saved = load_json(app.API_FILE)
        if saved is MISSING:
            return app.default_api_config()
        try:
            return app.validate_api_config(saved)
        except ValueError as error:
            raise RuntimeError(f"Supabase api.json is invalid: {error}") from error

    def load_google_calendar():
        saved = load_json(app.GOOGLE_CALENDAR_FILE)
        if saved is MISSING:
            return app.default_google_calendar()
        try:
            return app.validate_google_calendar(saved)
        except ValueError as error:
            raise RuntimeError(
                f"Supabase google_calendar.json is invalid: {error}"
            ) from error

    def load_telegram():
        saved = load_json(app.TELEGRAM_FILE)
        if saved is MISSING:
            return {
                "token": None, "bot_username": None,
                "authorized_chats": [], "offset": 0,
                **app.default_telegram_reminder(),
            }
        if not isinstance(saved, dict):
            raise RuntimeError("Supabase telegram.json must contain a JSON object.")
        if saved.get("token") is None:
            if (
                saved.get("bot_username") is not None
                or saved.get("authorized_chats") != []
                or saved.get("offset", 0) != 0
            ):
                raise RuntimeError("Supabase Telegram configuration is invalid.")
            try:
                reminder = app.normalize_telegram_reminder(saved)
            except ValueError as error:
                raise RuntimeError(
                    "Supabase Telegram configuration is invalid."
                ) from error
            return {
                "token": None, "bot_username": None,
                "authorized_chats": [], "offset": 0,
                **reminder,
            }
        if (
            not isinstance(saved.get("token"), str)
            or not app.TELEGRAM_TOKEN_PATTERN.fullmatch(saved["token"])
            or not isinstance(saved.get("bot_username"), str)
            or not isinstance(saved.get("authorized_chats"), list)
            or any(
                not isinstance(chat_id, str)
                or not re.fullmatch(r"-?[0-9]+", chat_id)
                for chat_id in saved["authorized_chats"]
            )
            or not isinstance(saved.get("offset", 0), int)
            or isinstance(saved.get("offset", 0), bool)
            or saved.get("offset", 0) < 0
        ):
            raise RuntimeError("Supabase Telegram configuration is invalid.")
        try:
            reminder = app.normalize_telegram_reminder(saved)
        except ValueError as error:
            raise RuntimeError(
                "Supabase Telegram configuration is invalid."
            ) from error
        return {
            "token": saved["token"],
            "bot_username": saved["bot_username"],
            "authorized_chats": list(dict.fromkeys(saved["authorized_chats"])),
            "offset": saved.get("offset", 0),
            **reminder,
        }

    app.config = load_config()
    app.workflows[:] = load_workflows()
    app.planner.clear()
    app.planner.update(load_planner())
    app.telegram_config.clear()
    app.telegram_config.update(load_telegram())
    app.google_calendar_config.clear()
    app.google_calendar_config.update(load_google_calendar())
    app.api_config.clear()
    app.api_config.update(load_api())
    app.save_json_file = save_json
    app.save_config_file = lambda data: save_json(app.CONFIG_FILE, data)
    app.save_telegram_file = lambda data: save_json(app.TELEGRAM_FILE, data)
    app.save_google_calendar_file = lambda data: save_json(
        app.GOOGLE_CALENDAR_FILE, data
    )
    app.save_api_file = lambda data: save_json(app.API_FILE, data)
    return storage


CHAT_STORAGE = _configure_supabase_storage()


def load_memories():
    if CHAT_STORAGE is not None:
        saved = CHAT_STORAGE.load("memories.json")
        if saved is MISSING:
            return []
        return user_memory.validate_memories(saved)
    try:
        with MEMORY_FILE.open("r", encoding="utf-8") as memory_file:
            saved = json.load(memory_file)
    except FileNotFoundError:
        return []
    return user_memory.validate_memories(saved)


def save_memories(memories):
    validated = user_memory.validate_memories(memories)
    if CHAT_STORAGE is not None:
        CHAT_STORAGE.save("memories.json", validated)
    else:
        app.save_json_file(MEMORY_FILE, validated)
    return validated


def validate_chat_artifacts(artifacts):
    if not isinstance(artifacts, list) or len(artifacts) > 10:
        raise ValueError("Allegati conversazione non validi.")
    safe = []
    for artifact in artifacts:
        if (
            not isinstance(artifact, dict)
            or not isinstance(artifact.get("filename"), str)
            or not artifact["filename"]
            or len(artifact["filename"]) > 200
            or not isinstance(artifact.get("mime_type"), str)
            or len(artifact["mime_type"]) > 100
            or not isinstance(artifact.get("bytes"), int)
            or isinstance(artifact.get("bytes"), bool)
            or artifact["bytes"] < 0
            or not isinstance(artifact.get("url"), str)
            or not re.fullmatch(r"/api/exports/[a-f0-9]{32}", artifact["url"])
        ):
            raise ValueError("Allegato conversazione non valido.")
        safe.append({
            "filename": artifact["filename"],
            "mime_type": artifact["mime_type"],
            "bytes": artifact["bytes"],
            "url": artifact["url"],
        })
    return safe


def validate_chats(chats):
    if not isinstance(chats, list) or len(chats) > 100:
        raise ValueError("Puoi conservare al massimo 100 conversazioni.")
    validated = []
    seen_ids = set()
    for chat in chats:
        if not isinstance(chat, dict):
            raise ValueError("Formato conversazione non valido.")
        chat_id = chat.get("id")
        title = chat.get("title")
        updated_at = chat.get("updated_at")
        messages = chat.get("messages")
        if not isinstance(chat_id, str) or not CHAT_ID_PATTERN.fullmatch(chat_id):
            raise ValueError("Identificativo conversazione non valido.")
        if chat_id in seen_ids:
            raise ValueError("Gli identificativi delle conversazioni devono essere unici.")
        if not isinstance(title, str) or len(title) > 120:
            raise ValueError("Titolo conversazione non valido.")
        if not isinstance(updated_at, (int, float)) or isinstance(updated_at, bool):
            raise ValueError("Data conversazione non valida.")
        if not isinstance(messages, list) or len(messages) > 500:
            raise ValueError("La conversazione supera il limite di messaggi.")
        safe_messages = []
        for message in messages:
            if (
                not isinstance(message, dict)
                or message.get("role") not in {"user", "assistant"}
                or not isinstance(message.get("content"), str)
                or len(message["content"]) > 12000
            ):
                raise ValueError("Messaggio conversazione non valido.")
            safe_message = {"role": message["role"], "content": message["content"]}
            artifacts = message.get("artifacts")
            if artifacts is not None:
                safe_message["artifacts"] = validate_chat_artifacts(artifacts)
            safe_messages.append(safe_message)
        seen_ids.add(chat_id)
        validated.append({
            "id": chat_id, "title": title, "updated_at": updated_at,
            "messages": safe_messages,
        })
    return sorted(validated, key=lambda chat: chat["updated_at"], reverse=True)


def load_chats():
    if CHAT_STORAGE is not None:
        saved = CHAT_STORAGE.load("chats.json")
        if saved is MISSING:
            try:
                with CHAT_FILE.open("r", encoding="utf-8") as state_file:
                    saved = json.load(state_file)
            except FileNotFoundError:
                return []
            CHAT_STORAGE.save("chats.json", saved)
            print("Imported existing chats.json into Supabase.")
    else:
        try:
            with CHAT_FILE.open("r", encoding="utf-8") as state_file:
                saved = json.load(state_file)
        except FileNotFoundError:
            return []
    return validate_chats(saved)


def save_chats(chats):
    validated = validate_chats(chats)
    if CHAT_STORAGE is not None:
        CHAT_STORAGE.save("chats.json", validated)
    else:
        app.save_json_file(CHAT_FILE, validated)
    return validated


class AuthenticatedAppHandler(app.AppHandler):
    def _is_authenticated(self):
        authorization = self.headers.get("Authorization", "")
        scheme, separator, encoded = authorization.partition(" ")
        if not separator or scheme.lower() != "basic":
            return False
        try:
            credentials = base64.b64decode(encoded, validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError, ValueError):
            return False
        username, separator, password = credentials.partition(":")
        if not separator:
            return False
        return hmac.compare_digest(
            username.encode("utf-8"), USERNAME.encode("utf-8")
        ) and hmac.compare_digest(
            password.encode("utf-8"), PASSWORD.encode("utf-8")
        )

    def _require_authentication(self):
        if self._is_authenticated():
            return True
        body = b"Authentication required.\n"
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="NOKK", charset="UTF-8"')
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
        return False

    def _send_chat_script(self):
        try:
            body = (app.APP_DIR / "web" / "chat-history.js").read_bytes()
        except OSError:
            self._send_json(404, {"error": "Script cronologia chat non disponibile."})
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/javascript; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _send_user_memory_script(self):
        try:
            body = (app.APP_DIR / "web" / "user-memory.js").read_bytes()
        except OSError:
            self._send_json(404, {"error": "Script memoria non disponibile."})
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/javascript; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _send_home(self):
        try:
            body = (app.APP_DIR / "web" / "index.html").read_bytes()
            body = body.replace(
                b"</head>",
                b'<script src="/chat-history.js" defer></script>'
                b'<script src="/user-memory.js" defer></script></head>',
            )
        except OSError:
            self._send_json(500, {"error": "Interfaccia web non disponibile."})
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'self'; script-src 'self'; "
            "connect-src 'self'; media-src 'self' https: http: blob:; "
            "base-uri 'none'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        # Google redirects the browser here without Basic credentials; the
        # single-use OAuth state ties the callback to an authenticated start.
        path = self.path.split("?", 1)[0]
        if path != "/oauth/google/callback" and not path.startswith(
            app.API_PREFIX
        ):
            # /api/v1/* carries its own key instead of the browser password.
            if not self._require_authentication():
                return
        if self.path == "/":
            self._send_home()
            return
        if self.path == "/chat-history.js":
            self._send_chat_script()
            return
        if self.path == "/user-memory.js":
            self._send_user_memory_script()
            return
        if self.path == "/api/chats":
            try:
                with CHAT_LOCK:
                    chats = load_chats()
                self._send_json(200, {"chats": chats})
            except Exception as error:
                print(f"Unable to load chats: {error}")
                self._send_json(502, {"error": "Impossibile caricare le conversazioni."})
            return
        super().do_GET()

    def do_POST(self):
        if not self.path.startswith(app.API_PREFIX):
            if not self._require_authentication():
                return
        if self.path != "/api/chats":
            super().do_POST()
            return
        try:
            data = self._read_json()
            if not isinstance(data, dict):
                raise ValueError("La richiesta deve essere un oggetto JSON.")
            action = data.get("action")
            with CHAT_LOCK:
                chats = load_chats()
                if action == "save":
                    chat = data.get("chat")
                    if not isinstance(chat, dict):
                        raise ValueError("Conversazione non valida.")
                    chat_id = chat.get("id")
                    if not isinstance(chat_id, str) or not CHAT_ID_PATTERN.fullmatch(chat_id):
                        raise ValueError("Identificativo conversazione non valido.")
                    replacement = validate_chats([chat])[0]
                    index = next((i for i, item in enumerate(chats) if item["id"] == chat_id), None)
                    if index is None:
                        if len(chats) >= 100:
                            raise ValueError("Hai raggiunto il limite di 100 conversazioni.")
                        chats.append(replacement)
                    else:
                        chats[index] = replacement
                    chats = save_chats(chats)
                    self._send_json(200, {"chats": chats})
                    return
                if action == "delete":
                    chat_id = data.get("id")
                    if not isinstance(chat_id, str) or not CHAT_ID_PATTERN.fullmatch(chat_id):
                        raise ValueError("Identificativo conversazione non valido.")
                    chats = [chat for chat in chats if chat["id"] != chat_id]
                    chats = save_chats(chats)
                    self._send_json(200, {"chats": chats})
                    return
                raise ValueError("Azione conversazione non valida.")
        except ValueError as error:
            self._send_json(400, {"error": str(error)})
        except Exception as error:
            print(f"Unable to save chats: {error}")
            self._send_json(502, {"error": "Impossibile salvare le conversazioni."})


def collect_chat_search_documents():
    """Saved conversations are searchable too on the hosted branch."""
    try:
        with CHAT_LOCK:
            chats = load_chats()
    except Exception:  # noqa: BLE001 - search must not break on storage
        return []
    documents = []
    for chat in chats[:100]:
        text = "\n".join(
            message.get("content", "") for message in chat["messages"][-12:]
        )
        documents.append(
            make_document("chat", chat["id"], chat["title"], text)
        )
    return documents


app.search_extra_provider = collect_chat_search_documents

user_memory.install(app, AuthenticatedAppHandler, load_memories, save_memories)


if __name__ == "__main__":
    app.HOST = "0.0.0.0"
    app.PORT = int(os.environ.get("PORT", "10000"))
    app.start_telegram_polling()
    app.start_workflow_scheduler()
    print("Web search: " + ", ".join(app.search_providers()), flush=True)
    print(f"NOKK listening on {app.HOST}:{app.PORT}", flush=True)
    ThreadingHTTPServer((app.HOST, app.PORT), AuthenticatedAppHandler).serve_forever()
