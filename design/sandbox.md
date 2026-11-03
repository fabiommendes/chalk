# Modelo de segurança e sandbox do autograder

Estado em 2026-11-02. Rascunho para discussão.

Cenários em `design/historias-correcao.md`. Este documento cobre as duas
classes de correção que rodam script: **dado** (a resposta é lida por um
script do professor) e **código** (a resposta é executada). Objetiva (mdq)
e manual não rodam script e ficam fora daqui.

Caso mais comum da classe código: o aluno entrega um projeto Python, o
professor tem um template com `pyproject.toml`, `uv.lock` e testes pytest, e
a nota é `testes que passaram / total de testes`. Hoje cada prova monta um
sandbox diferente (bubblewrap ou outro). A ideia é o chalk trazer perfis
prontos e deixar o resto configurável.


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

Os itens 2, 3 e 5 foram corrigidos no commit `b051cf0`: cópia em vez de
hard link, ambiente com allowlist (mais `autograder.pass_env`) e grupo de
processos próprio, morto no timeout e no fim da execução. Falta limite de
memória, processos e disco.


## Dado e código

| | Dado | Código |
| --- | --- | --- |
| A resposta do aluno é | lida pelo script | executada |
| Exemplos | regex, segredo do enunciado, análise de AST | pytest, cargo, elm-test, entrada e saída |
| Sandbox | não | sim |
| Timeout, memória, tamanho da resposta | sim | sim |
| Quem escreve o relatório | o script do professor | o test runner, num processo que o aluno controla |

Na classe dado, o script é confiável e a resposta é só um texto. Os riscos
são de disponibilidade (regex com backtracking catastrófico, resposta de
500 MB) e de injeção: se o script imprime a resposta e o chalk procura
`CHALK_RESULT:` no stdout, uma resposta com essa linha vira nota. Por isso
o resultado passa a vir só do arquivo de relatório, nunca do stdout, nas
duas classes.

Quem declara a classe é a questão, no `conf.yaml`, pela chave `sandbox` (ver
"Configuração"). Cada perfil tem um padrão: os da classe código usam
`bwrap`; `regex` e `ast` usam `none`; `script` usa `bwrap`, e o professor
põe `sandbox: none` quando o script só lê a resposta. Assim, esquecer a
declaração erra para o lado seguro.

Corretores embutidos da classe dado:

- `regex`: o aluno entrega uma regex; o perfil lista exemplos que devem e
  que não devem casar; nota = acertos / total. Cada exemplo roda num
  subprocesso com timeout próprio, porque `re` do Python não pode ser
  interrompido; exemplo que estoura o tempo conta como erro.
- `ast`: o aluno entrega código que é só parseado (Python, por `ast`); o
  perfil lista construções exigidas ou proibidas. Nunca executa.
- `script` com `sandbox: none`: o resto, incluindo segredos do enunciado,
  que o chalk não trata de forma especial.


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
   JSON do pytest) continua para o perfil `script`; a linha `CHALK_RESULT:`
   no stdout sai (ver "Dado e código").

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
- `none`. Sem isolamento, mas com timeout e limites. Padrão dos perfis da
  classe dado. Num perfil da classe código, só vale com `--unsafe` na linha
  de comando, para depurar o próprio template.

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

**`script`**: o script do professor de hoje, com as variáveis `CHALK_*`.
Roda no sandbox por padrão; com `sandbox: none`, fora dele (classe dado).

Outros perfis, sob demanda: `node-test`.


## Configuração

No `conf.yaml`, por questão, com padrão em `chalk.toml`:

```yaml
questions:
  - id: q1
    type: repo
    autograder:
      profile: python-pytest
      timeout: 60
      limits:
        memory: 1G
        processes: 64
        disk: 200M
      network: none       # none | services | internal | host
  - id: q2
    type: repo
    autograder:
      profile: rust-cargo
      build:
        timeout: 180      # sobrescreve só a etapa de build
      on_build_error: manual   # zero | manual
  - id: q3
    autograder:
      profile: regex
      match: [ana@unb.br, x.y@a.com]
      reject: ["@unb.br", "ana@"]
  - id: q4
    autograder:
      profile: script
      script: segredo.py
      sandbox: none       # o script só lê a resposta
```

- `profile` escolhe o perfil; as outras chaves sobrescrevem os padrões dele.
  Chaves no nível do autograder valem para todas as etapas; `build:`,
  `test:` e `prepare:` sobrescrevem uma etapa só.
- `sandbox` escolhe o backend (`bwrap`, `podman`, `none`); o padrão vem do
  perfil.
- Sem `profile`, uma questão com `script:` usa o perfil `script`, como hoje.
- Perfis próprios do professor ficam em `chalk.toml` (`[profiles.<nome>]`,
  com `extends` para herdar de outro perfil), para reaproveitar entre
  provas.


## Fases

1. ~~Corrigir os bugs 2, 3 e 5 do "Estado atual".~~ Feito (`b051cf0`).
2. ~~Resultado só pelo arquivo em `$CHALK_RESULT`, fora da área do aluno;
   leitor JUnit; nota `3/4` no formato texto.~~ Feito. Limites (`memory`,
   `file_size`, `answer_size`), chaves `profile` e `sandbox` (só `none`) e
   perfil `regex` também feitos. Limite de processos fica para o sandbox:
   `RLIMIT_NPROC` conta todos os processos do usuário, não só os do aluno.
3. ~~Backend `bwrap` com o perfil `script`.~~ Feito. O script inteiro roda
   no sandbox (padrão quando `sandbox` não é declarado), com lista de
   bloqueio, `network: none|host` e `mounts`. O resultado fica fora da área
   de trabalho, mas montado com escrita no sandbox: protege a máquina, não
   a nota. Proteger a nota fica para os perfis da fase 4, ou para um
   `$CHALK_RUN` em que só a parte do aluno roda isolada. Limite de
   processos (cgroups) ainda falta.
4. ~~Perfil `python-pytest` com preparo em cache, nota pela lista coletada e
   `chalk autograde --check`.~~ Feito. A coleta usa o template mais
   `solution/` e roda fora do sandbox (código confiável). Teste pulado
   conta como falha, para o aluno não fugir de um teste com
   `pytest.skip()`. Sem `--trace` por enquanto. `sandbox: none` é aceito
   sem `--unsafe`: a declaração explícita no `conf.yaml` já basta.
5. ~~Etapa `build` e perfil `rust-cargo`, com cache de `target/` em overlay e
   o resultado `build-error`.~~ Feito, com duas mudanças. O cache de
   `target/` é copiado (`cp -a --reflink=auto`) em vez de montado em
   overlay: o kernel da máquina de desenvolvimento não tinha overlayfs, e
   a cópia funciona em qualquer lugar (instantânea em btrfs). Os arquivos
   do aluno recebem mtime atual depois da cópia, porque o cargo decide o
   que recompilar pelo mtime e o cache pode ser mais novo que eles.
   `CARGO_HOME` fica no cache, separado do `~/.cargo` do professor (que
   guarda o token do crates.io). O sandbox chama os binários do toolchain
   direto (`rustc --print sysroot`), sem os proxies do rustup. Só testes
   de integração (`tests/`) contam. `on_build_error` aceita `build-error`
   (padrão), `zero` e `manual`.
6. ~~Perfis em `chalk.toml`~~ (feito antes da fase de perfis novos, que
   dependia disso) e rede `services` (falta). `python-pytest` e
   `rust-cargo` viraram dados em `chalk/autograder/profiles.toml`, e um
   único `ProfileGrader` executa qualquer perfil. Mudanças em relação ao
   desenho:
   - A lista de testes esperados vem do relatório JUnit de uma execução da
     solução de referência (build e test no sandbox, como um aluno), não de
     um comando de coleta por linguagem. Sai o parser do
     `pytest --collect-only` e do `nextest list`. Custa uma execução extra
     por correção e exige que a solução rode; a nota dela não importa, só
     os nomes dos testes.
   - O que era código virou chaves: `probe` (comandos que descobrem o
     toolchain, como `rustc --print sysroot` e `uv python dir`), `key`
     (arquivos que escolhem o cache), `files` (arquivos gerados no cache,
     como a config do nextest), `build.seed` (cópia do `target/`) e
     `unset`.
   - O pytest não recebe mais `-c`: `pytest.ini`, `pyproject.toml`,
     `tox.ini`, `setup.cfg` e `conftest.py` são arquivos confiáveis, vindos
     do template ou removidos.
   - Os testes aparecem no feedback como `classname::name` do JUnit
     (`tests.test_calc::test_sub`), para todos os perfis.
   - `script` e `regex` continuam em código: não seguem o modelo de etapas.
7. ~~Perfis `c-make`, `stdio` e `elm-test`, para validar que a abstração
   serve sem código novo.~~ Feito, também `c-stdio`. Os três couberam em
   TOML; o código novo foi de apoio, não por linguagem:
   - `c-make` usa `chalk_test.h`, uma biblioteca de testes em C que o chalk
     distribui (`{runners}` no include path): um processo por teste
     (crash e laço infinito derrubam só o teste), relatório JUnit direto
     em `$CHALK_RESULT`. Compila com ASan e UBSan; vazamento não é checado
     porque o LSan precisa de ptrace. Sem Criterion ou Unity, que não geram
     JUnit sem ferramentas extras.
   - `stdio` ganhou um executor em Python (`runners/stdio.py`, só stdlib,
     `python -I`) e um formato de relatório próprio (`report = "stdio"`).
     O desenho original, um executor que compara e gera JUnit, deixava os
     `.out` visíveis no sandbox: o programa do aluno acharia o `.in` igual
     à sua entrada e imprimiria o `.out`. Agora a chave `hide` tira os
     `.out` da área de trabalho, o executor só grava as saídas e o chalk
     compara fora do sandbox, com o modo da variável `compare`.
   - `elm-test`: o elm grava um lock no `ELM_HOME` até para ler, então o
     cache de pacotes não pode ser montado só leitura; cada execução recebe
     uma cópia (`build.seed`, 2-3 MB). `elm-test make` é a etapa de build.
     `node`, `elm` e `elm-test` são achados por probe e montados só
     leitura (o fnm deixa tudo em `~/.local/share/fnm`).
   - Chaves novas: `vars` (com `vars` por questão no `conf.yaml`, para
     `run`, `compare`, `test_timeout`, `binary`), `hide` e `report`.
   - As montagens só leitura dos testes passaram a usar a cópia na área de
     trabalho em vez do template, para os arquivos removidos por `hide`
     não voltarem pela montagem.
   - A mensagem de falha de cada teste do JUnit entra no feedback.
8. Backend `podman` com rede `internal`.


## Decisões tomadas

- Só Linux, sem suporte a outros sistemas. `bwrap` é o backend padrão;
  `podman` é o segundo, para imagens próprias e rede `internal`.
- O aluno não adiciona dependências. Vale só o lockfile do template.
- Rede desligada por padrão; os outros modos são opção por questão.

