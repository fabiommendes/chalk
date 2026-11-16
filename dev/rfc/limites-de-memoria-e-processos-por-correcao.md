---
type: rfc
status: draft
tags: [grading, sandbox, limits, cgroups, worker]
created: 2026-11-13
creator: claude
---

# Limites de memória e de processos por correção

Estado em 2026-11-16. Rascunho. Continua o item "limite de memória,
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
   `python-pytest` e no `stdio` (retirado na fase 3b), `--stack-limit` do
   swipl no `prolog-plunit`. `vars.jobs` (padrão 1) limita o paralelismo:
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
3b. **Feita (2026-11-14).** Correções depois da revisão de código e de
   medições com questões reais. Decisões:
   - **Sem `ulimit -v` nos perfis.** Com cgroup, ele só atrapalha (medidas
     abaixo): o `python-pytest` e o `stdio` perderam o `ulimit -v
     {memory_mib}`. Havia ainda um defeito: `limits.address_space` menor
     que o `memory_mib` fazia o `ulimit -v` do perfil tentar subir o limite
     *hard* que o lançador já tinha baixado, e toda execução dava `Error`.
     `MALLOC_ARENA_MAX=2` nos dois perfis, para as arenas do glibc não
     multiplicarem a memória por thread.
   - **`limits.address_space`** só vale quando configurado. Sem cgroup,
     `limits.memory` vira o `RLIMIT_AS` de reserva, como no 0.2.0, mas só o
     `memory` da configuração do usuário, não o padrão `vars.memory_mib` do
     perfil, que quebraria torch, Node e JVM em máquinas sem cgroup. A
     distinção é de tipo: o padrão do perfil chega ao `ScriptRunner` como
     `default_memory`, à parte de `limits`, e só serve de `memory.max`.
     Vale em todos os perfis, não só no `script`: no 0.2.0 o
     `limits.memory` era `RLIMIT_AS` em qualquer perfil, e uma
     configuração que funcionava lá continua funcionando.
   - **Culpa sem `memory.max`.** Uma execução sem limite de memória
     próprio (perfil `script` sem `limits.memory`) só vê OOMs globais, e a
     resposta que come a RAM é a escolha mais provável do OOM killer.
     Então: sem `memory.max`, `oom_kill > 0` dá `dq.MemoryLimit()`, com
     feedback sem número; `RunKilled` só quando havia `memory.max` e
     `oom == 0`.
   - **`RunKilled` tratado num ponto só**, em `ScriptRunner.run()`: a
     execução (o passo, não a correção inteira) roda de novo uma vez; na
     segunda, sai `RunKilled` com mensagem "twice: the grading machine may
     be short of memory". O `chalk autograde` lista o aluno como não
     corrigido e sai com 1 no fim, sem gravar nota; o
     `chalk codehood autograde` já tratava `RuntimeError` como erro do
     item. No `prepare`/`verify_reference` a questão ainda é abortada:
     sem a execução da referência não há testes esperados.
   - **Falha do lançador** (não entrou no cgroup, `ulimit` recusado) é
     `RunError`, a base de `RunKilled`, e não `build-error` do aluno. O
     lançador diz o motivo num descritor herdado que ele fecha antes do
     `exec`, então o código do aluno não consegue se passar por ele (um
     `exit 125` do aluno continua sendo dele). `ulimit -v`/`-f` arredondam
     para cima: `file_size` abaixo de 512 bytes dava limite zero.
   - **prolog-plunit:** pilha = 5/8 da memória (mínimo 16 MiB), no lugar
     de memória − 64 MiB. O RSS do swipl chega a ~1,37× o
     `--stack-limit` (GC, `findall/3`): com 512 MiB e pilha de 448 MiB, um
     estouro de pilha virava `memory-limit` da execução inteira em vez de
     falhar só aquele teste.
   - **Setup do cgroup cedo:** `cgroup.controller()` é chamado no `main()`
     do CLI logo depois da reexecução e no início dos passos do
     `ProfileGrader`, antes dos serviços. Se a escrita em
     `subtree_control` falha depois de o processo ir para `supervisor/`, ele
     volta ao cgroup original e `supervisor/` é removido.
   - **Reexecução sem barramento:** `reexec_delegated` só faz o `exec` do
     `systemd-run` quando `systemctl --user show-environment` responde
     (ssh sem lingering, cron e contêiner não têm o systemd do usuário).
   - **Limpeza:** no `atexit` e em `SIGTERM`/`SIGHUP` o grader mata os
     `run-*` que sobraram, para não manter o escopo vivo. `SIGKILL` não tem
     tratamento.
   - `vars.memory_mib` que não é um número inteiro de MiB ("1G") é erro de
     configuração no `prepare`. No `stdio`, uma referência em que todos os
     casos falham também.

   Picos medidos (`memory.peak` do cgroup da execução) e os padrões:

   | Perfil | Pico medido | Padrão |
   |---|---|---|
   | `prolog-plunit` | 21 MiB | 512 MiB |
   | `python-pytest` | 269 MiB no teste, 382 MiB no prepare (pandas) | 1 GiB |
   | `stdio` | 16 MiB (C), 48 MiB (Python) | 512 MiB |
   | `c-make` | 135 MiB | 1 GiB |
   | `rust-cargo` | 476 MiB no build (`-j1`), 91 MiB no teste | 2 GiB |

   Espaço de endereçamento, que motivou tirar o `ulimit -v`: o torch do
   PyPI (build CUDA) tem VmPeak de 3,3 GiB com RSS de ~760 MiB, e
   `import torch` falha com 1 GiB; pandas com 16 threads dá "can't start
   new thread" (arenas do glibc); o Node abaixo de ~1,4 GiB morre com
   "Failed to reserve virtual memory for CodeRange"; a JVM não inicia com
   512 MiB.
4. **Feita (2026-11-16).** `chalk-worker` (commit `c115d39c` do codehood,
   em `workers/chalk-worker/`), com `chalk-grader>=0.3.0`. Diferenças do
   desenho:
   - **`--memory` vai como `vars.memory_mib`, não como `limits.memory`.**
     Sem cgroup delegado, `limits.memory` vira `RLIMIT_AS` (fase 3b), e o
     Node não inicia abaixo de ~1,4 GiB de espaço de endereçamento: toda
     execução Elm falharia. Como variável do perfil, o orçamento é o
     `memory.max` de cada execução (build e teste) e o heap do Node, e sem
     cgroup sobra só o heap. Saíram os `profile_overrides` (o paliativo).
     `--memory 0` deixa o padrão do perfil e desliga a admissão por
     `MemAvailable`, que continua para os outros valores.
   - Reexecução sob `Delegate=yes` e `cgroup.controller()` no `main()` do
     CLI, antes de qualquer thread, exceto em `--help`. O worker diz no
     início (log ou título da TUI) se as execuções têm limite; sem cgroup,
     avisa e segue.
   - `MemoryLimit` no relatório é `resource-limit` em todos os casos, com a
     mensagem do motor, como o timeout.
   - **`RunError` (inclusive `RunKilled`) gasta uma tentativa:** o job
     volta à fila com `retry=True` e sem nota; depois de `RunKilled` o
     worker espera antes de pedir mais jobs. Não gastar daria tentativas
     sem fim a uma resposta que derruba a máquina sem bater no próprio
     limite.
   - Na referência: `RunError` é falha de preparo (os jobs voltam sem
     gastar tentativas); `resource-limit` é erro da questão ("give the
     worker more --memory"), que gasta as tentativas de todos os jobs.
   - Na saída abrupta (segundo Ctrl+C, abort da TUI, segundo SIGHUP) o
     worker mata os `run-*` antes do `os._exit`, que pula o `atexit`.

5. **Feita (2026-11-16).** Pontas soltas, no `chalk-grader` (commits
   `caee6c1` a `c5d3159`, sem versão nova). Decisões:
   - **Referência que estoura a memória:** `ReferenceMemoryLimit`, subclasse
     de `PrepareError` em `chalk_grader.profiles`, levantada por
     `ProfileGrader.prepare()` quando a execução da referência dá
     `dq.MemoryLimit()`, antes da checagem de "no tests". A mensagem diz o
     orçamento em MiB (atributo `memory`, em bytes, `None` sem limite) e
     sugere `vars.memory_mib` ou `limits.memory`; `Result.memory_limit`
     leva o `memory.max` da execução até lá. O `chalk-worker` pode tratá-la
     como erro da questão, que gasta tentativas. No chalk nada mudou: o
     `chalk codehood autograde` já aborta a questão com a mensagem de
     qualquer `PrepareError`, e o `codehood check` também a mostra.
   - **`prepare` e probes num cgroup `run-*` próprio** (`run_trusted` em
     `script_runner.py`, com o `LAUNCHER`), com teto generoso:
     `TRUSTED_MEMORY` = 4 GiB e `TRUSTED_PROCESSES` = 1024. São comandos
     confiáveis do perfil; o limite só impede que um comando quebrado tome
     a máquina, não é orçamento. Medido (`memory.peak`, que conta o cache de
     página dos downloads): `elm-test make` 537 a 658 MiB, mais que os
     512 MiB de uma execução Elm; `uv sync` 98 MiB num projeto pequeno e
     382 MiB com pandas; `cargo fetch` 25 MiB; `cargo build` de uma crate
     pequena em 16 núcleos 111 MiB, que cresce com a crate e os núcleos
     (o `prepare` do rust não usa `--jobs`); probes até 41 MiB. No fim, ou
     no timeout, o cgroup é morto e removido: antes, o `subprocess.run`
     matava só o shell no timeout, e o que o comando deixava em segundo
     plano ficava órfão. Um comando que passa do teto falha com "(it used
     more than 4096 MiB)" no `PrepareError`. Sem cgroup, roda como antes,
     mas num grupo de processos próprio, morto no timeout.
   - **Serviços:** um cgroup por serviço, com os mesmos limites, morto e
     removido no `stop`. Um serviço que passa do teto só gera um aviso no
     log: o efeito sobre a correção (testes do serviço falhando) já aparece
     no relatório.
   - **Nova tentativa depois de `RunKilled` reinicia os serviços**
     (`Services.restart`, chamado pelo `before_retry` do `ScriptRunner`).
     Um serviço pode guardar estado (o relatório conta o que recebeu), e
     reaproveitá-lo daria à segunda tentativa o que a primeira mandou. Os
     sockets ficam nos mesmos caminhos, então o comando e o sandbox do teste
     não mudam. Se um serviço não sobe de novo, é `RunError`.
   - **`systemd-oomd`.** Investigado no código do systemd (`src/oom/`,
     `src/core/cgroup.c`) e com experimentos curtos num escopo delegado
     (systemd 262, CachyOS):
     - Configuração desta máquina: `slice.d/10-oomd-per-slice-defaults.conf`
       do systemd do usuário põe `ManagedOOMMemoryPressure=kill` com 80% em
       toda slice do usuário (`app.slice`, onde caem os escopos do
       `systemd-run --user --scope`, `background.slice` etc.), e há
       monitoramento de swap a 90%. O padrão do oomd (60% por 30 s) só vale
       para unidades sem limite próprio. O escopo do grader não é
       monitorado por si.
     - O oomd compara a linha **`full`** do `memory.pressure` (avg10) da
       unidade monitorada com o limite, por 30 s seguidos, e só age se
       houve reclaim recente. Os candidatos são os cgroups folha **e os com
       `memory.oom.group=1`** abaixo dela; escolhe o de maior taxa de
       `pgscan` e mata só ele (`cgroup.kill`). Os `run-*` são candidatos
       (folha e `oom.group=1`); o escopo do grader não é (tem filhos e
       `oom.group=0`); o `supervisor/` é (folha).
     - (a) **Uma resposta que bate no próprio limite não leva o oomd a
       matar o escopo.** Medido: estouro de memória anônima com
       `memory.swap.max=0` morre em 0,05 s, com 1,7 ms de stall no escopo;
       uma execução que relê um arquivo de 256 MiB em disco com
       `memory.max` de 64 MiB por 4 s teve `full` avg10 de 0,36% no
       próprio cgroup e 0,14 a 0,18% na `app.slice`, longe de 80% por
       30 s (e o timeout padrão da execução é 30 s). `full` na slice
       exige todas as tarefas dela paradas ao mesmo tempo. Se o oomd agir
       por pressão vinda de fora (navegador), quem ele escolhe é uma folha:
       uma execução ou o `supervisor/`.
     - (b) **`ManagedOOMPreference` vale em cgroup de usuário**, não só de
       root: no caminho de pressão, o oomd lê os xattrs `user.oomd_avoid`
       e `user.oomd_omit` de um cgroup que não é de root se o dono dele é
       o mesmo da unidade monitorada (aqui, uid 1000 nos dois). No caminho
       de swap, só em cgroup de root. Mas `systemd-run -p
       ManagedOOMPreference=avoid` grava o xattr no cgroup do escopo, que
       não é candidato, e o xattr não é herdado: não serve.
     - (c) **Feito:** o grader grava `user.oomd_avoid` no próprio
       `supervisor/` (gravação confirmada; falha só gera log de depuração),
       e o oomd escolhe uma execução antes dele. E o oomd marca o cgroup que
       mata com o xattr `user.oomd_ooms`: `Events.oomd` o lê, e uma execução
       com limite próprio morta pelo oomd vira `RunKilled` (roda de novo
       uma vez), em vez de um `SIGKILL` comum. Sem limite próprio, conta
       como `MemoryLimit`, como um OOM global. O código do aluno não forja
       o xattr: dentro do bwrap, `/sys` é somente leitura (testado: `EROFS`).
       `memory.high` não foi usado: ele estrangula a execução em vez de
       encerrá-la, o que aumenta a pressão em vez de reduzi-la. O swap não
       preocupa: as execuções têm `memory.swap.max=0`, e o oomd só escolhe
       por swap cgroups com mais de 5% do swap total.
     - Não dá para provocar um kill real do oomd sem deixar a máquina sob
       pressão por 30 s; o caminho foi testado com o xattr gravado à mão.
   - **Disco:** `limits.file_size` passa a ter padrão de 256 MiB
     (`TEST_FILE_SIZE`) no passo de teste dos perfis, quando os limites do
     passo não definem outro. Não no build nem no `prepare` (o rustc e o cc
     gravam binários grandes), nem no perfil `script`. Seguro para os perfis
     embutidos: o passo de teste deles não grava nada grande (o `cargo
     nextest run` não recompila depois do build, verificado; o `elm-test`
     compila no teste, mas o JS gerado tem poucos MiB). O limite é por
     arquivo: impede encher o disco com um arquivo só, não com muitos.
   - **CI:** `taiki-e/install-action@v2` instala o `cargo-nextest`, e os
     testes do `rust-cargo` passam a rodar lá (não verificado: o CI não roda
     daqui).
   - **O compilador no mesmo cgroup da build:** fechado. Os picos medidos da
     build ficam bem abaixo dos padrões: `elm-test make` do aluno 126 MiB
     contra 512 MiB, `c-make` 135 MiB contra 1 GiB, `rust-cargo` 476 MiB
     (`-j1`) contra 2 GiB, todos com folga de 4× ou mais. E a referência
     passa pela mesma build no `prepare`: um projeto cujo compilador não
     cabe no orçamento falha lá, como `ReferenceMemoryLimit`, antes de
     qualquer aluno. O que sobra é uma resposta que faz o compilador
     explodir (tabelas enormes, macros recursivas), e aí a culpa é dela.
     Uma questão com build pesada usa `build.limits`.

## Em aberto

- O `systemd-oomd` ainda pode escolher uma execução sob pressão vinda de
  fora do grader, se ela for a folha com mais reclaim. Agora isso vira
  `RunKilled` e nova tentativa, mas nenhum kill real do oomd foi observado.
- O limite de disco é por arquivo. Uma resposta pode encher o disco do
  `--cache-dir` ou do diretório de trabalho com muitos arquivos menores
  (em `/tmp` em tmpfs, eles contam como memória da execução). Uma cota de
  disco por execução exigiria um sistema de arquivos próprio (tmpfs com
  `size=`, no sandbox).
- O teto dos comandos confiáveis (4 GiB) é fixo. Um `prepare` que precise
  de mais (uma crate grande com `cargo build` em todos os núcleos) falha
  com mensagem clara, mas não há como subir o teto pela configuração.
