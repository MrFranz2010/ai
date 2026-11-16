#!/usr/bin/env python3
"""Espone NOKK come server MCP via stdio.

Un client MCP (Claude Desktop, un IDE, un altro agente) può avviare questo
processo e usare i tool ``nokk_health`` e ``nokk_chat``. Il server parla
JSON-RPC su righe, come previsto dal trasporto stdio di MCP.

Esempio di configurazione:

    {
      "mcpServers": {
        "nokk": {
          "command": "python3",
          "args": ["/percorso/nokk_mcp.py"],
          "env": {"NOKK_URL": "https://tuo-nokk.onrender.com"}
        }
      }
    }
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from nokk_cli import (
    VERSION,
    CliError,
    NokkClient,
    default_config_path,
    normalize_base_url,
    read_config,
)

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "nokk"
JOB_POLL_SECONDS = 0.5
JOB_TIMEOUT_SECONDS = 180
MAX_MESSAGE_CHARS = 12_000


def tool_definitions():
    return [
        {
            "name": "nokk_health",
            "description": "Legge lo stato e il modello configurato su NOKK.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "nokk_chat",
            "description": (
                "Invia un messaggio a NOKK e restituisce la risposta finale. "
                "I comandi sul server che richiedono approvazione non vengono "
                "eseguiti automaticamente."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "Messaggio da inviare a NOKK.",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["codice", "studio", "analista"],
                    },
                },
                "required": ["message"],
            },
        },
    ]


def _text_result(text, is_error=False):
    result = {
        "content": [{"type": "text", "text": str(text)}],
    }
    if is_error:
        result["isError"] = True
    return result


def call_nokk_chat(client, arguments):
    message = arguments.get("message")
    mode = arguments.get("mode")
    if not isinstance(message, str) or not message.strip():
        return _text_result("Il campo message è obbligatorio.", True)
    if len(message) > MAX_MESSAGE_CHARS:
        return _text_result("Il messaggio è troppo lungo.", True)
    payload = [{"role": "user", "content": message.strip()}]
    try:
        job_id = client.start_chat(payload, mode)
        deadline = time.monotonic() + JOB_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            job = client.job(job_id)
            status = job.get("status")
            if status == "complete":
                reply = job.get("reply")
                return _text_result(reply if isinstance(reply, str) else "")
            if status == "failed":
                return _text_result(
                    job.get("error") or "Attività NOKK fallita.",
                    True,
                )
            if status == "cancelled":
                return _text_result("Attività annullata.", True)
            if status == "awaiting_approval":
                action = job.get("action") or {}
                command = action.get("command") if isinstance(action, dict) else ""
                return _text_result(
                    "NOKK richiede un'approvazione per il comando: "
                    f"{command or '(non specificato)'}. "
                    "Approva dalla pagina web o dalla TUI.",
                    True,
                )
            time.sleep(JOB_POLL_SECONDS)
    except CliError as error:
        return _text_result(str(error), True)
    return _text_result("Timeout in attesa della risposta di NOKK.", True)


def handle_message(message, client):
    """Handle one JSON-RPC message; return None for notifications."""
    if not isinstance(message, dict):
        return {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32600, "message": "Invalid Request"},
        }
    method = message.get("method")
    request_id = message.get("id")
    if request_id is None:
        return None
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": VERSION},
            },
        }
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"tools": tool_definitions()},
        }
    if method == "tools/call":
        params = message.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            arguments = {}
        if name == "nokk_health":
            try:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": _text_result(json.dumps(client.health(), ensure_ascii=False)),
                }
            except CliError as error:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": _text_result(str(error), True),
                }
        if name == "nokk_chat":
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": call_nokk_chat(client, arguments),
            }
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32602, "message": f"Tool sconosciuto: {name}"},
        }
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"Metodo sconosciuto: {method}"},
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Server MCP per NOKK")
    parser.add_argument("--config", help="percorso di cli.json")
    args = parser.parse_args(argv)
    config_path = (
        Path(args.config).expanduser()
        if args.config
        else default_config_path()
    )
    config = read_config(config_path)
    if os.environ.get("NOKK_URL"):
        config.base_url = normalize_base_url(os.environ["NOKK_URL"])
    if os.environ.get("NOKK_API_KEY"):
        config.api_key = os.environ["NOKK_API_KEY"].strip()
    client = NokkClient(config.base_url, config.api_key)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error"},
            }
        else:
            response = handle_message(message, client)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
