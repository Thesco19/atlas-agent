"""Controlled shell command execution with security policy enforcement."""
from __future__ import annotations
import subprocess
from typing import Optional
from atlas_agent.security.policy import ToolPolicy, PolicyVerdict, WorkspaceGuard
from atlas_agent import ui

MAX_OUTPUT_LINES = 100
MAX_OUTPUT_BYTES = 8192

def run_command(
    policy: ToolPolicy,
    guard: WorkspaceGuard,
    command: str,
    timeout: int = 30,
    auto_approve: bool = False
) -> str:
    """Execute shell command inside workspace with policy checks."""
    verdict, reason = policy.evaluate_command(command)

    if verdict == PolicyVerdict.DENY:
        return f"Security Error: Command blocked by policy: {reason}"

    if verdict == PolicyVerdict.CONFIRM and not auto_approve:
        prompt_msg = f"Model requested to run command: '{command}' ({reason}). Allow?"
        allowed = ui.ask_confirmation(prompt_msg, default=False)
        if not allowed:
            return f"Command execution denied by user: '{command}'"

    try:
        proc = subprocess.run(
            command,
            cwd=str(guard.workspace_root),
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            errors="replace"
        )
    except subprocess.TimeoutExpired:
        return f"Command timed out after {timeout} seconds: '{command}'"
    except Exception as e:
        return f"Failed to execute command '{command}': {e}"

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    exit_code = proc.returncode

    # Build output
    lines = []
    if stdout:
        lines.append(stdout)
    if stderr:
        lines.append(f"[STDERR]\n{stderr}")

    raw_output = "\n".join(lines).strip()
    if not raw_output:
        if exit_code != 0:
            return f"[Exit code {exit_code}] (no output)."
        return f"Command completed with exit code 0 (no output)."

    # Truncate if output is too voluminous to protect memory and tokens
    split_lines = raw_output.splitlines()
    if len(split_lines) > MAX_OUTPUT_LINES:
        truncated_text = "\n".join(split_lines[:MAX_OUTPUT_LINES])
        truncated_text += f"\n... [Output truncated: {len(split_lines) - MAX_OUTPUT_LINES} lines omitted]"
        raw_output = truncated_text
    elif len(raw_output) > MAX_OUTPUT_BYTES:
        raw_output = raw_output[:MAX_OUTPUT_BYTES] + "\n... [Output truncated by byte limit]"

    prefix = f"[Exit code {exit_code}]\n" if exit_code != 0 else ""
    return prefix + raw_output
