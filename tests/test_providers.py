import json
import tempfile
import unittest

from pathlib import Path

from app import (
    build_provider_request,
    extract_reply,
    is_read_only_command,
    parse_tool_response,
)

OPENAI_COMPATIBLE = {
    "openai", "openrouter", "mistral", "groq", "deepseek", "xai", "custom",
}
IMAGE_PROVIDERS = {"openai", "openrouter", "mistral", "xai", "custom"}
PROVIDER_CASES = [
    ("openai", "gpt-4o-mini", {}),
    ("anthropic", "claude-model", {}),
    ("google", "gemini-model", {}),
    ("openrouter", "openrouter/free", {}),
    ("mistral", "mistral-small-latest", {}),
    ("groq", "llama-3.3-70b-versatile", {}),
    ("deepseek", "deepseek-chat", {}),
    ("xai", "grok-2-latest", {}),
    ("custom", "my-model", {"base_url": "https://llm.example.com/v1"}),
]
IMAGE_CASES = [
    ("openai", "gpt-4o-mini", {}),
    ("anthropic", "claude-model", {}),
    ("google", "gemini-model", {}),
    ("openrouter", "openrouter/free", {}),
    ("mistral", "mistral-small-latest", {}),
    ("custom", "my-model", {"base_url": "https://llm.example.com/v1"}),
]


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.messages = [
            {"role": "system", "content": "Sei conciso."},
            {"role": "user", "content": "Ciao"},
        ]

    def test_openai_request(self):
        request = build_provider_request(
            "openai", "gpt-4o-mini", "secret", self.messages
        )
        self.assertEqual(request.full_url, "https://api.openai.com/v1/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer secret")
        self.assertEqual(json.loads(request.data)["messages"], self.messages)

    def test_anthropic_request_separates_system_prompt(self):
        request = build_provider_request(
            "anthropic", "claude-model", "secret", self.messages
        )
        payload = json.loads(request.data)
        self.assertEqual(payload["system"], "Sei conciso.")
        self.assertEqual(payload["messages"], [{"role": "user", "content": "Ciao"}])
        self.assertEqual(request.get_header("X-api-key"), "secret")

    def test_google_request_separates_system_prompt(self):
        request = build_provider_request(
            "google", "gemini-model", "secret", self.messages
        )
        payload = json.loads(request.data)
        self.assertIn("x-goog-api-key", {key.lower(): value for key, value in request.header_items()})
        self.assertEqual(payload["systemInstruction"]["parts"][0]["text"], "Sei conciso.")
        self.assertEqual(payload["contents"][0]["role"], "user")

    def test_openrouter_request_uses_free_router(self):
        request = build_provider_request(
            "openrouter", "openrouter/free", "secret", self.messages
        )
        self.assertEqual(
            request.full_url,
            "https://openrouter.ai/api/v1/chat/completions",
        )
        self.assertEqual(request.get_header("Authorization"), "Bearer secret")
        self.assertEqual(json.loads(request.data)["model"], "openrouter/free")
        self.assertEqual(json.loads(request.data)["messages"], self.messages)

    def test_application_tools_are_declared_for_every_provider(self):
        for provider, model, extra in PROVIDER_CASES:
            with self.subTest(provider=provider):
                request = build_provider_request(
                    provider,
                    model,
                    "secret",
                    self.messages,
                    enable_app_tools=True,
                    **extra,
                )
                payload = json.loads(request.data)
                if provider in OPENAI_COMPATIBLE:
                    names = [
                        tool["function"]["name"] for tool in payload["tools"]
                    ]
                elif provider == "anthropic":
                    names = [tool["name"] for tool in payload["tools"]]
                else:
                    names = [
                        tool["name"]
                        for tool in payload["tools"][0]["functionDeclarations"]
                    ]
                self.assertEqual(names, [
                    "get_app_data", "manage_planner_item", "manage_workflow",
                    "web_search", "fetch_url", "list_repository_files",
                    "read_repository_file", "create_pull_request",
                ])
                if provider == "google":
                    task_tool = payload["tools"][0]["functionDeclarations"][1]
                    self.assertEqual(
                        task_tool["parameters"]["properties"]["completed"]["type"],
                        "BOOLEAN",
                    )

    def test_custom_system_prompt_is_added_for_all_providers(self):
        for provider, model, extra in PROVIDER_CASES:
            with self.subTest(provider=provider):
                request = build_provider_request(
                    provider,
                    model,
                    "secret",
                    self.messages,
                    system_prompt="Rispondi in italiano.",
                    **extra,
                )
                payload = json.loads(request.data)
                if provider in OPENAI_COMPATIBLE:
                    system = "\n".join(
                        message["content"]
                        for message in payload["messages"]
                        if message["role"] == "system"
                    )
                elif provider == "anthropic":
                    system = payload["system"]
                else:
                    system = payload["systemInstruction"]["parts"][0]["text"]
                self.assertIn("Rispondi in italiano.", system)
                self.assertIn("Sei conciso.", system)

    def test_text_and_image_attachments_use_provider_specific_formats(self):
        attachments = [
            {
                "kind": "text",
                "name": "note.md",
                "content": "Decisione: consegna venerdì.",
            },
            {
                "kind": "image",
                "name": "diagram.png",
                "mime_type": "image/png",
                "data": "aW1hZ2U=",
            },
        ]
        for provider, model, extra in IMAGE_CASES:
            with self.subTest(provider=provider):
                request = build_provider_request(
                    provider,
                    model,
                    "secret",
                    [{"role": "user", "content": "Riassumi.", "attachments": attachments}],
                    **extra,
                )
                payload = json.loads(request.data)
                if provider in IMAGE_PROVIDERS:
                    content = payload["messages"][0]["content"]
                    self.assertIn("Decisione: consegna venerdì.", content[0]["text"])
                    self.assertTrue(content[1]["image_url"]["url"].startswith("data:image/png;base64,"))
                elif provider == "anthropic":
                    content = payload["messages"][0]["content"]
                    self.assertIn("Decisione: consegna venerdì.", content[0]["text"])
                    self.assertEqual(content[1]["source"]["media_type"], "image/png")
                    self.assertEqual(content[1]["source"]["data"], "aW1hZ2U=")
                else:
                    parts = payload["contents"][0]["parts"]
                    self.assertIn("Decisione: consegna venerdì.", parts[0]["text"])
                    self.assertEqual(parts[1]["inlineData"]["mimeType"], "image/png")
                    self.assertEqual(parts[1]["inlineData"]["data"], "aW1hZ2U=")

    def test_extracts_provider_replies(self):
        self.assertEqual(
            extract_reply("openai", {"choices": [{"message": {"content": "Ciao!"}}]}),
            "Ciao!",
        )
        self.assertEqual(
            extract_reply("anthropic", {"content": [{"type": "text", "text": "Ciao!"}]}),
            "Ciao!",
        )
        self.assertEqual(
            extract_reply(
                "google",
                {"candidates": [{"content": {"parts": [{"text": "Ciao!"}]}}]},
            ),
            "Ciao!",
        )
        self.assertEqual(
            extract_reply(
                "openrouter",
                {"choices": [{"message": {"content": "Ciao gratis!"}}]},
            ),
            "Ciao gratis!",
        )
        self.assertEqual(
            extract_reply(
                "mistral",
                {"choices": [{"message": {"content": "Ciao Mistral!"}}]},
            ),
            "Ciao Mistral!",
        )

    def test_provider_tool_response_parsing(self):
        openai_message, openai_calls = parse_tool_response("openai", {
            "choices": [{
                "message": {
                    "content": "",
                    "tool_calls": [{
                        "id": "call-1",
                        "function": {
                            "name": "run_terminal_command",
                            "arguments": '{"command":"pwd"}',
                        },
                    }],
                },
            }],
        })
        self.assertEqual(openai_message["tool_calls"][0]["id"], "call-1")
        self.assertEqual(openai_calls[0]["arguments"], {"command": "pwd"})

        _, anthropic_calls = parse_tool_response("anthropic", {
            "content": [{
                "type": "tool_use",
                "id": "tool-1",
                "name": "run_terminal_command",
                "input": {"command": "pwd"},
            }],
        })
        self.assertEqual(anthropic_calls[0]["id"], "tool-1")

        _, google_calls = parse_tool_response("google", {
            "candidates": [{
                "content": {
                    "parts": [{
                        "functionCall": {
                            "name": "run_terminal_command",
                            "args": {"command": "pwd"},
                        },
                    }],
                },
            }],
        })
        self.assertEqual(google_calls[0]["arguments"], {"command": "pwd"})

    def test_provider_requests_include_terminal_tool_schemas(self):
        for provider, model, extra in PROVIDER_CASES:
            with self.subTest(provider=provider):
                request = build_provider_request(
                    provider,
                    model,
                    "secret",
                    self.messages,
                    system_prompt="Use tools safely.",
                    enable_tools=True,
                    **extra,
                )
                payload = json.loads(request.data)
                self.assertIn("tools", payload)
                if provider in OPENAI_COMPATIBLE:
                    tool_name = payload["tools"][0]["function"]["name"]
                elif provider == "anthropic":
                    tool_name = payload["tools"][0]["name"]
                else:
                    tool_name = payload["tools"][0]["functionDeclarations"][0]["name"]
                self.assertEqual(tool_name, "run_terminal_command")

    def test_mistral_request_uses_its_own_endpoint(self):
        request = build_provider_request(
            "mistral", "mistral-small-latest", "secret", self.messages
        )
        self.assertEqual(
            request.full_url, "https://api.mistral.ai/v1/chat/completions"
        )
        self.assertEqual(request.get_header("Authorization"), "Bearer secret")
        payload = json.loads(request.data)
        self.assertEqual(payload["model"], "mistral-small-latest")
        self.assertEqual(payload["messages"], self.messages)

    def test_custom_provider_appends_chat_completions_once(self):
        for base_url, expected in (
            (
                "https://llm.example.com/v1",
                "https://llm.example.com/v1/chat/completions",
            ),
            (
                "http://localhost:11434/v1",
                "http://localhost:11434/v1/chat/completions",
            ),
            (
                "https://llm.example.com/v1/chat/completions",
                "https://llm.example.com/v1/chat/completions",
            ),
        ):
            with self.subTest(base_url=base_url):
                request = build_provider_request(
                    "custom", "my-model", "secret", self.messages,
                    base_url=base_url,
                )
                self.assertEqual(request.full_url, expected)

    def test_custom_provider_requires_a_secure_base_url(self):
        for base_url in ("", None, "http://api.example.com/v1", "ftp://x.example"):
            with self.subTest(base_url=base_url):
                with self.assertRaises(ValueError):
                    build_provider_request(
                        "custom", "my-model", "secret", self.messages,
                        base_url=base_url,
                    )

    def test_compatible_providers_drop_internal_message_fields(self):
        messages = [{
            "role": "user",
            "content": "Quando è nato Fabrizio Corona?",
            "attachments": [],
            "created_at": 1700000000,
        }]
        for provider, extra in (
            ("mistral", {}),
            ("groq", {}),
            ("deepseek", {}),
            ("xai", {}),
            ("custom", {"base_url": "https://llm.example.com/v1"}),
        ):
            with self.subTest(provider=provider):
                request = build_provider_request(
                    provider, "my-model", "secret", messages, **extra
                )
                payload = json.loads(request.data)
                self.assertEqual(
                    payload["messages"],
                    [{"role": "user", "content": "Quando è nato Fabrizio Corona?"}],
                )

    def test_auto_approval_only_accepts_restricted_read_commands(self):
        workspace = Path(__file__).resolve().parents[1]
        self.assertTrue(is_read_only_command("pwd", workspace))
        self.assertTrue(is_read_only_command("ls", workspace))
        self.assertTrue(is_read_only_command("ls -l", workspace))
        self.assertFalse(is_read_only_command("ls -a", workspace))
        self.assertFalse(is_read_only_command("ls -la .", workspace))
        self.assertFalse(is_read_only_command("rm important.txt", workspace))
        self.assertFalse(is_read_only_command("cat ../../outside.txt", workspace))
        self.assertFalse(is_read_only_command("ls; rm important.txt", workspace))
        with tempfile.TemporaryDirectory(dir=workspace) as temp_dir:
            secret_file = Path(temp_dir) / ".env.local"
            secret_file.write_text("API_KEY=not-for-the-model", encoding="utf-8")
            relative_path = secret_file.relative_to(workspace).as_posix()
            self.assertFalse(
                is_read_only_command(f"cat {relative_path}", workspace)
            )
            self.assertFalse(
                is_read_only_command(f"ls -a {Path(temp_dir).name}", workspace)
            )


if __name__ == "__main__":
    unittest.main()
