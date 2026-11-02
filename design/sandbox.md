# Modelo de segurança e sandbox do autograder

Estado em 2026-11-02. Rascunho para discussão.

Caso de uso principal: o aluno entrega um projeto Python (repositório ou
diretório), o professor tem um template com `pyproject.toml`, `uv.lock` e
testes pytest, e a nota é `testes que passaram / total de testes`. Hoje cada
prova monta um sandbox diferente (bubblewrap ou outro). A ideia é o chalk
trazer perfis prontos e deixar o resto configurável.


## Estado atual

O autograder roda um script arbitrário do professor
(`chalk/autograder/script_runner.py`, `chalk/autograder/script_grader.py`).
O isolamento, quando existe, fica por conta desse script (em geral, um
bwrap montado à mão para cada prova). Problemas concretos:

1. **Isolamento opcional e refeito a cada prova.** Se o script esquece o
   sandbox, o código do aluno roda como o usuário do professor, com acesso a
   `$HOME`, rede, chaves SSH e tokens.
2. **Ambiente vazado.** `ChalkEnv.to_env_dict` repassa todo o `os.environ`
   (`keep_env=True` por padrão), incluindo `GITHUB_TOKEN` e afins.
3. **Template com hard link.** `ScriptGrader.student_repository` chama
   `sync_template(copy_mode="link")`. Um `open("tests/test_x.py", "w")` no
   código do aluno sobrescreve o arquivo do template do professor, e o
   estrago vale para todos os alunos corrigidos depois.
4. **Nota forjável.** O relatório (`graded.*`) fica no diretório em que o
   aluno escreve, e a linha `CHALK_RESULT:` vem do stdout que o aluno
   controla. Um `print('CHALK_RESULT: 1.0')` no import já dá nota máxima.
5. **Timeout parcial.** `process.kill()` mata só o shell (`shell=True`).
   Filhos e netos continuam rodando. Não há limite de memória, processos ou
   disco.

Os itens 2, 3 e 5 são bugs e valem correção mesmo sem sandbox.


## Modelo de ameaças

Ator: o aluno, por descuido (loop infinito, `rm -rf`, teste que enche o
disco) ou de má-fé (quer nota maior, quer ler a resposta de colegas ou o
gabarito).

Ativos, em ordem de prioridade:

1. A máquina do professor: arquivos, credenciais, rede.
2. A correção dos outros alunos: template, gabarito e notas alheias.
3. A disponibilidade da correção: um aluno não pode travar a turma toda.
4. A integridade da própria nota do aluno.

Fora do escopo: exploits de kernel, canais laterais, e um aluno que derrota
o pytest de dentro do mesmo processo (ver "Limite honesto").


## Princípio: separar quem roda de quem dá a nota

- **Preparo (confiável, com rede, uma vez por questão).** O chalk instala as
  dependências do template (`uv sync --frozen`) num venv em cache, chaveado
  pelo hash do `uv.lock`. Também coleta a lista de testes do template
  (`pytest --collect-only` só sobre o código do professor).
- **Execução (não confiável, sem rede, uma vez por aluno).** O código do
  aluno roda no sandbox com o venv montado só leitura. Nada do aluno é
  instalado.
- **Avaliação (confiável, fora do sandbox).** O chalk lê o relatório gerado
  e calcula a nota. Só contam os testes da lista coletada no preparo; o
  denominador é o total dessa lista, não o que o aluno conseguiu coletar.
  Teste ausente do relatório conta como falha.

Com isso, apagar testes, pular coleta ou criar testes falsos não muda a
nota.


## Limite honesto

O pytest importa o código do aluno no mesmo processo. Quem roda ali pode
alterar o pytest, o relatório ou os resultados. Nenhum sandbox resolve isso
sem rodar cada teste em processo separado que o aluno não alcança. O que
dá para fazer barato:

- Testes, `conftest.py` e configuração do pytest vêm do template, montados
  só leitura por cima dos arquivos do aluno. `conftest.py`, `pytest.ini` e a
  seção `[tool.pytest]` do aluno são ignorados.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, `-p no:cacheprovider` e `-c` apontando
  para a configuração do template.
- O relatório vai para um diretório fora da área de trabalho do aluno.
- O chalk guarda stdout e relatório de cada aluno para auditoria e marca
  anomalias (relatório ausente, testes com ids desconhecidos, duração zero).

Isso detém o aluno que tenta trapacear com pouco esforço e deixa rastro
para o resto. Para prova de alto risco, a saída é revisar os suspeitos à
mão.


## Abstração: sandbox, perfil e formato do relatório

Integração por linguagem não escala, mas a parte que muda por linguagem é
pequena. Três camadas:

1. **Sandbox** (independe de linguagem): montagens, ambiente, rede, limites.
   Um backend, `bwrap`.
2. **Perfil** (por ecossistema): a lista de etapas (ver abaixo), com
   comando, limites e montagens de cada uma, e o formato do relatório. São
   dados, não código: um `python-pytest` e um `elm-test` diferem em umas
   cinco linhas de configuração.
3. **Leitor de relatório** (por formato, não por linguagem): JUnit XML cobre
   quase tudo (`pytest --junit-xml`, `elm-test --report junit`, jest,
   `cargo nextest`, `gotestsum`). O `result_extractor` atual (JSON do chalk,
   JSON do pytest, linha `CHALK_RESULT:`) continua para o perfil `script`.

Linguagem nova vira perfil novo em `chalk.toml`, sem código no chalk, desde
que o test runner gere JUnit.


## Etapas

Todo perfil é a mesma sequência; linguagem interpretada só deixa a etapa de
compilação vazia.

| Etapa | Quando | Confiança | Rede | Grava em |
| --- | --- | --- | --- | --- |
| `prepare` | uma vez por questão, em cache | confiável (só template e solução) | sim | cache |
| `build` | por aluno, opcional | não confiável | não | diretório de trabalho e de build |
| `test` | por aluno | não confiável | não | diretório de trabalho e de saída |
| `score` | por aluno, dentro do chalk | confiável | não | nada |

- **`prepare`** baixa e compila as dependências a partir do lockfile do
  template (`uv sync --frozen`, `cargo fetch` + `cargo build --tests` da
  solução, `elm make`). O resultado vira cache só leitura para as outras
  etapas. Também coleta a lista de testes esperada.
- **`build`** roda no sandbox porque compilar já executa código do aluno:
  `build.rs` e macros procedurais em Rust, `Makefile` e CMake em C. Tem
  timeout e limite de memória próprios (rustc e linkers pedem mais memória
  e tempo que os testes).
- **`test`** roda o binário ou o test runner. Pode montar o resultado do
  `build` só leitura, para o teste não alterar o binário que está testando.
- **`score`** lê o relatório e calcula a nota.

Falha de compilação é um resultado próprio, não uma nota zero muda: o chalk
guarda a saída do compilador como feedback e marca a resposta como
`build-error` (vira uma `Disqualification`, como `Timeout` e `Error` hoje).
O professor decide no perfil se isso vale zero ou se a resposta vai para
correção manual.

**Cache de compilação.** Recompilar as dependências por aluno é o que mata o
tempo em Rust. O `prepare` compila a solução de referência e guarda o
diretório `target/`. Cada aluno começa com uma cópia desse diretório: com
`bwrap --overlay-src <cache> --tmp-overlay target`, o cache fica como
camada inferior só leitura e as escritas do aluno caem num tmpfs que some ao
final. Só o crate do aluno recompila.

**O template manda no build.** `Cargo.toml`, `Cargo.lock`, `Makefile`,
`CMakeLists.txt` e flags de compilação vêm do template (`.chalkoverwrite`).
O aluno não adiciona dependências nem troca flags. Isso também impede um
`Makefile` do aluno que pule a compilação dos testes.


## Como tornar o bwrap menos frágil

A fragilidade vem da lista de permissões: descobrir, caminho a caminho, o
que o test runner precisa (`/usr`, `/etc/alternatives`, o Python do uv, o
cache do npm...). Duas mudanças resolvem a maior parte.

**Lista de bloqueio em vez de lista de permissões.** Monta `/` inteiro só
leitura e esconde o que é sensível:

- `$HOME`, `/root`, `/home` → tmpfs vazio.
- `/run`, `/var/run`, `/tmp`, `/var/tmp`, `/mnt`, `/media` → tmpfs (some com
  os sockets do Docker, do D-Bus e do agente SSH).
- `/dev` e `/proc` novos (`--dev`, `--proc`).
- Rede desligada (`--unshare-net`).
- Depois, só leitura, o que o perfil pede de dentro do `$HOME`: o Python do
  uv (`~/.local/share/uv/python`) e o venv em cache.

Tudo que é pacote do sistema fica visível sem configurar nada. O segredo
quase sempre mora no `$HOME` ou em `/run`, e esses são escondidos. O risco
residual é um arquivo legível por todos fora do `$HOME` (por exemplo
`/etc/` de algum serviço), que o aluno já leria de qualquer forma com uma
conta na máquina.

**Ensaio com a solução de referência.** Antes de corrigir a turma,
`chalk autograde --check` roda o template com a solução do professor
(`solution/`) dentro do sandbox e exige nota máxima. Se falhar, mostra o
stderr e, com `--trace`, os caminhos negados (`strace -f -e trace=file`
filtrado por `ENOENT`/`EACCES`). Assim o erro de configuração aparece numa
rodada, não em 80 alunos com nota zero.


## Backends

- `bwrap` (padrão no Linux). Já instalado e sem daemon. Namespaces de
  usuário, rede, PID, IPC e UTS; raiz só leitura; `--die-with-parent`;
  `--new-session` (evita injeção no terminal via TIOCSTI).
- `podman` (segundo backend). Para quando a questão precisa de outra
  distribuição, de pacotes de sistema que o professor não tem, ou de rede
  com servidores simulados (ver "Rede"). Configuração mais trabalhosa, por
  isso não é o padrão.
- `none`. Sem isolamento. Só com `--unsafe` explícito na linha de comando,
  para depurar o próprio template.

Limites de recurso: `systemd-run --user --scope -p MemoryMax=... -p
TasksMax=...` quando disponível, senão `prlimit` (CPU, memória, tamanho de
arquivo). O timeout mata o grupo de processos inteiro, não só o filho
direto.


## Rede

Desligada por padrão. Quando a questão precisa de rede, quase sempre é um
cenário simulado: o código do aluno conversa com servidores fixos que o
professor sobe. Acesso livre à internet é raro e exige opção explícita.

| Modo | Backend | O que o aluno alcança |
| --- | --- | --- |
| `none` (padrão) | bwrap | só o loopback do próprio sandbox |
| `services` | bwrap | loopback, com serviços do professor iniciados dentro do sandbox antes dos testes |
| `internal` | podman | uma rede interna (`podman network create --internal`) com contêineres de serviço do professor, sem saída para fora |
| `host` | bwrap ou podman | a rede da máquina; só com opção explícita |

- `services` cobre o caso comum (um servidor HTTP ou banco que a questão
  usa) sem podman: o perfil declara os comandos, o chalk os inicia dentro
  do mesmo namespace de rede e espera as portas abrirem. Como os serviços
  dividem o sandbox com o aluno, o aluno pode alterá-los; serve para
  simulação, não para guardar segredo.
- `internal` é para quando o serviço precisa ficar fora do alcance do aluno
  (ele só fala com o serviço pela rede) ou é uma imagem pronta (Postgres,
  Redis, um servidor de referência). Os contêineres de serviço sobem uma
  vez por questão e são compartilhados; se o estado entre alunos importa, o
  perfil pede reinício por aluno.
- Lista de destinos permitidos na internet (`allow: [api.exemplo.br]`)
  fica de fora até aparecer o caso. Daria para fazer com o `pasta` do
  podman ou um proxy, como o sandbox do próprio Claude Code.


## Perfis

Um perfil é um conjunto nomeado de opções do sandbox mais os passos de
preparo, execução e avaliação. Primeiro perfil:

**`python-pytest`**

- Preparo: `uv sync --frozen` do template em
  `.chalk/cache/venv-<hash do uv.lock>`; coleta dos ids de teste.
- Montagens: as da lista de bloqueio acima; Python do uv e venv só
  leitura; diretório de trabalho (cópia, nunca link) leitura e escrita;
  `tests/` e config do template só leitura por cima.
- Ambiente: limpo, com allowlist (`PATH`, `LANG`, `PYTHONHASHSEED`,
  `PYTHONDONTWRITEBYTECODE`, variáveis `CHALK_*`).
- Comando: `pytest -c <config do template> --junit-xml=<saída> tests/`.
- Avaliação: junit XML lido pelo chalk, nota = aprovados / total coletado no
  preparo. Pesos por teste ficam para depois (por exemplo, marcador
  `@pytest.mark.points(2)`).

**`elm-test`**: preparo com `elm make` do template (popula `~/.elm` em
cache), comando `elm-test --report junit`, o mesmo leitor JUnit.

**`rust-cargo`**

- `prepare`: `cargo fetch --locked` e `cargo build --tests --offline` da
  solução, guardando `~/.cargo/registry` e `target/` em cache.
- `build`: `cargo build --tests --offline --locked` com `CARGO_HOME` só
  leitura e `target/` em overlay. Timeout de 120 s, 2 GB de memória.
- `test`: `cargo nextest run --offline --no-fail-fast` com saída JUnit
  (`cargo test` só gera JUnit no nightly, com `-Z unstable-options`; por
  isso o perfil usa o nextest).

**`c-make`**

- `prepare`: nada além de checar que o compilador existe; bibliotecas de
  teste (Unity, Criterion) vêm no template ou no sistema.
- `build`: `make -f <Makefile do template> tests`, com `CFLAGS` do perfil
  (`-O0 -g -fsanitize=address,undefined` ajuda a pegar erros de memória que
  passariam despercebidos).
- `test`: o binário de teste com saída JUnit, ou o perfil `stdio` abaixo.

**`stdio`** (qualquer linguagem compilada ou não): roda o programa do aluno
com cada `tests/*.in` na entrada e compara com `tests/*.out`. Nota = casos
corretos / total. Comparação exata, por linhas ignorando espaços finais, ou
por um script do professor. Cobre exercícios estilo juiz online em C sem
framework de teste.

Outros perfis, sob demanda: `script` (o script do professor atual, agora
dentro do sandbox), `python-stdin` (entrada e saída comparadas),
`node-test`.


## Configuração

No `conf.yaml`, por questão, com padrão em `chalk.toml`:

```yaml
questions:
  - id: q1
    type: repo
    autograder:
      sandbox: python-pytest
      timeout: 60
      limits:
        memory: 1G
        processes: 64
        disk: 200M
      network: none       # none | services | internal | host
  - id: q2
    type: repo
    autograder:
      sandbox: rust-cargo
      build:
        timeout: 180      # sobrescreve só a etapa de build
      on_build_error: manual   # zero | manual
```

- `sandbox` escolhe o perfil; as outras chaves sobrescrevem os padrões dele.
  Chaves no nível do autograder valem para todas as etapas; `build:`,
  `test:` e `prepare:` sobrescrevem uma etapa só.
- `sandbox: script` com `script:` roda o script do professor dentro do
  sandbox, cobrindo os casos que o perfil não prevê.
- Perfis próprios do professor ficam em `chalk.toml` (`[sandbox.<nome>]`,
  herdando de um perfil embutido), para reaproveitar entre provas.


## Fases

1. Corrigir os bugs 2, 3 e 5 do "Estado atual" (sem sandbox ainda).
2. Backend `bwrap` com o perfil `script`: o script atual passa a rodar
   isolado, com relatório fora da área do aluno.
3. Perfil `python-pytest` com preparo em cache, nota pela lista coletada e
   `chalk autograde --check`. Leitor JUnit.
4. Etapa `build` e perfil `rust-cargo`, com cache de `target/` em overlay e
   o resultado `build-error`.
5. Perfis `c-make`, `stdio` e `elm-test`, para validar que a abstração serve
   sem código novo.
6. Perfis em `chalk.toml` e rede `services`.
7. Backend `podman` com rede `internal`.


## Decisões tomadas

- Só Linux, sem suporte a outros sistemas. `bwrap` é o backend padrão;
  `podman` é o segundo, para imagens próprias e rede `internal`.
- O aluno não adiciona dependências. Vale só o lockfile do template.
- Rede desligada por padrão; os outros modos são opção por questão.

