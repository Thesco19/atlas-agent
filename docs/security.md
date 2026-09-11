# Política de Segurança e Modelo de Ameaças

O **atlas-agent** implementa uma camada rigorosa de proteção para garantir que um modelo de linguagem remoto jamais tenha acesso irrestrito ao sistema operacional host.

## 1. Princípios de Segurança

1. **O Modelo é Não-Confiável:** O output do modelo (código, argumentos de ferramentas) é tratado como entrada potencialmente hostil ou errônea.
2. **Isolamento de Workspace (`WorkspaceGuard`):** Toda operação de leitura, escrita ou deleção deve ser estritamente contida dentro do diretório raiz do projeto definido na inicialização.
3. **Prevenção de Path Traversal:** Sequências como `../../etc/passwd` ou links simbólicos que apontem para fora do workspace são detectados e rejeitados antes de qualquer chamada ao sistema de arquivos.
4. **Proteção de Segredos:** Chaves de API nunca são exibidas em logs, telas de ajuda ou comandos de configuração.

---

## 2. Matriz de Políticas de Execução de Comandos (`ToolPolicy`)

| Categoria | Ação do Agente | Comandos e Padrões |
| :--- | :--- | :--- |
| **SAFE** | Executa diretamente sem interrupção | `ls`, `pwd`, `cat`, `head`, `tail`, `grep`, `find`, `echo`, `diff`, `git status`, `git diff`, `git log`, `python3 -m unittest`, `pytest` |
| **CONFIRM** | Exige aprovação interativa `[y/N]` no terminal antes de executar | `rm`, `mv`, `cp`, `chmod`, `chown`, `sudo`, `su`, `apt`, `dpkg`, `systemctl`, `service`, `git commit`, `git checkout`, comandos arbitrários desconhecidos |
| **DENY** | Bloqueado incondicionalmente | `mkfs`, `dd`, `shutdown`, `reboot`, `poweroff`, `init`, fork bombs (`:(){ :|:& };:`), escrita direta em `/dev/sd*` |

---

## 3. Modo Dry-Run (`--dry-run`)

Ao executar com a flag `--dry-run`:
```bash
atlas-agent --dry-run .
```
O agente calcula e exibe todos os diffs e planos de modificação, mas **não altera nenhum byte no disco**, permitindo auditoria prévia completa do raciocínio do modelo.
