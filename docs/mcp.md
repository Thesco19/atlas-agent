# Suporte ao Model Context Protocol (MCP) no atlas-agent

O **atlas-agent** possui um cliente **MCP (Model Context Protocol)** nativo, implementado **100% com a biblioteca padrão do Python** (`subprocess` + `json` via stdio JSON-RPC 2.0).

Isso significa que você tem acesso completo ao ecossistema MCP no seu **MX Linux (32-bit ou 64-bit)** sem precisar instalar runtimes pesados ou pacotes externos!

---

## 1. Como o MCP funciona com o Gemini?

1. O `atlas-agent` lê o arquivo `.mcp.json` na raiz do projeto (ou `~/.config/atlas-agent/mcp.json`).
2. Ele inicia os servidores MCP configurados via subprocesso e negocia as ferramentas disponíveis (`tools/list`).
3. As ferramentas do MCP são convertidas automaticamente no formato de **Function Calling do Google Gemini** (`function_declarations`).
4. Quando o Gemini decide usar uma ferramenta do MCP, o `atlas-agent` encaminha a chamada via JSON-RPC (`tools/call`), recebe o resultado e entrega de volta ao Gemini.

---

## 2. Como ativar no seu projeto

Basta criar um arquivo `.mcp.json` na raiz do seu repositório:

```json
{
  "mcpServers": {
    "demo": {
      "command": "python3",
      "args": ["examples/mcp_server_demo.py"]
    }
  }
}
```

Ao iniciar o agente:
```bash
./bin/atlas-agent doctor
```
Você verá:
```text
  MCP Servers ..... Configured (demo)
```

E ao abrir a sessão:
```bash
./bin/atlas-agent .
```
O agente anunciará:
```text
✓ Servidores MCP ativos: demo (3 ferramentas extras)
```

---

## 3. Exemplos de Servidores MCP Úteis

### A. Servidor MCP Demo Incluso (Zero Instalação)
Já deixamos um servidor pronto em `examples/mcp_server_demo.py`:
- `get_system_info`: Mostra hardware, RAM e arquitetura do Linux.
- `calculate_expression`: Executa cálculos matemáticos.
- `get_current_time`: Informa horário e data atuais.

### B. Servidor SQLite (Banco de Dados Local)
Se tiver `uvx` ou Python:
```json
{
  "mcpServers": {
    "sqlite": {
      "command": "uvx",
      "args": ["mcp-server-sqlite", "--db-path", "meu_banco.db"]
    }
  }
}
```

### C. Servidor Web Fetch (Buscar Páginas e APIs na Web)
```json
{
  "mcpServers": {
    "fetch": {
      "command": "uvx",
      "args": ["mcp-server-fetch"]
    }
  }
}
```

### D. Servidores Python Customizados
Qualquer script Python padrão que leia JSON-RPC via `sys.stdin` e responda via `sys.stdout` funciona instantaneamente como ferramenta para o Gemini!
