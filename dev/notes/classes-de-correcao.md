---
type: note
status: open
kind: research
tags: [grading, sandbox]
relatedTo: [docs/user-stories/teacher.md]
created: 2026-11-12
creator: claude
---

# Classes de correção

Estado em 2026-11-02. Veio do antigo `design/historias-correcao.md`; as histórias foram para `docs/user-stories/teacher.md`. Ator: o professor, que corrige na própria máquina Linux.

## O eixo que importa

O que decide se a correção precisa de sandbox não é existir um script, e sim
o que acontece com a resposta do aluno:

| Classe | A resposta do aluno é... | Quem corrige | Sandbox |
| --- | --- | --- | --- |
| **Objetiva** | escolha, número, texto curto | o mdq, sem script | não |
| **Manual** | texto livre, desenho, código lido | o professor | não |
| **Dado** | string, regex, trecho de código analisado sem executar | script do professor | não, mas com limites |
| **Código** | programa executado | testes do professor | sim |

Na classe **dado**, o código arbitrário é o do professor e a resposta só é
lida. Ainda assim há riscos que não pedem sandbox mas pedem limites: uma
regex do aluno com backtracking catastrófico trava o script; uma resposta
de 500 MB estoura a memória. Timeout e limite de memória valem para todas
as classes que rodam script.


## Consequências para o desenho

- O sandbox é exigência da classe **código**, não do autograder em geral.
  Script que só lê a resposta (teacher: Grade with my own script) roda sem sandbox, com timeout e limite
  de memória; script que executa a resposta roda no sandbox.
- Quem declara a classe é a questão no `conf.yaml`, não uma flag na linha
  de comando. Padrão seguro: script sem declaração roda no sandbox.
- As histórias de regex e de código sem execução viram perfis embutidos parametrizados no `conf.yaml` (`regex` e
  `ast`), como os perfis da classe código. O script livre (teacher: Grade with my own script) cobre o
  resto.
- Agrupar respostas e revisar sugestão ligam a correção manual à automática; hoje são caminhos
  separados.
