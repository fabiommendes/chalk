---
type: adr
status: accepted
tags: [grading, sandbox, security]
created: 2026-11-12
decided: 2026-11-12
creator: claude
---

# Sandbox bwrap com lista de bloqueio, só para código executado

## Contexto

O que decide se a correção precisa de sandbox é o que acontece com a resposta do aluno, não existir um script (`dev/notes/classes-de-correcao.md`). E a fragilidade do bwrap vinha da lista de permissões: descobrir, caminho a caminho, o que cada test runner precisa (`dev/rfc/modelo-de-seguranca-e-sandbox-do-autograder.md`, "Como tornar o bwrap menos frágil").

Evidência: `packages/chalk-grader/chalk_grader/sandbox.py:1-14`; "Decisões tomadas" do RFC do sandbox.

## Opções

- Sandbox para todo script do autograder.
- Lista de permissões de caminhos montados.
- Lista de bloqueio: `/` só leitura e os lugares de segredo escondidos.

## Decisão

Só Linux, com `bwrap`. O código que executa a resposta do aluno roda no sandbox; um script do professor que só lê a resposta roda fora dele, com timeout e limite de memória. O sandbox monta `/` só leitura e troca por tmpfs vazio `/home`, `/root`, `/run`, `/tmp`, `/var/tmp`, `/mnt` e `/media`; remonta só leitura o PATH, o Python do chalk, o script e os `mounts` da questão. A rede fica desligada salvo `network: host`.

## Consequências

- Pacotes do sistema ficam visíveis sem configuração.
- Risco aceito: um arquivo legível por todos fora do `$HOME`, que o aluno leria de qualquer forma com uma conta na máquina.
- Sem Windows nem macOS para correção de código.
