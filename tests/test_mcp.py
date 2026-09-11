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

if __name__ == "__main__":
    unittest.main()
