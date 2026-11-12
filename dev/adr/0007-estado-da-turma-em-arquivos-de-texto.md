---
type: adr
status: accepted
tags: [classroom, storage]
created: 2026-11-12
decided: 2026-11-12
creator: claude
---

# Estado da turma em arquivos de texto

## Contexto

O chalk corrige o que foi respondido fora dele (prova em papel, exportação do Moodle ou do Google Forms, repositórios do GitHub Classroom) e convive com um curso do codehood no mesmo repositório.

Evidência: `README.md`, primeiro parágrafo e "Directory structure"; `dev/adr/0001-questoes-em-mdq-e-roster-compartilhado-com-o-codehood.md`.

## Decisão

Toda a turma fica num diretório, em texto: `chalk.toml`, `roster.csv`, uma pasta por quiz com `conf.yaml`, `questions/`, `submissions.csv` e `grades.csv`. Não há banco de dados nem servidor. Motivo não registrado além do que o README diz.

## Consequências

- A turma vai para o git e é editada à mão quando preciso.
- O codehood lê os mesmos arquivos (`roster.csv`, `grades.csv`), por isso o chalk preserva colunas e linhas que não conhece.
- Escrita concorrente nos mesmos arquivos não é tratada.
