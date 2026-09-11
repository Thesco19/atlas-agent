"""Base contracts and message types for all LLM providers."""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from atlas_agent.tools import ToolDefinition

@dataclass
class ToolCall:
    """Canonical representation of a model tool request."""
    id: str
    name: str
    arguments: Dict[str, Any]

@dataclass
class ToolResult:
    """Canonical representation of a tool execution outcome."""
    call_id: str
    name: str
    content: str

@dataclass
class Message:
    """Canonical conversation message."""
    role: str  # "user", "model", "system", "tool"
    content: str
    tool_calls: List[ToolCall] = field(default_factory=list)
    tool_results: List[ToolResult] = field(default_factory=list)

@dataclass
class ProviderResponse:
    """Response returned by any provider implementation."""
    text: str
    tool_calls: List[ToolCall] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    raw: Optional[Dict[str, Any]] = None

class BaseProvider(ABC):
    """Abstract Base Class for LLM providers."""

    @abstractmethod
    def chat(
        self,
        messages: List[Message],
        tools: List[ToolDefinition],
        system_instruction: Optional[str] = None
    ) -> ProviderResponse:
        """Send chat messages and tool definitions, receiving model response."""
        pass

    def count_tokens(self, text: str) -> int:
        """Estimate tokens for low-resource environments (approx 4 chars/token)."""
        if not text:
            return 0
        return max(1, len(text) // 4)

    @abstractmethod
    def check_health(self) -> tuple[bool, str]:
        """Verify API key configuration and network reachability."""
        pass
