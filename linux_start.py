import json
from pathlib import Path

import app
from user_memory import install, validate_memories


MEMORY_FILE = app.CONFIG_FILE.with_name("memories.json")


def load_memories():
    try:
        with MEMORY_FILE.open("r", encoding="utf-8") as memory_file:
            saved = json.load(memory_file)
    except FileNotFoundError:
        return []
    return validate_memories(saved)


def save_memories(memories):
    app.save_json_file(MEMORY_FILE, validate_memories(memories))


install(app, app.AppHandler, load_memories, save_memories)


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
                    b'<script src="/user-memory.js" defer></script>'
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
        if self.path == "/user-memory.js":
            self._send_static("user-memory.js", "text/javascript; charset=utf-8")
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
