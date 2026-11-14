"""Browser smoke tests for the static UI.

They serve web/ with stubbed API responses, so they do not need the real backend
and run the same way on both variants. Playwright is optional locally: without it
the class is skipped, while CI installs it and runs the checks.
"""
import json
import threading
import unittest
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_AVAILABLE = True
except Exception:  # pragma: no cover - depends on the environment
    PLAYWRIGHT_AVAILABLE = False

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

CONFIG = {"configured": False}


class StubHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def log_message(self, *_args):
        return

    def _json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/":
            try:
                body = (WEB_DIR / "index.html").read_bytes()
            except OSError:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/config":
            self._json(200, {
                "provider": "openai" if CONFIG["configured"] else None,
                "model": "gpt-4o-mini" if CONFIG["configured"] else None,
                "models": {"openai": "gpt-4o-mini"} if CONFIG["configured"] else {},
                "base_url": "",
                "configured": CONFIG["configured"],
                "configured_providers": ["openai"] if CONFIG["configured"] else [],
                "search_configured": False,
                "search_providers": [],
                "google_calendar_configured": False,
                "google_calendar_connected": False,
                "terminal_enabled": False,
                "approval_mode": "manual",
                "workspace": "",
                "system_prompt": "",
                "wake_phrase": "Nok",
                "transcribe_model": "",
                "wake_window_seconds": 5,
                "tts_auto_play": False,
                "notifications_enabled": False,
                "weather_enabled": False,
                "weather_city": "",
                "alerts_enabled": False,
                "alerts_disk_percent": 90,
                "alerts_memory_percent": 92,
                "workflows": [],
            })
            return
        if path == "/api/telegram":
            self._json(200, {"configured": False, "authorized_chats": 0})
            return
        if path == "/api/api-keys":
            self._json(200, {"enabled": False, "keys": []})
            return
        if path == "/api/google-calendar":
            self._json(200, {"configured": False, "connected": False})
            return
        if path == "/api/weather":
            self._json(200, {"configured": False})
            return
        if path == "/api/chats":
            self._json(200, {"chats": []})
            return
        if path == "/api/workflows":
            self._json(200, {"workflows": []})
            return
        if path == "/api/planner":
            self._json(200, {"events": [], "tasks": []})
            return
        if path == "/api/memory":
            self._json(200, {"memories": []})
            return
        if path.startswith("/api/"):
            self._json(200, {})
            return
        return super().do_GET()

    def do_POST(self):
        self._json(200, {"ok": True, "chats": [], "workflows": []})


class ServerMixin:
    server = None
    base_url = ""

    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(
            ("127.0.0.1", 0), partial(StubHandler)
        )
        cls.base_url = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()


@unittest.skipUnless(PLAYWRIGHT_AVAILABLE, "playwright non installato")
class FrontendSmokeTests(ServerMixin, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def open_page(self, configured, width=1280, height=900, touch=False):
        CONFIG["configured"] = configured
        context = self.browser.new_context(
            viewport={"width": width, "height": height},
            has_touch=touch,
            is_mobile=touch,
        )
        page = context.new_page()
        page.goto(self.base_url, wait_until="domcontentloaded")
        page.wait_for_timeout(700)
        return context, page

    def test_unconfigured_welcome_offers_the_setup_action(self):
        context, page = self.open_page(False)
        try:
            self.assertFalse(page.locator("#welcome-setup").is_hidden())
            self.assertTrue(page.locator("#message-input").is_disabled())
        finally:
            context.close()

    def test_configured_welcome_hides_the_setup_action(self):
        context, page = self.open_page(True)
        try:
            self.assertTrue(page.locator("#welcome-setup").is_hidden())
            self.assertFalse(page.locator("#message-input").is_disabled())
        finally:
            context.close()

    def test_mobile_drawer_opens_and_closes(self):
        context, page = self.open_page(False, width=390, height=844, touch=True)
        try:
            theme = page.locator("#theme-toggle").bounding_box()
            send = page.locator("#send-button").bounding_box()
            self.assertGreaterEqual(theme["width"], 44)
            self.assertGreaterEqual(theme["height"], 44)
            self.assertGreaterEqual(send["width"], 44)
            page.locator("#sidebar-toggle").tap()
            page.wait_for_timeout(350)
            self.assertIn("sidebar-open", page.locator("body").get_attribute("class"))
            sidebar = page.locator("#sidebar").bounding_box()
            self.assertEqual(round(sidebar["x"]), 0)
            page.locator("#sidebar-backdrop").dispatch_event("click")
            page.wait_for_timeout(350)
            self.assertNotIn("sidebar-open", page.locator("body").get_attribute("class"))
        finally:
            context.close()

    def test_chat_actions_and_usage_estimates(self):
        context, page = self.open_page(True)
        try:
            page.route("**/api/chat", lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"job_id": "smoke-1"}),
            ))
            page.route("**/api/jobs/smoke-1", lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({
                    "status": "complete",
                    "reply": "Risposta di prova",
                    "tool_events": [],
                }),
            ))
            page.evaluate("() => { configured = true; sendButton.disabled = false; }")
            page.evaluate("() => sendChatMessage('Ciao NOKK')")
            self.assertEqual(page.locator(".message-action.regenerate").count(), 1)
            self.assertEqual(
                page.locator(".message-action").filter(has_text="Modifica").count(), 1
            )
            self.assertEqual(
                page.locator(".message-action").filter(has_text="Semplifica").count(), 1
            )
            self.assertEqual(
                page.locator(".message-action").filter(has_text="Approfondisci").count(), 1
            )
            self.assertEqual(
                page.locator(".message-action").filter(has_text="Critica").count(), 1
            )
            self.assertEqual(
                page.locator(".message-action").filter(has_text="Continua").count(), 1
            )
            self.assertEqual(
                page.locator(".message-action").filter(has_text="Ricorda").count(), 1
            )
            self.assertEqual(page.locator(".message.user > .message-actions").count(), 1)
            self.assertEqual(page.locator(".message.assistant > .message-actions").count(), 1)
            page.locator("#settings-toggle").click()
            page.wait_for_timeout(300)
            page.locator("#settings-tab-usage").click()
            self.assertIn("1 risposta", page.locator("#usage-summary").inner_text())
            page.locator("#settings-close").click()
            page.locator(".message-action.regenerate").click()
            page.wait_for_timeout(700)
            self.assertEqual(page.evaluate("() => messages.length"), 2)
            page.evaluate("() => handleChatCommand('/riassumi')")
            self.assertEqual(page.evaluate("() => messages.length"), 4)
            self.assertIn(
                "Riassumi questa conversazione",
                page.evaluate("() => messages[2].content"),
            )
            page.locator(".message-action").filter(has_text="Modifica").first.click()
            self.assertEqual(page.evaluate("() => messages.length"), 0)
            self.assertEqual(page.locator("#message-input").input_value(), "Ciao NOKK")
        finally:
            context.close()

    def test_remember_saves_a_fact_to_memory(self):
        context, page = self.open_page(True)
        try:
            saved = {"items": []}

            def memory_route(route):
                if route.request.method == "POST":
                    payload = route.request.post_data_json or {}
                    saved["items"] = payload.get("memories", [])
                    route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps({"ok": True}),
                    )
                else:
                    route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps({"memories": saved["items"]}),
                    )

            page.route("**/api/memory", memory_route)
            page.evaluate("() => addMessage('user', 'Ricorda che preferisco risposte brevi.')")
            page.once(
                "dialog",
                lambda dialog: dialog.accept("Preferisco risposte brevi."),
            )
            page.locator(".message-action").filter(has_text="Ricorda").click()
            page.wait_for_timeout(400)
            self.assertEqual(saved["items"], ["Preferisco risposte brevi."])
            self.assertEqual(
                page.locator(".message-action").filter(has_text="Salvato").count(), 1
            )
        finally:
            context.close()

    def test_retry_recovers_from_a_failed_request(self):
        context, page = self.open_page(True)
        try:
            attempts = {"count": 0}

            def chat_route(route):
                attempts["count"] += 1
                if attempts["count"] == 1:
                    route.fulfill(
                        status=500,
                        content_type="application/json",
                        body=json.dumps({"error": "Errore simulato"}),
                    )
                else:
                    route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps({"job_id": "retry-1"}),
                    )

            page.route("**/api/chat", chat_route)
            page.route("**/api/jobs/retry-1", lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({
                    "status": "complete",
                    "reply": "Recuperata",
                    "tool_events": [],
                }),
            ))
            page.evaluate("() => { configured = true; sendButton.disabled = false; }")
            page.evaluate("() => sendChatMessage('Ciao')")
            self.assertEqual(page.locator(".message.error").count(), 1)
            self.assertEqual(
                page.locator(".message.error .message-action").filter(has_text="Riprova").count(),
                1,
            )
            page.locator(".message-action").filter(has_text="Riprova").click()
            page.wait_for_timeout(700)
            self.assertEqual(page.evaluate("() => messages.length"), 2)
            self.assertEqual(page.locator(".message.error").count(), 0)
        finally:
            context.close()

    def test_mobile_settings_tabs_scroll_horizontally(self):
        context, page = self.open_page(True, width=390, height=844, touch=True)
        try:
            page.locator("#settings-toggle").tap()
            page.wait_for_timeout(400)
            tabs = page.locator(".settings-tabs").evaluate(
                "el => ({ wrap: getComputedStyle(el).flexWrap, client: el.clientWidth, scroll: el.scrollWidth })"
            )
            self.assertEqual(tabs["wrap"], "nowrap")
            self.assertGreater(tabs["scroll"], tabs["client"])
        finally:
            context.close()


if __name__ == "__main__":
    unittest.main()
