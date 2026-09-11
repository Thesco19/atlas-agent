"""Unit tests for the Agent loop with MockProvider."""
import tempfile
import unittest
from pathlib import Path
from atlas_agent.config import Config
from atlas_agent.agent import Agent
from atlas_agent.providers.mock import MockProvider
from atlas_agent.providers.base import ToolCall

class TestAgentLoop(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_agent_simple_response_without_tools(self):
        mock = MockProvider()
        mock.queue_response(text="Hello, I am Atlas Agent.")

        cfg = Config(workspace=self.workspace, provider="mock")
        agent = Agent(cfg, provider=mock)

        answer = agent.process_turn("Hello!")
        self.assertEqual(answer, "Hello, I am Atlas Agent.")
        self.assertEqual(len(agent.history), 2)  # user + model

    def test_agent_tool_calling_flow(self):
        mock = MockProvider()
        # Turn 1: Model calls write_file
        mock.queue_response(
            text="I will create the file for you.",
            tool_calls=[ToolCall(
                id="call_1",
                name="write_file",
                arguments={"path": "hello.py", "content": "print('hello world')\n"}
            )]
        )
        # Turn 2: Model concludes
        mock.queue_response(text="File hello.py has been created successfully.")

        cfg = Config(workspace=self.workspace, provider="mock", auto_approve=True)
        agent = Agent(cfg, provider=mock)

        answer = agent.process_turn("Create hello.py")
        self.assertIn("File hello.py has been created successfully", answer)

        # Verify file on disk
        target_file = self.workspace / "hello.py"
        self.assertTrue(target_file.is_file())
        self.assertEqual(target_file.read_text(encoding="utf-8"), "print('hello world')\n")

    def test_agent_infinite_loop_protection(self):
        mock = MockProvider()
        # Queue 5 identical tool calls
        for _ in range(5):
            mock.queue_response(
                text="Reading again...",
                tool_calls=[ToolCall(
                    id="call_loop",
                    name="list_directory",
                    arguments={"path": "."}
                )]
            )
        mock.queue_response(text="Finally finished.")

        cfg = Config(workspace=self.workspace, provider="mock", max_iterations=5, auto_approve=True)
        agent = Agent(cfg, provider=mock)

        answer = agent.process_turn("Explore workspace")
        self.assertTrue(len(mock.call_history) > 0)

if __name__ == "__main__":
    unittest.main()
