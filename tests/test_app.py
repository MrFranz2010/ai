import io
import base64
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


class AppRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config_directory = tempfile.TemporaryDirectory()
        app.CONFIG_FILE = Path(cls.config_directory.name) / "config.json"
        app.WORKFLOWS_FILE = Path(cls.config_directory.name) / "workflows.json"
        app.PLANNER_FILE = Path(cls.config_directory.name) / "planner.json"
        app.TELEGRAM_FILE = Path(cls.config_directory.name) / "telegram.json"
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
        self.assertIn("settings-section", assets["/"])
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
        }])
        self.assertEqual(app.load_workflows_file(), updated)

        deleted = self.request_json("/api/workflows", {
            "action": "delete",
            "id": workflow_id,
        })["workflows"]
        self.assertEqual(deleted, [])
        if os.name != "nt":
            self.assertEqual(app.WORKFLOWS_FILE.stat().st_mode & 0o777, 0o600)

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
            "terminal_enabled": False,
            "approval_mode": "manual",
            "workspace": str(Path(app.APP_DIR).resolve()),
            "system_prompt": "Rispondi in italiano e sii conciso.",
            "wake_phrase": "Nok",
            "tts_auto_play": True,
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

    def test_public_config_reports_search_configuration(self):
        with patch.object(app, "SERPER_API_KEY", "test-serper-key"):
            with urlopen(f"{self.base_url}/api/config") as response:
                public_config = json.loads(response.read())
        self.assertTrue(public_config["search_configured"])

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



class GoogleSearchToolTests(unittest.TestCase):
    def test_search_requires_api_key(self):
        with patch.object(app, "SERPER_API_KEY", ""):
            with self.assertRaises(RuntimeError) as raised:
                app.execute_app_tool(
                    "google_search", {"query": "meteo Roma"},
                )
        self.assertIn("SERPER_API_KEY", str(raised.exception))

    def test_search_returns_google_results(self):
        payload = {
            "organic": [
                {
                    "title": "Meteo Roma",
                    "link": "https://example.com/roma",
                    "snippet": "Sole e 24 gradi.",
                },
                {"title": "Senza link", "snippet": "Da ignorare."},
            ],
        }
        with (
            patch.object(app, "SERPER_API_KEY", "test-serper-key"),
            patch("app.urlopen", return_value=FakeResponse(payload)) as search_call,
        ):
            result = app.execute_app_tool("google_search", {
                "query": " meteo Roma ",
                "num_results": 3,
            })
        self.assertEqual(result["results"], [{
            "title": "Meteo Roma",
            "url": "https://example.com/roma",
            "snippet": "Sole e 24 gradi.",
        }])
        request = search_call.call_args.args[0]
        self.assertEqual(request.full_url, app.SERPER_SEARCH_URL)
        headers = {key.lower(): value for key, value in request.header_items()}
        self.assertEqual(headers["x-api-key"], "test-serper-key")
        self.assertEqual(
            json.loads(request.data), {"q": "meteo Roma", "num": 3},
        )

    def test_search_validates_query_and_result_count(self):
        with patch.object(app, "SERPER_API_KEY", "test-serper-key"):
            for arguments in (
                {"query": ""},
                {"query": "x" * (app.MAX_SEARCH_QUERY_LENGTH + 1)},
                {"query": "ok", "num_results": 0},
                {"query": "ok", "num_results": app.MAX_SEARCH_RESULTS + 1},
            ):
                with self.subTest(arguments=arguments):
                    with self.assertRaises(ValueError):
                        app.execute_app_tool("google_search", arguments)


if __name__ == "__main__":
    unittest.main()
