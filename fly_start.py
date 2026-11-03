import base64
import binascii
import hmac
import os
from http.server import ThreadingHTTPServer

import app


USERNAME = os.environ.get("APP_USERNAME", "")
PASSWORD = os.environ.get("APP_PASSWORD", "")

if not USERNAME or ":" in USERNAME:
    raise SystemExit("Set APP_USERNAME to a non-empty name without ':'.")
if len(PASSWORD) < 16:
    raise SystemExit("Set APP_PASSWORD to a password of at least 16 characters.")


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

    def do_GET(self):
        if self._require_authentication():
            super().do_GET()

    def do_POST(self):
        if self._require_authentication():
            super().do_POST()


if __name__ == "__main__":
    app.HOST = os.environ.get("HOST", "0.0.0.0")
    app.PORT = int(os.environ.get("PORT", "8080"))
    app.start_telegram_polling()
    print(f"NOKK listening on {app.HOST}:{app.PORT}")
    ThreadingHTTPServer((app.HOST, app.PORT), AuthenticatedAppHandler).serve_forever()
