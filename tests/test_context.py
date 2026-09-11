"""Unit tests for ContextManager."""
import tempfile
import unittest
from pathlib import Path
from atlas_agent.security.policy import WorkspaceGuard
from atlas_agent.context import ContextManager
from atlas_agent.providers.base import Message

class TestContextManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)
        self.guard = WorkspaceGuard(self.workspace)
        self.ctx = ContextManager(self.guard)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_load_project_instructions_atlas_md(self):
        (self.workspace / "ATLAS.md").write_text("Rule 1: Always test code.", encoding="utf-8")
        self.assertTrue(self.ctx.has_atlas_file())
        self.assertEqual(self.ctx.get_instruction_file_path().name, "ATLAS.md")
        loaded = self.ctx.load_project_instructions()
        self.assertIn("ATLAS.md", loaded)
        self.assertIn("Rule 1: Always test code.", loaded)

    def test_atlas_md_priority_over_agents_and_readme(self):
        (self.workspace / "README.md").write_text("Readme contents", encoding="utf-8")
        (self.workspace / "AGENTS.md").write_text("Agents contents", encoding="utf-8")
        (self.workspace / "ATLAS.md").write_text("Atlas specific priority", encoding="utf-8")

        self.assertTrue(self.ctx.has_atlas_file())
        self.assertEqual(self.ctx.get_instruction_file_path().name, "ATLAS.md")
        loaded = self.ctx.load_project_instructions()
        self.assertIn("Atlas specific priority", loaded)
        self.assertNotIn("Agents contents", loaded)

    def test_no_instructions_when_absent(self):
        self.assertFalse(self.ctx.has_atlas_file())
        self.assertIsNone(self.ctx.get_instruction_file_path())
        self.assertEqual(self.ctx.load_project_instructions(), "")

    def test_extract_mentioned_paths(self):
        (self.workspace / "app.py").touch()
        (self.workspace / "utils.py").touch()
        prompt = "Please look into app.py and also check utils.py for bugs."
        paths = self.ctx.extract_mentioned_paths(prompt)
        self.assertIn("app.py", paths)
        self.assertIn("utils.py", paths)

    def test_prune_history_sliding_window(self):
        # Create history exceeding small token budget
        msgs = [
            Message(role="user", content="msg 1 " * 50),
            Message(role="model", content="msg 2 " * 50),
            Message(role="user", content="msg 3 " * 50),
            Message(role="model", content="final answer"),
        ]
        pruned = self.ctx.prune_history(msgs, current_budget=40)
        self.assertLess(len(pruned), len(msgs))
        self.assertEqual(pruned[-1].content, "final answer")

if __name__ == "__main__":
    unittest.main()
