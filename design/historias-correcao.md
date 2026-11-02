# Histórias de usuário: correção

Estado em 2026-11-02. Rascunho. Base para `design/sandbox.md`, que foi
escrito antes destas histórias e assume só o cenário de testes unitários.

Ator: o professor, que corrige na própria máquina Linux.


## O eixo que importa

O que decide se a correção precisa de sandbox não é existir um script, e sim
o que acontece com a resposta do aluno:

| Classe | A resposta do aluno é... | Quem corrige | Sandbox |
| --- | --- | --- | --- |
| **Objetiva** | escolha, número, texto curto | o mdq, sem script | não |
| **Manual** | texto livre, desenho, código lido | o professor | não |
| **Dado** | string, regex, trecho de código analisado sem executar | script do professor | não, mas com limites |
| **Código** | programa executado | testes do professor | sim |

Na classe **dado**, o código arbitrário é o do professor e a resposta só é
lida. Ainda assim há riscos que não pedem sandbox mas pedem limites: uma
regex do aluno com backtracking catastrófico trava o script; uma resposta
de 500 MB estoura a memória. Timeout e limite de memória valem para todas
as classes que rodam script.


## Objetiva

**H1. Corrigir questões mdq automaticamente.** Como professor, quero que
múltipla escolha, múltipla seleção, verdadeiro/falso, numérica e resposta
curta sejam corrigidas pelo gabarito do arquivo mdq, sem escrever script.
Já existe (`chalk/question/mdq.py`).

**H2. Misturar objetiva e manual no mesmo quiz.** Como professor, quero que
um quiz tenha questões mdq corrigidas sozinhas e questões abertas que eu
corrijo à mão, com uma nota única no fim. Já existe; a questão sem arquivo
mdq é aberta.


## Manual

**H3. Corrigir à mão com atalhos.** Como professor, quero passar pelas
respostas de uma questão, uma por aluno, e dar nota e feedback com poucas
teclas, podendo voltar e desfazer.

**H4. Agrupar respostas iguais.** Como professor, quero corrigir de uma vez
todas as respostas idênticas (ou equivalentes depois de normalizar
espaços e caixa), para não repetir o mesmo trabalho 40 vezes.

**H5. Pré-correção por script, revisão manual.** Como professor, quero que
um script sugira nota e feedback e eu só confirme ou ajuste, para questões
em que a correção automática acerta quase sempre mas não sempre.


## Dado

**H6. Validar uma resposta com script.** Como professor, quero corrigir uma
questão com um script meu que recebe a resposta do aluno como texto e
devolve nota e feedback, para critérios que não cabem em teste unitário ou
em gabarito (relações entre partes da resposta, formato, equivalência).

**H7. Exercício de regex.** Como professor, quero que o aluno entregue uma
regex e meu script a teste contra exemplos que devem casar e que não devem
casar, com nota proporcional aos acertos. Uma regex que demora demais em
um exemplo conta como erro naquele exemplo, não trava a correção.

**H8. Segredo vindo do enunciado.** Como professor, quero corrigir uma
resposta verificando se ela contém um segredo que estava no enunciado, seja
o mesmo para a turma ou um por aluno (derivado da matrícula, por exemplo).
O chalk não tem suporte próprio a segredos: é um caso de uso da H6, e o
script do professor gera ou recalcula o segredo a partir de
`CHALK_STUDENT`.

**H9. Análise estática de código.** Como professor, quero corrigir um
trecho de código sem executá-lo (parse, AST, lint, presença ou ausência de
construções), quando executar não é o objetivo ou não é seguro.

**H10. Reaproveitar corretores.** Como professor, quero usar de novo em
outra prova um corretor que já escrevi (regex, segredo, AST), mudando só os
parâmetros no `conf.yaml`.


## Código

**H11. Testes unitários em Python.** Como professor, quero corrigir um
projeto Python do aluno rodando os testes do meu template (projeto uv com
lockfile), com nota = testes aprovados / total, sem me preocupar em montar
o sandbox a cada prova.

**H12. Outras linguagens interpretadas.** Como H11, para Elm, JavaScript e
outras linguagens com test runner, sem escrever código novo no chalk.

**H13. Linguagens compiladas.** Como H11, para Rust e C, em que a resposta
precisa compilar antes dos testes. Erro de compilação aparece como tal, com
a saída do compilador, e eu decido se vale zero ou vai para correção manual.

**H14. Entrada e saída.** Como professor, quero corrigir um programa
comparando a saída com a esperada para várias entradas, no estilo juiz
online, para exercícios sem framework de teste.

**H15. Testes com rede simulada.** Como professor, quero que os testes
falem com servidores que eu subo (HTTP, banco), sem acesso à internet.

**H16. Testes ocultos.** Como professor, quero corrigir com testes que o
aluno não viu, e que o aluno não consiga alterar nem burlar com um `print`.


## Comuns a todas as classes

**H17. Ensaiar antes de corrigir a turma.** Como professor, quero rodar o
corretor contra a minha resposta de referência (e contra respostas erradas
que eu escrevo) antes de corrigir a turma, para achar erro no corretor numa
rodada e não em 80 notas.

**H18. Recorrigir um aluno ou uma questão.** Como professor, quero
recorrigir só um aluno ou só uma questão, depois de corrigir o corretor ou
de um pedido de revisão, sem refazer o resto.

**H19. Ver o que aconteceu.** Como professor, quero ver, para cada aluno, a
saída do corretor, o feedback e o motivo de uma nota zero (timeout, erro,
não compilou, resposta vazia), para responder a pedidos de revisão.

**H20. Feedback para o aluno.** Como professor, quero que o feedback do
corretor seja legível pelo aluno (quais exemplos falharam, quais testes não
passaram), separado do log interno que só eu vejo.


## Consequências para o desenho

- O sandbox é exigência da classe **código**, não do autograder em geral.
  O perfil `script` do `design/sandbox.md` se divide em dois: script que só
  lê a resposta (sem sandbox, com timeout e limite de memória) e script que
  executa a resposta (com sandbox).
- Quem declara a classe é a questão no `conf.yaml`, não uma flag na linha
  de comando. Padrão seguro: script sem declaração roda no sandbox.
- H7 e H9 viram corretores embutidos parametrizáveis (H10), como os perfis
  da classe código: `regex` e `ast`. O script livre continua para o resto,
  incluindo H8.
- H4 e H5 ligam a correção manual à automática; hoje são caminhos separados.
