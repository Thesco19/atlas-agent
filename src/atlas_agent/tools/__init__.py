"""Tool registry and dispatcher for atlas-agent."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Dict, List
from atlas_agent.security.policy import WorkspaceGuard, ToolPolicy
from atlas_agent.tools import filesystem, shell, git

@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: Dict[str, Any]

class ToolRegistry:
    """Registry managing available tools and execution dispatch."""

    def __init__(
        self,
        guard: WorkspaceGuard,
        policy: ToolPolicy,
        dry_run: bool = False,
        auto_approve: bool = False
    ):
        self.guard = guard
        self.policy = policy
        self.dry_run = dry_run
        self.auto_approve = auto_approve
        self._tools: Dict[str, ToolDefinition] = {}
        self._handlers: Dict[str, Callable[..., str]] = {}
        self._register_default_tools()

    def _register_default_tools(self) -> None:
        # 1. read_file
        self.register(
            name="read_file",
            description="Read file contents with line numbers and optional line offset/limit.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path to file in workspace"},
                    "offset": {"type": "integer", "description": "1-based starting line number (default: 1)"},
                    "limit": {"type": "integer", "description": "Maximum number of lines to read (default: 300)"}
                },
                "required": ["path"]
            },
            handler=lambda args: filesystem.read_file(
                self.guard,
                path=str(args.get("path")),
                offset=int(args.get("offset", 1)),
                limit=int(args.get("limit", 300))
            )
        )

        # 2. write_file
        self.register(
            name="write_file",
            description="Create or overwrite a file with given content. Generates a unified diff.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path to file in workspace"},
                    "content": {"type": "string", "description": "Full text content to write"}
                },
                "required": ["path", "content"]
            },
            handler=lambda args: filesystem.write_file(
                self.guard,
                path=str(args.get("path")),
                content=str(args.get("content")),
                dry_run=self.dry_run
            )
        )

        # 3. edit_file
        self.register(
            name="edit_file",
            description="Surgically replace a unique block of text with new text. Generates a unified diff.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path to file in workspace"},
                    "target_content": {"type": "string", "description": "Exact unique string to be replaced"},
                    "replacement_content": {"type": "string", "description": "Replacement string"}
                },
                "required": ["path", "target_content", "replacement_content"]
            },
            handler=lambda args: filesystem.edit_file(
                self.guard,
                path=str(args.get("path")),
                target_content=str(args.get("target_content")),
                replacement_content=str(args.get("replacement_content")),
                dry_run=self.dry_run
            )
        )

        # 4. list_directory
        self.register(
            name="list_directory",
            description="List files and subdirectories in a given workspace directory.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path to directory (default: '.')"},
                    "recursive": {"type": "boolean", "description": "Whether to list subdirectories recursively (default: false)"},
                    "max_items": {"type": "integer", "description": "Maximum entries to return (default: 50)"}
                }
            },
            handler=lambda args: filesystem.list_directory(
                self.guard,
                path=str(args.get("path", ".")),
                recursive=bool(args.get("recursive", False)),
                max_items=int(args.get("max_items", 50))
            )
        )

        # 5. search_files
        self.register(
            name="search_files",
            description="Search for regex or substring pattern across workspace files.",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regex or substring to find"},
                    "path": {"type": "string", "description": "Subdirectory to search inside (default: '.')"},
                    "max_matches": {"type": "integer", "description": "Maximum matches to return (default: 25)"}
                },
                "required": ["pattern"]
            },
            handler=lambda args: filesystem.search_files(
                self.guard,
                pattern=str(args.get("pattern")),
                path=str(args.get("path", ".")),
                max_matches=int(args.get("max_matches", 25))
            )
        )

        # 6. run_command
        self.register(
            name="run_command",
            description="Run a shell command inside workspace subject to security policy checks.",
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to execute"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default: 30)"}
                },
                "required": ["command"]
            },
            handler=lambda args: shell.run_command(
                self.policy,
                self.guard,
                command=str(args.get("command")),
                timeout=int(args.get("timeout", 30)),
                auto_approve=self.auto_approve
            )
        )

        # 7. git_status
        self.register(
            name="git_status",
            description="Inspect git branch, staged files, and modified files in the workspace.",
            parameters={"type": "object", "properties": {}},
            handler=lambda args: git.git_status(self.guard)
        )

        # 8. git_diff
        self.register(
            name="git_diff",
            description="Inspect git uncommitted changes or staged changes.",
            parameters={
                "type": "object",
                "properties": {
                    "staged": {"type": "boolean", "description": "View staged diff instead of working tree (default: false)"}
                }
            },
            handler=lambda args: git.git_diff(self.guard, staged=bool(args.get("staged", False)))
        )

        # 9. git_log
        self.register(
            name="git_log",
            description="Show recent git commit history.",
            parameters={
                "type": "object",
                "properties": {
                    "max_count": {"type": "integer", "description": "Number of commits to show (default: 5)"}
                }
            },
            handler=lambda args: git.git_log(self.guard, max_count=int(args.get("max_count", 5)))
        )

        # 10. delete_file
        self.register(
            name="delete_file",
            description="Delete a file from workspace. Always asks confirmation.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to file to delete"}
                },
                "required": ["path"]
            },
            handler=lambda args: filesystem.delete_file(
                self.guard,
                path=str(args.get("path")),
                dry_run=self.dry_run
            )
        )

        # 11. git_commit
        self.register(
            name="git_commit",
            description="Create a git commit with a message. Always requires confirmation.",
            parameters={
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Commit message"}
                },
                "required": ["message"]
            },
            handler=lambda args: git.git_commit(
                self.guard,
                message=str(args.get("message")),
                auto_approve=self.auto_approve
            )
        )

    def register(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        handler: Callable[[Dict[str, Any]], str]
    ) -> None:
        self._tools[name] = ToolDefinition(name=name, description=description, parameters=parameters)
        self._handlers[name] = handler

    def get_definitions(self) -> List[ToolDefinition]:
        return list(self._tools.values())

    def execute(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        handler = self._handlers.get(tool_name)
        if not handler:
            return f"Error: Tool '{tool_name}' not found."
        try:
            return handler(arguments or {})
        except Exception as e:
            return f"Error executing tool '{tool_name}': {e}"
