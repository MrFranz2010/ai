import sys
import tempfile
import unittest
from pathlib import Path

from mcp_client import load_mcp_registry, normalize_mcp_servers


FAKE_SERVER = r'''
import json
import sys

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    message = json.loads(line)
    method = message.get("method")
    request_id = message.get("id")
    if method == "initialize":
        result = {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "fake", "version": "1"},
        }
    elif method == "notifications/initialized":
        continue
    elif method == "tools/list":
        result = {"tools": [{
            "name": "echo",
            "description": "Ripete il testo.",
            "inputSchema": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        }]}
    elif method == "tools/call":
        arguments = message.get("params", {}).get("arguments", {})
        result = {
            "content": [{"type": "text", "text": arguments.get("text", "")}],
            "isError": False,
        }
    else:
        result = {}
    if request_id is not None:
        print(json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result}))
        sys.stdout.flush()
'''


class McpClientTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.script = Path(self.directory.name) / "fake_mcp.py"
        self.script.write_text(FAKE_SERVER, encoding="utf-8")

    def tearDown(self):
        self.directory.cleanup()

    def config(self):
        return {
            "name": "fake",
            "command": sys.executable,
            "args": [str(self.script)],
        }

    def test_discovers_and_calls_a_tool(self):
        registry = load_mcp_registry([self.config()])
        try:
            definitions = registry.definitions()
            self.assertEqual(len(definitions), 1)
            self.assertEqual(definitions[0]["name"], "mcp_fake_echo")
            self.assertTrue(registry.has("mcp_fake_echo"))
            result = registry.call("mcp_fake_echo", {"text": "ciao"})
            self.assertEqual(result, "ciao")
        finally:
            registry.close()

    def test_broken_server_is_skipped(self):
        config = self.config()
        config["command"] = str(Path(self.directory.name) / "missing")
        registry = load_mcp_registry([config])
        try:
            self.assertEqual(registry.definitions(), [])
        finally:
            registry.close()

    def test_normalizes_enabled_and_rejects_bad_names(self):
        servers = normalize_mcp_servers([{
            **self.config(), "enabled": False,
        }])
        self.assertFalse(servers[0]["enabled"])
        with self.assertRaises(ValueError):
            normalize_mcp_servers([{"name": "bad name", "command": "x"}])
        with self.assertRaises(ValueError):
            normalize_mcp_servers([{"name": "ok", "command": ""}])


if __name__ == "__main__":
    unittest.main()
