---
type: rfc
status: draft
tags: [grading, sandbox, limits, cgroups, worker]
created: 2026-11-13
creator: claude
---

# Limites de memória e de processos por correção

Estado em 2026-11-13. Rascunho. Continua o item "limite de memória,
processos e disco" que ficou em aberto em
`dev/rfc/modelo-de-seguranca-e-sandbox-do-autograder.md` (estado atual,
item 5, e a fase 8, que já citava `systemd-run --user --scope` em volta do
bwrap).

## Problema

O motor não limita a memória nem o número de processos de uma correção. O
único freio é o timeout. Isso passou a importar porque o `chalk-worker`
agora corrige uma resposta por núcleo, em threads, num processo só. Um
aluno que aloca sem parar (uma lista enorme ou uma estrutura aninhada numa
recursão em Elm, um `malloc` num laço em C) ou que faz uma fork bomb tira
memória e processos de todas as correções e da máquina do professor. Em C
isso vai acontecer em toda turma.

Hoje existem três caminhos, e nenhum serve:

- **`limits.memory`** aplica `RLIMIT_AS` por processo. Ele limita o espaço
  de endereçamento, não a memória usada: o Node e a JVM reservam áreas
  virtuais enormes e não sobem com um valor apertado. Além disso, é
  aplicado em `preexec_fn` (`script_runner.py`), que a documentação do
  Python declara inseguro num processo com threads (pode travar o filho
  entre o `fork` e o `exec`). O worker tem threads.
- **Um cgroup em volta do worker inteiro** (`systemd-run --user --scope -p
  MemoryMax=...`) mata o worker. Medido abaixo: quando o escopo estoura, o
  systemd encerra a unidade toda (`OOMPolicy=stop`), e o processo principal
  vai junto.
- **O OOM killer do sistema** escolhe pela maior memória residente, não por
  quem causou o estouro. E o `systemd-oomd` (ativo na máquina onde medimos)
  mata o cgroup inteiro sob pressão, que é o escopo do terminal onde o
  worker roda.

Pior: quando um processo da correção morre por `SIGKILL`, o aluno leva a
culpa. Na etapa de build, um código de saída diferente de zero vira
`build-error` com saída vazia. Na etapa de teste, não sobra relatório e a
nota é `dq.Error()`; o `chalk-worker` então roda a referência de novo, ela
passa, e todos os casos viram `error`. Um OOM causado por outra correção, ou
pelo navegador do professor, vira nota contra um aluno que não fez nada.

## Medições (2026-11-13)

Máquina com 14 GiB e 16 núcleos, Node 26, elm-test com o heap padrão do V8
(2144 MiB). Questão `elm-soma` dos testes do worker. Pico pelo
`memory.peak` do cgroup da correção, contando arquivos em tmpfs e cache de
página.

| Resposta | elm-test | Heap do node | Pico | Resultado |
|---|---|---|---|---|
| correta | 16 workers (padrão) | 256 MiB | 416 MiB | `pass` |
| lista enorme | 16 workers | 256 MiB | 1453 MiB | `error` em todos os casos |
| lista enorme | 16 workers | padrão | > 3 GiB | escopo inteiro morto pelo OOM, worker incluído |
| lista enorme | 16 workers | 1024 MiB | > 3 GiB | idem |
| correta | `--workers 1` | 256 MiB | 213 MiB | `pass` |
| lista enorme | `--workers 1` | 256 MiB | 348 MiB | `error` em todos os casos |
| estrutura aninhada | `--workers 1` | 256 MiB | 349 MiB | `error` em todos os casos |
| lista enorme | `--workers 1` | 512 MiB | 623 MiB | `error` em todos os casos |

Duas conclusões:

1. O `elm-test` abre um worker por núcleo **em cada correção**, cada um com
   o próprio heap. Com o worker corrigindo 16 respostas ao mesmo tempo,
   isso daria 256 isolates. Com `--workers 1`, o pico é cerca de heap
   + 110 MiB, e 8 correções em paralelo ficaram mais rápidas (6,1 s contra
   7,7 s).
2. Um limite de heap dentro do runtime resolve o caso comum de uma
   linguagem com runtime gerenciado. Não resolve C, nem processos que o
   aluno cria, nem o compilador.

## Paliativo já no chalk-worker

Sem mudar o motor, o worker passou a:

- sobrescrever o perfil `elm-test` (`profile_overrides` em
  `chalk_worker/grading.py`): `--workers 1` no comando de teste e
  `NODE_OPTIONS=--max-old-space-size=<orçamento − 128 MiB>`;
- só reservar um envio quando `MemAvailable`, menos uma folga, comporta o
  orçamento dele somado ao dos envios em andamento (`--memory`,
  `--memory-reserve`).

O override repete o `test.command` inteiro do perfil embutido, o que é
frágil. Ver a fase 1.

## Proposta

### Um cgroup por execução

Cada execução de um passo do perfil (build, test, os serviços) roda num
cgroup v2 próprio, filho de um cgroup delegado ao processo que corrige:

```
<unidade com Delegate=yes>/
  supervisor/        o processo do chalk ou do worker, com as threads
  run-<id>/          uma execução: memory.max, memory.swap.max=0,
                     pids.max, memory.oom.group=1
```

- O processo entra no cgroup antes de qualquer código do aluno, por um
  shim no lugar do `preexec_fn`:
  `sh -c 'echo $$ > "$0/cgroup.procs" && exec "$@"' <cgroup> bwrap ...`.
  O `subprocess` do Python não sabe criar o filho direto num cgroup
  (`CLONE_INTO_CGROUP`).
- O OOM do kernel fica confinado ao cgroup da execução: só processos dela
  podem ser escolhidos. Com `memory.oom.group=1`, morre a execução inteira,
  sem sobrar filho pela metade.
- `memory.swap.max=0` evita que a máquina entre em swap antes do OOM.
- No fim, `cgroup.kill` mata o que sobrou (inclusive processos que saíram
  do grupo de processos, que o `killpg` de hoje não pega), e o cgroup é
  removido.

Protótipo (`systemd-run --user --scope -p Delegate=yes`, sessão comum, sem
root): numa execução com `memory.max=200M`, uma bomba de memória morreu com
`oom_kill=2` no `memory.events`; uma fork bomb bateu em `pids.max` e o
`fork` devolveu `EAGAIN`, com `max 1` no `pids.events`. O supervisor, com
threads, continuou vivo.

### De quem é a culpa

Depois de cada execução, o motor lê os eventos do cgroup dela:

| Fim da execução | Eventos do cgroup | Resultado |
|---|---|---|
| morta por sinal | `oom_kill > 0` | `dq.MemoryLimit()`: culpa do aluno, como `dq.Timeout()`, com feedback "a resposta usou mais de N de memória" |
| qualquer | `pids.max` atingido | segue o resultado normal; o evento vai para as notas do professor |
| morta por `SIGKILL` | nenhum | falha de infraestrutura: exceção, e o chamador decide (o worker devolve o envio com `retry`) |

O `chalk-worker` mapeia `dq.MemoryLimit()` para um relatório como o do
timeout: todos os casos com uma mensagem própria.

### Configuração

- `Limits.memory` passa a significar o `memory.max` da execução quando há
  cgroup. `RLIMIT_AS` fica num campo à parte (`address_space`), para quem
  precisar sem cgroup.
- Campo novo `Limits.processes` (`pids.max`), com um padrão (por exemplo,
  256) em todos os perfis.
- Cada perfil embutido ganha um `limits.memory` padrão medido (Elm: 512 MiB
  com `--workers 1`).

### Delegação

Quem chama o motor precisa estar numa unidade com `Delegate=yes`. O motor
detecta se o próprio cgroup é delegado (dono é o usuário e
`cgroup.subtree_control` aceita escrita), e então se move para
`supervisor/` e liga `+memory +pids`. O `chalk-worker` e o
`chalk autograde` se reexecutam ao iniciar sob
`systemd-run --user --scope -p Delegate=yes` quando não estão numa unidade
delegada, com uma variável de ambiente para não entrar em laço.

Sem cgroup v2 delegável (sem systemd, cgroup v1, contêiner sem delegação),
o motor avisa uma vez e cai no fallback: `RLIMIT_AS` por `prlimit` no shim,
em vez de `preexec_fn`, e o comportamento de hoje.

## Fases

1. **Feita (2026-11-14).** Controles por perfil, em todos os perfis
   embutidos, não só no `elm-test`. `limits.memory` deixou de ser
   `RLIMIT_AS` (que foi para `limits.address_space`) e virou o orçamento
   da execução, exposto como `{memory_mib}` por passo; cada perfil tem um
   padrão em `vars.memory_mib` e o converte para o próprio runtime:
   heap do Node no `elm-test` (orçamento − 128 MiB), `ulimit -v` no
   `python-pytest` e no `stdio`, `--stack-limit` do swipl no
   `prolog-plunit`. `vars.jobs` (padrão 1) limita o paralelismo:
   `--workers` do elm-test, `--jobs` e `--test-threads` do rust,
   `OMP_NUM_THREADS`/`OPENBLAS_NUM_THREADS` no pytest. Ficam sem limite
   de memória até a fase 3: `rust-cargo` (threads reservam espaço de
   endereçamento demais para `RLIMIT_AS`) e `c-make` (o ASan reserva
   terabytes, e o `hard_rss_limit_mb` dele não chega ao processo de cada
   teste, criado por `fork`: medido, o filho chegou a 3 GiB).
2. **Feita (2026-11-14).** Lançador em shell no `ScriptRunner`
   (`LAUNCHER`) no lugar do `preexec_fn`: entra no cgroup e aplica
   `ulimit -v`/`-f` antes do `exec`. Sem `prlimit`, que nem toda
   distribuição traz.
3. **Feita (2026-11-14).** `chalk_grader/cgroup.py`. Diferenças do
   desenho:
   - Delegação: `reexec_delegated` só pula a reexecução quando o
     `systemctl --user show` da unidade diz `Delegate=yes`. Dono e
     permissão de escrita não bastam: o escopo do terminal também é do
     usuário. O systemd não marca a delegação com xattr.
   - Culpa: `oom` e `oom_kill` em `memory.events`. `oom > 0` é a
     execução que bateu no próprio `memory.max` (`dq.MemoryLimit`);
     `oom_kill > 0` com `oom == 0` é o OOM killer do sistema
     (`RunKilled`, a exceção de infraestrutura). Um `SIGKILL` sem evento
     de OOM segue como resultado normal: o aluno pode mandá-lo a si mesmo,
     e tratar isso como falha de infraestrutura daria a ele novas
     tentativas sem fim.
   - O orçamento da execução é o `{memory_mib}` do passo (o padrão do
     perfil ou `limits.memory`), usado no build e no teste. `rust-cargo`
     tem 2 GiB, `c-make` 1 GiB.
   - O heap do Node passou a ser o orçamento inteiro: com cgroup, a
     execução costuma estourar primeiro e o aluno recebe `memory-limit`,
     com mensagem clara, em vez de `error`.
   - O `chalk autograde` e o `chalk codehood autograde` se reexecutam no
     `main()` do CLI, não dentro dos comandos, para que o `CliRunner` dos
     testes não troque o pytest pelo `systemd-run`.
   - Serviços (`services`) e os comandos de `prepare` ainda rodam sem
     cgroup próprio.
   - Os testes de cgroup (`tests/test_cgroup.py`) só rodam com o pytest
     direto num escopo delegado:
     `systemd-run --user --scope -p Delegate=yes .venv/bin/python -m pytest`.
     Sob `uv run`, o uv dividiria o escopo.
4. `chalk-worker`: reexecução sob `Delegate=yes`, envio devolvido com
   `retry` na exceção de infraestrutura, relatório de `MemoryLimit`. O
   `--memory` do worker passa a ser o `limits.memory` do motor, e a
   admissão por `MemAvailable` continua.

## Em aberto

- `systemd-oomd`: com `memory.max` por execução e sem swap, a pressão fica
  contida. Falta verificar se a unidade do worker precisa de
  `ManagedOOMPreference=avoid` e se isso vale numa unidade de usuário.
- Disco: um aluno pode encher o tmpfs de `/tmp` (que conta como memória no
  cgroup, então já é limitado) ou o disco do `--cache-dir`. Um
  `RLIMIT_FSIZE` padrão cobre o caso simples.
- O compilador (por exemplo, `elm make`) roda dentro do mesmo cgroup da
  build. Um limite apertado demais para ele vira `dq.MemoryLimit` contra o
  aluno. O padrão de cada perfil precisa de folga para a build, ou de um
  limite próprio para ela (`build.limits` já existe).
