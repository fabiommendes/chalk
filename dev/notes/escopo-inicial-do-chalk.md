---
type: note
status: open
kind: research
tags: [scope]
created: 2026-11-12
creator: claude
---

# Escopo inicial do chalk

## Proposta inicial de organização

chalk init
chalk info
chalk roster (show | add | import | validate)
chalk quiz (list | create | show)
chalk attendance (start | show | update | import)
chalk group (create | show | update | delete)
chalk question (list | show | choices | convert | edit)
chalk response (show | set | import | export)
chalk grade (show | report | auto | manual | student | quiz | override)
chalk script <plugin_name>
chalk log

## Bloco A: Produto e Fronteiras

1. Qual problema principal o Chalk resolve no dia a dia do professor?

Adminstrar turmas, atividades, respostas e notas de forma simples e eficiente,
sem depender de sistemas complexos ou planilhas desorganizadas.

2. O usuário principal é só docente, ou também monitor/coordenador/aluno?

O foco é no uso pelo docente. Pode ser útil para alunos e monitores, mas seria
uma utilidade secundária.

3. O foco é uso individual local ou colaboração em equipe?
   
Foco é no uso pessoal.

4. Você quer CLI opinativa e simples, ou CLI altamente configurável?

Chalk deve ser opinativa e simples. A flexbilidade se limita a formatos
diferentes de arquivos para armazenamento dos dados. Planilhas vs JSON, vs YAML, etc.

5. Quais recursos ficam fora do escopo da V1?

- Integração com LMS.
- Suporte a rubricas.
- Suporte a grupos.
- Suporte a atividades complexas como projetos ou trabalhos em grupo.
- Suporte a plugins de correção automática.

## Bloco B: Modelo Mental da CLI

1. Você prefere comandos orientados por entidade (roster, quiz, question)
   ou por fluxo (prepare, collect, grade, report)?

Os comandos são orientados por entidade. Isso pode necessitar um refactor com
relação aos comandos atualmente implementados. Como `chalk add`, por exemplo.

2. Você quer manter comandos “curtos e mágicos” ou tornar tudo explícito em
   subcomandos?

Os comandos devem ser explícitos em subcomandos. Parecido com a estrutura do
git, por exemplo.

3. Você quer aliases curtos oficiais?

Sim, mas apenas para os comandos mais comuns. Seguiria uma convenção tipo npm de
usar letras como alias.

4. Você quer consistência total de naming em inglês, ou aceita mistura com
   termos acadêmicos locais?

Prefiro consistência total em inglês, para evitar confusão com termos locais e
mistura de idiomas.


## Bloco C: Fluxo Principal (Happy Path)

1. Qual é o caminho canônico do começo ao fim para uma turma nova?

   1. `chalk init` cria estrutura da turma.
   2. `chalk roster add` ou edita a planilha de roster externamente para
      adicionar alunos.
   3. `chalk quiz create` para criar uma nova atividade, definindo
      questões e critérios.
   4. Alunos submetem respostas por meio de upload ou integração com LMS.
   5. `chalk grade auto` para rodar a correção automática, se aplicável, e
      depois `chalk grade override` para ajustes manuais.
   6. `chalk grade report` para criar relatórios de notas e feedback.

2. Em que etapa entram respostas dos alunos?

As respostas vem de um recurso externo via upload de arquivos ou integração com
LMS. O comando `chalk response import` pode ser usado para trazer essas
respostas para o sistema.

3. O cálculo de nota é automático por padrão?

O cálculo da nota de cada questão pode vir pré-populado pelo LMS ou ser feito
por um plugin de correção automática. O comando `chalk grade auto` pode ser
usado para rodar a correção automática, se aplicável. O professor pode então
usar `chalk grade override` para ajustes manuais.

4. Relatório é sempre etapa final ou usado continuamente durante a correção?

Os relatórios são gerados continuamente por demanda do usuário. Eles podem ser
impressos na tela ou exportados para arquivos.

5. Quais 3 comandos mais importantes precisam ficar memorizáveis?

- `chalk quiz create` para criar atividades.
- `chalk grade auto/manual` para rodar a correção das atividades.
- `chalk grade report` para gerar relatórios de notas e feedback.

## Bloco D: Roster (Alunos)

1. Identificador principal é id institucional, email ou outro?

O sistema é indiferente quanto ao id principal do aluno. Uso id institucional
por padrão, mas email ou github username também podem ser usados como
identificadores únicos, desde que sejam consistentes. O id não pode ter espaços
ou caracteres especiais, para facilitar o uso em comandos e arquivos.

2. Busca por aluno deve aceitar fuzzy match por nome/email/github?

Sim.

3. Importação de roster substitui ou faz merge?

Faz merge, para evitar perda acidental de dados. O comando `chalk roster
validate` pode ser usado para verificar se há nomes ou e-mails duplicados ou
alunos que não submeteram nenhuma resposta, por exemplo.

4. Quer validação de duplicados como erro bloqueante?

Não. O sistema pode alertar para as duplicatas, mas deve tentar resolver
automaticamente quando possível. A resolução pode ser via merge ou adicionando
suffixos numéricos nos identificadores.

## Bloco E: Quiz (Atividades)

1. Diferença entre atividade simples e complexa deve aparecer no comando?

Idealmente o quiz theve ser uma entidade única e flexível e cada tipo de
atividade pode criada incorporando recursos diferentes ou configurações
específicas. A atividade deve ser relativamente independente da estratégia de
correção.

2. Você quer versionamento de atividade (v1, v2) no CLI?

Não. O versionamento pode ser feito manualmente clonando a atividade.

3. Renomear atividade deve atualizar arquivos relacionados automaticamente?

O id da atividade é vinculado ao caminho que ela fica no sistema de arquivos. 
Então mudar o id é o mesmo que mudar a pasta onde ela fica. O nome é apenas um
campo de metadados independente.

4. Datas de início/fim são obrigatórias?

Não. Via de regra o sistema deve impor o mínimo possível de campos obrigatórios
em cada entidade.

5. Formato padrão de arquivo da atividade deve ser qual?

O formato padrão para armazenamento é YAML. Mas também podemos usar formatos de
tabela ou mesmo distribuir a atividade em múltiplos arquivos.


## Bloco F: Question (Questões)

1. Questões são sempre identificadas por q1, q2, q3?
   
Não, mas essa é a convenção padrão.

2. Você quer comandos para reordenar questões?

Não precisa. O usuário pode usar o formato de planilha e renomear as colunas.

3. Converter tipo de questão deve ser permitido em quais casos?

As questões começam sem tipo por padrão e o tipo assumido é questão aberta. Aceitamos as conversões:

- Aberta <-> Múltipla escolha
- Aberta <-> Numérica
- Múltipla escolha <-> Múltipla seleção

4. Peso/nota máxima por questão é obrigatório?

Não. Por padrão o sistema assume que as provas valem 100 pontos e as questões
possuem o mesmo peso dentro da atividade.

5. Quer suporte a rubricas já na v1?

Rúbricas podem ser suportadas em versões futuras do Chalk, tanto na correção
manual quanto na correção automatizada. Mas o escopo fica fora da V1.


## Bloco G: Response (Respostas)

1. Resposta é sempre por aluno+atividade+questão?

Na V1 sim, mas futuramente podemos ter respostas únicas para múltiplas questões
ou respostas em grupo.

2. Você quer comando para editar resposta manualmente?

Não. Talvez isso possa ser necessário na V2.

3. Importação de respostas vem de qual fonte típica?

Vem de algum LMS. Pode ser um conjunto de repositórios, planilhas vindas de um
LMS ou de um Google Form ou mesmo um arquivo JSON exportado de um sistema de
coleta de respostas.

4. Conflito em import (já existe resposta) deve sobrescrever, pular ou perguntar?

Devemos primeiro tentar o merge e por padrão perguntar. Pode ter uma flag para
controlar o comportamento em caso de conflito, como `--overwrite` ou `--skip`.

5. Exibir resposta deve ter modo “raw” e modo formatado por padrão?

Sim. O modo formatado é mais amigável para leitura humana, enquanto o modo raw 
é útil para debugging e scripts. Também deve ter uma opção tipo `--output` para salvar
o output em um arquivo.


## Bloco H: Grading (Notas)

1. Ação principal é gerar notas de uma atividade inteira ou de um aluno?

De atividades inteiras. Pode ter flags pra filtar alunos específicos ou talvez grupos.

2. Você quer regrade completo após mudança de critério?
3. Nota manual pode sobrescrever auto-grade?
4. Precisa de lock de nota para evitar sobrescrita acidental?
5. Precisamos de trilha de auditoria (quem alterou, quando)?

## Bloco I: Reports

1. Relatórios alvo: por atividade, por aluno, por turma?

Por padrão os relatórios tem a seguinte glanularidade:

- Por turma (padrão): mostra notas + presença de todos os alunos em todas as atividades.
- Por atividade: mostra nota total + notas por questão de cada aluno na atividade.
- Por aluno: mostra nota total + notas por questão de cada atividade do aluno.
- Por aluno detalhado: mostra todas as respostas do aluno, notas e feedbacks. Pode filtrar por atividade ou fazer global.

2. Quais formatos são obrigatórios na v1?

Reports podem ser exibidos no terminal em format rich text ou exportados para
arquivos CSV, XLSX ou JSON. O formato padrão é CSV, mas o usuário pode escolher
o formato que preferir.

3. Relatório deve ser só arquivo ou também saída amigável no terminal?

Por padrão a saída é o terminal. Mas pode redirecionar para um arquivo usando a
flag `--output` ou algo similar.

4. Deve existir comando para listar relatórios existentes?

Não porque os relatórios não ficam necessariamente armazenados na estrutura do
chalk. Podemos criar uma pasta de relatórios apenas para o professor persistir
relatórios que queira guardar, mas fica fora do escopo do chalk.

5. Quer templates customizáveis de relatório já na v1?

Não. O formato do relatório pode ser customizado por flags para filtrar, ordenar
etc, mas não precisa de um sistema mais elaborado que isso.

## Bloco J: UX de CLI

1. Padrão deve ser não interativo com flags, ou interativo quando faltar argumento?

O padrão deve ser interativo, mas pode usar flags para fornecer respostas padrão 
como por exemplo `--yes/--no` ou ações específicas relevantes para cada comando.

2. Em CI, o comportamento deve ser estritamente não interativo?

Não vejo muito sentido de rodar em CI. Mas obviamente sim.

3. Você quer mensagens de erro curtas ou didáticas com sugestão de correção?

Idealmente as mensagens devem ser didáticas e incluir sugestões de correção.

4. Quer padrão de saída estável para scripts?

Isso deve ser ligado como opção. A saída padrão é rich text (não-estável), mas
deve ser possível gerar saídas em formatos estáveis como JSON, YAML ou CSV.

5. Quer códigos de saída bem definidos por tipo de erro?

Não precisa. Podemos usar `exit(1)` para todos erros. Chalk é usada por humanos
e não vejo muito sentido na interação com outros scripts, CI, etc.


## Bloco K: Compatibilidade e Migração

1. Você quer preservar comandos atuais mesmo que subótimos?

Não. Devemos refatorar para a estrutura definida neste documento.

2. Se renomearmos comandos, quer período de depreciação com aviso?

Não. O projeto ainda é beta e só tem um usuário. Pode quebrar a vontade.

3. Quer compatibilidade entre versões de formato de arquivo?

Só depois da V1.

4. Dados antigos devem ser migrados automaticamente?

Não. Talvez numa eventual migração da V1 para a V2.

5. Versão mínima do Python e estratégia de release já estão definidas?

Dada a existência do uv/uvx como método fácil de instalação, podemos ser 
agressivos com a versão do Python e usar recursos modernos. A release é: faça um alias
de `alias chalk='uvx chalk'` no `.bashrc` ou use `uvx chalk` diretamente.

Por enquanto vamos usar python 3.15 para brincar com  lazy imports.


## Bloco L: Extensibilidade

1. O sistema de plugins de correção entra já na v1?

Apenas um sistema básico baseado na execução de scripts externos. As considerações de
segurança ficam a cargo desse script.

2. Como usuário ativa plugin: configuração global, por atividade ou por questão?

Por atividade ou usando imports no script de correção ou via `chalk script <plugin_name>`

3. Plugin pode adicionar subcomandos próprios?

É possível. Idealmente plugins que extendem o comando poderiam registrar
comandos Typer em locais específicos do namespace do chalk.

4. Você quer comando para listar plugins instalados?

Talvez na V2. Podemos pensar em um sistema integrado de gerenciamento de plugins.

5. Falha de plugin deve interromper tudo ou degradar graciosamente?

Idealmente deve degradar graciosamente. Plugins ficam para V2+. Ainda precisamos
definir o escopo de atuação dos plugins, tipos de plugins, interfaces, etc.


## Bloco M: Documentação e Onboarding

1. Documentação deve ser focada em uso ou também em desenvolvimento?

O foco principal é no uso. Podemos incluir um guia de contribuição para
desenvolvedores e gerar a documentação usando docstrings e ferramentas como
Sphinx para facilitar o onboarding de novos desenvolvedores. Mas a expectativa
principal é que serei o único desenvolvedor fora talvez contribuições muito
esporádicas.

2. Quer guias passo a passo para casos de uso comuns?

Sim, alguns no README e outros mais detalhados na wiki, especialmente se a IA
conseguir gerar exemplos automaticamente.

3. Você quer exemplos de configuração e estrutura de arquivos?

Sim, alguns no README e outros mais detalhados na wiki, especialmente se a IA
conseguir gerar exemplos automaticamente. Também devemos ter algumas turmas 
de exemplos para testes automatizados e de integração.

4. Quer um guia de contribuição para desenvolvedores?

Curto e grosso no README.


## Bloco N: Backlog e recursos futuros

Não está ordenado por prioridade:

* Integração com LMS.
* Suporte a rubricas.
* Suporte a grupos.
* Suporte a atividades com múltiplas partes ou entregas parciais.
* Suporte a atividades complexas como projetos ou trabalhos em grupo.
* Suporte a plugins de correção automática.
* Detectar plágio.
* Suporte a feedback qualitativo.
* Mecanismos de envio de e-mails de feedback para os alunos.
