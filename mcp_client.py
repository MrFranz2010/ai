"""Client MCP su stdio per NOKK.

NOKK può avviare server MCP esterni configurati dall'utente, elencarne i tool e
inoltrarne le chiamate. Il trasporto è JSON-RPC su righe, come previsto dal
trasporto stdio di MCP; il processo viene avviato senza shell.

La configurazione è una lista di oggetti::

    [{
        "name": "filesystem",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
        "env": {"DEBUG": "0"}
    }]

I server esterni eseguono codice sulla macchina di NOKK: vanno configurati solo
server fidati.
"""

from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import threading
import time

PROTOCOL_VERSION = "2024-11-05"
CLIENT_NAME = "nokk"
MAX_SERVERS = 10
MAX_TOOLS_PER_SERVER = 50
MAX_TOOL_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 4000
MAX_OUTPUT_CHARS = 100_000
DEFAULT_TIMEOUT = 20.0
CALL_TIMEOUT = 90.0
SERVER_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


class McpError(RuntimeError):
    """Errore di configurazione, trasporto o risposta MCP."""


def normalize_mcp_servers(value):
    """Validate and normalize the MCP server list from config."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("La configurazione MCP deve essere una lista.")
    if len(value) > MAX_SERVERS:
        raise ValueError(f"Puoi configurare al massimo {MAX_SERVERS} server MCP.")
    servers = []
    seen = set()
    for raw in value:
        if not isinstance(raw, dict):
            raise ValueError("Configurazione server MCP non valida.")
        name = raw.get("name")
        if not isinstance(name, str) or not SERVER_NAME_PATTERN.fullmatch(name):
            raise ValueError("Nome server MCP non valido.")
        if name in seen:
            raise ValueError(f"Server MCP duplicato: {name}")
        seen.add(name)
        enabled = raw.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError(f"Impostazione enabled non valida per {name}.")
        command = raw.get("command")
        if not isinstance(command, str) or not command.strip():
            raise ValueError(f"Comando mancante per il server MCP {name}.")
        command = command.strip()
        if len(command) > 500:
            raise ValueError(f"Comando troppo lungo per il server MCP {name}.")
        args = raw.get("args", [])
        if not isinstance(args, list) or len(args) > 32:
            raise ValueError(f"Argomenti non validi per il server MCP {name}.")
        clean_args = []
        for arg in args:
            if not isinstance(arg, str) or len(arg) > 2000:
                raise ValueError(f"Argomento non valido per il server MCP {name}.")
            clean_args.append(arg)
        env = raw.get("env", {})
        if not isinstance(env, dict) or len(env) > 32:
            raise ValueError(f"Variabili d'ambiente non valide per {name}.")
        clean_env = {}
        for key, env_value in env.items():
            if (
                not isinstance(key, str)
                or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,100}", key)
                or not isinstance(env_value, str)
                or len(env_value) > 4000
            ):
                raise ValueError(f"Variabile d'ambiente non valida per {name}.")
            clean_env[key] = env_value
        servers.append({
            "name": name,
            "command": command,
            "args": clean_args,
            "env": clean_env,
            "enabled": enabled,
        })
    return servers


def _tool_text(result):
    """Flatten an MCP tool result into text for the model."""
    parts = []
    content = result.get("content") if isinstance(result, dict) else None
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            if block_type == "text" and isinstance(block.get("text"), str):
                parts.append(block["text"])
            elif block_type == "resource":
                resource = block.get("resource") or {}
                if isinstance(resource, dict):
                    text = resource.get("text")
                    if isinstance(text, str):
                        parts.append(text)
                    else:
                        uri = resource.get("uri")
                        if isinstance(uri, str):
                            parts.append(f"Risorsa MCP: {uri}")
            elif block_type in {"image", "audio"}:
                parts.append(f"[{block_type} MCP non visualizzato]")
            else:
                parts.append(json.dumps(block, ensure_ascii=False))
    structured = result.get("structuredContent") if isinstance(result, dict) else None
    if structured is not None:
        parts.append(json.dumps(structured, ensure_ascii=False))
    text = "\n".join(part for part in parts if part)
    if not text:
        text = "Tool MCP completato senza output."
    return text[:MAX_OUTPUT_CHARS]


class McpServer:
    """One external MCP server process."""

    def __init__(self, config):
        self.config = config
        self.name = config["name"]
        self.process = None
        self._messages = queue.Queue()
        self._request_id = 0
        self._request_lock = threading.Lock()
        self._closed = False
        self._stderr_lines = []
        self._stderr_thread = None
        self._reader_thread = None

    def start(self):
        if self.process is not None:
            return
        safe_keys = {
            "PATH", "HOME", "USERPROFILE", "TMPDIR", "TEMP", "TMP",
            "SYSTEMROOT", "COMSPEC", "PATHEXT", "LANG", "LC_ALL",
            "NODE_PATH", "APPDATA", "LOCALAPPDATA",
        }
        env = {
            key: value for key, value in os.environ.items()
            if key in safe_keys or key.startswith("npm_config_")
        }
        env.update(self.config.get("env") or {})
        try:
            self.process = subprocess.Popen(
                [self.config["command"], *self.config.get("args", [])],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=env,
                shell=False,
            )
        except (OSError, ValueError) as error:
            raise McpError(f"Impossibile avviare il server MCP {self.name}: {error}") from error
        self._reader_thread = threading.Thread(
            target=self._read_stdout, name=f"mcp-{self.name}", daemon=True,
        )
        self._reader_thread.start()
        self._stderr_thread = threading.Thread(
            target=self._read_stderr, name=f"mcp-{self.name}-err", daemon=True,
        )
        self._stderr_thread.start()
        try:
            self.request("initialize", {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": CLIENT_NAME, "version": "1"},
            })
            self._send({
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {},
            })
        except Exception:
            self.close()
            raise

    def _read_stdout(self):
        stream = self.process.stdout if self.process else None
        if stream is None:
            return
        try:
            for line in stream:
                line = line.strip()
                if not line:
                    continue
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(message, dict):
                    self._messages.put(message)
        except (OSError, ValueError):
            pass
        finally:
            self._messages.put({"__mcp_eof__": True})

    def _read_stderr(self):
        stream = self.process.stderr if self.process else None
        if stream is None:
            return
        try:
            for line in stream:
                line = line.strip()
                if line:
                    self._stderr_lines.append(line[-500:])
                    del self._stderr_lines[:-20]
        except (OSError, ValueError):
            pass

    def _send(self, message):
        if self.process is None or self.process.stdin is None:
            raise McpError(f"Server MCP {self.name} non avviato.")
        try:
            self.process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
            self.process.stdin.flush()
        except (OSError, ValueError) as error:
            raise McpError(f"Connessione persa con il server MCP {self.name}.") from error

    def request(self, method, params=None, timeout=DEFAULT_TIMEOUT):
        with self._request_lock:
            self._request_id += 1
            request_id = self._request_id
            self._send({
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params or {},
            })
            deadline = time.monotonic() + timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise McpError(
                        f"Timeout del server MCP {self.name} durante {method}."
                    )
                try:
                    message = self._messages.get(timeout=remaining)
                except queue.Empty:
                    raise McpError(
                        f"Timeout del server MCP {self.name} durante {method}."
                    ) from None
                if message.get("__mcp_eof__"):
                    details = " ".join(self._stderr_lines[-3:])
                    suffix = f" ({details})" if details else ""
                    raise McpError(
                        f"Il server MCP {self.name} si è chiuso{suffix}."
                    )
                if message.get("id") != request_id:
                    continue
                if "error" in message:
                    error = message["error"]
                    if isinstance(error, dict):
                        error = error.get("message") or str(error)
                    raise McpError(f"MCP {self.name}: {error}")
                result = message.get("result")
                if not isinstance(result, dict):
                    raise McpError(f"Risposta MCP non valida da {self.name}.")
                return result

    def list_tools(self):
        result = self.request("tools/list")
        tools = result.get("tools")
        if not isinstance(tools, list):
            return []
        clean = []
        for tool in tools[:MAX_TOOLS_PER_SERVER]:
            if not isinstance(tool, dict):
                continue
            name = tool.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            schema = tool.get("inputSchema")
            if not isinstance(schema, dict):
                schema = {"type": "object", "properties": {}}
            else:
                schema = dict(schema)
            schema.setdefault("type", "object")
            if not isinstance(schema.get("properties"), dict):
                schema["properties"] = {}
            description = tool.get("description")
            if not isinstance(description, str):
                description = ""
            clean.append({
                "name": name.strip(),
                "description": description[:MAX_DESCRIPTION_LENGTH],
                "inputSchema": schema,
            })
        return clean

    def call_tool(self, name, arguments):
        result = self.request(
            "tools/call",
            {"name": name, "arguments": arguments},
            timeout=CALL_TIMEOUT,
        )
        text = _tool_text(result)
        if result.get("isError"):
            raise McpError(text)
        return text

    def close(self):
        if self._closed:
            return
        self._closed = True
        process = self.process
        if process is None:
            return
        try:
            if process.stdin:
                process.stdin.close()
        except OSError:
            pass
        try:
            process.terminate()
            process.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            try:
                process.kill()
                process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                pass
        for stream in (process.stdout, process.stderr):
            try:
                if stream:
                    stream.close()
            except OSError:
                pass


class McpRegistry:
    """Discovered MCP tools for one chat job."""

    def __init__(self):
        self.servers = {}
        self.tools = {}

    def add(self, server, tools):
        for tool in tools:
            original = tool["name"]
            exposed = _exposed_tool_name(server.name, original, self.tools)
            self.tools[exposed] = {
                "server": server,
                "tool": original,
                "definition": {
                    "name": exposed,
                    "description": (
                        f"[MCP {server.name}] {tool['description']}".strip()
                    ),
                    "parameters": tool["inputSchema"],
                },
            }
        self.servers[server.name] = server

    def definitions(self):
        return [item["definition"] for item in self.tools.values()]

    def has(self, name):
        return name in self.tools

    def call(self, name, arguments):
        item = self.tools.get(name)
        if item is None:
            raise McpError("Tool MCP non trovato.")
        if not isinstance(arguments, dict):
            raise McpError("Argomenti del tool MCP non validi.")
        return item["server"].call_tool(item["tool"], arguments)

    def close(self):
        for server in self.servers.values():
            server.close()
        self.servers.clear()
        self.tools.clear()


def _exposed_tool_name(server_name, tool_name, existing):
    base = re.sub(r"[^A-Za-z0-9_-]", "_", f"mcp_{server_name}_{tool_name}")
    base = base[:MAX_TOOL_NAME_LENGTH]
    if not base:
        base = "mcp_tool"
    candidate = base
    suffix = 2
    while candidate in existing:
        ending = f"_{suffix}"
        candidate = base[:MAX_TOOL_NAME_LENGTH - len(ending)] + ending
        suffix += 1
    return candidate


def load_mcp_registry(configs):
    """Start enabled servers, discover tools and ignore broken ones."""
    registry = McpRegistry()
    for config in normalize_mcp_servers(configs):
        if not config.get("enabled", True):
            continue
        server = McpServer(config)
        try:
            server.start()
            tools = server.list_tools()
        except McpError as error:
            server.close()
            print(f"MCP {config['name']}: {error}")
            continue
        registry.add(server, tools)
    return registry
