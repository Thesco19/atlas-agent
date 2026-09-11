"""Workspace sandbox and command execution policies."""
from __future__ import annotations
import os
import shlex
from enum import Enum
from pathlib import Path
from typing import Set

class SecurityException(Exception):
    """Raised when an operation violates security or workspace boundary."""
    pass

class PolicyVerdict(Enum):
    SAFE = "safe"          # Auto-run permitted
    CONFIRM = "confirm"    # Requires user interactive confirmation
    DENY = "deny"          # Blocked unconditionally

class WorkspaceGuard:
    """Guards file operations to strictly remain inside workspace directory."""

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root.resolve()
        if not self.workspace_root.exists():
            raise SecurityException(f"Workspace directory does not exist: {self.workspace_root}")

    def is_safe_path(self, target_path: str | Path) -> bool:
        """Check if target path is strictly within workspace."""
        try:
            resolved = (self.workspace_root / target_path).resolve()
            # Compatibility check for Python < 3.9 using os.path.commonpath
            common = os.path.commonpath([str(self.workspace_root), str(resolved)])
            return common == str(self.workspace_root)
        except Exception:
            return False

    def validate_path(self, target_path: str | Path) -> Path:
        """Validate and return safe resolved Path or raise SecurityException."""
        raw_path = Path(target_path)
        if raw_path.is_absolute():
            resolved = raw_path.resolve()
        else:
            resolved = (self.workspace_root / raw_path).resolve()

        try:
            common = os.path.commonpath([str(self.workspace_root), str(resolved)])
            if common != str(self.workspace_root):
                raise SecurityException(
                    f"Path traversal blocked: '{target_path}' resolves outside workspace ({self.workspace_root})"
                )
        except ValueError:
            raise SecurityException(f"Invalid path traversal: '{target_path}'")

        # Symlink check: if path exists as symlink, verify its real target stays inside
        check_path = self.workspace_root / target_path if not raw_path.is_absolute() else raw_path
        if check_path.is_symlink():
            real_target = check_path.resolve()
            if not self.is_safe_path(real_target):
                raise SecurityException(
                    f"Symlink target escapes workspace: '{target_path}' -> '{real_target}'"
                )

        return resolved

class ToolPolicy:
    """Classifies commands and actions into SAFE, CONFIRM, or DENY."""

    # Unconditional denied commands/patterns
    DENIED_BINARIES: Set[str] = {
        "mkfs", "dd", "shutdown", "reboot", "poweroff", "init", "telinit",
        "halt", "wipefs", "fdisk", "parted"
    }

    # Safe inspection binaries
    SAFE_BINARIES: Set[str] = {
        "ls", "pwd", "cat", "head", "tail", "grep", "egrep", "fgrep",
        "find", "which", "whereis", "whoami", "uname", "date", "uptime",
        "echo", "printf", "diff", "wc", "sort", "uniq", "tr", "cut",
        "python", "python3", "pytest"
    }

    # Safe subcommands for git
    SAFE_GIT_SUBCOMMANDS: Set[str] = {
        "status", "diff", "log", "branch", "show", "tag", "remote"
    }

    # Commands requiring confirmation
    CONFIRM_BINARIES: Set[str] = {
        "rm", "mv", "cp", "chmod", "chown", "sudo", "su",
        "apt", "apt-get", "dpkg", "systemctl", "service", "kill", "pkill"
    }

    def evaluate_command(self, cmd_str: str) -> tuple[PolicyVerdict, str]:
        """Classify a shell command and return verdict and reason."""
        cmd_clean = cmd_str.strip()
        if not cmd_clean:
            return PolicyVerdict.DENY, "Empty command"

        # Check for fork bombs or raw device pipes
        if ":(){ :|:& };:" in cmd_clean or "/dev/sd" in cmd_clean or "/dev/nvme" in cmd_clean:
            return PolicyVerdict.DENY, "Dangerous system destruction signature detected"

        # Check shell operators: chaining or piping with destructive commands
        # Parse tokens
        try:
            tokens = shlex.split(cmd_clean)
        except Exception:
            tokens = cmd_clean.split()

        if not tokens:
            return PolicyVerdict.DENY, "Malformed command"

        first_token = Path(tokens[0]).name.lower()

        if first_token in self.DENIED_BINARIES:
            return PolicyVerdict.DENY, f"Command '{first_token}' is prohibited by security policy"

        if first_token in self.CONFIRM_BINARIES:
            return PolicyVerdict.CONFIRM, f"Command '{first_token}' requires interactive confirmation"

        if first_token == "git":
            if len(tokens) > 1:
                subcmd = tokens[1].lower()
                if subcmd in self.SAFE_GIT_SUBCOMMANDS:
                    return PolicyVerdict.SAFE, f"Git inspection ('git {subcmd}') is safe"
                return PolicyVerdict.CONFIRM, f"Git modifying command ('git {subcmd}') requires confirmation"
            return PolicyVerdict.SAFE, "Git command is safe"

        # Safe inspection commands
        if first_token in self.SAFE_BINARIES:
            # Special check for python executing arbitrary eval/rm
            if first_token in ("python", "python3"):
                if "-c" in tokens or "-m" in tokens and "pytest" not in tokens and "unittest" not in tokens:
                    return PolicyVerdict.CONFIRM, "Arbitrary python execution requires confirmation"
            return PolicyVerdict.SAFE, f"Inspection command '{first_token}' is safe"

        # Default for unknown commands: require user confirmation
        return PolicyVerdict.CONFIRM, f"Unrecognized binary '{first_token}' requires confirmation"

    def evaluate_file_write(self, target_path: Path) -> tuple[PolicyVerdict, str]:
        """Validate if file write requires confirmation."""
        # Critical system files or dotfiles in workspace
        name = target_path.name
        if name in (".gitignore", ".git", "LICENSE", "pyproject.toml"):
            return PolicyVerdict.CONFIRM, f"Modifying core project file '{name}' requires confirmation"
        return PolicyVerdict.SAFE, f"Writing to '{name}' is permitted"

    def evaluate_file_delete(self, target_path: Path) -> tuple[PolicyVerdict, str]:
        """File deletion is always sensitive."""
        return PolicyVerdict.CONFIRM, f"Deleting file '{target_path.name}' requires confirmation"
