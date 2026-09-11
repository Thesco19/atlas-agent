"""Filesystem tools with workspace security and diff generation."""
from __future__ import annotations
import difflib
import os
import re
from pathlib import Path
from typing import Optional, List
from atlas_agent.security.policy import WorkspaceGuard

EXCLUDED_DIRS = {".git", "__pycache__", "node_modules", "dist", "build", ".venv", "venv", ".eggs", ".pytest_cache"}

def read_file(
    guard: WorkspaceGuard,
    path: str,
    offset: int = 1,
    limit: int = 300
) -> str:
    """Read file content with line numbers within line range."""
    safe_path = guard.validate_path(path)
    if not safe_path.is_file():
        return f"Error: File '{path}' does not exist or is not a regular file."

    try:
        lines = safe_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as e:
        return f"Error reading file '{path}': {e}"

    total_lines = len(lines)
    if total_lines == 0:
        return f"File '{path}' is empty (0 lines)."

    start_idx = max(0, offset - 1)
    end_idx = min(total_lines, start_idx + limit)

    result_lines = [
        f"File '{path}' (showing lines {start_idx + 1} to {end_idx} of {total_lines}):"
    ]
    for i in range(start_idx, end_idx):
        result_lines.append(f"{i + 1:4d} | {lines[i]}")

    if end_idx < total_lines:
        result_lines.append(f"... ({total_lines - end_idx} more lines truncated)")

    return "\n".join(result_lines)

def write_file(
    guard: WorkspaceGuard,
    path: str,
    content: str,
    dry_run: bool = False
) -> str:
    """Create or overwrite a file, returning unified diff if file existed."""
    safe_path = guard.validate_path(path)
    original_lines: List[str] = []
    existed = safe_path.exists()

    if existed:
        try:
            original_lines = safe_path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        except Exception:
            original_lines = []

    new_lines = content.splitlines(keepends=True)
    diff = list(difflib.unified_diff(
        original_lines,
        new_lines,
        fromfile=f"a/{path}" if existed else "/dev/null",
        tofile=f"b/{path}"
    ))
    diff_text = "".join(diff)

    if dry_run:
        return f"[DRY RUN] Would write {len(content)} bytes to '{path}'.\nDiff:\n{diff_text or '(no change)'}"

    # Ensure parent directories exist
    safe_path.parent.mkdir(parents=True, exist_ok=True)
    safe_path.write_text(content, encoding="utf-8")

    status = "Updated" if existed else "Created"
    if diff_text:
        return f"{status} file '{path}'.\nDiff:\n{diff_text}"
    return f"{status} file '{path}' successfully ({len(content)} bytes)."

def edit_file(
    guard: WorkspaceGuard,
    path: str,
    target_content: str,
    replacement_content: str,
    dry_run: bool = False
) -> str:
    """Surgically replace a unique block of text in a file and return unified diff."""
    safe_path = guard.validate_path(path)
    if not safe_path.is_file():
        return f"Error: File '{path}' does not exist."

    try:
        current_text = safe_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"Error reading file '{path}': {e}"

    count = current_text.count(target_content)
    if count == 0:
        return (
            f"Error in '{path}': Target content was not found in file. "
            f"Ensure exact match including whitespace and indentation."
        )
    if count > 1:
        return (
            f"Error in '{path}': Target content matched {count} times. "
            f"Target block must match uniquely. Provide more surrounding context lines."
        )

    updated_text = current_text.replace(target_content, replacement_content, 1)

    diff = list(difflib.unified_diff(
        current_text.splitlines(keepends=True),
        updated_text.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}"
    ))
    diff_text = "".join(diff)

    if dry_run:
        return f"[DRY RUN] Would edit '{path}'.\nDiff:\n{diff_text}"

    safe_path.write_text(updated_text, encoding="utf-8")
    return f"Successfully edited '{path}'.\nDiff:\n{diff_text}"

def list_directory(
    guard: WorkspaceGuard,
    path: str = ".",
    recursive: bool = False,
    max_items: int = 50
) -> str:
    """List directory contents up to max_items."""
    safe_path = guard.validate_path(path)
    if not safe_path.is_dir():
        return f"Error: '{path}' is not a directory."

    items_found: List[str] = []

    def scan(current_dir: Path, depth: int = 0):
        if len(items_found) >= max_items:
            return
        try:
            entries = sorted(list(current_dir.iterdir()), key=lambda e: (not e.is_dir(), e.name.lower()))
        except Exception:
            return

        for entry in entries:
            if entry.name in EXCLUDED_DIRS:
                continue
            if len(items_found) >= max_items:
                break
            rel = entry.relative_to(guard.workspace_root)
            if entry.is_dir():
                items_found.append(f"📁 {rel}/")
                if recursive and depth < 3:
                    scan(entry, depth + 1)
            else:
                size_str = f"{entry.stat().st_size} B"
                items_found.append(f"📄 {rel} ({size_str})")

    scan(safe_path)

    if not items_found:
        return f"Directory '{path}' is empty."

    header = f"Directory listing for '{path}' ({len(items_found)} items shown):"
    if len(items_found) >= max_items:
        items_found.append(f"... (truncated at {max_items} items)")
    return header + "\n" + "\n".join(items_found)

def search_files(
    guard: WorkspaceGuard,
    pattern: str,
    path: str = ".",
    max_matches: int = 25
) -> str:
    """Search for string or regex across files in workspace."""
    safe_path = guard.validate_path(path)
    if not safe_path.exists():
        return f"Error: Path '{path}' does not exist."

    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        return f"Invalid regex pattern '{pattern}': {e}"

    matches: List[str] = []

    for root, dirs, files in os.walk(str(safe_path)):
        # Filter excluded dirs in-place
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS and not d.startswith(".")]
        for file_name in files:
            if file_name.startswith(".") and file_name not in (".gitignore", ".env.example"):
                continue
            file_path = Path(root) / file_name
            try:
                # Quick binary check
                sample = file_path.read_bytes()[:1024]
                if b"\x00" in sample:
                    continue  # Binary file
                text = file_path.read_text(encoding="utf-8", errors="replace")
                lines = text.splitlines()
                for idx, line in enumerate(lines):
                    if regex.search(line):
                        rel = file_path.relative_to(guard.workspace_root)
                        matches.append(f"{rel}:{idx + 1}: {line.strip()[:100]}")
                        if len(matches) >= max_matches:
                            return (
                                f"Matches for '{pattern}' (limited to {max_matches}):\n"
                                + "\n".join(matches)
                                + f"\n... (more matches truncated)"
                            )
            except Exception:
                continue

    if not matches:
        return f"No matches found for pattern '{pattern}'."

    return f"Matches for '{pattern}' ({len(matches)} found):\n" + "\n".join(matches)

def delete_file(
    guard: WorkspaceGuard,
    path: str,
    dry_run: bool = False
) -> str:
    """Delete a file safely."""
    safe_path = guard.validate_path(path)
    if not safe_path.exists():
        return f"Error: Path '{path}' does not exist."
    if safe_path.is_dir():
        return f"Error: '{path}' is a directory. Tool 'delete_file' only removes files."

    if dry_run:
        return f"[DRY RUN] Would delete file '{path}'."

    try:
        safe_path.unlink()
        return f"Successfully deleted file '{path}'."
    except Exception as e:
        return f"Error deleting file '{path}': {e}"

def copy_file(
    guard: WorkspaceGuard,
    source: str,
    destination: str,
    dry_run: bool = False
) -> str:
    """Copy a file to another location in the workspace."""
    src_path = guard.validate_path(source)
    dest_path = guard.validate_path(destination)

    if not src_path.is_file():
        return f"Error: Source file '{source}' does not exist."

    if dry_run:
        return f"[DRY RUN] Would copy '{source}' to '{destination}'."

    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(src_path.read_bytes())
        return f"Successfully copied '{source}' to '{destination}'."
    except Exception as e:
        return f"Error copying '{source}' to '{destination}': {e}"

def move_file(
    guard: WorkspaceGuard,
    source: str,
    destination: str,
    dry_run: bool = False
) -> str:
    """Move or rename a file or directory in the workspace."""
    src_path = guard.validate_path(source)
    dest_path = guard.validate_path(destination)

    if not src_path.exists():
        return f"Error: Source path '{source}' does not exist."

    if dry_run:
        return f"[DRY RUN] Would move '{source}' to '{destination}'."

    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        src_path.rename(dest_path)
        return f"Successfully moved '{source}' to '{destination}'."
    except Exception as e:
        return f"Error moving '{source}' to '{destination}': {e}"

