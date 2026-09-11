"""OpenAI-compatible provider using pure standard library urllib.

Supports local servers (Ollama, vLLM, LM Studio) and remote providers (OpenRouter, OpenAI)
without requiring the heavy `openai` Python SDK.
"""
from __future__ import annotations
import json
import ssl
import time
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional
from atlas_agent.providers.base import (
    BaseProvider, Message, ProviderResponse, ToolCall, ToolResult
)
from atlas_agent.tools import ToolDefinition

class OpenAICompatibleProvider(BaseProvider):
    """Provider for OpenAI-compatible REST APIs."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
        endpoint: str = "https://api.openai.com/v1",
        temperature: float = 0.2,
        max_tokens: int = 4096,
        timeout: int = 45,
        max_retries: int = 3
    ):
        self.api_key = api_key or "sk-no-key-required"
        self.model = model
        self.endpoint = endpoint.rstrip("/")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.max_retries = max_retries

    def _convert_tools(self, tools: List[ToolDefinition]) -> List[Dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters
                }
            }
            for t in tools
        ]

    def _convert_messages(
        self,
        messages: List[Message],
        system_instruction: Optional[str]
    ) -> List[Dict[str, Any]]:
        formatted: List[Dict[str, Any]] = []

        if system_instruction:
            formatted.append({"role": "system", "content": system_instruction})

        for msg in messages:
            if msg.role == "tool" or msg.tool_results:
                for tr in msg.tool_results:
                    formatted.append({
                        "role": "tool",
                        "tool_call_id": tr.call_id,
                        "name": tr.name,
                        "content": tr.content
                    })
                continue

            entry: Dict[str, Any] = {
                "role": "assistant" if msg.role == "model" else msg.role,
                "content": msg.content or ""
            }

            if msg.tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments)
                        }
                    }
                    for tc in msg.tool_calls
                ]

            formatted.append(entry)

        return formatted

    def chat(
        self,
        messages: List[Message],
        tools: List[ToolDefinition],
        system_instruction: Optional[str] = None
    ) -> ProviderResponse:
        url = f"{self.endpoint}/chat/completions"

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": self._convert_messages(messages, system_instruction),
            "temperature": self.temperature,
            "max_tokens": self.max_tokens
        }

        api_tools = self._convert_tools(tools)
        if api_tools:
            payload["tools"] = api_tools
            payload["tool_choice"] = "auto"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "atlas-agent/0.1.0"
        }
        if "openrouter.ai" in self.endpoint:
            headers["HTTP-Referer"] = "https://github.com/thesco1902/atlas-agent"
            headers["X-Title"] = "atlas-agent"

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")

        for attempt in range(1, self.max_retries + 1):
            try:
                ctx = ssl.create_default_context()
                with urllib.request.urlopen(req, timeout=self.timeout, context=ctx) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                    choice = body.get("choices", [{}])[0]
                    msg_obj = choice.get("message", {})
                    text = msg_obj.get("content") or ""

                    raw_tool_calls = msg_obj.get("tool_calls", [])
                    tool_calls = []
                    for rtc in raw_tool_calls:
                        func = rtc.get("function", {})
                        fname = func.get("name", "")
                        try:
                            fargs = json.loads(func.get("arguments", "{}"))
                        except Exception:
                            fargs = {}
                        tool_calls.append(ToolCall(
                            id=rtc.get("id", f"call_{fname}"),
                            name=fname,
                            arguments=fargs
                        ))

                    usage = body.get("usage", {})
                    return ProviderResponse(
                        text=text,
                        tool_calls=tool_calls,
                        prompt_tokens=usage.get("prompt_tokens", 0),
                        completion_tokens=usage.get("completion_tokens", 0),
                        raw=body
                    )
            except urllib.error.HTTPError as e:
                err_text = e.read().decode("utf-8", errors="replace")
                if attempt == self.max_retries:
                    raise RuntimeError(f"OpenAI API Error {e.code}: {err_text}")
                time.sleep(attempt * 1.5)
            except Exception as e:
                if attempt == self.max_retries:
                    raise RuntimeError(f"Network error: {e}")
                time.sleep(attempt * 1.0)

        raise RuntimeError("Failed to complete chat completion.")

    def check_health(self) -> tuple[bool, str]:
        url = f"{self.endpoint}/models"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "atlas-agent/0.1.0"
        }
        try:
            req = urllib.request.Request(url, headers=headers, method="GET")
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                if resp.status == 200:
                    return True, f"Connected to OpenAI-compatible endpoint ({self.endpoint})"
                return False, f"HTTP {resp.status}"
        except Exception as e:
            return False, f"Connection check failed: {e}"
