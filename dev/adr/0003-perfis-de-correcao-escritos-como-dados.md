---
type: adr
status: accepted
tags: [grading, profiles]
created: 2026-11-12
decided: 2026-11-12
creator: claude
---

# Perfis de correção escritos como dados

## Contexto

Integração por linguagem não escala, mas a parte que muda de uma linguagem para outra é pequena: comandos, ambiente, arquivos do template e formato do relatório (`dev/rfc/modelo-de-seguranca-e-sandbox-do-autograder.md`, "Abstração: sandbox, perfil e formato do relatório").

Evidência: `packages/chalk-grader/chalk_grader/profiles.toml`; `packages/chalk-grader/chalk_grader/profile_grader.py:1`; tabelas `[profiles.<nome>]` do `chalk.toml`, documentadas em `docs/user-manual/autograding-scripts.md`.

## Opções

- Um grader em Python por linguagem.
- Perfis em TOML lidos por um único grader.

## Decisão

Cada ecossistema é um perfil em TOML (`python-pytest`, `elm-test`, `rust-cargo`, `c-make`, `stdio`, `prolog-plunit`...). O professor adiciona um perfil, ou muda um embutido com `extends`, no `chalk.toml`. O relatório é lido por formato (JUnit XML), não por linguagem. Motivo, no RFC: "Linguagem nova vira perfil novo em `chalk.toml`, sem código no chalk, desde que o test runner gere JUnit."

## Consequências

- Linguagem nova não precisa de release do chalk.
- O que não cabe em dados (pontuação própria, leitura de outro formato) vai para um script de scoring do perfil.
- O formato do perfil vira contrato com os `chalk.toml` dos professores.
