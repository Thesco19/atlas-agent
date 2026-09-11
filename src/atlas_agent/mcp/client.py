"""Lightweight JSON-RPC 2.0 stdio and HTTP/SSE client for Model Context Protocol (MCP) servers."""
from __future__ import annotations
import json
import os
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

@dataclass
class MCPServerConfig:
    name: str
    command: Optional[str] = None
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    cwd: Optional[str] = None
    url: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)

class MCPClient:
    """Stdio and HTTP/SSE JSON-RPC 2.0 client for interacting with MCP servers."""

    def __init__(self, config: MCPServerConfig, workspace_root: Optional[Path] = None):
        self.config = config
        self.workspace_root = workspace_root or Path.cwd()
        self.proc: Optional[subprocess.Popen[str]] = None
        self._msg_id = 0
        self._tools: List[Dict[str, Any]] = []

        # HTTP/SSE state
        self._is_http = bool(self.config.url)
        self._sse_thread: Optional[threading.Thread] = None
        self._sse_stop_event = threading.Event()
        self._post_endpoint: Optional[str] = None
        self._sse_responses: Dict[int, Dict[str, Any]] = {}
        self._sse_cond = threading.Condition()

    def _next_id(self) -> int:
        self._msg_id += 1
        return self._msg_id

    def connect(self, timeout: float = 6.0) -> bool:
        """Connect to either stdio process or remote HTTP/SSE MCP server."""
        if self._is_http:
            return self._connect_http(timeout=timeout)
        return self._connect_stdio(timeout=timeout)

    # -------------------------------------------------------------------------
    # Stdio transport
    # -------------------------------------------------------------------------
    def _connect_stdio(self, timeout: float = 5.0) -> bool:
        if not self.config.command:
            return False

        cmd = [self.config.command] + self.config.args
        env = os.environ.copy()
        env.update(self.config.env)
        workdir = self.config.cwd or str(self.workspace_root)

        try:
            self.proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                cwd=workdir,
                env=env
            )
        except Exception:
            self.proc = None
            return False

        # Handshake: initialize
        init_req = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "clientInfo": {"name": "atlas-agent", "version": "0.1.0"}
            }
        }

        resp = self._send_request_stdio(init_req, timeout=timeout)
        if not resp or "error" in resp:
            self.close()
            return False

        self._send_notification_stdio({
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        })

        self._tools = self.list_tools(timeout=timeout)
        return True

    def _send_notification_stdio(self, payload: Dict[str, Any]) -> None:
        if not self.proc or not self.proc.stdin:
            return
        try:
            line = json.dumps(payload) + "\n"
            self.proc.stdin.write(line)
            self.proc.stdin.flush()
        except Exception:
            pass

    def _send_request_stdio(self, payload: Dict[str, Any], timeout: float = 10.0) -> Optional[Dict[str, Any]]:
        if not self.proc or not self.proc.stdin or not self.proc.stdout:
            return None

        req_id = payload.get("id")
        try:
            line = json.dumps(payload) + "\n"
            self.proc.stdin.write(line)
            self.proc.stdin.flush()
        except Exception:
            return None

        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.proc.poll() is not None:
                return None
            try:
                line = self.proc.stdout.readline()
                if not line:
                    time.sleep(0.05)
                    continue
                line_str = line.strip()
                if not line_str:
                    continue
                try:
                    data = json.loads(line_str)
                except json.JSONDecodeError:
                    continue
                if isinstance(data, dict) and data.get("id") == req_id:
                    return data
            except Exception:
                return None

        return None

    # -------------------------------------------------------------------------
    # HTTP / SSE transport (Remote MCP Bridge)
    # -------------------------------------------------------------------------
    def _connect_http(self, timeout: float = 6.0) -> bool:
        raw_url = (self.config.url or "").strip()
        if not raw_url.startswith(("http://", "https://")):
            raw_url = "http://" + raw_url

        self._post_endpoint = raw_url

        # Attempt SSE discovery
        sse_candidate = raw_url if "/sse" in raw_url else raw_url.rstrip("/") + "/sse"
        sse_connected = self._try_init_sse(sse_candidate, timeout=timeout / 2)

        if not sse_connected and sse_candidate != raw_url:
            # Try base URL as SSE
            sse_connected = self._try_init_sse(raw_url, timeout=timeout / 2)

        # Send initialize request
        init_req = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "clientInfo": {"name": "atlas-agent", "version": "0.1.0"}
            }
        }

        resp = self._send_request_http(init_req, timeout=timeout)
        if not resp or "error" in resp:
            # If failed, attempt direct HTTP RPC endpoint
            if not self._post_endpoint.endswith("/rpc") and not self._post_endpoint.endswith("/mcp"):
                alt_endpoint = raw_url.rstrip("/") + "/rpc"
                self._post_endpoint = alt_endpoint
                resp = self._send_request_http(init_req, timeout=timeout)

        if not resp or "error" in resp:
            return False

        # Send notifications/initialized
        self._send_notification_http({
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        })

        self._tools = self.list_tools(timeout=timeout)
        return True

    def _try_init_sse(self, sse_url: str, timeout: float = 3.0) -> bool:
        """Connect to SSE endpoint and wait for 'endpoint' event."""
        headers = {"Accept": "text/event-stream"}
        headers.update(self.config.headers)

        endpoint_event = threading.Event()

        def sse_worker():
            try:
                req = urllib.request.Request(sse_url, headers=headers)
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    current_event = "message"
                    buffer: List[str] = []

                    while not self._sse_stop_event.is_set():
                        raw_line = resp.readline()
                        if not raw_line:
                            break
                        line = raw_line.decode("utf-8", errors="replace").strip()
                        if not line:
                            # Dispatch block
                            if buffer:
                                payload_text = "\n".join(buffer)
                                buffer.clear()
                                self._handle_sse_payload(current_event, payload_text, sse_url, endpoint_event)
                            current_event = "message"
                            continue

                        if line.startswith("event:"):
                            current_event = line[6:].strip()
                        elif line.startswith("data:"):
                            buffer.append(line[5:].strip())
            except Exception:
                pass

        thread = threading.Thread(target=sse_worker, daemon=True)
        thread.start()

        # Wait briefly for endpoint event
        if endpoint_event.wait(timeout=timeout):
            self._sse_thread = thread
            return True

        return False

    def _handle_sse_payload(self, event: str, text: str, sse_url: str, endpoint_event: threading.Event):
        if event == "endpoint":
            # Endpoint event specifies where to POST messages
            self._post_endpoint = urllib.parse.urljoin(sse_url, text.strip())
            endpoint_event.set()
        elif event == "message":
            try:
                data = json.loads(text)
                req_id = data.get("id")
                if req_id is not None:
                    with self._sse_cond:
                        self._sse_responses[req_id] = data
                        self._sse_cond.notify_all()
            except Exception:
                pass

    def _send_notification_http(self, payload: Dict[str, Any]) -> None:
        if not self._post_endpoint:
            return
        try:
            body = json.dumps(payload).encode("utf-8")
            headers = {"Content-Type": "application/json"}
            headers.update(self.config.headers)
            req = urllib.request.Request(self._post_endpoint, data=body, headers=headers, method="POST")
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass

    def _send_request_http(self, payload: Dict[str, Any], timeout: float = 15.0) -> Optional[Dict[str, Any]]:
        if not self._post_endpoint:
            return None

        req_id = payload.get("id")
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        headers.update(self.config.headers)

        try:
            req = urllib.request.Request(self._post_endpoint, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                resp_bytes = resp.read()
                if resp_bytes:
                    try:
                        data = json.loads(resp_bytes.decode("utf-8", errors="replace"))
                        if isinstance(data, dict):
                            return data
                    except Exception:
                        pass
        except Exception:
            pass

        # If direct HTTP response was empty (common in SSE transport), check SSE response buffer
        if req_id is not None and self._sse_thread:
            start = time.time()
            with self._sse_cond:
                while time.time() - start < timeout:
                    if req_id in self._sse_responses:
                        return self._sse_responses.pop(req_id)
                    self._sse_cond.wait(timeout=0.5)

        return None

    # -------------------------------------------------------------------------
    # Unified Tool calling
    # -------------------------------------------------------------------------
    def list_tools(self, timeout: float = 5.0) -> List[Dict[str, Any]]:
        """Retrieve list of tool definitions from server."""
        req = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/list",
            "params": {}
        }
        resp = self._send_request_http(req, timeout=timeout) if self._is_http else self._send_request_stdio(req, timeout=timeout)
        if resp and "result" in resp and "tools" in resp["result"]:
            return resp["result"]["tools"]
        return []

    def call_tool(self, tool_name: str, arguments: Dict[str, Any], timeout: float = 30.0) -> str:
        """Call an MCP tool and format the returned content as string."""
        req = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
        resp = self._send_request_http(req, timeout=timeout) if self._is_http else self._send_request_stdio(req, timeout=timeout)
        if not resp:
            return f"Error: MCP server '{self.config.name}' did not respond within {timeout}s or connection failed."

        if "error" in resp:
            err = resp["error"]
            return f"MCP Error: {err.get('message', 'Unknown error')} (code {err.get('code')})"

        result = resp.get("result", {})
        is_error = result.get("isError", False)
        content_items = result.get("content", [])

        output_parts: List[str] = []
        for item in content_items:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    output_parts.append(item.get("text", ""))
                elif item.get("type") == "image":
                    output_parts.append("[Binary Image content returned by MCP]")
                elif item.get("type") == "resource":
                    output_parts.append(f"[Resource: {item.get('resource', {}).get('uri')}]")
            elif isinstance(item, str):
                output_parts.append(item)

        output_str = "\n".join(output_parts) if output_parts else json.dumps(result, indent=2)
        if is_error:
            return f"Tool returned error:\n{output_str}"
        return output_str

    def close(self) -> None:
        """Gracefully terminate server process or SSE streams."""
        self._sse_stop_event.set()

        if self.proc:
            try:
                if self.proc.stdin:
                    self.proc.stdin.close()
                if self.proc.stdout:
                    self.proc.stdout.close()
                if self.proc.stderr:
                    self.proc.stderr.close()
            except Exception:
                pass

            try:
                self.proc.terminate()
                self.proc.wait(timeout=1.0)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
            self.proc = None
