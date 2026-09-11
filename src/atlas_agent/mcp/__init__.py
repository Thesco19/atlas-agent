"""Model Context Protocol (MCP) support for atlas-agent."""
from atlas_agent.mcp.client import MCPClient, MCPServerConfig
from atlas_agent.mcp.manager import MCPManager

__all__ = ["MCPClient", "MCPServerConfig", "MCPManager"]
