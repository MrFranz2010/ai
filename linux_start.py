import json
import re
import threading
import time
from http.server import ThreadingHTTPServer

import app


CHAT_FILE = app.CONFIG_FILE.with_name("chats.json")
CHAT_LOCK = threading.Lock()
CHAT_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")
MAX_CHATS = 100
MAX_MESSAGES_PER_CHAT = 500


def validate_chats(chats):
    if not isinstance(chats, list) or len(chats) > MAX_CHATS:
        raise ValueError(f"Puoi conservare al massimo {MAX_CHATS} conversazioni.")
    clean_chats = []
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
        if not isinstance(messages, list) or len(messages) > MAX_MESSAGES_PER_CHAT:
            raise ValueError("La conversazione supera il limite di messaggi.")
        clean_messages = []
        for message in messages:
            if (
                not isinstance(message, dict)
                or message.get("role") not in {"user", "assistant"}
                or not isinstance(message.get("content"), str)
                or len(message["content"]) > 12000
            ):
                raise ValueError("Messaggio conversazione non valido.")
            clean_messages.append({"role": message["role"], "content": message["content"]})
        seen_ids.add(chat_id)
        clean_chats.append({
            "id": chat_id,
            "title": title,
            "updated_at": updated_at,
            "messages": clean_messages,
        })
    return sorted(clean_chats, key=lambda item: item["updated_at"], reverse=True)


def load_chats():
    try:
        with CHAT_FILE.open("r", encoding="utf-8") as state_file:
            saved = json.load(state_file)
    except FileNotFoundError:
        return []
    return validate_chats(saved)


def save_chats(chats):
    clean = validate_chats(chats)
    app.save_json_file(CHAT_FILE, clean)
    return clean


class LocalAppHandler(app.AppHandler):
    def _send_static(self, filename, content_type):
        try:
            body = (app.APP_DIR / "web" / filename).read_bytes()
        except OSError:
            self._send_json(404, {"error": "Risorsa interfaccia non disponibile."})
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            try:
                body = (app.APP_DIR / "web" / "index.html").read_bytes()
                insert = (
                    b'<link rel="stylesheet" href="/chat-history.css">'
                    b'<script src="/chat-history.js" defer></script>'
                )
                body = body.replace(b"</head>", insert + b"</head>")
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
                "connect-src 'self'; base-uri 'none'; frame-ancestors 'none'",
            )
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/chat-history.js":
            self._send_static("chat-history.js", "text/javascript; charset=utf-8")
            return
        if self.path == "/chat-history.css":
            self._send_static("chat-history.css", "text/css; charset=utf-8")
            return
        if self.path == "/api/chats":
            try:
                with CHAT_LOCK:
                    chats = load_chats()
                self._send_json(200, {"chats": chats})
            except Exception as error:
                print(f"Unable to load chats: {error}")
                self._send_json(500, {"error": "Impossibile caricare le conversazioni."})
            return
        super().do_GET()

    def do_POST(self):
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
                        if len(chats) >= MAX_CHATS:
                            raise ValueError(f"Hai raggiunto il limite di {MAX_CHATS} conversazioni.")
                        chats.append(replacement)
                    else:
                        chats[index] = replacement
                    self._send_json(200, {"chats": save_chats(chats)})
                    return
                if action == "delete":
                    chat_id = data.get("id")
                    if not isinstance(chat_id, str) or not CHAT_ID_PATTERN.fullmatch(chat_id):
                        raise ValueError("Identificativo conversazione non valido.")
                    chats = [chat for chat in chats if chat["id"] != chat_id]
                    self._send_json(200, {"chats": save_chats(chats)})
                    return
                raise ValueError("Azione conversazione non valida.")
        except ValueError as error:
            self._send_json(400, {"error": str(error)})
        except Exception as error:
            print(f"Unable to save chats: {error}")
            self._send_json(500, {"error": "Impossibile salvare le conversazioni."})


if __name__ == "__main__":
    app.start_telegram_polling()
    print(f"Apri http://{app.HOST}:{app.PORT} nel browser.")
    ThreadingHTTPServer((app.HOST, app.PORT), LocalAppHandler).serve_forever()
