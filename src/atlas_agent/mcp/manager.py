"""Manager for loading MCP servers from configuration and binding tools to the registry."""
from __future__ import annotations
import atexit
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from atlas_agent.mcp.client import MCPClient, MCPServerConfig
from atlas_agent.security.policy import WorkspaceGuard
from atlas_agent import ui

MCP_CONFIG_FILENAMES = [
    ".mcp.json",
    "mcp.json",
    "atlas_mcp.json",
]

GLOBAL_MCP_CONFIG = Path.home() / ".config" / "atlas-agent" / "mcp.json"

class MCPManager:
    """Discovers, launches, and registers MCP servers and their tools."""

    def __init__(self, guard: WorkspaceGuard, registry: Any):
        self.guard = guard
        self.registry = registry
        self.clients: Dict[str, MCPClient] = {}
        self.registered_tools: List[str] = []
        # Ensure cleanup on process exit
        atexit.register(self.shutdown)

    def find_config_files(self) -> List[Path]:
        """Find local workspace and global MCP config files."""
        found: List[Path] = []
        for name in MCP_CONFIG_FILENAMES:
            local = self.guard.workspace_root / name
            if local.is_file():
                found.append(local)

        if GLOBAL_MCP_CONFIG.is_file() and GLOBAL_MCP_CONFIG not in found:
            found.append(GLOBAL_MCP_CONFIG)

        return found

    def load_configs(self) -> Dict[str, MCPServerConfig]:
        """Load and parse server configurations from detected files."""
        configs: Dict[str, MCPServerConfig] = {}
        files = self.find_config_files()

        for config_path in files:
            try:
                data = json.loads(config_path.read_text(encoding="utf-8"))
                servers = data.get("mcpServers") or data.get("servers") or {}
                if isinstance(servers, dict):
                    for name, srv in servers.items():
                        if not isinstance(srv, dict):
                            continue
                        cmd = srv.get("command")
                        url = srv.get("url") or srv.get("endpoint")
                        if not cmd and not url:
                            continue
                        args = srv.get("args") or []
                        env = srv.get("env") or {}
                        cwd = srv.get("cwd")
                        headers = srv.get("headers") or {}
                        configs[name] = MCPServerConfig(
                            name=name,
                            command=str(cmd) if cmd else None,
                            args=[str(a) for a in args],
                            env={str(k): str(v) for k, v in env.items()},
                            cwd=str(cwd) if cwd else None,
                            url=str(url) if url else None,
                            headers={str(k): str(v) for k, v in headers.items()}
                        )
            except Exception:
                continue

        return configs

    def initialize_servers(self) -> int:
        """Launch configured MCP servers and register their tools into the registry."""
        configs = self.load_configs()
        if not configs:
            return 0

        connected_count = 0
        for name, cfg in configs.items():
            client = MCPClient(cfg, workspace_root=self.guard.workspace_root)
            success = client.connect()
            if not success:
                continue

            self.clients[name] = client
            connected_count += 1

            # Register tools
            for tool in client._tools:
                raw_name = tool.get("name")
                if not raw_name:
                    continue

                desc = tool.get("description") or f"MCP tool from server {name}"
                schema = tool.get("inputSchema") or {"type": "object", "properties": {}}

                # Namespaced tool name
                namespaced_name = f"mcp__{name}__{raw_name}"

                # Register namespaced tool
                self._register_single_tool(
                    client=client,
                    tool_id=namespaced_name,
                    raw_tool_name=raw_name,
                    description=f"[MCP:{name}] {desc}",
                    parameters=schema
                )

                # Also register short name if not already occupied by default tools
                if raw_name not in self.registry.list_tools():
                    self._register_single_tool(
                        client=client,
                        tool_id=raw_name,
                        raw_tool_name=raw_name,
                        description=f"[MCP:{name}] {desc}",
                        parameters=schema
                    )

        return connected_count

    def _register_single_tool(
        self,
        client: MCPClient,
        tool_id: str,
        raw_tool_name: str,
        description: str,
        parameters: Dict[str, Any]
    ) -> None:
        """Helper to register an MCP tool handler in ToolRegistry."""
        def handler(args: Dict[str, Any]) -> str:
            return client.call_tool(raw_tool_name, args)

        self.registry.register(
            name=tool_id,
            description=description,
            parameters=parameters,
            handler=handler
        )
        self.registered_tools.append(tool_id)

    def shutdown(self) -> None:
        """Terminate all active MCP client processes."""
        for client in self.clients.values():
            client.close()
        self.clients.clear()
