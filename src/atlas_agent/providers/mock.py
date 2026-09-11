"""Mock provider for unit tests and offline testing."""
from __future__ import annotations
from typing import List, Optional, Callable, Dict, Any
from atlas_agent.providers.base import BaseProvider, Message, ProviderResponse, ToolCall
from atlas_agent.tools import ToolDefinition

class MockProvider(BaseProvider):
    """Deterministic mock provider for unit testing without network."""

    def __init__(self, responses: Optional[List[ProviderResponse]] = None):
        self.responses: List[ProviderResponse] = list(responses or [])
        self.call_history: List[List[Message]] = []

    def queue_response(self, text: str, tool_calls: Optional[List[ToolCall]] = None) -> None:
        self.responses.append(ProviderResponse(
            text=text,
            tool_calls=tool_calls or [],
            prompt_tokens=10,
            completion_tokens=20
        ))

    def chat(
        self,
        messages: List[Message],
        tools: List[ToolDefinition],
        system_instruction: Optional[str] = None
    ) -> ProviderResponse:
        self.call_history.append(list(messages))
        if self.responses:
            return self.responses.pop(0)
        return ProviderResponse(
            text="Mock fallback: Task processed successfully.",
            tool_calls=[]
        )

    def check_health(self) -> tuple[bool, str]:
        return True, "Mock provider is operational."
