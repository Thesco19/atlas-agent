"""Unit tests for Gemini provider and schema sanitizer."""
import unittest
from atlas_agent.providers.gemini import sanitize_gemini_schema, GeminiProvider
from atlas_agent.tools import ToolDefinition

class TestGeminiProvider(unittest.TestCase):
    def test_sanitize_gemini_schema_strips_forbidden_fields(self):
        mcp_schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "title": "ComplexMCPTool",
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query",
                    "default": "all",
                    "pattern": "^[a-z]+$"
                },
                "options": {
                    "type": "object",
                    "additionalProperties": True,
                    "description": "Arbitrary options dict"
                },
                "tags": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "title": "TagItem"
                    }
                }
            },
            "required": ["query", "non_existent_prop"]
        }

        sanitized = sanitize_gemini_schema(mcp_schema)

        # Forbidden fields stripped
        self.assertNotIn("$schema", sanitized)
        self.assertNotIn("title", sanitized)
        self.assertNotIn("additionalProperties", sanitized)
        self.assertNotIn("default", sanitized["properties"]["query"])
        self.assertNotIn("pattern", sanitized["properties"]["query"])

        # Object without properties converted to STRING
        self.assertEqual(sanitized["properties"]["options"]["type"], "STRING")

        # Required only retains valid properties
        self.assertIn("query", sanitized["required"])
        self.assertNotIn("non_existent_prop", sanitized["required"])

        # Items in array sanitized
        self.assertEqual(sanitized["properties"]["tags"]["type"], "ARRAY")
        self.assertNotIn("title", sanitized["properties"]["tags"]["items"])

    def test_tool_name_sanitization_and_reverse_mapping(self):
        provider = GeminiProvider(api_key="mock_key")
        tool = ToolDefinition(
            name="server-bridge.tool-v1:run",
            description="Remote tool with complex name",
            parameters={"type": "object", "properties": {"arg": {"type": "string"}}}
        )
        converted = provider._convert_tools([tool])
        decl = converted[0]["functionDeclarations"][0]

        # Valid function identifier
        self.assertTrue(decl["name"].isidentifier())
        self.assertEqual(decl["name"], "server_bridge_tool_v1_run")

        # Reverse lookup works
        self.assertEqual(provider._tool_name_map["server_bridge_tool_v1_run"], "server-bridge.tool-v1:run")

if __name__ == "__main__":
    unittest.main()
