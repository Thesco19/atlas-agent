# ATLAS.md - Diretrizes do Projeto atlas-agent

Este arquivo define as instruções permanentes e diretrizes arquiteturais para o **atlas-agent**.

## 1. Missão e Filosofia
- **Ambiente Alvo:** Linux 32-bit (i386) e computadores com hardware modesto (ex: MX Linux, Debian 32-bit).
- **Sem Dependências Pesadas:** Usar estritamente a biblioteca padrão do Python (`urllib`, `json`, `dataclasses`, `argparse`, `ssl`).
- **Eficiência Extrema:**
  - Baixo consumo de RAM (< 25 MB de pegada de memória).
  - Inicialização instantânea (< 50 ms).
  - Respeitar cotas de tokens nas chamadas de API remotas.

## 2. Modelos & Provedores Suportados
- **Google Gemini:** `gemini-2.5-flash` via API REST direta (https://aistudio.google.com).
- **OpenRouter:** `openrouter.ai` (multi-provedor, modelos como `google/gemini-2.5-flash`, `deepseek/deepseek-chat`, `meta-llama/llama-3.3-70b-instruct`).
- **OpenAI / Compatível:** Endpoints REST padrão OpenAI ou instâncias locais (Ollama, vLLM, LM Studio).
- **Mock / Offline:** Modo de simulação para testes e ambientes sem conectividade.

## 3. Segurança & Proteção do Workspace
- **WorkspaceGuard:** Nenhuma escrita ou leitura é permitida fora da pasta do workspace. Bloqueio absoluto de Path Traversal (`../`) e symlinks maliciosos.
- **ToolPolicy (3 Níveis):**
  - *Tier 1 (Safe):* Leitura, listagem de arquivos, git status/diff (execução automática).
  - *Tier 2 (Confirm):* Edição e escrita de arquivos, comandos com efeito colateral (confirmação do usuário ou flag `-y`).
  - *Tier 3 (Denied):* Comandos destrutivos ou de elevação de privilégios (`sudo`, `rm -rf /`, `mkfs`, fork bombs) são sumariamente bloqueados.

## 4. Testes e Validação
- Todos os componentes devem conter testes unitários baseados em `unittest`:
  ```bash
  PYTHONPATH=src python3 -m unittest discover -s tests -v
  ```
- Diagnóstico rápido do sistema:
  ```bash
  atlas-agent doctor
  ```
