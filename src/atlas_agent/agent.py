"""Core agent orchestrator executing the model-tool reasoning loop."""
from __future__ import annotations
import signal
import sys
from typing import List, Optional, Set
from atlas_agent.config import Config
from atlas_agent.security.policy import WorkspaceGuard, ToolPolicy
from atlas_agent.tools import ToolRegistry
from atlas_agent.context import ContextManager
from atlas_agent.providers.base import (
    BaseProvider, Message, ToolCall, ToolResult, ProviderResponse
)
from atlas_agent.providers import create_provider
from atlas_agent.mcp.manager import MCPManager
from atlas_agent import ui

class Agent:
    """Agent orchestrator managing the conversational loop and tool execution."""

    def __init__(
        self,
        config: Config,
        provider: Optional[BaseProvider] = None
    ):
        self.config = config
        self.guard = WorkspaceGuard(config.workspace)
        self.policy = ToolPolicy()
        self.tools = ToolRegistry(
            guard=self.guard,
            policy=self.policy,
            dry_run=config.dry_run,
            auto_approve=config.auto_approve
        )
        self.mcp_mgr = MCPManager(guard=self.guard, registry=self.tools)
        try:
            self.mcp_mgr.initialize_servers()
        except Exception:
            pass

        self.context_mgr = ContextManager(
            guard=self.guard,
            max_context_tokens=config.max_tokens * 2
        )
        self.provider = provider or create_provider(config)
        self.history: List[Message] = []
        self._interrupted = False

    def reset_session(self) -> None:
        """Clear conversation history."""
        self.history.clear()

    def process_turn(self, user_prompt: str) -> str:
        """Execute a single conversational turn with tools execution loop."""
        self._interrupted = False

        # Set up signal handler for graceful Ctrl+C cancellation
        original_sigint = signal.getsignal(signal.SIGINT)

        def handle_sigint(sig, frame):
            self._interrupted = True
            ui.print_warning("\nCancellation requested by user (Ctrl+C)...")

        signal.signal(signal.SIGINT, handle_sigint)

        try:
            # 1. Inspect mentioned files to preload relevant context
            mentioned_files = self.context_mgr.extract_mentioned_paths(user_prompt)
            preloaded_context = []
            for mf in mentioned_files:
                content = self.tools.execute("read_file", {"path": mf, "limit": 100})
                preloaded_context.append(f"--- Context for mentioned file '{mf}' ---\n{content}")

            effective_prompt = user_prompt
            if preloaded_context:
                effective_prompt = f"{user_prompt}\n\n" + "\n\n".join(preloaded_context)

            # Add user message
            self.history.append(Message(role="user", content=effective_prompt))

            system_prompt = self.context_mgr.build_system_prompt()
            tool_defs = self.tools.get_definitions()

            iteration = 0
            call_fingerprints: Set[str] = set()

            while iteration < self.config.max_iterations and not self._interrupted:
                iteration += 1

                # Prune history if nearing limits
                active_history = self.context_mgr.prune_history(
                    self.history,
                    self.context_mgr.max_context_tokens
                )

                if self.config.verbose:
                    ui.print_info(f"Iteration {iteration}/{self.config.max_iterations} - Querying {self.config.provider}...")

                try:
                    resp: ProviderResponse = self.provider.chat(
                        messages=active_history,
                        tools=tool_defs,
                        system_instruction=system_prompt
                    )
                except Exception as e:
                    ui.print_error(f"Provider error: {e}")
                    return f"Error during model inference: {e}"

                if self._interrupted:
                    return "Operation cancelled by user."

                # If no tool calls, the model gave its final answer
                if not resp.tool_calls:
                    final_text = resp.text.strip()
                    self.history.append(Message(role="model", content=final_text))
                    return final_text

                # Log tool calls and model thoughts if any text was included
                if resp.text:
                    clean_thought = resp.text.strip()
                    if clean_thought:
                        print(f"{ui.Ansi.DIM}{clean_thought}{ui.Ansi.RESET}")

                # Append model message with tool calls
                self.history.append(Message(
                    role="model",
                    content=resp.text or "",
                    tool_calls=resp.tool_calls
                ))

                tool_results: List[ToolResult] = []

                # Execute requested tools
                for tc in resp.tool_calls:
                    if self._interrupted:
                        break

                    # Infinite loop detection
                    fingerprint = f"{tc.name}:{sorted(tc.arguments.items())}"
                    if fingerprint in call_fingerprints and tc.name in ("read_file", "list_directory"):
                        output = f"Notice: Tool '{tc.name}' was already executed with identical arguments. Move forward."
                    else:
                        call_fingerprints.add(fingerprint)
                        arg_summary = ", ".join(f"{k}='{v}'" for k, v in list(tc.arguments.items())[:3])
                        ui.print_tool(tc.name, arg_summary)

                        output = self.tools.execute(tc.name, tc.arguments)

                        # If tool produced diff, format nicely
                        if "Diff:" in output and ui.USE_COLOR:
                            parts = output.split("Diff:\n", 1)
                            print(parts[0])
                            ui.print_diff(parts[1])
                        elif self.config.verbose:
                            preview = output[:200] + ("..." if len(output) > 200 else "")
                            print(f"{ui.Ansi.DIM}{preview}{ui.Ansi.RESET}")

                    tool_results.append(ToolResult(
                        call_id=tc.id,
                        name=tc.name,
                        content=output
                    ))

                # Append tool results as user/tool response for next turn
                self.history.append(Message(
                    role="user",
                    content="",
                    tool_results=tool_results
                ))

            if iteration >= self.config.max_iterations:
                ui.print_warning(f"Reached maximum iteration limit ({self.config.max_iterations}).")
                return "Reached maximum iteration steps without concluding."

            return "Session ended."
        finally:
            signal.signal(signal.SIGINT, original_sigint)

    def run_repl(self) -> None:
        """Run interactive terminal session."""
        from atlas_agent.config import prompt_api_key_if_missing

        ui.print_banner()

        # 1. Prompt for API key if missing and not mock
        if not self.config.api_key and self.config.provider != "mock":
            self.config = prompt_api_key_if_missing(self.config, interactive=True)
            self.provider = create_provider(self.config)

        print(f"{ui.Ansi.DIM}Workspace: {self.guard.workspace_root}{ui.Ansi.RESET}")
        print(f"{ui.Ansi.DIM}Provider:  {self.config.provider} ({self.config.model}){ui.Ansi.RESET}")

        # 2. Check and announce ATLAS.md in workspace
        atlas_path = self.guard.workspace_root / "ATLAS.md"
        if atlas_path.is_file():
            try:
                content = atlas_path.read_text(encoding="utf-8", errors="replace").strip()
                lines = [line for line in content.splitlines() if line.strip()]
                ui.print_success(f"Diretrizes do projeto carregadas: ATLAS.md ({len(lines)} linhas de regras)")
            except Exception as e:
                ui.print_warning(f"Aviso ao ler ATLAS.md: {e}")
        else:
            inst_path = self.context_mgr.get_instruction_file_path()
            if inst_path:
                ui.print_info(f"Diretrizes carregadas de: {inst_path.name}")
            else:
                print(f"{ui.Ansi.DIM}Diretrizes: Nenhum ATLAS.md encontrado (use 'atlas-agent init' para criar){ui.Ansi.RESET}")

        # 3. Check and announce MCP servers
        if self.mcp_mgr.clients:
            srv_names = ", ".join(self.mcp_mgr.clients.keys())
            ui.print_success(f"Servidores MCP ativos: {srv_names} ({len(self.mcp_mgr.registered_tools)} ferramentas extras)")

        print(f"{ui.Ansi.DIM}Comandos: 'exit', 'quit' para sair | 'clear' para limpar contexto | Ctrl+C para cancelar.{ui.Ansi.RESET}\n")

        while True:
            try:
                sys.stdout.write(f"{ui.Ansi.BOLD}{ui.Ansi.GREEN}atlas>{ui.Ansi.RESET} ")
                sys.stdout.flush()
                prompt = input().strip()
            except (EOFError, KeyboardInterrupt):
                print(f"\n{ui.Ansi.DIM}Exiting atlas-agent.{ui.Ansi.RESET}")
                break

            if not prompt:
                continue

            if prompt.lower() in ("exit", "quit", ":q"):
                print(f"{ui.Ansi.DIM}Session closed.{ui.Ansi.RESET}")
                break

            if prompt.lower() in ("clear", "reset"):
                self.reset_session()
                ui.print_info("Conversation context cleared.")
                continue

            # Process prompt
            answer = self.process_turn(prompt)
            print(f"\n{answer}\n")
