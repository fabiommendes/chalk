---
type: issue
status: backlog
tags: [autograder, chalk-grader, elm]
kind: defect
created: 2026-11-13
creator: claude
---

# `elm-stuff/` no template quebra o build com uma mensagem que engana

O perfil `elm-test` declara `trusted = ["elm.json", "elm-stuff"]` (`packages/chalk-grader/chalk_grader/profiles.toml`). `install_trusted_files` (`profiles.py`) copia o `elm-stuff` do template para o workdir e o monta somente leitura. Se alguém rodou `elm make` ou `elm-test` dentro do `template/`, o `elm-test` não consegue criar `elm-stuff/generated-code/` e falha com:

```
ENOENT: no such file or directory, mkdir '.../elm-stuff/generated-code/elm-community/elm-test/0.19.2-1/src'
```

A mensagem não aponta o template. Na prova `lista1-elm` isso derrubou a preparação de duas questões, e a causa levou um tempo para aparecer.

Proposta: na preparação, recusar com mensagem clara um `elm-stuff/` dentro do template (`template/elm-stuff exists; delete it, it is generated`), ou ignorá-lo. Avaliar se `elm-stuff` precisa mesmo estar em `trusted`.
