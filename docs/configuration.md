# Configuração do Atlas Agent

O **atlas-agent** possui um sistema hierárquico de configuração simples, transparente e sem dependências externas.

## 1. Ordem de Prioridade

1. **Argumentos de Linha de Comando (CLI)** (maior precedência)
2. **Variáveis de Ambiente**
3. **Arquivo de Configuração** (`~/.config/atlas-agent/config.json`)
4. **Valores Padrão Seguros** (menor precedência)

---

## 2. Variáveis de Ambiente Suportadas

| Variável | Descrição | Valor Padrão |
| :--- | :--- | :--- |
| `ATLAS_AGENT_PROVIDER` | Provedor de IA (`gemini`, `openai`, `mock`) | `gemini` |
| `ATLAS_AGENT_MODEL` | Nome do modelo remoto | `gemini-2.5-flash` |
| `ATLAS_AGENT_API_KEY` | Chave de API (também aceita `GEMINI_API_KEY` ou `OPENAI_API_KEY`) | *Nenhum* |
| `ATLAS_AGENT_ENDPOINT` | Endpoint customizado (útil para proxies, OpenRouter ou Ollama) | Padrão do provider |
| `ATLAS_AGENT_TEMPERATURE` | Temperatura de amostragem (0.0 a 1.0) | `0.2` |
| `ATLAS_AGENT_MAX_TOKENS` | Limite máximo de tokens por resposta | `4096` |
| `ATLAS_AGENT_TIMEOUT` | Timeout de chamadas de rede em segundos | `45` |
| `ATLAS_AGENT_WORKSPACE` | Caminho do workspace raiz | Diretório atual (`.`) |

---

## 3. Arquivo de Configuração

O arquivo de configuração pode ser colocado em:
```
~/.config/atlas-agent/config.json
```

Exemplo:
```json
{
  "provider": "gemini",
  "model": "gemini-2.5-flash",
  "temperature": 0.2,
  "max_tokens": 4096,
  "timeout": 45,
  "max_iterations": 10
}
```

> **Nota de Segurança:** Nunca versione arquivos com chaves de API. Prefira exportar `ATLAS_AGENT_API_KEY` em sua sessão de shell (`.bashrc`) em vez de gravar no disco.

---

## 4. Inspecionar Configuração Ativa

Para verificar a configuração ativa sem vazar segredos:

```bash
atlas-agent config
```

A saída mascara chaves de API automaticamente (exemplo: `AIza...4xQ9`).
