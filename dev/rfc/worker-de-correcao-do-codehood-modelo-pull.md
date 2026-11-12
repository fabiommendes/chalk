---
type: rfc
status: draft
tags: [grading, codehood, worker]
created: 2026-11-12
creator: claude
---

# Worker de correção do codehood (modelo pull)

Estado em 2026-11-12. Rascunho. Parte de `dev/spec/corrigir-respostas-do-codehood-com-o-autograder-do-chalk.md`, que
corrige uma prova por comando.

## Problema

A VPS principal do codehood não executa código de aluno. A correção de
questões de código fica com serviços externos, em dois modelos:

- **push**: o codehood manda a submissão para um serviço instalado na infra
  (fora do escopo deste documento);
- **pull**: um processo na máquina do professor pede trabalho ao codehood,
  corrige em sandbox e devolve a nota. Serve para questões que dependem de um
  ambiente específico que só o professor tem.

O `chalk codehood autograde` já corrige uma prova fechada de uma vez. O
worker é o mesmo motor rodando sem parar, para tentativas fechadas e para
respostas que chegam durante a prova. O MVP é Elm (perfil `elm-test`).

## Decisões

- Três projetos: o motor `chalk-grader` (`packages/chalk-grader/`, extraído
  de `chalk/autograder/`), o chalk, e o `chalk-worker`, repositório próprio
  incluído no codehood como subtree em `workers/chalk-worker/`. O worker depende do `chalk-grader` e do
  `codehood-cli` (cliente gerado do OpenAPI), não do chalk.
- `chalk.codehood_autograde` (graders, `verify_reference`, `grade_answer`,
  `to_feedback`) e `chalk.codehood_api` vão para o `chalk-worker`; o
  `chalk codehood autograde` vira o `--once` dele. O chalk fica só com
  `chalk codehood grades`.
- A fila no servidor está no RFC `dev/rfc/fila-de-correcao-externa.md` do
  codehood.
- Os graders vêm do checkout local do curso (`graders/`), como no
  `autograde`. O servidor não guarda template nem solução.
- O servidor mantém uma fila de trabalhos de correção, comum a push e pull.
  O worker pull pega trabalhos por claim com lease; o dispatcher push, quando
  existir, consome a mesma fila.

## Fila no servidor (codehood)

Um trabalho por par (resposta, questão), não por submissão: o autosave da
página da prova cria uma submissão a cada edição, e só a mais nova importa.

```
GradingJob
  responseId, questionRefId     -- chave natural, única
  submissionId                  -- a submissão mais nova; trocada a cada nova
  bot                           -- serviço responsável (slug da chave BOT)
  state   QUEUED | CLAIMED | DONE | FAILED
  claimedBy, leaseUntil
  attempts, lastError
```

- Uma submissão nova a uma questão cujo grader é externo cria ou atualiza o
  trabalho: troca `submissionId` e volta para `QUEUED`. Se o trabalho estava
  `CLAIMED`, o resultado do worker para a submissão antiga é aceito como pass
  daquela submissão, mas não fecha o trabalho.
- A questão declara o id do worker que a corrige (string, por exemplo
  `elm-test`), no frontmatter. Exige mudança no mdq. Questão sem id segue o
  fluxo manual de hoje. A fila só anda com um worker que aceita o id.
- Workers push registram no servidor os ids que aceitam. Um worker pull
  filtra por ids no claim e se liga a uma prova ou a uma disciplina. O worker
  pull é sempre do instrutor e usa a chave `BOT` dele.
- Lease expirado volta para `QUEUED`. Depois de N tentativas com erro de
  infraestrutura, `FAILED`, visível para o professor na tela de correção.
- Trabalho com pass humano não é criado nem reaberto (R10 de
  `runner-de-correcao`).

REST nova:

- `POST .../grading-jobs/claim` com `{workers, limit, lease, exam?,
  questions?}` devolve até `limit` trabalhos com a submissão e a resposta.
  `workers` são os ids aceitos; `exam` limita a uma prova (sem ele, a
  disciplina inteira); `questions` restringe aos slugs que o worker tem
  grader.
- `POST .../grading-jobs/<id>/renew` estende o lease (build longo).
- `POST .../grading-jobs/<id>/fail` com `{error}` devolve à fila e conta a
  tentativa.
- O resultado continua no `PUT .../submission/<publicId>/feedback`, que fecha
  o trabalho quando a submissão é a atual.

## Worker (chalk)

```
chalk-worker [--exam <slug> | --discipline <slug>] [--poll 10] [--batch 4]
                      [--server <url>] [--key-file <arquivo>] [--once]
```

1. Na partida, acha os graders do curso e roda `prepare` e
   `verify_reference` de cada um. Grader com solução que não tira nota máxima
   fica fora da lista de questões do claim, com aviso.
2. Loop: `claim` com os slugs dos graders válidos; sem trabalho, espera
   `--poll` segundos (com backoff até um teto).
3. Para cada trabalho: corrige com o `ProfileGrader`, renovando o lease
   enquanto roda, e grava o feedback. Erro de infraestrutura chama `fail`.
   `Timeout` e `build-error` gravam 0, como no `autograde`.
4. Mudança na pasta de um grader (hash do conteúdo) refaz o passo 1 só para
   ele, antes do próximo claim.
5. `SIGINT`/`SIGTERM`: termina o trabalho em curso, devolve os outros com
   `fail` sem contar tentativa, e sai.
6. `--once` processa a fila até esvaziar e sai (cron, testes).
7. Log de uma linha por trabalho: aluno, questão, nota, tempo.

Correção durante a prova: em `EXAM` o aluno só vê a nota quando ela é
liberada, então a correção imediata serve ao professor; em `PRACTICE`, o
aluno vê na hora. A regra de liberação é a que já existe.

## Elm no MVP

- Perfil `elm-test` existente. A resposta é um `Main.elm` com cabeçalho
  `module` (mesma regra do runner do cliente, `runner-elm.md` do codehood);
  o `template/` traz `elm.json` e `tests/`.
- Os pacotes são baixados no `prepare`, fora do sandbox, e copiados para o
  `ELM_HOME` de cada execução. O sandbox continua sem rede.
- Build de Elm leva segundos; o lease padrão deve cobrir `build.timeout`
  mais `test` com folga, e o worker renova na metade.

## Fora do escopo

- Worker push e o dispatcher do servidor.
- Rubrica parcial e correção semi-automática de essay, short-answer e
  ordering. Short-answer e ordering com gabarito são determinísticos e cabem
  no servidor (mdq-js, `auto-grading.md` do codehood).
- Vários cursos por processo.

## Perguntas abertas

- Q1. O worker corrige rascunhos do autosave de uma tentativa aberta, ou só a
  submissão que o aluno enviou explicitamente?
