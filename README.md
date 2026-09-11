# atlas-agent 🧭

> *Este projeto é experimental e prioriza compatibilidade e leveza.*

Um agente de programação via linha de comando (CLI) extremamente leve, transparente e seguro, projetado especificamente para reviver máquinas antigas e sistemas **Linux 32-bit (i386)** (como MX Linux rodando em processadores Intel Core 2 Duo ou equivalentes com 2 a 4 GB de RAM), delegando o raciocínio pesado para modelos remotos de IA via APIs HTTPS eficientes.

---

## 💡 Por que o atlas-agent existe?

Agentes modernos de linha de comando frequentemente dependem de engines pesadas (Node.js/V8, compilações Rust com AVX, binários exclusivos de 64 bits, Electron ou Docker). Isso exclui completamente computadores antigos perfeitamente funcionais.

O **atlas-agent** inverte esse paradigma:
- **Zero dependências externas obrigatórias:** Desenvolvido 100% sobre a biblioteca padrão do Python (`urllib.request`, `argparse`, `difflib`, `json`, `pathlib`, `unittest`).
- **Nenhum compilador Rust/C necessário no host.**
- **Tempo de inicialização medido:** ~0.12 ms.
- **Consumo de memória em repouso:** ~21 MB de RAM (RSS).
- **Compatível com 32-bit:** Sem instruções AVX/AVX2, sem dependências de 64-bit.

---

## 🏛️ Arquitetura do Sistema

```
CLI / REPL (Terminal)
       │
       ▼
  Agent Core (Turn Loop, Infinite Loop Prevention, Iteration Cap)
   ┌───┴──────────────────────────────┐
   ▼                                  ▼
Context Manager                 Tool Registry
(ATLAS.md, Token Budget)        (WorkspaceGuard, ToolPolicy)
   │                                  │
   ▼                                  ▼
Provider (REST puro)            Filesystem, Shell, Git
- Google Gemini (Oficial)
- OpenAI-compatible / Local LLM
- Mock Provider (Offline tests)
   │
   ▼ HTTPS
Remote LLM (Gemini 2.5 Flash)
```

---

## 📋 Requisitos Mínimos

- **Sistema Operacional:** Linux (testado em Debian/MX Linux e distribuições POSIX).
- **Arquitetura:** x86 (i386/i686) ou x86_64.
- **Processador:** Intel Core 2 Duo ou equivalente (sem exigência de AVX).
- **RAM:** A partir de 1 GB (ideal 2 GB - 4 GB).
- **Python:** Python 3.8 ou superior (apenas biblioteca padrão).
- **Git:** Recomendado para versionamento.

---

## 🚀 Instalação Rápida

### Opção 1: Execução direta (Sem instalação de pacotes)
```bash
git clone https://github.com/SEU_USUARIO/atlas-agent.git
cd atlas-agent

# Executar imediatamente com a biblioteca padrão do Python
PYTHONPATH=src python3 -m atlas_agent --help
```

### Opção 2: Criar link no PATH do usuário
```bash
mkdir -p ~/.local/bin
cat << 'EOF' > ~/.local/bin/atlas-agent
#!/bin/sh
exec python3 -m atlas_agent "$@"
EOF
chmod +x ~/.local/bin/atlas-agent
```

---

## ⚙️ Configuração

O atlas-agent busca a configuração na seguinte ordem:
1. Argumentos de linha de comando (`--provider`, `--model`, `--api-key`)
2. Variáveis de ambiente
3. Arquivo de configuração (`~/.config/atlas-agent/config.json`)
4. Valores padrão seguros

### Configurando a Chave do Google Gemini (Primeiro Provedor Oficial)
```bash
export ATLAS_AGENT_API_KEY="sua-chave-gemini"
# Ou se preferir usar a variável padrão:
export GEMINI_API_KEY="sua-chave-gemini"
```

### Inspecionar Configuração (Sem vazar segredos)
```bash
atlas-agent config
```

### Diagnóstico Completo do Ambiente (`doctor`)
```bash
atlas-agent doctor
```
Verifica versão do Python, arquitetura de hardware, memória do sistema, conectividade com a API remota, Git e permissões do workspace.

---

## 💻 Uso e Exemplos

### 1. Iniciar REPL Interativo no Projeto Atual
```bash
cd /caminho/do/seu/projeto
atlas-agent .
```

Dentro da sessão interativa:
```
atlas> analise a estrutura deste projeto e liste os arquivos
atlas> leia o arquivo src/main.py e encontre possíveis erros
atlas> implemente testes unitários para a função de cálculo
atlas> execute os testes e corrija se houver falhas
```

### 2. Execução Não-Interativa (Modo Único)
```bash
atlas-agent run "analise o arquivo README.md e adicione seção de licença"
```

### 3. Modo Dry-Run (Simulação sem alterar arquivos)
```bash
atlas-agent --dry-run .
```

### 4. Inicializar Diretrizes de Projeto
```bash
atlas-agent init
```
Cria um template `ATLAS.md` no workspace para orientar o agente em turnos futuros.

---

## 🛡️ Segurança e Workspace

- **Workspace Sandbox (`WorkspaceGuard`):** Todas as operações são restritas ao diretório alvo. Ataques de *path traversal* (`../../`) e links simbólicos que apontam para fora do workspace são estritamente bloqueados.
- **Política de Comandos (`ToolPolicy`):**
  - **SAFE:** Comandos de inspeção (`ls`, `cat`, `git status`, `git diff`, `pytest`) executam sem interrupção.
  - **CONFIRM:** Comandos modificadores (`rm`, `mv`, `sudo`, `git commit`) solicitam autorização explícita `[y/N]` no terminal.
  - **DENY:** Comandos perigosos (`mkfs`, `dd`, `shutdown`, fork bombs) são sumariamente rejeitados.

---

## 🧪 Testes Automatizados

O projeto conta com suíte completa de testes unitários sem dependência externa:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Testes cobertos:
- Segurança de workspace e bloqueio de *path traversal*
- Tratamento de links simbólicos maliciosos
- Classificação de comandos seguros, de confirmação e proibidos
- Manipulação de arquivos UTF-8, arquivos vazios, grandes e inexistentes
- Aplicação de edições cirúrgicas e geração de diffs unificados
- Limite de iterações e prevenção de loop infinito no loop do agente
- Mock Provider para testes determinísticos sem necessidade de API ou rede

---

## 📊 Benchmark de Desempenho

Meça a eficiência em sua própria máquina:
```bash
atlas-agent benchmark
```
Exemplo de métricas coletadas em hardware modesto:
- **Tempo de Inicialização:** `~0.12 ms`
- **Uso de Memória RAM (RSS):** `~21.6 MB`
- **Módulos Carregados:** `< 180` (apenas biblioteca padrão)

---

## 🗺️ Roadmap Incremental

- [x] **Fase 1 (Atual - v0.1.0):**
  - [x] CLI minimalista e REPL interativo
  - [x] Provedor oficial Google Gemini via REST nativo (`urllib.request`)
  - [x] Provedor OpenAI-compatible nativo
  - [x] Ferramentas de sistema de arquivos com *unified diff*
  - [x] Execução controlada de shell com políticas em 3 camadas
  - [x] Integração Git (status, diff, log, commit com confirmação)
  - [x] Context Manager com suporte a `ATLAS.md` e `AGENTS.md`
  - [x] Comandos `doctor`, `config`, `benchmark`, `init`, `diff`
  - [x] Suíte de testes automatizados com `MockProvider`
- [ ] **Fase 2:**
  - [ ] Histórico de sessões com persistência leve em arquivo
  - [ ] Recuperação inteligente de erros de sintaxe
  - [ ] Cache local de leituras para evitar re-envio de arquivos não modificados
- [ ] **Fase 3:**
  - [ ] Suporte opcional a MCP (Model Context Protocol) sem impactar a instalação mínima
  - [ ] Sistema opcional de plugins leves
- [ ] **Fase 4:**
  - [ ] Otimizações finas para terminais seriais e computadores industriais legados

---

## 📄 Licença

Distribuído sob a licença **MIT**. Consulte `LICENSE` para detalhes.
