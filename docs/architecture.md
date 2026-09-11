# Arquitetura do Atlas Agent

O **atlas-agent** foi projetado seguindo o princípio da orquestração determinística e desacoplamento radical: o computador local atua exclusivamente como orquestrador e executor de ferramentas, enquanto a computação de inferência é delegada a modelos remotos de linguagem via chamadas HTTPS eficientes.

```
                          +-------------------------+
                          |   CLI / REPL (Terminal) |
                          +-------------------------+
                                       |
                                       v
                          +-------------------------+
                          |       Agent Core        |
                          | (Turn Loop & State Mgt) |
                          +-------------------------+
                               /               \
                              /                 \
                             v                   v
              +---------------------+     +----------------------+
              |   Context Manager   |     |    Tool Registry     |
              | (ATLAS.md, History, |     | (Security, Dispatch) |
              |    Token Budget)    |     +----------------------+
              +---------------------+                |
                         |                           v
                         v               +-----------------------+
              +---------------------+    |       Subsystems      |
              |   Provider (REST)   |    | - Filesystem (Safe)   |
              |  - Gemini (Default) |    | - Shell (Safe/Confirm)|
              |  - OpenAI/Local LLM |    | - Git (Diff, Status)  |
              |  - Mock (Testing)   |    +-----------------------+
              +---------------------+
                         |
                   HTTPS | (Zero SDK overhead)
                         v
              +---------------------+
              |    Remote LLM API   |
              +---------------------+
```

## 1. Separação de Responsabilidades

1. **CLI (`src/atlas_agent/cli.py`):**
   - Parse de argumentos com `argparse` nativo.
   - Ponto de entrada para subcomandos: `doctor`, `config`, `init`, `benchmark`, `diff`, `run`, `version`.
   - Inicialização do REPL interativo.

2. **Agent Core (`src/atlas_agent/agent.py`):**
   - Controla o ciclo de raciocínio do modelo (`process_turn`).
   - Monitora limite máximo de iterações (`max_iterations`, padrão: 10).
   - Previne loops infinitos (se o modelo repetir chamadas de ferramentas de inspeção idênticas, interrompe ou avisa).
   - Gerencia sinais de cancelamento (`SIGINT` / Ctrl+C) de forma limpa, sem deixar processos zumbis ou travar o terminal.

3. **Context Manager (`src/atlas_agent/context.py`):**
   - Lê e prioriza diretrizes de projeto (`ATLAS.md`, `AGENTS.md`, `README.md`).
   - Detecta arquivos citados pelo usuário e faz pré-leitura contextual.
   - Gerencia orçamento de tokens (*sliding window* com descarte seguro de mensagens antigas para não saturar memória ou limite da API).

4. **Camada de Provedores (`src/atlas_agent/providers/`):**
   - Totalmente desacoplada do restante do sistema.
   - Contratos canônicos: `Message`, `ToolCall`, `ToolResult`, `ProviderResponse`.
   - Implementação **Gemini** nativa via `urllib.request` (sem `google-genai`, sem gRPC, sem pydantic).
   - Implementação **OpenAICompatible** para servidores locais (Ollama, vLLM) ou OpenRouter.
   - Implementação **Mock** para testes automatizados determinísticos sem necessidade de conexão.

5. **Camada de Segurança (`src/atlas_agent/security/`):**
   - `WorkspaceGuard`: Isolamento de diretório, bloqueio de *path traversal* (`../../`), inspeção de links simbólicos.
   - `ToolPolicy`: Classificação em 3 níveis:
     - `SAFE`: auto-execução permitida para leitura e inspeção (`ls`, `cat`, `git status`, `git diff`, etc.).
     - `CONFIRM`: exige confirmação explícita do usuário no terminal (`rm`, `sudo`, `git commit`, edição de arquivos críticos).
     - `DENY`: bloqueio incondicional (`mkfs`, `dd`, `shutdown`, etc.).

6. **Ferramentas (`src/atlas_agent/tools/`):**
   - Manipulação atômica de arquivos com cálculo de *unified diff* (`difflib` nativo).
   - Leitura paginada com limites de linhas.
   - Execução de shell com limites de saída (máximo de linhas e bytes) e timeout configurável.
