"""Git integration tools for project state inspection and safe committing."""
from __future__ import annotations
import subprocess
from atlas_agent.security.policy import WorkspaceGuard
from atlas_agent import ui

def _run_git(guard: WorkspaceGuard, args: list[str]) -> tuple[int, str]:
    """Helper to run git command safely within workspace."""
    try:
        proc = subprocess.run(
            ["git"] + args,
            cwd=str(guard.workspace_root),
            capture_output=True,
            text=True,
            timeout=15,
            errors="replace"
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode, output.strip()
    except FileNotFoundError:
        return 1, "Git binary not found in PATH."
    except Exception as e:
        return 1, f"Git execution error: {e}"

def is_git_repo(guard: WorkspaceGuard) -> bool:
    """Check if workspace is a git repository."""
    code, _ = _run_git(guard, ["rev-parse", "--is-inside-work-tree"])
    return code == 0

def git_status(guard: WorkspaceGuard) -> str:
    """Inspect current git branch, staged files, and modified working tree."""
    if not is_git_repo(guard):
        return "Not a git repository."

    code, branch = _run_git(guard, ["branch", "--show-current"])
    current_branch = branch if code == 0 and branch else "detached/unknown"

    code, status_out = _run_git(guard, ["status", "--short"])
    if not status_out:
        return f"Branch: {current_branch}\nWorking tree clean (no changes)."

    return f"Branch: {current_branch}\nChanges:\n{status_out}"

def git_diff(guard: WorkspaceGuard, staged: bool = False) -> str:
    """Inspect uncommitted diffs."""
    if not is_git_repo(guard):
        return "Not a git repository."

    args = ["diff"]
    if staged:
        args.append("--staged")

    code, diff_out = _run_git(guard, args)
    if not diff_out:
        target = "staged" if staged else "working tree"
        return f"No {target} git diff."

    # Truncate if diff is huge
    lines = diff_out.splitlines()
    if len(lines) > 200:
        return "\n".join(lines[:200]) + f"\n... [Diff truncated: {len(lines) - 200} lines omitted]"

    return diff_out

def git_log(guard: WorkspaceGuard, max_count: int = 5) -> str:
    """Show recent commits."""
    if not is_git_repo(guard):
        return "Not a git repository."

    code, log_out = _run_git(guard, ["log", f"-n{max_count}", "--oneline", "--decorate"])
    if not log_out:
        return "No commits yet."
    return f"Recent commits:\n{log_out}"

def git_commit(
    guard: WorkspaceGuard,
    message: str,
    auto_approve: bool = False
) -> str:
    """Create a git commit with explicit confirmation."""
    if not is_git_repo(guard):
        return "Error: Not a git repository."

    clean_msg = message.strip()
    if not clean_msg:
        return "Error: Commit message cannot be empty."

    if not auto_approve:
        allowed = ui.ask_confirmation(f"Create git commit with message: '{clean_msg}'?", default=False)
        if not allowed:
            return "Git commit cancelled by user."

    # Commit tracked and staged files
    code, out = _run_git(guard, ["commit", "-m", clean_msg])
    if code != 0:
        return f"Git commit failed:\n{out}"
    return f"Git commit created successfully:\n{out}"
