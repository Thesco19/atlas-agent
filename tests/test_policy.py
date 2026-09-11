"""Unit tests for WorkspaceGuard and ToolPolicy security subsystem."""
import os
import tempfile
import unittest
from pathlib import Path
from atlas_agent.security.policy import (
    WorkspaceGuard, ToolPolicy, SecurityException, PolicyVerdict
)

class TestWorkspaceGuard(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)
        self.guard = WorkspaceGuard(self.workspace)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_safe_relative_path(self):
        safe = self.guard.validate_path("src/main.py")
        self.assertEqual(safe, (self.workspace / "src/main.py").resolve())

    def test_path_traversal_blocked(self):
        with self.assertRaises(SecurityException):
            self.guard.validate_path("../../etc/passwd")

    def test_absolute_path_outside_workspace_blocked(self):
        with self.assertRaises(SecurityException):
            self.guard.validate_path("/etc/shadow")

    def test_symlink_target_outside_workspace_blocked(self):
        # Create a file outside workspace
        outside_file = Path(tempfile.gettempdir()) / "outside_secret.txt"
        outside_file.write_text("secret", encoding="utf-8")
        
        # Create symlink inside workspace pointing outside
        symlink_path = self.workspace / "symlink_test"
        try:
            os.symlink(str(outside_file), str(symlink_path))
            with self.assertRaises(SecurityException):
                self.guard.validate_path("symlink_test")
        except OSError:
            # Skip if OS / permissions don't allow creating symlinks
            pass
        finally:
            if outside_file.exists():
                outside_file.unlink()

class TestToolPolicy(unittest.TestCase):
    def setUp(self):
        self.policy = ToolPolicy()

    def test_safe_commands(self):
        verdict, _ = self.policy.evaluate_command("ls -la")
        self.assertEqual(verdict, PolicyVerdict.SAFE)

        verdict, _ = self.policy.evaluate_command("git status")
        self.assertEqual(verdict, PolicyVerdict.SAFE)

        verdict, _ = self.policy.evaluate_command("git diff")
        self.assertEqual(verdict, PolicyVerdict.SAFE)

        verdict, _ = self.policy.evaluate_command("pytest")
        self.assertEqual(verdict, PolicyVerdict.SAFE)

    def test_confirm_commands(self):
        verdict, _ = self.policy.evaluate_command("rm -rf node_modules")
        self.assertEqual(verdict, PolicyVerdict.CONFIRM)

        verdict, _ = self.policy.evaluate_command("sudo apt update")
        self.assertEqual(verdict, PolicyVerdict.CONFIRM)

        verdict, _ = self.policy.evaluate_command("git commit -m 'feat'")
        self.assertEqual(verdict, PolicyVerdict.CONFIRM)

    def test_denied_commands(self):
        verdict, _ = self.policy.evaluate_command("mkfs.ext4 /dev/sda1")
        self.assertEqual(verdict, PolicyVerdict.DENY)

        verdict, _ = self.policy.evaluate_command("shutdown -h now")
        self.assertEqual(verdict, PolicyVerdict.DENY)

        verdict, _ = self.policy.evaluate_command(":(){ :|:& };:")
        self.assertEqual(verdict, PolicyVerdict.DENY)

if __name__ == "__main__":
    unittest.main()
