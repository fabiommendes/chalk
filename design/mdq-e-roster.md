# Questões em mdq e roster compartilhado com o codehood

Estado em 2026-11-01. Contexto: chalk e codehood rodam no mesmo repositório
da turma, cada um com as próprias configurações (ver a conversa que gerou
`design/migracao-codehood-mdq.md`). O chalk corrige o que acontece fora da
plataforma e entrega notas ao codehood pelo `grades.csv` da raiz.


## Layout

```
turma/
├── codehood.toml        # codehood
├── grades.csv           # codehood lê; o chalk pode gerar (fase 4)
├── grades.py            # codehood
├── questions/ exams/ resources/   # codehood
├── roster.csv           # compartilhado (ver "Roster")
├── chalk.toml           # chalk
├── conf.py              # chalk (opcional)
└── quiz1/               # um quiz do chalk: pasta com conf.yaml
    ├── conf.yaml
    ├── questions/
    │   ├── q1.md        # mdq em Markdown
    │   └── q2.yaml      # mdq na forma parseada (YAML ou JSON)
    ├── submissions.csv
    └── grades.csv
```

O codehood só lê os arquivos e pastas dele, e o chalk só trata como quiz
uma pasta com `conf.yaml`. O único arquivo disputado é `roster.csv`.


## Questões

- O documento de cada questão é um arquivo mdq em `<quiz>/questions/`,
  carregado com `mdq.load`. O id da questão é o nome do arquivo sem
  extensão; um `id` no documento que não bata com ele é erro.
- `conf.yaml` guarda só o que é do chalk, por questão:
  `value` (peso), `autograder`, `answer_suffix` e, para `repo`, `required`.
  A ordem das questões é a da lista `questions:` do `conf.yaml`; questões
  sem entrada na lista vêm depois, em ordem natural de nome.
- Uma questão que aparece em `conf.yaml` sem arquivo mdq é uma questão
  aberta: correção manual ou por autograder. Isso mantém a regra do
  `escopo.md` de que questões começam sem tipo.
- O tipo `repo` (resposta é um diretório) não existe no mdq e continua
  nativo do chalk, declarado em `conf.yaml` com `type: repo`.
- `association` sai até o mdq ter o tipo matching.
- A inferência de gabarito a partir das respostas sai. O gabarito fica no
  arquivo mdq.
- A correção automática de questões mdq usa `score_response` do mdq.
  Respostas seguem `docs/responses.md` do mdq (id da alternativa, lista de
  ids, texto, número...).
- Escala: o mdq dá a nota da questão em [-1, 1]. O chalk guarda esse valor
  como `Score` e multiplica por `value` no total do quiz, como hoje.

### Regras do mdq que o chalk segue

- O mdq não muda por causa do chalk. `stem` é obrigatório, então todo
  arquivo de questão do chalk tem enunciado.
- `association` só volta se o mdq ganhar o tipo matching.


## Roster

Esquema proposto para `roster.csv`, com os campos que o servidor do codehood
já tem (`username`, `name`, `email`, `schoolId`, `githubId`, status
`active|dropped`):

```csv
school_id,username,name,email,github,status
190012345,maria,Maria Silva,maria@exemplo.br,mariasilva,active
```

- Colunas em snake_case, como o cabeçalho do `grades.csv` do codehood
  (`school_id`, `username`, `github`, `email`).
- Todas opcionais, exceto que cada linha precisa de uma chave.
- O chalk usa `school_id` como id do aluno por padrão
  (`[chalk] student_id = "school_id"` em `chalk.toml` muda isso). A coluna
  `id` antiga é aceita como sinônimo de `school_id`.
- Colunas extras são preservadas pelos dois lados.
- O `codehood roster` (ROADMAP 0.1) baixa o arquivo do servidor e faz merge
  por chave, sem apagar colunas que não conhece. O chalk faz o mesmo no
  `chalk roster import`.

Resposta da sessão do codehood (2026-11-01, ainda sem aval do dono do
projeto):

- Não há esquema planejado; os nomes acima não conflitam. São os mesmos
  identificadores que o `grades.csv` aceita (`ID_FIELDS` em
  `cli/codehood/push/grades.py`).
- O codehood deve fazer merge por `username`, a única chave que o servidor
  sempre tem. O chalk continua usando `school_id` como id do aluno; uma
  linha sem `school_id` fica sem id no chalk e é ignorada por ele.
- `status` entra, em minúsculas (`active`, `dropped`).
- Célula vazia quando o valor falta. O servidor guarda `schoolId` e
  `githubId` nulos como `!<username>`, e isso não pode ir para o arquivo.


## Integração com o codehood

Implementado:

- `roster.csv` no esquema acima, lido e escrito pelo chalk sem perder o que
  é do codehood.
- `chalk codehood grades`: uma coluna por quiz no `grades.csv` da raiz, em
  porcentagem (a mesma escala de `ExamResult.score`), com a chave do roster.
  Preserva as outras colunas, as linhas e o delimitador. O `grades.py` do
  curso lê as colunas em `student.scores`.

Propostas, ainda sem decisão:

- Quiz do chalk que reaproveita questões do banco `questions/` do codehood
  (por exemplo, `source: ../questions/x.md` na entrada do `conf.yaml`). Hoje
  é preciso copiar o arquivo.
- Ler do codehood a lista de matriculados quando existir `codehood roster`;
  até lá, o roster é mantido à mão ou com `chalk roster import`.
- Nota de questão aberta corrigida no chalk enviada como `Feedback` do
  codehood. Depende de API e de `codehood pull`, que não existem.
