import base64
import io
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import app


class FakeTranscriptionResponse:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class TranscriptionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        base = Path(cls.directory.name)
        app.CONFIG_FILE = base / "config.json"
        app.WORKFLOWS_FILE = base / "workflows.json"
        app.PLANNER_FILE = base / "planner.json"
        app.TELEGRAM_FILE = base / "telegram.json"
        app.GOOGLE_CALENDAR_FILE = base / "google_calendar.json"
        app.API_FILE = base / "api.json"
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), app.AppHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.directory.cleanup()

    def setUp(self):
        with app.config_lock:
            app.config.update(app.default_config())
            app.config.update({
                "provider": "openai",
                "model": "gpt-4o-mini",
                "api_key": "sk-chiave-di-prova",
                "base_url": "",
            })

    def request_json(self, path, payload):
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request) as response:
            return json.loads(response.read())

    def post(self, payload):
        request = Request(
            f"{self.base_url}/api/transcribe",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request) as response:
                return response.status, json.loads(response.read())
        except HTTPError as error:
            return error.code, json.loads(error.read() or b"{}")

    def test_recorded_audio_is_transcribed_by_the_provider(self):
        audio = base64.b64encode(b"RIFF....WAVE").decode("ascii")
        with patch(
            "app.urlopen",
            return_value=FakeTranscriptionResponse({"text": "Ciao dal microfono"}),
        ) as provider_call:
            status, payload = self.post({
                "audio": audio,
                "mime_type": "audio/mp4",
            })
        self.assertEqual(status, 200)
        self.assertEqual(payload["text"], "Ciao dal microfono")
        request = provider_call.call_args.args[0]
        self.assertTrue(request.full_url.endswith("/audio/transcriptions"))
        self.assertIn(b"whisper-1", request.data)
        self.assertIn(b"audio/mp4", request.data)

    def test_openrouter_gets_the_json_audio_payload_it_expects(self):
        with app.config_lock:
            app.config.update({
                "provider": "openrouter",
                "model": "openrouter/free",
                "api_key": "sk-or-di-prova",
            })
        audio = b"RIFF....WAVE"
        with patch(
            "app.urlopen",
            return_value=FakeTranscriptionResponse({"text": "Ciao"}),
        ) as provider_call:
            status, payload = self.post({
                "audio": base64.b64encode(audio).decode("ascii"),
                "mime_type": "audio/mp4",
            })
        self.assertEqual(status, 200)
        self.assertEqual(payload["text"], "Ciao")
        request = provider_call.call_args.args[0]
        self.assertEqual(request.get_header("Content-type"), "application/json")
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["model"], "openai/whisper-large-v3")
        self.assertEqual(body["input_audio"]["format"], "m4a")
        self.assertEqual(body["input_audio"]["data"], base64.b64encode(audio).decode("ascii"))
        self.assertNotIn(b"multipart/form-data", request.data)

    def test_audio_formats_map_to_the_right_file_extension(self):
        for mime_type, extension in (
            ("audio/wav", "wav"),
            ("audio/ogg", "ogg"),
            ("audio/mpeg", "mp3"),
            ("audio/webm", "webm"),
        ):
            with self.subTest(mime_type=mime_type), patch(
                "app.urlopen",
                return_value=FakeTranscriptionResponse({"text": "Ciao"}),
            ) as provider_call:
                status, _payload = self.post({
                    "audio": base64.b64encode(b"RIFF....WAVE").decode("ascii"),
                    "mime_type": mime_type,
                })
                self.assertEqual(status, 200)
                self.assertIn(
                    f'filename="voce.{extension}"'.encode("utf-8"),
                    provider_call.call_args.args[0].data,
                )

    def test_a_missing_audio_route_falls_back_to_a_saved_provider(self):
        with app.config_lock:
            app.config.update({
                "provider": "custom",
                "model": "gpt-4o-mini",
                "base_url": "https://gateway.example/v1",
                "api_key": "sk-gateway",
                "api_keys": {"openai": "sk-openai"},
            })
        missing_route = HTTPError(
            "https://gateway.example/v1/audio/transcriptions", 404,
            "Not Found", {}, io.BytesIO(b'{"error":"route not found"}'),
        )
        with patch(
            "app.urlopen",
            side_effect=[missing_route, FakeTranscriptionResponse({"text": "Ciao"})],
        ) as provider_call:
            status, payload = self.post({
                "audio": base64.b64encode(b"RIFF....WAVE").decode("ascii"),
                "mime_type": "audio/webm",
            })
        self.assertEqual(status, 200)
        self.assertEqual(payload["text"], "Ciao")
        self.assertEqual(provider_call.call_count, 2)
        fallback = provider_call.call_args_list[1].args[0]
        self.assertEqual(
            fallback.full_url, "https://api.openai.com/v1/audio/transcriptions",
        )
        self.assertIn(b"whisper-1", fallback.data)
        self.assertIn(b"voce.webm", fallback.data)

    def test_a_missing_route_without_fallback_names_the_endpoint(self):
        with app.config_lock:
            app.config.update({
                "provider": "custom",
                "model": "gpt-4o-mini",
                "base_url": "https://gateway.example/v1",
                "api_key": "sk-gateway",
                "api_keys": {},
            })
        missing_route = HTTPError(
            "https://gateway.example/v1/audio/transcriptions", 404,
            "Not Found", {}, io.BytesIO(b"route not found"),
        )
        with patch("app.urlopen", side_effect=missing_route):
            status, payload = self.post({
                "audio": base64.b64encode(b"RIFF....WAVE").decode("ascii"),
                "mime_type": "audio/wav",
            })
        self.assertEqual(status, 400)
        self.assertIn("HTTP 404", payload["error"])
        self.assertIn("gateway.example/v1/audio/transcriptions", payload["error"])

    def test_a_refusal_reports_the_provider_status(self):
        error = HTTPError(
            "https://example.test/audio/transcriptions", 400,
            "Bad Request", {}, io.BytesIO(b'{"error":"bad audio"}'),
        )
        with patch("app.urlopen", side_effect=error):
            status, payload = self.post({
                "audio": base64.b64encode(b"RIFF....WAVE").decode("ascii"),
                "mime_type": "audio/wav",
            })
        self.assertEqual(status, 400)
        self.assertIn("HTTP 400", payload["error"])
        self.assertIn("bad audio", payload["error"])

    def test_an_unsupported_format_is_refused(self):
        status, payload = self.post({
            "audio": base64.b64encode(b"ciao").decode("ascii"),
            "mime_type": "video/mp4",
        })
        self.assertEqual(status, 400)
        self.assertIn("audio", payload["error"])

    def test_a_provider_without_transcription_is_explained(self):
        with app.config_lock:
            app.config["provider"] = "google"
        status, payload = self.post({
            "audio": base64.b64encode(b"RIFF....WAVE").decode("ascii"),
            "mime_type": "audio/mp4",
        })
        self.assertEqual(status, 400)
        self.assertIn("trascrizione", payload["error"])

    def test_transcription_needs_a_key(self):
        with app.config_lock:
            app.config["api_key"] = ""
        status, payload = self.post({
            "audio": base64.b64encode(b"RIFF....WAVE").decode("ascii"),
            "mime_type": "audio/mp4",
        })
        self.assertEqual(status, 400)
        self.assertIn("chiave API", payload["error"])

    def test_the_transcription_model_can_be_configured(self):
        with app.config_lock:
            app.config["transcribe_model"] = "whisper-large-v3"
        audio = base64.b64encode(b"RIFF....WAVE").decode("ascii")
        with patch(
            "app.urlopen",
            return_value=FakeTranscriptionResponse({"text": "Ciao"}),
        ) as provider_call:
            status, _payload = self.post({"audio": audio, "mime_type": "audio/mp4"})
        self.assertEqual(status, 200)
        self.assertIn(b"whisper-large-v3", provider_call.call_args.args[0].data)

    def test_voice_settings_are_saved_and_validated(self):
        saved = self.request_json("/api/config", {
            "wake_window_seconds": 7,
            "transcribe_model": "whisper-1",
        })
        self.assertTrue(saved["ok"])
        current = self.get_config()
        self.assertEqual(current["wake_window_seconds"], 7)
        self.assertEqual(current["transcribe_model"], "whisper-1")
        with self.assertRaises(HTTPError) as raised:
            self.request_json("/api/config", {"wake_window_seconds": 30})
        self.assertEqual(raised.exception.code, 400)
        payload = json.loads(raised.exception.read())
        self.assertIn("secondi", payload["error"])
        with self.assertRaises(HTTPError):
            self.request_json("/api/config", {"transcribe_model": "modello con spazi"})

    def get_config(self):
        with urlopen(f"{self.base_url}/api/config") as response:
            return json.loads(response.read())
