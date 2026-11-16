import unittest

from nokk_mcp import handle_message


class FakeClient:
    def __init__(self):
        self.messages = []

    def health(self):
        return {"provider": "openai", "model": "fake-model"}

    def start_chat(self, messages, mode=None):
        self.messages.append((messages, mode))
        return "a" * 32

    def job(self, job_id):
        return {"status": "complete", "reply": "Risposta MCP."}


class NokkMcpTests(unittest.TestCase):
    def setUp(self):
        self.client = FakeClient()

    def test_initialize_and_list_tools(self):
        init = handle_message(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            self.client,
        )
        self.assertEqual(init["result"]["serverInfo"]["name"], "nokk")
        listing = handle_message(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, self.client
        )
        names = {tool["name"] for tool in listing["result"]["tools"]}
        self.assertEqual(names, {"nokk_health", "nokk_chat"})

    def test_chat_tool_returns_the_reply(self):
        response = handle_message(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "nokk_chat",
                    "arguments": {"message": "Ciao", "mode": "codice"},
                },
            },
            self.client,
        )
        self.assertEqual(
            response["result"]["content"][0]["text"], "Risposta MCP."
        )
        self.assertEqual(self.client.messages[0][1], "codice")

    def test_health_tool(self):
        response = handle_message(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "nokk_health", "arguments": {}},
            },
            self.client,
        )
        self.assertIn("fake-model", response["result"]["content"][0]["text"])

    def test_unknown_tool_is_an_error(self):
        response = handle_message(
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {"name": "missing", "arguments": {}},
            },
            self.client,
        )
        self.assertEqual(response["error"]["code"], -32602)


if __name__ == "__main__":
    unittest.main()
