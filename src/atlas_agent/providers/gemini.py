"""Google Gemini provider implemented using pure standard library urllib.

Zero heavy dependencies (no grpcio, no pydantic, no google-genai SDK needed),
ensuring 100% compatibility with 32-bit Linux and low-resource CPUs.
"""
from __future__ import annotations
import json
import re
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

def sanitize_gemini_schema(schema: Any) -> Dict[str, Any]:
    """Sanitize arbitrary JSON Schema into strict Gemini OpenAPI Schema subset.
    
    Removes unsupported keys (additionalProperties, $schema, title, default, pattern),
    normalizes types, and ensures OBJECTs have properties.
    """
    if not isinstance(schema, dict):
        return {"type": "STRING"}

    sanitized: Dict[str, Any] = {}

    # Extract or infer type
    raw_type = schema.get("type", "OBJECT")
    if isinstance(raw_type, list):
        if "null" in raw_type:
            sanitized["nullable"] = True
        raw_type = next((t for t in raw_type if t != "null"), "STRING")

    type_str = str(raw_type).upper()
    if type_str not in ("STRING", "INTEGER", "NUMBER", "BOOLEAN", "ARRAY", "OBJECT"):
        if "properties" in schema:
            type_str = "OBJECT"
        elif "items" in schema:
            type_str = "ARRAY"
        else:
            type_str = "STRING"

    description = schema.get("description")
    if description and isinstance(description, str):
        sanitized["description"] = description[:1024]

    if "nullable" in schema:
        sanitized["nullable"] = bool(schema["nullable"])

    if "enum" in schema and isinstance(schema["enum"], list):
        sanitized["enum"] = [str(e) for e in schema["enum"]]

    # Handle OBJECT
    if type_str == "OBJECT":
        raw_props = schema.get("properties")
        if isinstance(raw_props, dict) and raw_props:
            clean_props = {}
            for k, v in raw_props.items():
                safe_k = re.sub(r"[^a-zA-Z0-9_]", "_", str(k))
                clean_props[safe_k] = sanitize_gemini_schema(v)
            sanitized["type"] = "OBJECT"
            sanitized["properties"] = clean_props

            if "required" in schema and isinstance(schema["required"], list):
                req = [re.sub(r"[^a-zA-Z0-9_]", "_", str(r)) for r in schema["required"]]
                valid_req = [r for r in req if r in clean_props]
                if valid_req:
                    sanitized["required"] = valid_req
        else:
            # Gemini strictly rejects OBJECT without properties! Represent as STRING
            sanitized["type"] = "STRING"
            desc = sanitized.get("description", "")
            sanitized["description"] = (desc + " (JSON string)").strip()

    # Handle ARRAY
    elif type_str == "ARRAY":
        sanitized["type"] = "ARRAY"
        raw_items = schema.get("items")
        if isinstance(raw_items, dict):
            sanitized["items"] = sanitize_gemini_schema(raw_items)
        elif isinstance(raw_items, list) and raw_items and isinstance(raw_items[0], dict):
            sanitized["items"] = sanitize_gemini_schema(raw_items[0])
        else:
            sanitized["items"] = {"type": "STRING"}

    else:
        sanitized["type"] = type_str

    return sanitized


class GeminiProvider(BaseProvider):
    """Google Gemini LLM provider via native REST API."""

    def __init__(
        self,
        api_key: Optional[str],
        model: str = "gemini-3.1-flash-lite",
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
        self._tool_name_map: Dict[str, str] = {}
        self._reverse_tool_name_map: Dict[str, str] = {}

    def _convert_tools(self, tools: List[ToolDefinition]) -> List[Dict[str, Any]]:
        """Convert ToolDefinitions to Gemini functionDeclarations schema with strict sanitization."""
        declarations = []
        for t in tools:
            # Gemini function name must match ^[a-zA-Z_][a-zA-Z0-9_]*$ and length <= 63
            safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", t.name)
            if safe_name and safe_name[0].isdigit():
                safe_name = f"tool_{safe_name}"
            safe_name = (safe_name or "unnamed_tool")[:63]

            self._tool_name_map[safe_name] = t.name
            self._reverse_tool_name_map[t.name] = safe_name

            declarations.append({
                "name": safe_name,
                "description": (t.description or "Tool function")[:1024],
                "parameters": sanitize_gemini_schema(t.parameters)
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
                safe_name = self._reverse_tool_name_map.get(tc.name, tc.name)
                parts.append({
                    "functionCall": {
                        "name": safe_name,
                        "args": tc.arguments or {}
                    }
                })

            # 3. Tool results returned to model
            if msg.tool_results:
                # Gemini expects functionResponse in a 'user' or 'function' role
                role = "user"
                for tr in msg.tool_results:
                    safe_name = self._reverse_tool_name_map.get(tr.name, tr.name)
                    parts.append({
                        "functionResponse": {
                            "name": safe_name,
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
                original_name = self._tool_name_map.get(name, name)
                args = fc.get("args", {})
                tool_calls.append(ToolCall(
                    id=f"call_{idx}_{int(time.time())}",
                    name=original_name,
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
