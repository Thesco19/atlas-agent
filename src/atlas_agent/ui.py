"""Lightweight ANSI formatting and terminal UI utilities."""
from __future__ import annotations
import os
import sys

def _supports_color() -> bool:
    """Determine if the current terminal supports ANSI colors."""
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

USE_COLOR = _supports_color()

class Ansi:
    RESET = "\033[0m" if USE_COLOR else ""
    BOLD = "\033[1m" if USE_COLOR else ""
    DIM = "\033[2m" if USE_COLOR else ""
    
    RED = "\033[31m" if USE_COLOR else ""
    GREEN = "\033[32m" if USE_COLOR else ""
    YELLOW = "\033[33m" if USE_COLOR else ""
    BLUE = "\033[34m" if USE_COLOR else ""
    MAGENTA = "\033[35m" if USE_COLOR else ""
    CYAN = "\033[36m" if USE_COLOR else ""
    WHITE = "\033[37m" if USE_COLOR else ""

def print_banner() -> None:
    """Display simple, clean startup header."""
    print(f"{Ansi.BOLD}{Ansi.CYAN}atlas-agent{Ansi.RESET} {Ansi.DIM}(v0.1.0 - 32-bit/Low-Resource Engine){Ansi.RESET}")

def print_info(msg: str) -> None:
    print(f"{Ansi.BLUE}ℹ{Ansi.RESET} {msg}")

def print_success(msg: str) -> None:
    print(f"{Ansi.GREEN}✓{Ansi.RESET} {msg}")

def print_warning(msg: str) -> None:
    print(f"{Ansi.YELLOW}⚠{Ansi.RESET} {msg}")

def print_error(msg: str) -> None:
    print(f"{Ansi.RED}✗{Ansi.RESET} {msg}", file=sys.stderr)

def print_tool(tool_name: str, args_summary: str) -> None:
    print(f"{Ansi.MAGENTA}▶ [{tool_name}]{Ansi.RESET} {args_summary}")

def print_diff(diff_text: str) -> None:
    """Print unified diff with syntax coloring."""
    for line in diff_text.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            print(f"{Ansi.BOLD}{line}{Ansi.RESET}")
        elif line.startswith("+"):
            print(f"{Ansi.GREEN}{line}{Ansi.RESET}")
        elif line.startswith("-"):
            print(f"{Ansi.RED}{line}{Ansi.RESET}")
        elif line.startswith("@@"):
            print(f"{Ansi.CYAN}{line}{Ansi.RESET}")
        else:
            print(f"{Ansi.DIM}{line}{Ansi.RESET}")

def ask_confirmation(prompt_text: str, default: bool = False) -> bool:
    """Prompt user for confirmation (y/N or Y/n)."""
    default_str = "Y/n" if default else "y/N"
    sys.stdout.write(f"{Ansi.YELLOW}⚠ {prompt_text} [{default_str}]: {Ansi.RESET}")
    sys.stdout.flush()
    try:
        choice = input().strip().lower()
        if not choice:
            return default
        return choice in ("y", "yes", "s", "sim")
    except (EOFError, KeyboardInterrupt):
        print("")
        return False
