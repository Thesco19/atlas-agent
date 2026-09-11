# Suporte ao Model Context Protocol (MCP) no atlas-agent

O **atlas-agent** possui um cliente **MCP (Model Context Protocol)** nativo com suporte a:
1. **Processos locais stdio** (Python, Node.js, binários ELF, etc.)
2. **Servidores e Bridges MCP Remotos via HTTP / SSE** (como o `mcp-bridge` no servidor `http://10.0.1.95:8001`)

Tudo implementado **100% com a biblioteca padrão do Python** (`urllib.request`, `subprocess`, `json`, `threading`), sem pacotes externos e com consumo mínimo de memória para 32-bit e 64-bit!

---

## 1. Como o MCP funciona com o Gemini?

1. O `atlas-agent` lê o arquivo `.mcp.json` na raiz do projeto (ou global em `~/.config/atlas-agent/mcp.json`).
2. Para servidores remotos (`url`), ele se conecta via HTTP/SSE ao bridge e obtém as ferramentas remotas.
3. Para servidores locais (`command`), ele inicializa o processo via subprocesso stdio.
4. As ferramentas do MCP são convertidas automaticamente no formato de **Function Calling do Google Gemini** (`function_declarations`).
5. Quando o Gemini decide usar uma ferramenta do MCP, o `atlas-agent` encaminha a chamada via JSON-RPC, recebe o resultado e entrega de volta ao raciocínio do Gemini.

---

## 2. Como conectar ao mcp-bridge do servidor (10.0.1.95:8001)

No seu `.mcp.json` (ou em `~/.config/atlas-agent/mcp.json` para ficar disponível em todas as pastas):

```json
{
  "mcpServers": {
    "server_bridge": {
      "url": "http://10.0.1.95:8001"
    }
  }
}
```

Se o seu mcp-bridge expõe um endpoint específico como `/sse` ou `/rpc`:
```json
{
  "mcpServers": {
    "server_bridge": {
      "url": "http://10.0.1.95:8001/sse"
    }
  }
}
```

O `atlas-agent` negociará automaticamente o handshake de inicialização e disponibilizará todas as ferramentas do servidor para o Gemini!

---

## 3. Servidores MCP Locais e Híbridos

Você pode combinar múltiplos servidores (locais e remotos) no mesmo arquivo:

```json
{
  "mcpServers": {
    "servidor_rede": {
      "url": "http://10.0.1.95:8001"
    },
    "demo_local": {
      "command": "python3",
      "args": ["examples/mcp_server_demo.py"]
    }
  }
}
```

---

## 4. Ferramentas Nativas Disponíveis no atlas-agent

Além do MCP, o `atlas-agent` já vem de fábrica com:
- **Manipulação de Arquivos**: `read_file` (com paginação e linhas), `write_file`, `edit_file` (substituição cirúrgica com diff), `copy_file`, `move_file`, `delete_file`, `list_directory`, `search_files` (regex).
- **Pesquisa na Web**: `duckduckgo_search` (busca web em tempo real pelo DuckDuckGo sem necessidade de chave de API).
- **Leitura de Páginas / APIs**: `fetch_url` (baixa qualquer URL ou API HTTP/HTTPS e extrai texto limpo e legível).
- **Terminal Seguro**: `run_command` com verificação de comandos perigosos e workspace sandboxing.
- **Git**: `git_status`, `git_diff`, `git_log`, `git_commit`.
