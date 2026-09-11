"""Google Gemini provider implemented using pure standard library urllib.

Zero heavy dependencies (no grpcio, no pydantic, no google-genai SDK needed),
ensuring 100% compatibility with 32-bit Linux and low-resource CPUs.
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

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"

class GeminiProvider(BaseProvider):
    """Google Gemini LLM provider via native REST API."""

    def __init__(
        self,
        api_key: Optional[str],
        model: str = "gemini-2.5-flash",
        endpoint: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        timeout: int = 45,
        max_retries: int = 3
    ):
        self.api_key = api_key
        self.model = model
        self.endpoint = endpoint or GEMINI_API_BASE
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.max_retries = max_retries

    def _convert_tools(self, tools: List[ToolDefinition]) -> List[Dict[str, Any]]:
        """Convert ToolDefinitions to Gemini functionDeclarations schema."""
        declarations = []
        for t in tools:
            declarations.append({
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters
            })
        if not declarations:
            return []
        return [{"functionDeclarations": declarations}]

    def _convert_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """Convert canonical Message list to Gemini contents format."""
        contents = []

        for msg in messages:
            role = "user" if msg.role == "user" else "model"
            parts: List[Dict[str, Any]] = []

            # 1. Text part
            if msg.content:
                parts.append({"text": msg.content})

            # 2. Tool calls requested by model
            for tc in msg.tool_calls:
                parts.append({
                    "functionCall": {
                        "name": tc.name,
                        "args": tc.arguments or {}
                    }
                })

            # 3. Tool results returned to model
            if msg.tool_results:
                # Gemini expects functionResponse in a 'user' or 'function' role
                role = "user"
                for tr in msg.tool_results:
                    parts.append({
                        "functionResponse": {
                            "name": tr.name,
                            "response": {
                                "output": tr.content
                            }
                        }
                    })

            if parts:
                contents.append({
                    "role": role,
                    "parts": parts
                })

        return contents

    def chat(
        self,
        messages: List[Message],
        tools: List[ToolDefinition],
        system_instruction: Optional[str] = None
    ) -> ProviderResponse:
        """Send chat request to Gemini REST endpoint."""
        if not self.api_key:
            raise ValueError(
                "Gemini API key is not configured. Set ATLAS_AGENT_API_KEY or GEMINI_API_KEY environment variable."
            )

        url = f"{self.endpoint}/models/{self.model}:generateContent?key={self.api_key}"

        payload: Dict[str, Any] = {
            "contents": self._convert_messages(messages),
            "generationConfig": {
                "temperature": self.temperature,
                "maxOutputTokens": self.max_tokens,
            }
        }

        # Add tools declarations if provided
        gemini_tools = self._convert_tools(tools)
        if gemini_tools:
            payload["tools"] = gemini_tools

        # Add system instruction if provided
        if system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "atlas-agent/0.1.0"
            },
            method="POST"
        )

        last_error: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                # Create default SSL context (standard verification)
                ctx = ssl.create_default_context()
                with urllib.request.urlopen(req, timeout=self.timeout, context=ctx) as response:
                    res_body = response.read().decode("utf-8")
                    data = json.loads(res_body)
                    return self._parse_gemini_response(data)
            except urllib.error.HTTPError as e:
                err_body = e.read().decode("utf-8", errors="replace")
                try:
                    err_json = json.loads(err_body)
                    msg = err_json.get("error", {}).get("message", err_body)
                except Exception:
                    msg = err_body
                last_error = RuntimeError(f"Gemini API HTTP {e.code}: {msg}")
                if e.code in (429, 500, 503) and attempt < self.max_retries:
                    time.sleep(attempt * 1.5)
                    continue
                raise last_error
            except urllib.error.URLError as e:
                last_error = RuntimeError(f"Network error connecting to Gemini API: {e.reason}")
                if attempt < self.max_retries:
                    time.sleep(attempt * 1.0)
                    continue
                raise last_error
            except Exception as e:
                last_error = e
                break

        raise last_error or RuntimeError("Unknown Gemini API error.")

    def _parse_gemini_response(self, data: Dict[str, Any]) -> ProviderResponse:
        """Extract text and functionCalls from Gemini generateContent JSON."""
        candidates = data.get("candidates", [])
        if not candidates:
            # Check prompt feedback
            feedback = data.get("promptFeedback", {})
            block_reason = feedback.get("blockReason")
            if block_reason:
                return ProviderResponse(text=f"Response blocked by safety filter: {block_reason}")
            return ProviderResponse(text="No response generated by model.")

        candidate = candidates[0]
        content = candidate.get("content", {})
        parts = content.get("parts", [])

        text_segments: List[str] = []
        tool_calls: List[ToolCall] = []

        for idx, part in enumerate(parts):
            if "text" in part:
                text_segments.append(part["text"])
            elif "functionCall" in part:
                fc = part["functionCall"]
                name = fc.get("name", "")
                args = fc.get("args", {})
                tool_calls.append(ToolCall(
                    id=f"call_{idx}_{int(time.time())}",
                    name=name,
                    arguments=args
                ))

        # Token usage if reported
        usage = data.get("usageMetadata", {})
        prompt_tokens = usage.get("promptTokenCount", 0)
        completion_tokens = usage.get("candidatesTokenCount", 0)

        return ProviderResponse(
            text="\n".join(text_segments),
            tool_calls=tool_calls,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            raw=data
        )

    def check_health(self) -> tuple[bool, str]:
        """Perform doctor healthcheck on Gemini provider."""
        if not self.api_key:
            return False, "Gemini API key is not configured (set ATLAS_AGENT_API_KEY or GEMINI_API_KEY)"

        # Verify network connectivity to API base
        try:
            req = urllib.request.Request(
                f"{self.endpoint}/models?key={self.api_key}",
                headers={"User-Agent": "atlas-agent/0.1.0"},
                method="GET"
            )
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, timeout=10, context=ctx) as res:
                if res.status == 200:
                    return True, f"Connected to Gemini API ({self.model})"
                return False, f"Unexpected HTTP status: {res.status}"
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            try:
                msg = json.loads(err_body).get("error", {}).get("message", f"HTTP {e.code}")
            except Exception:
                msg = f"HTTP {e.code}"
            return False, f"Gemini API Error: {msg}"
        except Exception as e:
            return False, f"Connection failed: {e}"
