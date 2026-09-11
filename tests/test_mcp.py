"""Unit tests for MCP (Model Context Protocol) integration."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from atlas_agent.mcp.client import MCPClient, MCPServerConfig
from atlas_agent.mcp.manager import MCPManager
from atlas_agent.security.policy import WorkspaceGuard, ToolPolicy
from atlas_agent.tools import ToolRegistry

class TestMCPIntegration(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmpdir.name)
        self.guard = WorkspaceGuard(self.workspace)
        self.policy = ToolPolicy()
        self.registry = ToolRegistry(self.guard, self.policy)
        self.demo_server = Path(__file__).parent.parent / "examples" / "mcp_server_demo.py"

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_mcp_client_handshake_and_tool_call(self):
        cfg = MCPServerConfig(
            name="demo",
            command=sys.executable,
            args=[str(self.demo_server)]
        )
        client = MCPClient(cfg, workspace_root=self.workspace)
        connected = client.connect(timeout=5.0)
        self.assertTrue(connected, "MCPClient failed to connect to demo server")

        # Verify tool list
        tools = client.list_tools()
        self.assertGreaterEqual(len(tools), 3)
        tool_names = [t["name"] for t in tools]
        self.assertIn("calculate_expression", tool_names)
        self.assertIn("get_system_info", tool_names)

        # Call a tool
        result = client.call_tool("calculate_expression", {"expression": "256 * 4"})
        self.assertIn("1024", result)

        # Close client
        client.close()
        self.assertIsNone(client.proc)

    def test_mcp_manager_discovery_and_registration(self):
        # Create .mcp.json in workspace
        config_data = {
            "mcpServers": {
                "local_math": {
                    "command": sys.executable,
                    "args": [str(self.demo_server)]
                }
            }
        }
        (self.workspace / ".mcp.json").write_text(json.dumps(config_data), encoding="utf-8")

        mgr = MCPManager(guard=self.guard, registry=self.registry)
        files = mgr.find_config_files()
        self.assertEqual(len(files), 1)

        connected = mgr.initialize_servers()
        self.assertEqual(connected, 1)
        self.assertIn("local_math", mgr.clients)

        # Verify tools registered in ToolRegistry
        self.assertTrue(self.registry.has_tool("mcp__local_math__calculate_expression"))
        self.assertTrue(self.registry.has_tool("calculate_expression"))

        # Execute registered tool through registry
        output = self.registry.execute("calculate_expression", {"expression": "10 + 20"})
        self.assertIn("30", output)

        mgr.shutdown()
        self.assertEqual(len(mgr.clients), 0)

    def test_http_mcp_bridge_connection(self):
        """Test HTTP MCP bridge connection (simulating remote MCP server like 10.0.1.95:8001)."""
        import http.server
        import threading

        class MockMCPHandler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                content_len = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_len)
                data = json.loads(body.decode("utf-8"))
                method = data.get("method")
                req_id = data.get("id")

                if method == "initialize":
                    resp = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {"tools": {}},
                            "serverInfo": {"name": "remote-bridge-test", "version": "1.0.0"}
                        }
                    }
                elif method == "notifications/initialized":
                    self.send_response(204)
                    self.end_headers()
                    return
                elif method == "tools/list":
                    resp = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "tools": [
                                {
                                    "name": "remote_echo",
                                    "description": "Echoes text from remote server",
                                    "inputSchema": {
                                        "type": "object",
                                        "properties": {"msg": {"type": "string"}},
                                        "required": ["msg"]
                                    }
                                }
                            ]
                        }
                    }
                elif method == "tools/call":
                    msg = data.get("params", {}).get("arguments", {}).get("msg", "")
                    resp = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [{"type": "text", "text": f"Remote Server Replied: {msg}"}]
                        }
                    }
                else:
                    resp = {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": "Method not found"}}

                resp_bytes = json.dumps(resp).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp_bytes)))
                self.end_headers()
                self.wfile.write(resp_bytes)

            def log_message(self, format, *args):
                pass  # Silence test server output

        server = http.server.HTTPServer(("127.0.0.1", 0), MockMCPHandler)
        port = server.server_address[1]
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        try:
            cfg = MCPServerConfig(
                name="remote_bridge",
                url=f"http://127.0.0.1:{port}"
            )
            client = MCPClient(cfg, workspace_root=self.workspace)
            connected = client.connect(timeout=3.0)
            self.assertTrue(connected)

            # Check listed tools
            self.assertEqual(len(client._tools), 1)
            self.assertEqual(client._tools[0]["name"], "remote_echo")

            # Call tool
            call_result = client.call_tool("remote_echo", {"msg": "Ola MCP Bridge!"})
            self.assertIn("Remote Server Replied: Ola MCP Bridge!", call_result)

            client.close()
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
