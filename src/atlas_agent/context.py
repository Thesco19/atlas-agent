"""Context manager for efficient, low-memory context assembly and token limits."""
from __future__ import annotations
import os
import re
from pathlib import Path
from typing import List, Optional, Set
from atlas_agent.security.policy import WorkspaceGuard
from atlas_agent.providers.base import Message

INSTRUCTION_FILES = [
    "ATLAS.md",
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    ".cursorrules",
    "CONTRIBUTING.md",
    "README.md"
]

class ContextManager:
    """Manages workspace guidelines, conversation history, and token budgets."""

    def __init__(
        self,
        guard: WorkspaceGuard,
        max_context_tokens: int = 8000
    ):
        self.guard = guard
        self.max_context_tokens = max_context_tokens
        self.workspace_root = guard.workspace_root

    def get_instruction_file_path(self) -> Optional[Path]:
        """Return the highest priority instruction file path found in workspace."""
        for filename in INSTRUCTION_FILES:
            target = self.workspace_root / filename
            if target.is_file():
                return target
        return None

    def has_atlas_file(self) -> bool:
        """Check if ATLAS.md specifically exists in workspace root."""
        return (self.workspace_root / "ATLAS.md").is_file()

    def load_project_instructions(self) -> str:
        """Search and read workspace instruction files (ATLAS.md, AGENTS.md, etc.)."""
        target = self.get_instruction_file_path()
        if target:
            try:
                content = target.read_text(encoding="utf-8", errors="replace").strip()
                if content:
                    # Limit to 3000 chars to avoid token hogging
                    if len(content) > 3000:
                        content = content[:3000] + "\n... [Instruction file truncated]"
                    return f"--- Workspace Instructions from {target.name} ---\n{content}\n---"
            except Exception:
                pass
        return ""

    def build_system_prompt(self) -> str:
        """Construct lean, clear system instructions for the LLM."""
        instructions = self.load_project_instructions()

        base_prompt = (
            "You are atlas-agent, an extremely lightweight programming agent running directly in a terminal "
            "on a resource-constrained Linux machine.\n"
            f"Workspace root: {self.workspace_root}\n\n"
            "Guiding Principles:\n"
            "1. Read files before editing them. Never assume contents.\n"
            "2. When editing, prefer 'edit_file' with exact unique text matches or 'write_file'.\n"
            "3. Make minimal, focused, atomic changes.\n"
            "4. Never output unnecessary boilerplate or marketing hype.\n"
            "5. After modifying files, verify your changes or run tests if relevant.\n"
            "6. Answer user queries concisely and provide operational details.\n"
        )

        if instructions:
            return f"{base_prompt}\n{instructions}"
        return base_prompt

    def extract_mentioned_paths(self, user_prompt: str) -> List[str]:
        """Heuristically identify file paths mentioned in user prompt."""
        # Look for tokens like path/to/file.ext or file.py
        tokens = re.findall(r"[\w\./\-]+\.[a-zA-Z0-9]+", user_prompt)
        valid_paths = []
        for t in tokens:
            cleaned = t.strip("`'\" ,;()[]{}")
            if self.guard.is_safe_path(cleaned):
                full_path = self.workspace_root / cleaned
                if full_path.is_file():
                    valid_paths.append(cleaned)
        return list(dict.fromkeys(valid_paths))[:3]  # Limit to 3 files

    def prune_history(self, messages: List[Message], current_budget: int) -> List[Message]:
        """Ensure message history stays within token budget using sliding window."""
        if not messages:
            return []

        # Always preserve the most recent user prompt and immediately preceding turns
        # Estimate ~4 chars per token
        total_tokens = sum(len(m.content) // 4 for m in messages)
        if total_tokens <= current_budget:
            return messages

        # Slide window from the back
        pruned: List[Message] = []
        accumulated = 0
        for msg in reversed(messages):
            t_count = max(1, len(msg.content) // 4)
            if accumulated + t_count > current_budget and len(pruned) >= 2:
                break
            pruned.insert(0, msg)
            accumulated += t_count

        return pruned
