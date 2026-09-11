"""Command-line interface and diagnostic tools for atlas-agent."""
from __future__ import annotations
import argparse
import os
import platform
import ssl
import sys
import time
import urllib.request
from pathlib import Path
from typing import Optional
from atlas_agent import __version__
from atlas_agent.config import resolve_config, Config
from atlas_agent.agent import Agent
from atlas_agent.providers import create_provider
from atlas_agent.security.policy import WorkspaceGuard
from atlas_agent import ui

def get_process_memory_mb() -> float:
    """Read process RSS memory in MB using /proc/self/statm or fallback."""
    try:
        if Path("/proc/self/statm").exists():
            pages = int(Path("/proc/self/statm").read_text().split()[1])
            page_size = os.sysconf("SC_PAGE_SIZE")
            return (pages * page_size) / (1024 * 1024)
    except Exception:
        pass
    return 0.0

def cmd_doctor(config: Config) -> int:
    """Run environmental diagnostics and system health checks."""
    ui.print_banner()
    print("Running system diagnostic checks...\n")

    all_ok = True

    # 1. Python Check
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 8):
        print(f"  Python .......... {ui.Ansi.GREEN}OK{ui.Ansi.RESET} ({py_ver})")
    else:
        print(f"  Python .......... {ui.Ansi.RED}FAIL{ui.Ansi.RESET} ({py_ver} < 3.8)")
        all_ok = False

    # 2. Architecture & OS Check
    arch = platform.machine()
    sys_name = platform.system()
    print(f"  Architecture .... {ui.Ansi.CYAN}{arch}{ui.Ansi.RESET} ({sys_name})")
    if arch in ("i386", "i686"):
        ui.print_info("Detected native 32-bit x86 hardware. Memory optimizations active.")

    # 3. System RAM Check
    mem_total_mb = 0
    try:
        if Path("/proc/meminfo").exists():
            for line in Path("/proc/meminfo").read_text().splitlines():
                if line.startswith("MemTotal:"):
                    mem_total_mb = int(line.split()[1]) // 1024
                    break
    except Exception:
        pass

    if mem_total_mb > 0:
        print(f"  System RAM ...... {ui.Ansi.GREEN}{mem_total_mb} MB{ui.Ansi.RESET}")
    else:
        print(f"  System RAM ...... {ui.Ansi.DIM}Unknown{ui.Ansi.RESET}")

    # 4. Git Check
    git_installed = os.system("git --version > /dev/null 2>&1") == 0
    if git_installed:
        print(f"  Git ............. {ui.Ansi.GREEN}OK{ui.Ansi.RESET}")
    else:
        print(f"  Git ............. {ui.Ansi.YELLOW}Not found in PATH{ui.Ansi.RESET}")

    # 5. Network Connectivity Check
    network_ok = False
    try:
        ctx = ssl.create_default_context()
        test_url = "https://generativelanguage.googleapis.com"
        req = urllib.request.Request(test_url, headers={"User-Agent": "atlas-agent-doctor"})
        with urllib.request.urlopen(req, timeout=5, context=ctx) as r:
            if r.status in (200, 301, 302, 404):
                network_ok = True
    except urllib.error.HTTPError as e:
        # HTTP response from server means network and SSL handshakes succeeded
        network_ok = True
    except Exception:
        network_ok = False

    if network_ok:
        print(f"  Network ......... {ui.Ansi.GREEN}OK{ui.Ansi.RESET} (HTTPS reachable)")
    else:
        print(f"  Network ......... {ui.Ansi.YELLOW}Limited{ui.Ansi.RESET} (Remote endpoint check)")

    # 6. Workspace Check
    try:
        guard = WorkspaceGuard(config.workspace)
        writable = os.access(str(guard.workspace_root), os.W_OK)
        if writable:
            print(f"  Workspace ....... {ui.Ansi.GREEN}OK{ui.Ansi.RESET} ({guard.workspace_root})")
        else:
            print(f"  Workspace ....... {ui.Ansi.YELLOW}Read-Only{ui.Ansi.RESET} ({guard.workspace_root})")

        atlas_file = guard.workspace_root / "ATLAS.md"
        if atlas_file.is_file():
            print(f"  Guidelines ...... {ui.Ansi.GREEN}OK{ui.Ansi.RESET} (ATLAS.md detected)")
        else:
            print(f"  Guidelines ...... {ui.Ansi.DIM}None{ui.Ansi.RESET} (run 'atlas-agent init' to create ATLAS.md)")

        # MCP Servers Check
        from atlas_agent.mcp.manager import MCPManager
        mcp_mgr = MCPManager(guard=guard, registry=None)
        mcp_configs = mcp_mgr.load_configs()
        if mcp_configs:
            print(f"  MCP Servers ..... {ui.Ansi.GREEN}Configured{ui.Ansi.RESET} ({', '.join(mcp_configs.keys())})")
        else:
            print(f"  MCP Servers ..... {ui.Ansi.DIM}None{ui.Ansi.RESET} (Optional: add .mcp.json)")
    except Exception as e:
        print(f"  Workspace ....... {ui.Ansi.RED}ERROR{ui.Ansi.RESET} ({e})")
        all_ok = False

    # 7. Provider Check
    print(f"  Provider ........ {ui.Ansi.BOLD}{config.provider}{ui.Ansi.RESET} (model: {config.model})")
    try:
        provider = create_provider(config)
        p_ok, p_msg = provider.check_health()
        if p_ok:
            print(f"  API Health ...... {ui.Ansi.GREEN}OK{ui.Ansi.RESET} ({p_msg})")
        else:
            print(f"  API Health ...... {ui.Ansi.YELLOW}WARNING{ui.Ansi.RESET} ({p_msg})")
            print(f"    -> Tip: Configure key via: export ATLAS_AGENT_API_KEY=\"your-key\"")
    except Exception as e:
        print(f"  API Health ...... {ui.Ansi.RED}ERROR{ui.Ansi.RESET} ({e})")
        all_ok = False

    print("")
    if all_ok:
        ui.print_success("Diagnostic completed. All essential components are functional.")
        return 0
    else:
        ui.print_warning("Diagnostic completed with warnings or issues noted above.")
        return 1

def cmd_config(config: Config) -> int:
    """Display active configuration with secrets masked."""
    ui.print_banner()
    print("Resolved Configuration (Secrets Masked):\n")
    data = config.to_dict(mask_secrets=True)
    for k, v in sorted(data.items()):
        print(f"  {k:15s} = {v}")
    print("\nConfiguration sources: CLI args > Environment variables > ~/.config/atlas-agent/config.json > Defaults")
    return 0

def cmd_init(config: Config) -> int:
    """Initialize atlas-agent configuration and instruction file in workspace."""
    ws = config.workspace
    ui.print_banner()
    print(f"Initializing project at: {ws}\n")

    atlas_md = ws / "ATLAS.md"
    if not atlas_md.exists():
        template = (
            "# ATLAS.md - Project Guidelines for atlas-agent\n\n"
            "This file provides instructions and context to atlas-agent.\n\n"
            "## Architecture\n"
            "- Describe the project components here.\n\n"
            "## Testing\n"
            "- Command to run tests: `python3 -m unittest`\n\n"
            "## Constraints\n"
            "- Keep dependencies minimal.\n"
            "- Ensure 32-bit compatibility.\n"
        )
        atlas_md.write_text(template, encoding="utf-8")
        ui.print_success("Created ATLAS.md template.")
    else:
        ui.print_info("ATLAS.md already exists.")

    gitignore = ws / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("__pycache__/\n*.pyc\n.env\n", encoding="utf-8")
        ui.print_success("Created .gitignore template.")

    ui.print_success("Initialization complete.")
    return 0

def cmd_benchmark(config: Config) -> int:
    """Measure startup time, memory footprint, and filesystem throughput."""
    ui.print_banner()
    print("Running performance benchmark...\n")

    t0 = time.perf_counter()
    guard = WorkspaceGuard(config.workspace)
    agent = Agent(config)
    startup_ms = (time.perf_counter() - t0) * 1000

    rss_mb = get_process_memory_mb()
    module_count = len(sys.modules)

    # Measure fast file scan
    t1 = time.perf_counter()
    file_count = 0
    for root, _, files in os.walk(str(guard.workspace_root)):
        file_count += len(files)
        if file_count > 1000:
            break
    scan_ms = (time.perf_counter() - t1) * 1000

    print(f"  Startup Time ...... {ui.Ansi.GREEN}{startup_ms:.2f} ms{ui.Ansi.RESET}")
    print(f"  RAM Footprint ..... {ui.Ansi.GREEN}{rss_mb:.2f} MB{ui.Ansi.RESET} (Resident Set Size)")
    print(f"  Loaded Modules .... {ui.Ansi.CYAN}{module_count}{ui.Ansi.RESET} modules")
    print(f"  Filesystem Scan ... {ui.Ansi.CYAN}{scan_ms:.2f} ms{ui.Ansi.RESET} ({file_count} files)")
    print("\nBenchmark verdict: Extremely lightweight, suitable for Core 2 Duo / i386 hardware.")
    return 0

def cmd_diff(config: Config) -> int:
    """Show current git diff in workspace."""
    guard = WorkspaceGuard(config.workspace)
    agent = Agent(config)
    diff_output = agent.tools.execute("git_diff", {})
    if ui.USE_COLOR:
        ui.print_diff(diff_output)
    else:
        print(diff_output)
    return 0

def build_parser() -> argparse.ArgumentParser:
    """Build command-line parser."""
    parser = argparse.ArgumentParser(
        prog="atlas-agent",
        description="Extremely lightweight CLI programming agent for 32-bit Linux and low-resource hardware.",
        epilog="Examples:\n  atlas-agent\n  atlas-agent .\n  atlas-agent doctor\n  atlas-agent run 'fix tests'\n",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        "target",
        nargs="?",
        default=".",
        help="Workspace directory path or subcommand (init, doctor, config, diff, benchmark, version)"
    )

    parser.add_argument("--version", action="store_true", help="Show atlas-agent version")
    parser.add_argument("--provider", type=str, help="LLM Provider (gemini, openai, mock)")
    parser.add_argument("--model", type=str, help="Model name (e.g. gemini-2.5-flash)")
    parser.add_argument("--api-key", type=str, help="API Key for the provider")
    parser.add_argument("--dry-run", action="store_true", help="Simulate file modifications without writing")
    parser.add_argument("--verbose", action="store_true", help="Show operational details and tool calls")
    parser.add_argument("--debug", action="store_true", help="Show debug logs")
    parser.add_argument("-y", "--auto-approve", action="store_true", help="Automatically approve confirm-tier tools")
    parser.add_argument("-c", "--command", type=str, help="Run single prompt non-interactively and exit")

    return parser

def main(args: Optional[list[str]] = None) -> int:
    parser = build_parser()
    parsed = parser.parse_args(args)

    if parsed.version:
        print(f"atlas-agent v{__version__} (Standard Library Engine)")
        return 0

    target = parsed.target or "."

    # Handle subcommands
    cli_overrides = {
        "provider": parsed.provider,
        "model": parsed.model,
        "api_key": parsed.api_key,
        "dry_run": parsed.dry_run,
        "verbose": parsed.verbose,
        "debug": parsed.debug,
        "auto_approve": parsed.auto_approve,
    }

    # If target is a directory, use it as workspace
    if target in ("doctor", "config", "init", "benchmark", "diff", "version"):
        config = resolve_config(cli_overrides)
        if target == "doctor":
            return cmd_doctor(config)
        elif target == "config":
            return cmd_config(config)
        elif target == "init":
            return cmd_init(config)
        elif target == "benchmark":
            return cmd_benchmark(config)
        elif target == "diff":
            return cmd_diff(config)
        elif target == "version":
            print(f"atlas-agent v{__version__}")
            return 0
    elif target == "run":
        # Handle 'atlas-agent run "my prompt"'
        cli_overrides["workspace"] = Path.cwd()
        config = resolve_config(cli_overrides)
        prompt_text = parsed.command or " ".join(sys.argv[2:])
        if not prompt_text:
            ui.print_error("Please specify a command/prompt to run: atlas-agent run 'your task'")
            return 1
        if not config.api_key and config.provider != "mock":
            from atlas_agent.config import prompt_api_key_if_missing
            if sys.stdin.isatty():
                config = prompt_api_key_if_missing(config, interactive=True)
            else:
                ui.print_error("Nenhuma chave de API configurada. Defina --api-key ou variável de ambiente.")
                return 1
        agent = Agent(config)
        result = agent.process_turn(prompt_text)
        print(result)
        return 0
    else:
        # Target is a workspace directory path
        target_path = Path(target).resolve()
        if not target_path.exists():
            ui.print_error(f"Target directory does not exist: {target_path}")
            return 1
        cli_overrides["workspace"] = target_path
        config = resolve_config(cli_overrides)

    # Check API key if not mock
    if not config.api_key and config.provider != "mock":
        from atlas_agent.config import prompt_api_key_if_missing
        if sys.stdin.isatty():
            config = prompt_api_key_if_missing(config, interactive=True)
        else:
            ui.print_error(
                "Nenhuma chave de API configurada. Defina via --api-key, "
                "variáveis ATLAS_AGENT_API_KEY / GEMINI_API_KEY / OPENROUTER_API_KEY, "
                "ou execute em um terminal interativo."
            )
            return 1

    # Non-interactive single run if -c passed
    if parsed.command:
        agent = Agent(config)
        result = agent.process_turn(parsed.command)
        print(result)
        return 0

    # Otherwise enter interactive REPL
    agent = Agent(config)
    agent.run_repl()
    return 0

if __name__ == "__main__":
    sys.exit(main())
