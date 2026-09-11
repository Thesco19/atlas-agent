"""Lightweight JSON-RPC 2.0 stdio client for Model Context Protocol (MCP) servers."""
from __future__ import annotations
import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

@dataclass
class MCPServerConfig:
    name: str
    command: str
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    cwd: Optional[str] = None

class MCPClient:
    """Stdio-based JSON-RPC 2.0 client for interacting with MCP servers."""

    def __init__(self, config: MCPServerConfig, workspace_root: Optional[Path] = None):
        self.config = config
        self.workspace_root = workspace_root or Path.cwd()
        self.proc: Optional[subprocess.Popen[str]] = None
        self._msg_id = 0
        self._tools: List[Dict[str, Any]] = []

    def _next_id(self) -> int:
        self._msg_id += 1
        return self._msg_id

    def connect(self, timeout: float = 5.0) -> bool:
        """Spawn the server process and execute the MCP initialization handshake."""
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
        except Exception as e:
            self.proc = None
            return False

        # Handshake: initialize
        init_req = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {}
                },
                "clientInfo": {
                    "name": "atlas-agent",
                    "version": "0.1.0"
                }
            }
        }

        resp = self._send_request(init_req, timeout=timeout)
        if not resp or "error" in resp:
            self.close()
            return False

        # Send notifications/initialized
        self._send_notification({
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        })

        # Fetch available tools
        self._tools = self.list_tools(timeout=timeout)
        return True

    def _send_notification(self, payload: Dict[str, Any]) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        if not self.proc or not self.proc.stdin:
            return
        try:
            line = json.dumps(payload) + "\n"
            self.proc.stdin.write(line)
            self.proc.stdin.flush()
        except Exception:
            pass

    def _send_request(self, payload: Dict[str, Any], timeout: float = 10.0) -> Optional[Dict[str, Any]]:
        """Send a JSON-RPC request and wait for matching response."""
        if not self.proc or not self.proc.stdin or not self.proc.stdout:
            return None

        req_id = payload.get("id")
        try:
            line = json.dumps(payload) + "\n"
            self.proc.stdin.write(line)
            self.proc.stdin.flush()
        except Exception:
            return None

        # Read lines until response with matching id is found or timeout occurs
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.proc.poll() is not None:
                # Process exited
                return None

            try:
                line = self.proc.stdout.readline()
                if not line:
                    time.sleep(0.05)
                    continue

                line_str = line.strip()
                if not line_str:
                    continue

                # Parse JSON
                try:
                    data = json.loads(line_str)
                except json.JSONDecodeError:
                    continue

                # Match id
                if isinstance(data, dict) and data.get("id") == req_id:
                    return data
            except Exception:
                return None

        return None

    def list_tools(self, timeout: float = 5.0) -> List[Dict[str, Any]]:
        """Retrieve list of tool definitions from server."""
        req = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/list",
            "params": {}
        }
        resp = self._send_request(req, timeout=timeout)
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
        resp = self._send_request(req, timeout=timeout)
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
        """Gracefully terminate server process and close streams."""
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
