import io
import base64
import datetime
import json
import os
import tempfile
import threading
import time
import unittest
import zipfile
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlsplit
from urllib.request import Request, urlopen

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

import app


class FakeResponse:
    def __init__(self, payload=None):
        self.payload = payload or {
            "choices": [{"message": {"content": "Ciao dal modello."}}],
        }

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class FakeHtmlResponse:
    def __init__(self, html):
        self.html = html

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _size=None):
        return self.html.encode("utf-8")


class FakeStatusHtmlResponse(FakeHtmlResponse):
    def __init__(self, html, status=200):
        super().__init__(html)
        self.status = status


class AppRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config_directory = tempfile.TemporaryDirectory()
        app.CONFIG_FILE = Path(cls.config_directory.name) / "config.json"
        app.WORKFLOWS_FILE = Path(cls.config_directory.name) / "workflows.json"
        app.PLANNER_FILE = Path(cls.config_directory.name) / "planner.json"
        app.TELEGRAM_FILE = Path(cls.config_directory.name) / "telegram.json"
        app.GOOGLE_CALENDAR_FILE = (
            Path(cls.config_directory.name) / "google_calendar.json"
        )
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), app.AppHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.config_directory.cleanup()

    def setUp(self):
        app.CONFIG_FILE.unlink(missing_ok=True)
        app.WORKFLOWS_FILE.unlink(missing_ok=True)
        app.PLANNER_FILE.unlink(missing_ok=True)
        app.TELEGRAM_FILE.unlink(missing_ok=True)
        app.GOOGLE_CALENDAR_FILE.unlink(missing_ok=True)
        with app.google_calendar_lock:
            app.google_calendar_config.clear()
            app.google_calendar_config.update(app.default_google_calendar())
            app.google_oauth_states.clear()
            app.google_access_token_cache["token"] = None
            app.google_access_token_cache["expires_at"] = 0.0
        with app.config_lock:
            app.config.update(app.default_config())
            app.workflows.clear()
            app.planner.clear()
            app.planner.update(app.default_planner())
        with app.telegram_lock:
            app.telegram_config.clear()
            app.telegram_config.update({
                "token": None,
                "bot_username": None,
                "authorized_chats": [],
                "offset": 0,
            })
            app.telegram_pairing = None
        with app.telegram_conversations_lock:
            app.telegram_conversations.clear()

    def request_json(self, path, payload):
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request) as response:
            return json.loads(response.read())

    def test_weather_endpoint_is_disabled_by_default(self):
        with urlopen(f"{self.base_url}/api/weather") as response:
            self.assertEqual(response.status, 200)
            payload = json.loads(response.read())
        self.assertEqual(payload, {"configured": False})

    def test_weather_endpoint_returns_the_city_forecast(self):
        with app.config_lock:
            app.config["weather_enabled"] = True
            app.config["weather_city"] = "Roma"
        fake = {
            "city": "Roma",
            "country": "IT",
            "temperature": 18,
            "minimum": 11,
            "maximum": 20,
            "description": "sereno",
            "updated_at": "2026-11-06T07:00:00+00:00",
        }
        with patch("app.fetch_weather", return_value=fake):
            with urlopen(f"{self.base_url}/api/weather") as response:
                payload = json.loads(response.read())
        self.assertTrue(payload["configured"])
        self.assertEqual(payload["temperature"], 18)
        self.assertEqual(payload["city"], "Roma")

    def test_weather_failure_is_reported_without_crashing(self):
        with app.config_lock:
            app.config["weather_enabled"] = True
            app.config["weather_city"] = "Roma"
        with patch(
            "app.fetch_weather", side_effect=RuntimeError("servizio non raggiungibile")
        ):
            with self.assertRaises(HTTPError) as raised:
                urlopen(f"{self.base_url}/api/weather")
        self.assertEqual(raised.exception.code, 503)

    def run_chat(self, messages, approve=True, expect_failure=False):
        response = self.request_json("/api/chat", {"messages": messages})
        job_id = response["job_id"]
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with urlopen(f"{self.base_url}/api/jobs/{job_id}") as job_response:
                job = json.loads(job_response.read())
            if job["status"] == "awaiting_approval":
                action = job["action"]
                approval = Request(
                    f"{self.base_url}/api/jobs/{job_id}/approval",
                    data=json.dumps({
                        "action_id": action["id"],
                        "approved": approve,
                    }).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(approval):
                    pass
            elif job["status"] == "complete":
                return job
            elif job["status"] == "failed":
                if expect_failure:
                    return job
                self.fail(job.get("error", "Attività fallita"))
            time.sleep(0.01)
        self.fail("Timeout in attesa del completamento dell'attività")

    def test_serves_page_and_static_assets(self):
        assets = {}
        for path, content_type in (
            ("/", "text/html"),
            ("/app.js", "text/javascript"),
            ("/style.css", "text/css"),
        ):
            with self.subTest(path=path), urlopen(f"{self.base_url}{path}") as response:
                self.assertIn(content_type, response.headers["Content-Type"])
                assets[path] = response.read().decode("utf-8")
                self.assertTrue(assets[path])
        self.assertIn("height: 100dvh", assets["/style.css"])
        self.assertIn("overflow: hidden", assets["/style.css"])
        self.assertIn("overflow-y: auto", assets["/style.css"])
        self.assertIn("conversation.scrollTo", assets["/app.js"])
        self.assertIn("function renderMarkdown", assets["/app.js"])
        self.assertIn("function startRecognition", assets["/app.js"])
        self.assertIn("Math.min(300 * (2 ** wakeRetryCount), 2000)", assets["/app.js"])
        self.assertIn("Riattivo l’ascolto tra", assets["/app.js"])
        self.assertIn("function speakText", assets["/app.js"])
        self.assertIn("createTextNode", assets["/app.js"])
        self.assertIn("function resizeComposer", assets["/app.js"])
        self.assertIn('id="theme-toggle"', assets["/"])
        self.assertIn('id="file-input"', assets["/"])
        self.assertIn('id="attachment-list"', assets["/"])
        self.assertIn('data-theme="dark"', assets["/"])
        self.assertIn('class="settings-tabs"', assets["/"])
        self.assertIn('id="settings-panel-connection"', assets["/"])
        self.assertIn("function activateSettingsTab", assets["/app.js"])
        self.assertIn('id="wake-toggle"', assets["/"])
        self.assertIn('id="mic-toggle"', assets["/"])
        self.assertIn("function renderWorkflows", assets["/app.js"])
        self.assertIn('id="workflow-panel"', assets["/"])
        self.assertIn('id="launcher-open"', assets["/"])
        self.assertIn('id="launcher-overlay"', assets["/"])
        self.assertIn('data-open-app="calendar"', assets["/"])
        self.assertIn('data-open-app="tasks"', assets["/"])
        self.assertIn("Ctrl K", assets["/"])
        self.assertIn("app-window", assets["/app.js"])
        self.assertIn("function renderFunctionsWindow", assets["/app.js"])
        self.assertIn("function renderCalendarApp", assets["/app.js"])
        self.assertIn("function renderTasksApp", assets["/app.js"])
        self.assertNotIn("input.style.height", assets["/app.js"])

    def test_workflows_can_be_created_edited_deleted_and_reloaded(self):
        created = self.request_json("/api/workflows", {
            "action": "save",
            "name": "Riassunto riunione",
            "prompt": "Riassumi le note e indica le decisioni.",
        })["workflows"]
        self.assertEqual(len(created), 1)
        workflow_id = created[0]["id"]
        self.assertRegex(workflow_id, r"^[a-f0-9]{32}$")
        self.assertEqual(json.loads(app.WORKFLOWS_FILE.read_text(encoding="utf-8")), created)

        updated = self.request_json("/api/workflows", {
            "action": "save",
            "id": workflow_id,
            "name": "Verbale riunione",
            "prompt": "Estrai decisioni e attività.",
        })["workflows"]
        self.assertEqual(updated, [{
            "id": workflow_id,
            "name": "Verbale riunione",
            "prompt": "Estrai decisioni e attività.",
            "schedule_enabled": False,
            "schedule_time": "07:00",
            "schedule_days": [],
            "last_run": None,
            "last_status": None,
            "last_result": None,
        }])
        self.assertEqual(app.load_workflows_file(), updated)

        deleted = self.request_json("/api/workflows", {
            "action": "delete",
            "id": workflow_id,
        })["workflows"]
        self.assertEqual(deleted, [])
        if os.name != "nt":
            self.assertEqual(app.WORKFLOWS_FILE.stat().st_mode & 0o777, 0o600)

    def test_workflow_schedule_is_saved_and_returned(self):
        created = self.request_json("/api/workflows", {
            "action": "save",
            "name": "Controllo mattutino",
            "prompt": "Controlla le attività di oggi.",
            "schedule_enabled": True,
            "schedule_time": "07:30",
            "schedule_days": [0, 2, 4],
        })["workflows"]
        workflow = created[0]
        self.assertTrue(workflow["schedule_enabled"])
        self.assertEqual(workflow["schedule_time"], "07:30")
        self.assertEqual(workflow["schedule_days"], [0, 2, 4])
        with urlopen(f"{self.base_url}/api/workflows") as response:
            listed = json.loads(response.read())["workflows"]
        self.assertEqual(listed, created)

        updated = self.request_json("/api/workflows", {
            "action": "save",
            "id": workflow["id"],
            "name": "Controllo serale",
            "prompt": "Controlla le attività di domani.",
            "schedule_enabled": False,
            "schedule_time": "20:00",
            "schedule_days": [5],
        })["workflows"][0]
        self.assertFalse(updated["schedule_enabled"])
        self.assertEqual(updated["schedule_time"], "20:00")
        self.assertEqual(updated["schedule_days"], [5])

    def test_workflow_validation_rejects_empty_or_oversized_content(self):
        with self.assertRaises(ValueError):
            app.validate_workflows([{
                "id": "a" * 32,
                "name": "Procedura",
                "prompt": " ",
            }])
        with self.assertRaises(ValueError):
            app.validate_workflows([{
                "id": "a" * 32,
                "name": "Procedura",
                "prompt": "x" * (app.MAX_WORKFLOW_PROMPT_LENGTH + 1),
            }])

    def test_ai_app_tools_read_and_manage_local_sections(self):
        task = app.execute_app_tool("manage_planner_item", {
            "section": "tasks",
            "action": "create",
            "title": "Preparare la demo",
            "due_date": "2026-11-03",
        })["item"]
        self.assertEqual(task["title"], "Preparare la demo")
        self.assertFalse(task["completed"])

        updated_task = app.execute_app_tool("manage_planner_item", {
            "section": "tasks",
            "action": "update",
            "id": task["id"],
            "completed": True,
        })["item"]
        self.assertTrue(updated_task["completed"])

        event = app.execute_app_tool("manage_planner_item", {
            "section": "calendar",
            "action": "create",
            "title": "Riunione",
            "starts_at": "2026-11-03T14:30",
        })["item"]
        self.assertEqual(event["description"], "")
        self.assertEqual(
            app.execute_app_tool("get_app_data", {"section": "calendar"})["events"],
            [event],
        )

        workflow = app.execute_app_tool("manage_workflow", {
            "action": "create",
            "name": "Sintesi",
            "prompt": "Riassumi i punti principali.",
        })["workflow"]
        self.assertEqual(
            app.execute_app_tool("get_app_data", {"section": "workflows"})[
                "workflows"
            ],
            [workflow],
        )
        self.assertIn("operating_system", app.execute_app_tool(
            "get_app_data", {"section": "system"},
        ))
        settings = app.execute_app_tool("get_app_data", {"section": "settings"})
        self.assertNotIn("api_key", settings)
        self.assertNotIn("system_prompt", settings)

    def test_chat_can_use_app_tools_without_calling_a_real_provider(self):
        with app.config_lock:
            app.config.update({
                "provider": "openai",
                "model": "gpt-4o-mini",
                "api_key": "test-key-not-sent",
                "terminal_enabled": False,
                "approval_mode": "manual",
                "workspace": str(Path(app.__file__).resolve().parent),
                "system_prompt": "",
            })
        tool_response = {
            "choices": [{
                "message": {
                    "content": None,
                    "tool_calls": [{
                        "id": "call-task",
                        "type": "function",
                        "function": {
                            "name": "manage_planner_item",
                            "arguments": json.dumps({
                                "section": "tasks",
                                "action": "create",
                                "title": "Task da chat",
                            }),
                        },
                    }],
                },
            }],
        }
        responses = iter([
            FakeResponse(tool_response),
            FakeResponse({
                "choices": [{"message": {"content": "Attività creata."}}],
            }),
        ])
        with patch("app.urlopen", side_effect=lambda *_args, **_kwargs: next(responses)):
            job = self.run_chat([{"role": "user", "content": "Crea una task."}])
        self.assertEqual(job["reply"], "Attività creata.")
        self.assertEqual(app.planner["tasks"][0]["title"], "Task da chat")
        self.assertEqual(len(job["tool_events"]), 1)

    def test_telegram_token_stays_local_and_pairing_is_private(self):
        token = "123456789:abcdefghijklmnopqrstuvwxyz0123456789"
        with (
            patch("app.telegram_api_call", return_value={
                "id": 123456789, "username": "nokk_test_bot",
            }) as api_call,
            patch("app.start_telegram_polling"),
        ):
            connected = self.request_json("/api/telegram", {
                "action": "connect", "token": token,
            })
        self.assertEqual(connected, {"ok": True, "bot_username": "nokk_test_bot"})
        api_call.assert_called_once_with(token, "getMe", {})

        with urlopen(f"{self.base_url}/api/telegram") as response:
            public_status = json.loads(response.read())
        self.assertEqual(public_status["authorized_chats"], 0)
        self.assertNotIn("token", public_status)

        pair = self.request_json("/api/telegram", {"action": "pair_code"})
        self.assertRegex(pair["code"], r"^[0-9]{6}$")
        update = {
            "update_id": 1,
            "message": {
                "chat": {"id": 42, "type": "private"},
                "from": {"id": 42},
                "text": f"/pair {pair['code']}",
            },
        }
        with patch("app._send_telegram_message") as send_message:
            app._handle_telegram_update(update)
        send_message.assert_called_once()
        self.assertEqual(app.telegram_config["authorized_chats"], ["42"])

        with patch("app._send_telegram_message") as send_message:
            app._handle_telegram_update({
                "message": {
                    "chat": {"id": 99, "type": "group"},
                    "from": {"id": 99},
                    "text": f"/pair {pair['code']}",
                },
            })
        send_message.assert_not_called()
        self.assertEqual(app.telegram_config["authorized_chats"], ["42"])

        self.request_json("/api/telegram", {"action": "disconnect"})
        self.assertIsNone(app.load_telegram_file()["token"])
        self.assertEqual(app.telegram_config["authorized_chats"], [])

    def test_calendar_and_tasks_are_persisted_and_can_be_updated(self):
        created_event = self.request_json("/api/planner", {
            "action": "save",
            "kind": "event",
            "title": "Revisione",
            "starts_at": "2026-11-03T14:30",
            "description": "Portare le note.",
        })
        event = created_event["events"][0]
        self.assertRegex(event["id"], r"^[a-f0-9]{32}$")
        self.assertEqual(event["title"], "Revisione")

        updated_event = self.request_json("/api/planner", {
            "action": "save",
            "kind": "event",
            "id": event["id"],
            "title": "Revisione finale",
            "starts_at": "2026-11-03T15:00",
            "description": "",
        })["events"]
        self.assertEqual(updated_event[0]["title"], "Revisione finale")
        self.assertEqual(updated_event[0]["starts_at"], "2026-11-03T15:00")

        created_task = self.request_json("/api/planner", {
            "action": "save",
            "kind": "task",
            "title": "Inviare il riepilogo",
            "due_date": "2026-11-04",
            "completed": False,
        })
        task = created_task["tasks"][0]
        completed_task = self.request_json("/api/planner", {
            "action": "save",
            "kind": "task",
            "id": task["id"],
            "title": task["title"],
            "due_date": task["due_date"],
            "completed": True,
        })["tasks"]
        self.assertTrue(completed_task[0]["completed"])

        deleted = self.request_json("/api/planner", {
            "action": "delete",
            "kind": "task",
            "id": task["id"],
        })
        self.assertEqual(deleted["tasks"], [])
        self.assertEqual(app.load_planner_file(), {
            "events": updated_event,
            "tasks": [],
        })
        with urlopen(f"{self.base_url}/api/planner") as response:
            self.assertEqual(json.loads(response.read()), {
                "events": updated_event,
                "tasks": [],
            })

    def test_calendar_normalizes_ai_date_formats(self):
        event = self.request_json("/api/planner", {
            "action": "save", "kind": "event", "title": "Riunione",
            "starts_at": "04/11/2026 14:30", "description": "",
        })["events"][0]
        self.assertEqual(event["starts_at"], "2026-11-04T14:30")

        event_with_seconds = self.request_json("/api/planner", {
            "action": "save", "kind": "event", "title": "Call",
            "starts_at": "2026-11-05T09:15:00", "description": "",
        })["events"][1]
        self.assertEqual(event_with_seconds["starts_at"], "2026-11-05T09:15")

        task = self.request_json("/api/planner", {
            "action": "save", "kind": "task", "title": "Scadenza",
            "due_date": "05/11/2026", "completed": False,
        })["tasks"][0]
        self.assertEqual(task["due_date"], "2026-11-05")

    def test_calendar_rejects_invalid_date_and_task_state(self):
        for payload in (
            {
                "action": "save", "kind": "event", "title": "Evento",
                "starts_at": "domani", "description": "",
            },
            {
                "action": "save", "kind": "task", "title": "Attività",
                "due_date": "2026-13-40", "completed": False,
            },
            {
                "action": "save", "kind": "task", "title": "Attività",
                "due_date": None, "completed": "false",
            },
        ):
            request = Request(
                f"{self.base_url}/api/planner",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with self.subTest(payload=payload), self.assertRaises(HTTPError) as error:
                urlopen(request)
            self.assertEqual(error.exception.code, 400)
            error.exception.close()

    def test_calendar_and_data_can_be_exported(self):
        self.request_json("/api/planner", {
            "action": "save", "kind": "event", "title": "Riunione",
            "starts_at": "2026-11-04T14:30", "description": "Note",
        })
        self.request_json("/api/planner", {
            "action": "save", "kind": "task", "title": "Scadenza",
            "due_date": "2026-11-05", "completed": False,
        })
        with urlopen(f"{self.base_url}/api/calendar.ics") as response:
            body = response.read().decode("utf-8")
        self.assertIn("BEGIN:VCALENDAR", body)
        self.assertIn("SUMMARY:Riunione", body)
        self.assertIn("DUE;VALUE=DATE:20261105", body)
        with urlopen(f"{self.base_url}/api/export") as response:
            exported = json.loads(response.read())
        self.assertEqual(exported["app"], "NOKK")
        self.assertNotIn("api_key", exported["config"])
        self.assertEqual(exported["config"]["planner"]["events"][0]["title"], "Riunione")

    def test_fetch_url_rejects_private_and_local_addresses(self):
        for value in (
            "http://localhost/", "http://127.0.0.1/", "file:///etc/passwd",
            "http://10.0.0.1/", "http://[::1]/",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                app._validate_public_url(value)

    def test_machine_status_does_not_expose_host_or_user_details(self):
        with urlopen(f"{self.base_url}/api/system") as response:
            status = json.loads(response.read())
        self.assertIn("operating_system", status)
        self.assertIn("python_version", status)
        self.assertIn("processor_count", status)
        self.assertIn("disk_free", status)
        self.assertNotIn("hostname", status)
        self.assertNotIn("username", status)
        self.assertNotIn("workspace", status)

    def test_docx_upload_extracts_text_without_saving_the_file(self):
        document_buffer = io.BytesIO()
        document_xml = (
            '<w:document xmlns:w="http://schemas.openxmlformats.org/'
            'wordprocessingml/2006/main"><w:body>'
            '<w:p><w:r><w:t>Verbale della riunione</w:t></w:r></w:p>'
            '<w:p><w:r><w:t>Consegna venerdì.</w:t></w:r></w:p>'
            '</w:body></w:document>'
        )
        with zipfile.ZipFile(document_buffer, "w") as document:
            document.writestr("word/document.xml", document_xml)
        encoded = base64.b64encode(document_buffer.getvalue()).decode("ascii")
        extracted = self.request_json("/api/extract", {
            "name": "verbale.docx",
            "data": encoded,
        })
        self.assertEqual(
            extracted["text"],
            "Verbale della riunione\nConsegna venerdì.",
        )
        self.assertEqual(
            {path.name for path in Path(self.config_directory.name).iterdir()},
            set(),
        )

    def test_pdf_upload_extracts_text(self):
        writer = PdfWriter()
        page = writer.add_blank_page(width=200, height=100)
        font = DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        })
        font_reference = writer._add_object(font)
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({
                NameObject("/F1"): font_reference,
            }),
        })
        content = DecodedStreamObject()
        content.set_data(b"BT /F1 12 Tf 10 50 Td (NOKK PDF text) Tj ET")
        page[NameObject("/Contents")] = writer._add_object(content)
        pdf_buffer = io.BytesIO()
        writer.write(pdf_buffer)
        self.assertEqual(
            app.extract_document_text("report.pdf", pdf_buffer.getvalue()).strip(),
            "NOKK PDF text",
        )

    def test_chat_sends_attachments_to_the_selected_provider(self):
        self.request_json("/api/config", {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "api_key": "test-secret",
        })
        attachments = [
            {"kind": "text", "name": "note.txt", "content": "Consegna venerdì."},
            {
                "kind": "image",
                "name": "diagram.png",
                "mime_type": "image/png",
                "data": (
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
                    "/x8AAwMCAO6RZioAAAAASUVORK5CYII="
                ),
            },
        ]
        with patch("app.urlopen", return_value=FakeResponse()) as provider_call:
            job = self.run_chat([{
                "role": "user",
                "content": "Riassumi.",
                "attachments": attachments,
            }])
        self.assertEqual(job["reply"], "Ciao dal modello.")
        provider_message = json.loads(provider_call.call_args.args[0].data)["messages"][-1]
        self.assertIn("Consegna venerdì.", provider_message["content"][0]["text"])
        self.assertTrue(
            provider_message["content"][1]["image_url"]["url"].startswith(
                "data:image/png;base64,"
            )
        )

    def test_document_extraction_rejects_unsupported_and_invalid_files(self):
        for payload in (
            {"name": "report.exe", "data": "aW1hZ2U="},
            {"name": "report.pdf", "data": "not-base64!"},
            {"name": "folder\\report.docx", "data": "aW1hZ2U="},
        ):
            with self.subTest(payload=payload):
                request = Request(
                    f"{self.base_url}/api/extract",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with self.assertRaises(HTTPError) as response:
                    urlopen(request)
                self.assertEqual(response.exception.code, 400)
                response.exception.close()

    def test_config_and_chat_without_real_provider_call(self):
        self.request_json("/api/config", {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "api_key": "test-secret",
            "system_prompt": "Rispondi in italiano e sii conciso.",
            "wake_phrase": "Nok",
            "tts_auto_play": True,
        })
        with urlopen(f"{self.base_url}/api/config") as response:
            public_config = json.loads(response.read())
        self.assertTrue(public_config["configured"])
        self.assertIsInstance(public_config["search_configured"], bool)
        self.assertNotIn("api_key", public_config)
        self.assertEqual(
            public_config["system_prompt"],
            "Rispondi in italiano e sii conciso.",
        )
        self.assertEqual(public_config["wake_phrase"], "Nok")
        self.assertTrue(public_config["tts_auto_play"])
        saved = json.loads(app.CONFIG_FILE.read_text(encoding="utf-8"))
        self.assertEqual(saved["api_key"], "test-secret")
        self.assertEqual(app.load_config_file(), {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "api_key": "test-secret",
            "api_keys": {"openai": "test-secret"},
            "models": {"openai": "gpt-4o-mini"},
            "base_url": "",
            "terminal_enabled": False,
            "approval_mode": "manual",
            "workspace": str(Path(app.APP_DIR).resolve()),
            "system_prompt": "Rispondi in italiano e sii conciso.",
            "wake_phrase": "Nok",
            "tts_auto_play": True,
            "notifications_enabled": False,
            "weather_enabled": False,
            "weather_city": "",
            "alerts_enabled": False,
            "alerts_disk_percent": 90,
            "alerts_memory_percent": 92,
        })
        if os.name != "nt":
            self.assertEqual(app.CONFIG_FILE.stat().st_mode & 0o777, 0o600)

        with patch("app.urlopen", return_value=FakeResponse()) as provider_call:
            job = self.run_chat([
                {"role": "user", "content": "Ciao"},
            ])
        self.assertEqual(job["reply"], "Ciao dal modello.")
        provider_payload = json.loads(provider_call.call_args.args[0].data)
        self.assertEqual(provider_payload["messages"][0]["role"], "system")
        self.assertTrue(provider_payload["messages"][0]["content"].startswith(
            f"{app.DEFAULT_SYSTEM_PROMPT}\n\n"
            "Rispondi in italiano e sii conciso."
        ))
        self.assertIn(
            "NOKK section tools",
            provider_payload["messages"][0]["content"],
        )

    def test_config_keeps_api_keys_when_switching_provider(self):
        self.request_json("/api/config", {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "api_key": "openai-secret",
        })
        self.request_json("/api/config", {
            "provider": "anthropic",
            "model": "claude-3-5-haiku-latest",
            "api_key": "anthropic-secret",
        })
        with urlopen(f"{self.base_url}/api/config") as response:
            public_config = json.loads(response.read())
        self.assertEqual(public_config["provider"], "anthropic")
        self.assertEqual(
            public_config["configured_providers"], ["anthropic", "openai"],
        )
        self.assertNotIn("api_keys", public_config)
        self.assertNotIn("api_key", public_config)

        self.request_json("/api/config", {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "api_key": "",
        })
        saved = json.loads(app.CONFIG_FILE.read_text(encoding="utf-8"))
        self.assertEqual(saved["provider"], "openai")
        self.assertEqual(saved["api_key"], "openai-secret")
        self.assertEqual(saved["api_keys"], {
            "openai": "openai-secret",
            "anthropic": "anthropic-secret",
        })

    def test_config_requires_key_for_a_new_provider(self):
        self.request_json("/api/config", {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "api_key": "openai-secret",
        })
        request = Request(
            f"{self.base_url}/api/config",
            data=json.dumps({
                "provider": "google",
                "model": "gemini-2.0-flash",
                "api_key": "",
            }).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(HTTPError) as response:
            urlopen(request)
        self.assertEqual(response.exception.code, 400)
        response.exception.close()
        saved = json.loads(app.CONFIG_FILE.read_text(encoding="utf-8"))
        self.assertEqual(saved["provider"], "openai")
        self.assertEqual(saved["api_keys"], {"openai": "openai-secret"})

    def test_config_saves_custom_provider_base_url(self):
        self.request_json("/api/config", {
            "provider": "custom",
            "model": "my-model",
            "api_key": "custom-secret",
            "base_url": "https://llm.example.com/v1/",
        })
        with urlopen(f"{self.base_url}/api/config") as response:
            public_config = json.loads(response.read())
        self.assertEqual(public_config["provider"], "custom")
        self.assertEqual(public_config["base_url"], "https://llm.example.com/v1")
        self.assertEqual(public_config["configured_providers"], ["custom"])
        self.assertNotIn("api_key", public_config)

    def test_config_rejects_insecure_custom_base_url(self):
        for base_url in (
            "",
            "http://api.example.com/v1",
            "https://llm.example.com/v1?key=1",
        ):
            with self.subTest(base_url=base_url):
                request = Request(
                    f"{self.base_url}/api/config",
                    data=json.dumps({
                        "provider": "custom",
                        "model": "my-model",
                        "api_key": "custom-secret",
                        "base_url": base_url,
                    }).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with self.assertRaises(HTTPError) as response:
                    urlopen(request)
                self.assertEqual(response.exception.code, 400)
                response.exception.close()

    def test_config_remembers_model_per_provider(self):
        self.request_json("/api/config", {
            "provider": "mistral",
            "model": "mistral-large-latest",
            "api_key": "mistral-secret",
        })
        self.request_json("/api/config", {
            "provider": "openai",
            "model": "gpt-4.1-mini",
            "api_key": "openai-secret",
        })
        with urlopen(f"{self.base_url}/api/config") as response:
            public_config = json.loads(response.read())
        self.assertEqual(public_config["model"], "gpt-4.1-mini")
        self.assertEqual(public_config["models"], {
            "mistral": "mistral-large-latest",
            "openai": "gpt-4.1-mini",
        })

    def test_legacy_config_file_keeps_its_api_key(self):
        app.CONFIG_FILE.write_text(json.dumps({
            "provider": "google",
            "model": "gemini-2.0-flash",
            "api_key": "legacy-secret",
            "terminal_enabled": False,
            "approval_mode": "manual",
            "workspace": str(Path(app.APP_DIR).resolve()),
            "system_prompt": "",
            "wake_phrase": "Nok",
            "tts_auto_play": False,
        }), encoding="utf-8")
        loaded = app.load_config_file()
        self.assertEqual(loaded["api_key"], "legacy-secret")
        self.assertEqual(loaded["api_keys"], {"google": "legacy-secret"})
        self.assertEqual(loaded["models"], {"google": "gemini-2.0-flash"})

    def test_public_config_reports_search_configuration(self):
        with patch.multiple(
            app, EXA_API_KEY="", TAVILY_API_KEY="", SERPER_API_KEY="",
        ):
            with urlopen(f"{self.base_url}/api/config") as response:
                public_config = json.loads(response.read())
        self.assertTrue(public_config["search_configured"])
        self.assertIn("duckduckgo", public_config["search_providers"])

    def test_config_rejects_system_prompt_over_limit(self):
        request = Request(
            f"{self.base_url}/api/config",
            data=json.dumps({
                "provider": "openai",
                "model": "gpt-4o-mini",
                "api_key": "test-secret",
                "system_prompt": "x" * (app.MAX_SYSTEM_PROMPT_LENGTH + 1),
            }).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(HTTPError) as response:
            urlopen(request)
        response.exception.close()
        self.assertEqual(response.exception.code, 400)

    def test_config_rejects_invalid_voice_preferences(self):
        for voice_options in (
            {"wake_phrase": " "},
            {"wake_phrase": "x" * (app.MAX_WAKE_PHRASE_LENGTH + 1)},
            {"tts_auto_play": "yes"},
        ):
            with self.subTest(voice_options=voice_options):
                request = Request(
                    f"{self.base_url}/api/config",
                    data=json.dumps({
                        "provider": "openai",
                        "model": "gpt-4o-mini",
                        "api_key": "test-secret",
                        **voice_options,
                    }).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with self.assertRaises(HTTPError) as response:
                    urlopen(request)
                response.exception.close()
                self.assertEqual(response.exception.code, 400)

    def test_provider_404_includes_model_hint_and_provider_details(self):
        self.request_json("/api/config", {
            "provider": "openai",
            "model": "invalid-model",
            "api_key": "test-secret",
        })
        provider_response = b'{"error":{"message":"The model was not found."}}'
        provider_error = HTTPError(
            "https://api.openai.com/v1/chat/completions",
            404,
            "Not Found",
            {},
            io.BytesIO(provider_response),
        )
        with patch("app.urlopen", side_effect=provider_error):
            job = self.run_chat(
                [{"role": "user", "content": "Ciao"}],
                expect_failure=True,
            )
        self.assertIn("HTTP 404", job["error"])
        self.assertIn("nome del modello", job["hint"])
        self.assertEqual(job["details"], provider_response.decode())

    def test_openrouter_rejects_non_free_models(self):
        request = Request(
            f"{self.base_url}/api/config",
            data=json.dumps({
                "provider": "openrouter",
                "model": "openai/gpt-4o",
                "api_key": "test-secret",
            }).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(HTTPError) as response:
            urlopen(request)
        with response.exception:
            payload = json.loads(response.exception.read())
        self.assertEqual(response.exception.code, 400)
        self.assertIn("router gratuito automatico", payload["error"])

    def test_openrouter_chat_uses_free_router(self):
        self.request_json("/api/config", {
            "provider": "openrouter",
            "model": "openrouter/free",
            "api_key": "test-secret",
        })
        with patch("app.urlopen", return_value=FakeResponse()) as provider_call:
            job = self.run_chat([
                {"role": "user", "content": "Ciao"},
            ])
        self.assertEqual(job["reply"], "Ciao dal modello.")
        request = provider_call.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "https://openrouter.ai/api/v1/chat/completions",
        )
        self.assertEqual(json.loads(request.data)["model"], "openrouter/free")

    def test_terminal_command_waits_for_explicit_approval(self):
        self.request_json("/api/config", {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "api_key": "test-secret",
            "terminal_enabled": True,
            "approval_mode": "manual",
            "workspace": str(Path(app.APP_DIR).resolve()),
        })
        tool_response = FakeResponse({
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "run_terminal_command",
                            "arguments": '{"command":"pwd"}',
                        },
                    }],
                },
            }],
        })
        final_response = FakeResponse({
            "choices": [{
                "message": {"role": "assistant", "content": "Ecco la cartella."},
            }],
        })
        with (
            patch("app.urlopen", side_effect=[tool_response, final_response]) as provider_call,
            patch(
                "app.execute_terminal_command",
                return_value={"exit_code": 0, "output": "cartella progetto"},
            ) as command_call,
        ):
            job = self.run_chat([{"role": "user", "content": "Mostra la cartella"}])

        self.assertEqual(job["reply"], "Ecco la cartella.")
        self.assertEqual(command_call.call_args.args[0], "pwd")
        self.assertEqual(len(job["tool_events"]), 1)
        first_request = json.loads(provider_call.call_args_list[0].args[0].data)
        self.assertEqual(first_request["tools"][0]["function"]["name"], "run_terminal_command")
        second_request = json.loads(provider_call.call_args_list[1].args[0].data)
        self.assertEqual(second_request["messages"][-1]["role"], "tool")
        self.assertIn("cartella progetto", second_request["messages"][-1]["content"])

    def test_auto_read_command_runs_without_prompt(self):
        self.request_json("/api/config", {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "api_key": "test-secret",
            "terminal_enabled": True,
            "approval_mode": "auto_readonly",
            "workspace": str(Path(app.APP_DIR).resolve()),
        })
        tool_response = FakeResponse({
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "call-auto",
                        "type": "function",
                        "function": {
                            "name": "run_terminal_command",
                            "arguments": '{"command":"pwd"}',
                        },
                    }],
                },
            }],
        })
        final_response = FakeResponse({
            "choices": [{
                "message": {"role": "assistant", "content": "Cartella letta."},
            }],
        })
        with (
            patch("app.urlopen", side_effect=[tool_response, final_response]),
            patch(
                "app.execute_terminal_command",
                wraps=app.execute_terminal_command,
            ) as command_call,
        ):
            job = self.run_chat([{"role": "user", "content": "Mostra la cartella"}])

        self.assertEqual(job["reply"], "Cartella letta.")
        command_call.assert_called_once()
        self.assertTrue(command_call.call_args.kwargs["automatic"])
        self.assertTrue(job["tool_events"][0]["automatic"])
        self.assertTrue(job["tool_events"][0]["executed"])

    def test_rejected_terminal_command_is_not_executed(self):
        self.request_json("/api/config", {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "api_key": "test-secret",
            "terminal_enabled": True,
            "approval_mode": "manual",
            "workspace": str(Path(app.APP_DIR).resolve()),
        })
        tool_response = FakeResponse({
            "choices": [{
                "message": {
                    "content": None,
                    "tool_calls": [{
                        "id": "call-rejected",
                        "type": "function",
                        "function": {
                            "name": "run_terminal_command",
                            "arguments": '{"command":"rm -rf build"}',
                        },
                    }],
                },
            }],
        })
        final_response = FakeResponse({
            "choices": [{
                "message": {"content": "Non ho eseguito il comando."},
            }],
        })
        with (
            patch("app.urlopen", side_effect=[tool_response, final_response]),
            patch("app.execute_terminal_command") as command_call,
        ):
            job = self.run_chat(
                [{"role": "user", "content": "Pulisci i file"}],
                approve=False,
            )

        command_call.assert_not_called()
        self.assertFalse(job["tool_events"][0]["executed"])
        self.assertIn("non è stato eseguito", job["tool_events"][0]["output"])


class RepositoryToolTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_directory.cleanup)
        self.root = Path(self.temp_directory.name)
        (self.root / "web").mkdir()
        (self.root / "app.py").write_text("print('ok')\n", encoding="utf-8")
        (self.root / "web" / "app.js").write_text(
            "const x = 1;\n", encoding="utf-8",
        )
        (self.root / "config.json").write_text(
            '{"api_key": "secret"}', encoding="utf-8",
        )
        (self.root / ".env").write_text("API_KEY=secret\n", encoding="utf-8")
        (self.root / ".git").mkdir()
        (self.root / ".git" / "config").write_text("[core]\n", encoding="utf-8")
        for name, value in (
            ("APP_DIR", self.root),
            ("CONFIG_FILE", self.root / "config.json"),
            ("WORKFLOWS_FILE", self.root / "workflows.json"),
            ("PLANNER_FILE", self.root / "planner.json"),
            ("TELEGRAM_FILE", self.root / "telegram.json"),
        ):
            patcher = patch.object(app, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_lists_repository_files_without_private_state(self):
        listing = app.execute_app_tool("list_repository_files", {})
        self.assertIn("app.py", listing["files"])
        self.assertIn("web", listing["directories"])
        self.assertNotIn("config.json", listing["files"])
        self.assertNotIn(".env", listing["files"])
        self.assertNotIn(".git", listing["directories"])

    def test_reads_repository_file(self):
        result = app.execute_app_tool(
            "read_repository_file", {"path": "web/app.js"},
        )
        self.assertEqual(result["path"], "web/app.js")
        self.assertEqual(result["content"], "const x = 1;\n")

    def test_rejects_private_or_outside_paths(self):
        for path in (
            "../outside.txt", "/etc/passwd", ".env", ".git/config",
            "config.json",
        ):
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    app.execute_app_tool(
                        "read_repository_file", {"path": path},
                    )


class SelfUpdatePullRequestTests(unittest.TestCase):
    @staticmethod
    def github_responses():
        return [
            FakeResponse({"object": {"sha": "a" * 40}}),
            FakeResponse({"tree": {"sha": "b" * 40}}),
            FakeResponse({"sha": "c" * 40}),
            FakeResponse({"sha": "d" * 40}),
            FakeResponse({"sha": "e" * 40}),
            FakeResponse({"ref": "refs/heads/nokk/auto-test"}),
            FakeResponse({
                "number": 7,
                "html_url": "https://github.com/acme/repo/pull/7",
            }),
        ]

    def test_opens_pull_request_with_one_commit(self):
        with (
            patch.object(app, "GITHUB_TOKEN", "test-token"),
            patch.object(app, "GITHUB_REPOSITORY", "acme/repo"),
            patch.object(app, "GITHUB_BASE_BRANCH", "main"),
            patch("app.urlopen", side_effect=self.github_responses()) as github,
        ):
            result = app.execute_app_tool("create_pull_request", {
                "title": "Migliora il messaggio di benvenuto",
                "body": "Aggiorna il testo.",
                "changes": [{
                    "path": "web/app.js",
                    "content": "const greeting = 'ciao';\n",
                }],
            })
        self.assertEqual(result["url"], "https://github.com/acme/repo/pull/7")
        self.assertEqual(result["number"], 7)
        self.assertTrue(result["branch"].startswith("nokk/auto-"))
        self.assertEqual(result["files"], ["web/app.js"])
        requests = [call.args[0] for call in github.call_args_list]
        self.assertEqual(requests[0].get_method(), "GET")
        self.assertIn("/repos/acme/repo/git/ref/heads/main", requests[0].full_url)
        self.assertEqual(
            requests[0].get_header("Authorization"), "Bearer test-token",
        )
        blob = requests[2]
        self.assertEqual(blob.get_method(), "POST")
        self.assertTrue(blob.full_url.endswith("/git/blobs"))
        self.assertEqual(json.loads(blob.data), {
            "content": "const greeting = 'ciao';\n",
            "encoding": "utf-8",
        })

    def test_requires_github_token(self):
        with patch.object(app, "GITHUB_TOKEN", ""):
            with self.assertRaises(RuntimeError) as raised:
                app.execute_app_tool("create_pull_request", {
                    "title": "Aggiorna il codice",
                    "changes": [{"path": "app.py", "content": "# x\n"}],
                })
        self.assertIn("GITHUB_TOKEN", str(raised.exception))

    def test_rejects_private_paths_in_pull_requests(self):
        with (
            patch.object(app, "GITHUB_TOKEN", "test-token"),
            patch.object(app, "GITHUB_REPOSITORY", "acme/repo"),
        ):
            for path in ("config.json", "../outside.py", ".env", ""):
                with self.subTest(path=path):
                    with self.assertRaises(ValueError):
                        app.execute_app_tool("create_pull_request", {
                            "title": "Aggiorna il codice",
                            "changes": [{"path": path, "content": "x"}],
                        })



class TelegramFormattingTests(unittest.TestCase):
    def test_markdown_is_converted_to_telegram_html(self):
        converted = app.markdown_to_telegram_html(
            "# Titolo\n\n"
            "**grassetto** e *corsivo* con `codice`.\n\n"
            "- uno\n- due\n\n"
            "```python\nif a < b and c > d:\n    print('x')\n```\n\n"
            "[Sito](https://example.com/a?b=1&c=2)\n\n"
            "| Nome | Valore |\n| --- | --- |\n| A | 1 |"
        )
        self.assertIn("<b>Titolo</b>", converted)
        self.assertIn("<b>grassetto</b>", converted)
        self.assertIn("<i>corsivo</i>", converted)
        self.assertIn("<code>codice</code>", converted)
        self.assertIn("• uno", converted)
        self.assertIn("<pre>if a &lt; b and c &gt; d:", converted)
        self.assertIn(
            '<a href="https://example.com/a?b=1&amp;c=2">Sito</a>', converted,
        )
        self.assertIn("Nome · Valore", converted)
        self.assertNotIn("**", converted)
        self.assertNotIn("| --- |", converted)

    def test_telegram_message_uses_html_parse_mode(self):
        with patch("app.telegram_api_call") as api_call:
            app._send_telegram_message("token", 42, "**ciao** a tutti")
        api_call.assert_called_once()
        method = api_call.call_args.args[1]
        payload = api_call.call_args.args[2]
        self.assertEqual(method, "sendMessage")
        self.assertEqual(payload["parse_mode"], "HTML")
        self.assertEqual(payload["text"], "<b>ciao</b> a tutti")

    def test_telegram_message_falls_back_to_plain_text(self):
        with patch(
            "app.telegram_api_call",
            side_effect=[RuntimeError("Telegram ha rifiutato la richiesta API."), None],
        ) as api_call:
            app._send_telegram_message("token", 42, "**ciao**")
        self.assertEqual(api_call.call_count, 2)
        self.assertEqual(api_call.call_args.args[2]["text"], "**ciao**")
        self.assertNotIn("parse_mode", api_call.call_args.args[2])

    def test_telegram_commands_are_published_for_the_slash_menu(self):
        with patch("app.telegram_api_call") as api_call:
            published = app.publish_telegram_commands("token")
        self.assertTrue(published)
        api_call.assert_called_once()
        method = api_call.call_args.args[1]
        payload = api_call.call_args.args[2]
        self.assertEqual(method, "setMyCommands")
        names = [item["command"] for item in payload["commands"]]
        self.assertEqual(names, ["oggi", "orario", "data", "compiti", "nuova"])
        for item in payload["commands"]:
            self.assertRegex(item["command"], r"^[a-z0-9_]{1,32}$")
            self.assertLessEqual(len(item["description"]), 256)
            self.assertTrue(item["description"])

    def test_telegram_commands_publication_failure_is_not_fatal(self):
        with patch(
            "app.telegram_api_call",
            side_effect=RuntimeError("Telegram ha rifiutato la richiesta API."),
        ):
            self.assertFalse(app.publish_telegram_commands("token"))
        self.assertFalse(app.publish_telegram_commands(""))

    def test_telegram_message_splits_long_replies(self):
        with patch("app.telegram_api_call") as api_call:
            app._send_telegram_message("token", 42, "riga di prova\n" * 1500)
        self.assertGreater(api_call.call_count, 1)
        for call in api_call.call_args_list:
            self.assertLessEqual(
                len(call.args[2]["text"]), app.MAX_TELEGRAM_REPLY_LENGTH,
            )


class TelegramCommandTests(unittest.TestCase):
    def setUp(self):
        self.saved_config = app.telegram_config.copy()
        self.saved_conversations = dict(app.telegram_conversations)
        self.saved_tasks = [item.copy() for item in app.planner["tasks"]]
        app.telegram_config.clear()
        app.telegram_config.update({
            "token": "123456789:abcdefghijklmnopqrstuvwxyz0123456789",
            "bot_username": "nokk_test_bot",
            "authorized_chats": ["42"],
            "offset": 0,
        })
        app.telegram_conversations.clear()

    def tearDown(self):
        app.telegram_config.clear()
        app.telegram_config.update(self.saved_config)
        app.telegram_conversations.clear()
        app.telegram_conversations.update(self.saved_conversations)
        app.planner["tasks"][:] = self.saved_tasks

    def _send(self, text):
        update = {
            "update_id": 7,
            "message": {
                "chat": {"id": 42, "type": "private"},
                "from": {"id": 42},
                "text": text,
            },
        }
        with patch("app._send_telegram_message") as send_message:
            app._handle_telegram_update(update)
        send_message.assert_called_once()
        return send_message.call_args.args[2]

    def test_nuova_command_clears_the_telegram_chat(self):
        app.telegram_conversations["42"] = [
            {"role": "user", "content": "ciao"},
            {"role": "assistant", "content": "ciao a te"},
        ]
        reply = self._send("/nuova")
        self.assertIn("Chat azzerata", reply)
        self.assertEqual(app.telegram_conversations.get("42", []), [])

    def test_compiti_lists_only_open_assignments_in_date_order(self):
        today = app._local_now().date()
        soon = today + datetime.timedelta(days=2)
        later = today + datetime.timedelta(days=20)
        app.planner["tasks"][:] = [
            {
                "id": "a" * 32,
                "title": "Verifica di matematica",
                "due_date": later.isoformat(),
                "completed": False,
            },
            {
                "id": "b" * 32,
                "title": "Interrogazione di storia",
                "due_date": soon.isoformat(),
                "completed": False,
            },
            {
                "id": "c" * 32,
                "title": "Compito di latino",
                "due_date": None,
                "completed": False,
            },
            {
                "id": "d" * 32,
                "title": "Relazione consegnata",
                "due_date": today.isoformat(),
                "completed": True,
            },
        ]
        reply = self._send("/compiti")
        lines = reply.splitlines()
        soon_label = app.TELEGRAM_WEEKDAYS[soon.weekday()]
        later_label = f"{later.day} {app.TELEGRAM_MONTHS[later.month - 1]}"
        first = lines.index(f"• Interrogazione di storia — {soon_label}")
        second = lines.index(f"• Verifica di matematica — {later_label}")
        self.assertLess(first, second)
        self.assertIn("Senza scadenza:", lines)
        self.assertIn("• Compito di latino", lines)
        self.assertNotIn("Relazione consegnata", reply)

    def test_compiti_labels_today_and_tomorrow(self):
        today = app._local_now().date().isoformat()
        tomorrow = (app._local_now().date() + datetime.timedelta(days=1)).isoformat()
        app.planner["tasks"][:] = [
            {
                "id": "a" * 32,
                "title": "Esercizi di fisica",
                "due_date": today,
                "completed": False,
            },
            {
                "id": "b" * 32,
                "title": "Parafrasi",
                "due_date": tomorrow,
                "completed": False,
            },
        ]
        reply = self._send("/compiti")
        self.assertIn("• Esercizi di fisica — oggi", reply)
        self.assertIn("• Parafrasi — domani", reply)

    def test_compiti_is_empty_when_nothing_is_open(self):
        app.planner["tasks"][:] = []
        reply = self._send("/compiti")
        self.assertIn("Nessun compito o verifica aperta", reply)

    def test_settimana_alias_is_gone(self):
        names = [item["command"] for item in app.TELEGRAM_BOT_COMMANDS]
        self.assertNotIn("settimana", names)


class WeatherConfigTests(unittest.TestCase):
    def test_weather_settings_are_validated(self):
        with self.assertRaises(ValueError):
            app.validate_config(
                "openai", "gpt-4o-mini", "key",
                weather_enabled=True, weather_city="  ",
            )
        with self.assertRaises(ValueError):
            app.validate_config(
                "openai", "gpt-4o-mini", "key", alerts_disk_percent=99.5,
            )
        saved = app.validate_config(
            "openai", "gpt-4o-mini", "key",
            weather_enabled=True,
            weather_city="  Milano  ",
            alerts_enabled=True,
            alerts_disk_percent=85,
            alerts_memory_percent=90,
        )
        self.assertEqual(saved["weather_city"], "Milano")
        self.assertTrue(saved["weather_enabled"])
        self.assertTrue(saved["alerts_enabled"])
        self.assertEqual(saved["alerts_disk_percent"], 85)


class GoogleCalendarToolTests(unittest.TestCase):
    CLIENT_ID = "123456-nokk.apps.googleusercontent.com"
    CLIENT_SECRET = "segreto-client"

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(self._restore)
        app.GOOGLE_CALENDAR_FILE = Path(self.directory.name) / "google_calendar.json"
        self._restore()
        app.GOOGLE_CALENDAR_FILE.unlink(missing_ok=True)
        with app.google_calendar_lock:
            app.google_calendar_config.clear()
            app.google_calendar_config.update(app.default_google_calendar())
            app.google_oauth_states.clear()
            app.google_access_token_cache["token"] = None
            app.google_access_token_cache["expires_at"] = 0.0

    def _restore(self):
        with app.google_calendar_lock:
            app.google_calendar_config.clear()
            app.google_calendar_config.update(app.default_google_calendar())
            app.google_oauth_states.clear()
            app.google_access_token_cache["token"] = None
            app.google_access_token_cache["expires_at"] = 0.0

    def save_credentials(self):
        app.update_google_calendar_settings({
            "client_id": self.CLIENT_ID,
            "client_secret": self.CLIENT_SECRET,
            "calendar_id": "primary",
        })

    def start_flow(self):
        url = app.google_oauth_start("http://127.0.0.1:8000/oauth/google/callback")
        query = dict(parse_qsl(urlsplit(url).query))
        return url, query

    def test_status_does_not_expose_the_secret(self):
        self.save_credentials()
        status = app.google_calendar_status("http://localhost/callback")
        self.assertTrue(status["configured"])
        self.assertFalse(status["connected"])
        self.assertNotIn("client_secret", status)
        self.assertNotIn("refresh_token", status)
        self.assertEqual(status["client_id"], self.CLIENT_ID)
        self.assertEqual(status["redirect_uri"], "http://localhost/callback")

    def test_oauth_start_builds_a_google_consent_url(self):
        self.save_credentials()
        url, query = self.start_flow()
        self.assertTrue(url.startswith(app.GOOGLE_OAUTH_AUTH_URL))
        self.assertEqual(query["client_id"], self.CLIENT_ID)
        self.assertEqual(query["scope"], app.GOOGLE_CALENDAR_SCOPE)
        self.assertEqual(query["access_type"], "offline")
        self.assertEqual(query["response_type"], "code")
        self.assertEqual(
            query["redirect_uri"],
            "http://127.0.0.1:8000/oauth/google/callback",
        )
        self.assertIn(query["state"], app.google_oauth_states)

    def test_oauth_start_requires_credentials(self):
        with self.assertRaises(ValueError):
            app.google_oauth_start("http://127.0.0.1:8000/oauth/google/callback")

    def test_callback_stores_the_refresh_token_once(self):
        self.save_credentials()
        _, query = self.start_flow()
        payload = {
            "access_token": "access",
            "refresh_token": "refresh",
            "expires_in": 3600,
        }
        with patch("app.urlopen", return_value=FakeResponse(payload)) as call:
            status = app.google_oauth_complete(
                "codice", query["state"],
                "http://127.0.0.1:8000/oauth/google/callback",
            )
        self.assertTrue(status["connected"])
        body = call.call_args.args[0].data.decode("utf-8")
        self.assertIn("grant_type=authorization_code", body)
        self.assertIn("code=codice", body)
        saved = json.loads(app.GOOGLE_CALENDAR_FILE.read_text(encoding="utf-8"))
        self.assertEqual(saved["refresh_token"], "refresh")
        with self.assertRaises(ValueError):
            app.google_oauth_complete(
                "codice", query["state"],
                "http://127.0.0.1:8000/oauth/google/callback",
            )

    def test_changing_the_client_credentials_disconnects(self):
        self.save_credentials()
        with app.google_calendar_lock:
            app.google_calendar_config["refresh_token"] = "refresh"
        app.update_google_calendar_settings({"client_secret": "nuovo-segreto"})
        status = app.google_calendar_status("http://localhost/callback")
        self.assertFalse(status["connected"])

    def test_list_events_uses_the_calendar_api(self):
        with app.google_calendar_lock:
            app.google_calendar_config.update({
                "client_id": self.CLIENT_ID,
                "client_secret": self.CLIENT_SECRET,
                "refresh_token": "refresh",
            })
        token_payload = {"access_token": "access", "expires_in": 3600}
        events_payload = {"items": [{
            "id": "abc_123",
            "summary": "Dentista",
            "start": {"dateTime": "2026-11-06T09:00:00+01:00"},
            "end": {"dateTime": "2026-11-06T10:00:00+01:00"},
            "location": "Studio",
            "htmlLink": "https://calendar.google.com/event?eid=abc",
        }]}
        with patch(
            "app.urlopen",
            side_effect=[FakeResponse(token_payload), FakeResponse(events_payload)],
        ) as call:
            result = app.execute_app_tool("google_calendar", {
                "action": "list",
                "time_min": "2026-11-06T00:00",
                "time_max": "2026-11-07T00:00",
                "max_results": 5,
            })
        self.assertTrue(result["ok"])
        self.assertEqual(result["calendar"], "primary")
        self.assertEqual(result["events"], [{
            "id": "abc_123",
            "title": "Dentista",
            "start": "2026-11-06T09:00:00+01:00",
            "end": "2026-11-06T10:00:00+01:00",
            "all_day": False,
            "location": "Studio",
            "description": "",
            "html_link": "https://calendar.google.com/event?eid=abc",
            "calendar": "primary",
        }])
        api_request = call.call_args_list[1].args[0]
        self.assertIn("/calendars/primary/events", api_request.full_url)
        self.assertIn("singleEvents=true", api_request.full_url)
        self.assertIn("timeMin=2026-11-06T00", api_request.full_url)
        headers = {key.lower(): value for key, value in api_request.header_items()}
        self.assertEqual(headers["authorization"], "Bearer access")

    def test_create_event_defaults_to_one_hour(self):
        with app.google_calendar_lock:
            app.google_calendar_config.update({
                "client_id": self.CLIENT_ID,
                "client_secret": self.CLIENT_SECRET,
                "refresh_token": "refresh",
            })
        token_payload = {"access_token": "access", "expires_in": 3600}
        created = {
            "id": "nuovo_1",
            "summary": "Riunione",
            "start": {"dateTime": "2026-11-06T15:00:00+01:00"},
            "end": {"dateTime": "2026-11-06T16:00:00+01:00"},
        }
        with patch(
            "app.urlopen",
            side_effect=[FakeResponse(token_payload), FakeResponse(created)],
        ) as call:
            result = app.execute_app_tool("google_calendar", {
                "action": "create",
                "title": "Riunione",
                "start": "2026-11-06T15:00",
                "description": "Sala 2",
            })
        self.assertEqual(result["event"]["title"], "Riunione")
        body = json.loads(call.call_args_list[1].args[0].data.decode("utf-8"))
        self.assertEqual(body["summary"], "Riunione")
        self.assertEqual(body["description"], "Sala 2")
        self.assertTrue(body["start"]["dateTime"].startswith("2026-11-06T15:00"))
        self.assertTrue(body["end"]["dateTime"].startswith("2026-11-06T16:00"))

    def test_delete_event_validates_the_identifier(self):
        with self.assertRaises(ValueError):
            app.google_calendar_delete("../../altro")
        with app.google_calendar_lock:
            app.google_calendar_config.update({
                "client_id": self.CLIENT_ID,
                "client_secret": self.CLIENT_SECRET,
                "refresh_token": "refresh",
            })
        token_payload = {"access_token": "access", "expires_in": 3600}
        with patch(
            "app.urlopen",
            side_effect=[FakeResponse(token_payload), FakeResponse({})],
        ) as call:
            result = app.google_calendar_delete("abc_123")
        self.assertEqual(result, {"ok": True, "id": "abc_123"})
        self.assertEqual(call.call_args_list[1].args[0].get_method(), "DELETE")

    def test_tool_reports_when_calendar_is_not_connected(self):
        with self.assertRaises(RuntimeError) as raised:
            app.execute_app_tool("google_calendar", {"action": "list"})
        self.assertIn("non è collegato", str(raised.exception))

    def test_authorization_rejection_is_explained(self):
        with app.google_calendar_lock:
            app.google_calendar_config.update({
                "client_id": self.CLIENT_ID,
                "client_secret": self.CLIENT_SECRET,
                "refresh_token": "refresh",
            })
        error = HTTPError(
            "https://oauth2.googleapis.com/token", 400, "Bad Request", {},
            io.BytesIO(json.dumps({
                "error": "invalid_grant",
                "error_description": "Token has been expired or revoked.",
            }).encode("utf-8")),
        )
        with patch("app.urlopen", side_effect=error):
            with self.assertRaises(RuntimeError) as raised:
                app.google_calendar_access_token()
        self.assertIn("revocato", str(raised.exception))


class WebSearchToolTests(unittest.TestCase):
    def setUp(self):
        app.SEARCH_CACHE.clear()

    def test_search_falls_back_to_bing_when_duckduckgo_is_blocked(self):
        challenge = FakeStatusHtmlResponse(
            "<html><body>Please complete the following challenge</body></html>",
            status=202,
        )
        target = base64.urlsafe_b64encode(
            b"https://example.com/roma"
        ).decode("utf-8")
        bing_page = f"""
        <ol id="b_results">
          <li class="b_algo" data-id iid=SERP.1>
            <h2><a target="_blank" href="https://www.bing.com/ck/a?!&amp;&amp;p=abc&amp;u=a1{target}&amp;ntb=1">
              Meteo <strong>Roma</strong>
            </a></h2>
            <div class="b_caption"><p>Sole e 24 gradi.</p></div>
          </li>
          <li class="b_algo" data-id iid=SERP.2>
            <h2><a href="https://www.example.org/altro">Altro risultato</a></h2>
            <p>Secondo estratto.</p>
          </li>
        </ol>
        """
        with (
            patch.multiple(
                app, EXA_API_KEY="", TAVILY_API_KEY="", SERPER_API_KEY="",
            ),
            patch(
                "app.urlopen",
                side_effect=[
                    challenge, FakeHtmlResponse("<html></html>"),
                    FakeHtmlResponse(bing_page),
                ],
            ) as search_call,
        ):
            result = app.execute_app_tool("web_search", {
                "query": " meteo Roma ",
                "num_results": 3,
            })
        self.assertEqual(result["provider"], "bing")
        self.assertEqual(result["results"], [
            {
                "title": "Meteo Roma",
                "url": "https://example.com/roma",
                "snippet": "Sole e 24 gradi.",
            },
            {
                "title": "Altro risultato",
                "url": "https://www.example.org/altro",
                "snippet": "Secondo estratto.",
            },
        ])
        bing_request = search_call.call_args_list[2].args[0]
        self.assertTrue(bing_request.full_url.startswith(app.BING_SEARCH_URL))
        self.assertIn("q=meteo+Roma", bing_request.full_url)

    def test_search_reports_antibot_challenge_when_nothing_answers(self):
        challenge = FakeStatusHtmlResponse("<html>challenge</html>", status=202)
        with (
            patch.multiple(
                app, EXA_API_KEY="", TAVILY_API_KEY="", SERPER_API_KEY="",
            ),
            patch(
                "app.urlopen",
                side_effect=[challenge] + [FakeHtmlResponse("<html></html>")] * 4,
            ),
            patch("app.time.sleep"),
        ):
            with self.assertRaises(RuntimeError) as raised:
                app.execute_app_tool("web_search", {"query": "meteo Roma"})
        self.assertIn("anti-bot", str(raised.exception))
        self.assertIn("Bing", str(raised.exception))

    def test_bing_retries_another_variant_when_first_answer_is_empty(self):
        challenge = FakeStatusHtmlResponse("<html>challenge</html>", status=202)
        empty_page = FakeHtmlResponse("<html>Non sono disponibili risultati</html>")
        result_page = FakeHtmlResponse("""
        <ol id="b_results">
          <li class="b_algo">
            <h2><a href="https://example.com/roma">Meteo Roma</a></h2>
            <p>Sole e 24 gradi.</p>
          </li>
        </ol>
        """)
        with (
            patch.multiple(
                app, EXA_API_KEY="", TAVILY_API_KEY="", SERPER_API_KEY="",
            ),
            patch(
                "app.urlopen",
                side_effect=[
                    challenge, empty_page, empty_page, result_page,
                ],
            ) as search_call,
            patch("app.time.sleep") as sleep,
        ):
            result = app.execute_app_tool("web_search", {"query": "meteo Roma"})
        self.assertEqual(result["provider"], "bing")
        self.assertEqual(result["results"][0]["url"], "https://example.com/roma")
        self.assertEqual(search_call.call_count, 4)
        second_bing = search_call.call_args_list[3].args[0].full_url
        self.assertIn("cc=IT", second_bing)
        sleep.assert_called_once()

    def test_bing_uses_rss_endpoint_when_html_stays_empty(self):
        challenge = FakeStatusHtmlResponse("<html>challenge</html>", status=202)
        empty_page = FakeHtmlResponse("<html>Non sono disponibili risultati</html>")
        rss = FakeHtmlResponse(
            '<?xml version="1.0" encoding="utf-8" ?>'
            '<rss version="2.0"><channel><title>Bing: meteo Roma</title>'
            '<item><title>Meteo Roma</title><link>https://example.com/roma</link>'
            '<description>Sole &amp; 24 gradi.</description></item>'
            '</channel></rss>'
        )
        with (
            patch.multiple(
                app, EXA_API_KEY="", TAVILY_API_KEY="", SERPER_API_KEY="",
            ),
            patch(
                "app.urlopen",
                side_effect=[challenge, empty_page, empty_page, empty_page, rss],
            ) as search_call,
            patch("app.time.sleep"),
        ):
            result = app.execute_app_tool("web_search", {"query": "meteo Roma"})
        self.assertEqual(result["provider"], "bing")
        self.assertEqual(result["results"], [{
            "title": "Meteo Roma",
            "url": "https://example.com/roma",
            "snippet": "Sole & 24 gradi.",
        }])
        self.assertIn("format=rss", search_call.call_args_list[4].args[0].full_url)

    def test_search_falls_back_to_wikipedia_when_every_engine_is_blocked(self):
        challenge = FakeStatusHtmlResponse("<html>challenge</html>", status=202)
        empty_page = FakeHtmlResponse("<html>Non sono disponibili risultati</html>")
        payload = {
            "query": {"search": [{
                "title": "Roma",
                "snippet": '<span class="searchmatch">Roma</span> è la capitale.',
            }]},
        }
        with (
            patch.multiple(
                app, EXA_API_KEY="", TAVILY_API_KEY="", SERPER_API_KEY="",
            ),
            patch(
                "app.urlopen",
                side_effect=[
                    challenge, empty_page, empty_page, empty_page,
                    empty_page, FakeResponse(payload),
                ],
            ) as search_call,
            patch("app.time.sleep"),
        ):
            result = app.execute_app_tool("web_search", {"query": "meteo Roma"})
        self.assertEqual(result["provider"], "wikipedia")
        self.assertEqual(result["results"], [{
            "title": "Roma",
            "url": "https://it.wikipedia.org/wiki/Roma",
            "snippet": "Roma è la capitale.",
        }])
        self.assertIn("notizie aggiornate", result["note"])
        self.assertIn(
            "it.wikipedia.org", search_call.call_args_list[5].args[0].full_url,
        )

    def test_unexpected_provider_error_does_not_stop_the_chain(self):
        page = FakeHtmlResponse("""
        <ol id="b_results">
          <li class="b_algo">
            <h2><a href="https://example.com/roma">Meteo Roma</a></h2>
            <p>Sole e 24 gradi.</p>
          </li>
        </ol>
        """)
        with (
            patch.multiple(
                app, EXA_API_KEY="test-exa", TAVILY_API_KEY="", SERPER_API_KEY="",
            ),
            patch("app._exa_search", side_effect=KeyError("results")),
            patch(
                "app.urlopen",
                side_effect=[
                    FakeHtmlResponse("<html></html>"),
                    FakeHtmlResponse("<html></html>"),
                    page,
                ],
            ),
            patch("app.time.sleep"),
        ):
            result = app.execute_app_tool("web_search", {"query": "meteo Roma"})
        self.assertEqual(result["provider"], "bing")
        self.assertEqual(result["results"][0]["url"], "https://example.com/roma")

    def test_search_works_without_any_api_key(self):
        page = """
        <div class="result">
          <a class="result__a"
             href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Froma">
            Meteo Roma
          </a>
          <a class="result__snippet">Sole e 24 gradi.</a>
        </div>
        """
        with (
            patch.multiple(
                app, EXA_API_KEY="", TAVILY_API_KEY="", SERPER_API_KEY="",
            ),
            patch("app.urlopen", return_value=FakeHtmlResponse(page)) as search_call,
        ):
            result = app.execute_app_tool("web_search", {
                "query": " meteo Roma ",
                "num_results": 3,
            })
        self.assertEqual(result["provider"], "duckduckgo")
        self.assertEqual(result["results"], [{
            "title": "Meteo Roma",
            "url": "https://example.com/roma",
            "snippet": "Sole e 24 gradi.",
        }])
        request = search_call.call_args.args[0]
        self.assertEqual(request.full_url, app.DUCKDUCKGO_SEARCH_URL)
        self.assertIn(b"q=meteo+Roma", request.data)

    def test_repeated_query_is_served_from_the_cache(self):
        page = """
        <div class="result">
          <a class="result__a"
             href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Ftorino">
            Meteo Torino
          </a>
          <a class="result__snippet">Sole e 22 gradi.</a>
        </div>
        """
        with (
            patch.multiple(
                app, EXA_API_KEY="", TAVILY_API_KEY="", SERPER_API_KEY="",
            ),
            patch("app.urlopen", return_value=FakeHtmlResponse(page)) as search_call,
        ):
            first = app.execute_app_tool("web_search", {"query": "meteo Torino"})
            second = app.execute_app_tool("web_search", {"query": "  meteo   Torino "})
        self.assertEqual(search_call.call_count, 1)
        self.assertEqual(first["results"], second["results"])
        self.assertIn("non ripetuta", second["note"].lower())

    def test_search_uses_exa_when_key_is_configured(self):
        payload = {
            "results": [{
                "title": "Meteo Roma",
                "url": "https://example.com/roma",
                "text": "Sole e 24 gradi.",
            }],
        }
        with (
            patch.multiple(
                app, EXA_API_KEY="test-exa", TAVILY_API_KEY="", SERPER_API_KEY="",
            ),
            patch("app.urlopen", return_value=FakeResponse(payload)) as search_call,
        ):
            result = app.execute_app_tool("web_search", {
                "query": " meteo Roma ",
                "num_results": 3,
            })
        self.assertEqual(result["provider"], "exa")
        self.assertEqual(result["results"][0]["url"], "https://example.com/roma")
        request = search_call.call_args.args[0]
        self.assertEqual(request.full_url, app.EXA_SEARCH_URL)
        headers = {key.lower(): value for key, value in request.header_items()}
        self.assertEqual(headers["x-api-key"], "test-exa")
        self.assertEqual(json.loads(request.data)["query"], "meteo Roma")

    def test_search_falls_back_to_yahoo_when_other_engines_are_blocked(self):
        challenge = FakeStatusHtmlResponse("<html>challenge</html>", status=202)
        yahoo_page = """
        <ol>
          <li><div class="dd algo algo-sr relsrch richAlgo">
            <div class="compTitle">
              <a href="https://r.search.yahoo.com/_ylt=abc/RV=2/RE=1/RO=10/RU=https%3a%2f%2fexample.com%2froma/RK=2/RS=x">
                <h3 class="title"><span>Meteo Roma</span></h3>
              </a>
            </div>
            <div class="compText aAbs">
              <p><span>Oggi</span> Sole e 24 gradi.</p>
            </div>
          </div></li>
        </ol>
        """
        with (
            patch.multiple(
                app, EXA_API_KEY="", TAVILY_API_KEY="", SERPER_API_KEY="",
            ),
            patch(
                "app.urlopen",
                side_effect=[challenge, FakeHtmlResponse(yahoo_page)],
            ) as search_call,
        ):
            result = app.execute_app_tool("web_search", {"query": "meteo Roma"})
        self.assertEqual(result["provider"], "yahoo")
        self.assertEqual(result["results"], [{
            "title": "Meteo Roma",
            "url": "https://example.com/roma",
            "snippet": "Oggi Sole e 24 gradi.",
        }])
        self.assertTrue(
            search_call.call_args_list[1].args[0].full_url.startswith(
                app.YAHOO_SEARCH_URL
            )
        )

    def test_bing_results_for_another_query_are_rejected(self):
        challenge = FakeStatusHtmlResponse("<html>challenge</html>", status=202)
        empty_page = FakeHtmlResponse("<html></html>")
        unrelated_page = FakeHtmlResponse("""
        <ol id="b_results">
          <li class="b_algo">
            <h2><a href="https://www.toyota.it/">Toyota Motor Italia</a></h2>
            <p>Gamma Toyota e promozioni.</p>
          </li>
        </ol>
        """)
        empty_rss = FakeHtmlResponse(
            '<?xml version="1.0" encoding="utf-8" ?>'
            "<rss version=\"2.0\"><channel><title>Bing</title></channel></rss>"
        )
        wiki = FakeResponse({"query": {"search": [{
            "title": "Roma",
            "snippet": "Roma è la capitale d'Italia.",
        }]}})
        with (
            patch.multiple(
                app, EXA_API_KEY="", TAVILY_API_KEY="", SERPER_API_KEY="",
            ),
            patch(
                "app.urlopen",
                side_effect=[
                    challenge, empty_page, unrelated_page, unrelated_page,
                    empty_rss, wiki,
                ],
            ),
            patch("app.time.sleep"),
        ):
            result = app.execute_app_tool("web_search", {"query": "meteo Roma"})
        self.assertEqual(result["provider"], "wikipedia")
        self.assertEqual(result["results"][0]["url"], "https://it.wikipedia.org/wiki/Roma")

    def test_search_validates_query_and_result_count(self):
        for arguments in (
            {"query": ""},
            {"query": "x" * (app.MAX_SEARCH_QUERY_LENGTH + 1)},
            {"query": "ok", "num_results": 0},
            {"query": "ok", "num_results": app.MAX_SEARCH_RESULTS + 1},
        ):
            with self.subTest(arguments=arguments):
                with self.assertRaises(ValueError):
                    app.execute_app_tool("web_search", arguments)


class ToolLimitTests(unittest.TestCase):
    CONFIG = {"provider": "openai", "model": "gpt-test", "api_key": "chiave"}

    def test_final_answer_is_requested_without_tools(self):
        payload = {"choices": [{"message": {"content": "Ecco cosa ho trovato."}}]}
        with patch("app.urlopen", return_value=FakeResponse(payload)) as request_call:
            reply = app._final_answer_without_tools(self.CONFIG, [], None)
        self.assertEqual(reply, "Ecco cosa ho trovato.")
        body = json.loads(request_call.call_args.args[0].data)
        self.assertFalse(body.get("tools"))

    def test_final_answer_falls_back_when_the_provider_fails(self):
        with patch("app.urlopen", side_effect=OSError("rete assente")):
            reply = app._final_answer_without_tools(self.CONFIG, [], None)
        self.assertEqual(reply, app.TOOL_LIMIT_REPLY)


if __name__ == "__main__":
    unittest.main()
