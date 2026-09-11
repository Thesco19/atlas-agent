"""Configuration management for atlas-agent.

Priority:
1. CLI arguments
2. Environment variables
3. Configuration file (~/.config/atlas-agent/config.json)
4. Safe defaults
"""
from __future__ import annotations
import os
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Any, Dict

DEFAULT_CONFIG_DIR = Path.home() / ".config" / "atlas-agent"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.json"
DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"

@dataclass
class Config:
    provider: str = "gemini"
    model: str = "gemini-3.1-flash-lite"
    api_key: Optional[str] = None
    endpoint: Optional[str] = None
    temperature: float = 0.2
    max_tokens: int = 4096
    timeout: int = 45
    max_retries: int = 3
    workspace: Path = field(default_factory=Path.cwd)
    verbose: bool = False
    debug: bool = False
    dry_run: bool = False
    max_iterations: int = 10
    auto_approve: bool = False

    def masked_api_key(self) -> str:
        """Return masked key for display to avoid leaking secrets."""
        if not self.api_key:
            return "(not configured)"
        k = self.api_key.strip()
        if len(k) <= 8:
            return "****"
        return f"{k[:4]}...{k[-4:]}"

    def to_dict(self, mask_secrets: bool = True) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "api_key": self.masked_api_key() if mask_secrets else self.api_key,
            "endpoint": self.endpoint or "(default)",
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "workspace": str(self.workspace),
            "verbose": self.verbose,
            "debug": self.debug,
            "dry_run": self.dry_run,
            "max_iterations": self.max_iterations,
            "auto_approve": self.auto_approve,
        }

def load_file_config(path: Optional[Path] = None) -> Dict[str, Any]:
    """Read configuration from JSON or INI file if present."""
    config_path = path or DEFAULT_CONFIG_FILE
    if not config_path.is_file():
        return {}
    try:
        content = config_path.read_text(encoding="utf-8")
        # Try JSON first
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    except Exception:
        pass
    return {}

def resolve_config(
    cli_args: Optional[Dict[str, Any]] = None,
    config_path: Optional[Path] = None
) -> Config:
    """Resolve final configuration honoring priority hierarchy."""
    cli_args = cli_args or {}
    file_cfg = load_file_config(config_path)

    # 1. Base defaults
    cfg = Config()

    # 2. File config overrides
    if "provider" in file_cfg:
        cfg.provider = str(file_cfg["provider"])
    if "model" in file_cfg:
        cfg.model = str(file_cfg["model"])
    if "api_key" in file_cfg:
        cfg.api_key = str(file_cfg["api_key"])
    if "endpoint" in file_cfg:
        cfg.endpoint = str(file_cfg["endpoint"])
    if "temperature" in file_cfg:
        cfg.temperature = float(file_cfg["temperature"])
    if "max_tokens" in file_cfg:
        cfg.max_tokens = int(file_cfg["max_tokens"])
    if "timeout" in file_cfg:
        cfg.timeout = int(file_cfg["timeout"])
    if "max_retries" in file_cfg:
        cfg.max_retries = int(file_cfg["max_retries"])
    if "workspace" in file_cfg:
        cfg.workspace = Path(file_cfg["workspace"]).resolve()
    if "max_iterations" in file_cfg:
        cfg.max_iterations = int(file_cfg["max_iterations"])

    # 3. Environment variable overrides
    env_provider = os.environ.get("ATLAS_AGENT_PROVIDER")
    if env_provider:
        cfg.provider = env_provider

    env_model = os.environ.get("ATLAS_AGENT_MODEL")
    if env_model:
        cfg.model = env_model

    env_endpoint = os.environ.get("ATLAS_AGENT_ENDPOINT")
    if env_endpoint:
        cfg.endpoint = env_endpoint

    # Support specific or generic API keys
    env_openrouter_key = os.environ.get("OPENROUTER_API_KEY")
    if env_openrouter_key:
        if not env_provider:
            cfg.provider = "openrouter"
        if not env_endpoint:
            cfg.endpoint = "https://openrouter.ai/api/v1"
        cfg.api_key = env_openrouter_key

    env_key = (
        os.environ.get("ATLAS_AGENT_API_KEY")
        or os.environ.get("GEMINI_API_KEY")
        or env_openrouter_key
        or os.environ.get("OPENAI_API_KEY")
    )
    if env_key and not cfg.api_key:
        cfg.api_key = env_key

    env_temp = os.environ.get("ATLAS_AGENT_TEMPERATURE")
    if env_temp:
        try:
            cfg.temperature = float(env_temp)
        except ValueError:
            pass

    env_tokens = os.environ.get("ATLAS_AGENT_MAX_TOKENS")
    if env_tokens:
        try:
            cfg.max_tokens = int(env_tokens)
        except ValueError:
            pass

    env_timeout = os.environ.get("ATLAS_AGENT_TIMEOUT")
    if env_timeout:
        try:
            cfg.timeout = int(env_timeout)
        except ValueError:
            pass

    # 4. CLI arguments overrides
    for key, value in cli_args.items():
        if value is not None and hasattr(cfg, key):
            setattr(cfg, key, value)

    # Ensure workspace is resolved Path
    if isinstance(cfg.workspace, str):
        cfg.workspace = Path(cfg.workspace).resolve()
    else:
        cfg.workspace = cfg.workspace.resolve()

    return cfg


def save_file_config(config: Config, path: Optional[Path] = None) -> bool:
    """Save configuration to ~/.config/atlas-agent/config.json with safe 0600 permissions."""
    target = path or DEFAULT_CONFIG_FILE
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        data: Dict[str, Any] = {
            "provider": config.provider,
            "model": config.model,
            "api_key": config.api_key,
        }
        if config.endpoint:
            data["endpoint"] = config.endpoint
        if config.temperature != 0.2:
            data["temperature"] = config.temperature
        if config.max_tokens != 4096:
            data["max_tokens"] = config.max_tokens

        target.write_text(json.dumps(data, indent=2), encoding="utf-8")
        try:
            os.chmod(target, 0o600)
        except Exception:
            pass
        return True
    except Exception:
        return False


def prompt_api_key_if_missing(config: Config, interactive: bool = True) -> Config:
    """Interactively prompt user for provider and API key if not configured."""
    import sys
    from atlas_agent import ui

    if config.api_key or config.provider == "mock":
        return config

    if not interactive or not sys.stdin.isatty():
        return config

    print(f"\n{ui.Ansi.BOLD}{ui.Ansi.CYAN}┌─────────────────────────────────────────────────────────────┐{ui.Ansi.RESET}")
    print(f"{ui.Ansi.BOLD}{ui.Ansi.CYAN}│  🔑 Configuração de Provedor & Chave de API                 │{ui.Ansi.RESET}")
    print(f"{ui.Ansi.BOLD}{ui.Ansi.CYAN}│  Nenhuma chave de API detectada para a sessão.              │{ui.Ansi.RESET}")
    print(f"{ui.Ansi.BOLD}{ui.Ansi.CYAN}└─────────────────────────────────────────────────────────────┘{ui.Ansi.RESET}\n")
    print("Escolha o provedor de IA desejado:")
    print(f"  {ui.Ansi.BOLD}[1]{ui.Ansi.RESET} Google Gemini   {ui.Ansi.DIM}(Recomendado - gemini-3.1-flash-lite, gratuito no AI Studio){ui.Ansi.RESET}")
    print(f"  {ui.Ansi.BOLD}[2]{ui.Ansi.RESET} OpenRouter      {ui.Ansi.DIM}(openrouter.ai - multi-modelos, Llama, DeepSeek, etc.){ui.Ansi.RESET}")
    print(f"  {ui.Ansi.BOLD}[3]{ui.Ansi.RESET} OpenAI ou outro {ui.Ansi.DIM}(Endpoint compatível ou modelo local){ui.Ansi.RESET}")
    print(f"  {ui.Ansi.BOLD}[4]{ui.Ansi.RESET} Modo Offline    {ui.Ansi.DIM}(Simulação / Mock para testes sem internet){ui.Ansi.RESET}\n")

    while True:
        try:
            choice = input(f"Selecione uma opção [1-4] (padrão: 1): ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nOperação cancelada.")
            sys.exit(0)

        if not choice or choice == "1":
            config.provider = "gemini"
            if not config.model or config.model in ("gpt-4o-mini", "gemini-2.5-flash"):
                config.model = DEFAULT_GEMINI_MODEL
            config.endpoint = None
            print(f"\n{ui.Ansi.DIM}Obtenha sua chave gratuitamente em: https://aistudio.google.com/app/apikey{ui.Ansi.RESET}")
            try:
                key = input("Informe sua chave Gemini API: ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nOperação cancelada.")
                sys.exit(0)
            if key:
                config.api_key = key
                break
            else:
                print(f"{ui.Ansi.YELLOW}A chave não pode ser vazia. Tente novamente.{ui.Ansi.RESET}")

        elif choice == "2":
            config.provider = "openrouter"
            config.endpoint = "https://openrouter.ai/api/v1"
            if not config.model or config.model == "gemini-2.5-flash":
                config.model = "google/gemini-2.5-flash"
            print(f"\n{ui.Ansi.DIM}Obtenha sua chave em: https://openrouter.ai/keys{ui.Ansi.RESET}")
            print(f"{ui.Ansi.DIM}Modelo padrão selecionado: {config.model}{ui.Ansi.RESET}")
            try:
                key = input("Informe sua chave OpenRouter (sk-or-v1-...): ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nOperação cancelada.")
                sys.exit(0)
            if key:
                config.api_key = key
                break
            else:
                print(f"{ui.Ansi.YELLOW}A chave não pode ser vazia. Tente novamente.{ui.Ansi.RESET}")

        elif choice == "3":
            config.provider = "openai"
            try:
                ep = input("Endpoint (padrão: https://api.openai.com/v1): ").strip()
                if ep:
                    config.endpoint = ep
                mdl = input("Modelo (padrão: gpt-4o-mini): ").strip()
                if mdl:
                    config.model = mdl
                key = input("Informe sua API Key: ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nOperação cancelada.")
                sys.exit(0)
            if key:
                config.api_key = key
                break
            else:
                print(f"{ui.Ansi.YELLOW}A chave não pode ser vazia. Tente novamente.{ui.Ansi.RESET}")

        elif choice == "4":
            config.provider = "mock"
            config.api_key = "mock-key"
            print(f"{ui.Ansi.GREEN}Modo Offline/Mock ativado.{ui.Ansi.RESET}")
            return config
        else:
            print(f"{ui.Ansi.YELLOW}Opção inválida. Digite 1, 2, 3 ou 4.{ui.Ansi.RESET}")

    # Ask if user wants to save
    try:
        save_opt = input(f"\nDeseja salvar essa configuração em {DEFAULT_CONFIG_FILE}? [S/n]: ").strip().lower()
        if save_opt in ("", "s", "sim", "y", "yes"):
            if save_file_config(config):
                print(f"{ui.Ansi.GREEN}✓ Configuração salva com sucesso em {DEFAULT_CONFIG_FILE} (permissões 0600){ui.Ansi.RESET}\n")
            else:
                print(f"{ui.Ansi.YELLOW}Aviso: Não foi possível salvar o arquivo de configuração.{ui.Ansi.RESET}\n")
        else:
            print(f"{ui.Ansi.DIM}Configuração mantida apenas para a sessão atual.{ui.Ansi.RESET}\n")
    except (KeyboardInterrupt, EOFError):
        pass

    return config
