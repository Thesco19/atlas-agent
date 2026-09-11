"""Unit tests for filesystem tools."""
import tempfile
import unittest
from pathlib import Path
from atlas_agent.security.policy import WorkspaceGuard
from atlas_agent.tools import filesystem

class TestFilesystemTools(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)
        self.guard = WorkspaceGuard(self.workspace)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_non_existent_file(self):
        res = filesystem.read_file(self.guard, "does_not_exist.txt")
        self.assertIn("does not exist", res)

    def test_empty_file(self):
        (self.workspace / "empty.txt").touch()
        res = filesystem.read_file(self.guard, "empty.txt")
        self.assertIn("empty", res)

    def test_unicode_reading_and_writing(self):
        content = "Olá, mundo! Café com açúcar: ☕ 🚀"
        write_res = filesystem.write_file(self.guard, "unicode.txt", content)
        self.assertIn("Created", write_res)

        read_res = filesystem.read_file(self.guard, "unicode.txt")
        self.assertIn("Olá, mundo!", read_res)
        self.assertIn("☕", read_res)

    def test_large_file_truncation(self):
        long_content = "\n".join(f"line {i}" for i in range(500))
        filesystem.write_file(self.guard, "large.txt", long_content)
        read_res = filesystem.read_file(self.guard, "large.txt", offset=1, limit=50)
        self.assertIn("more lines truncated", read_res)

    def test_edit_file_unique_match_and_diff(self):
        content = "def add(a, b):\n    return a - b\n"
        filesystem.write_file(self.guard, "math.py", content)

        edit_res = filesystem.edit_file(
            self.guard,
            "math.py",
            target_content="return a - b",
            replacement_content="return a + b"
        )
        self.assertIn("Successfully edited", edit_res)
        self.assertIn("-    return a - b", edit_res)
        self.assertIn("+    return a + b", edit_res)

        # Verify disk
        new_text = (self.workspace / "math.py").read_text(encoding="utf-8")
        self.assertIn("return a + b", new_text)

    def test_edit_file_not_found_error(self):
        content = "x = 10\n"
        filesystem.write_file(self.guard, "test.py", content)
        edit_res = filesystem.edit_file(
            self.guard,
            "test.py",
            target_content="y = 20",
            replacement_content="z = 30"
        )
        self.assertIn("Target content was not found", edit_res)

    def test_edit_file_non_unique_error(self):
        content = "value = 1\nvalue = 1\n"
        filesystem.write_file(self.guard, "dupes.py", content)
        edit_res = filesystem.edit_file(
            self.guard,
            "dupes.py",
            target_content="value = 1",
            replacement_content="value = 2"
        )
        self.assertIn("matched 2 times", edit_res)

    def test_dry_run_mode(self):
        res = filesystem.write_file(self.guard, "dry.txt", "hello", dry_run=True)
        self.assertIn("[DRY RUN]", res)
        self.assertFalse((self.workspace / "dry.txt").exists())

    def test_delete_file(self):
        (self.workspace / "to_delete.txt").write_text("bye", encoding="utf-8")
        del_res = filesystem.delete_file(self.guard, "to_delete.txt")
        self.assertIn("Successfully deleted", del_res)
        self.assertFalse((self.workspace / "to_delete.txt").exists())

if __name__ == "__main__":
    unittest.main()
