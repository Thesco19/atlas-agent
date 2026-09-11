"""Unit tests for controlled shell execution."""
import tempfile
import unittest
from pathlib import Path
from atlas_agent.security.policy import WorkspaceGuard, ToolPolicy
from atlas_agent.tools import shell

class TestShellTool(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)
        self.guard = WorkspaceGuard(self.workspace)
        self.policy = ToolPolicy()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_run_safe_command(self):
        res = shell.run_command(self.policy, self.guard, "echo 'hello atlas'", auto_approve=True)
        self.assertEqual(res.strip(), "hello atlas")

    def test_run_denied_command(self):
        res = shell.run_command(self.policy, self.guard, "shutdown -h now")
        self.assertIn("Security Error: Command blocked by policy", res)

    def test_command_timeout(self):
        res = shell.run_command(self.policy, self.guard, "sleep 5", timeout=1, auto_approve=True)
        self.assertIn("timed out after 1 seconds", res)

    def test_command_error_return_code(self):
        res = shell.run_command(self.policy, self.guard, "python3 -c 'import sys; sys.exit(42)'", auto_approve=True)
        self.assertIn("[Exit code 42]", res)

if __name__ == "__main__":
    unittest.main()
