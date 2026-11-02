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

**H1. Corrigir questões mdq pelo gabarito.** Como professor, quero que
múltipla escolha, múltipla seleção, verdadeiro/falso, numérica e resposta
curta sejam corrigidas pelo gabarito do arquivo mdq, sem escrever script.
Já existe (`chalk/question/mdq.py`).


## Manual

**H2. Corrigir à mão com atalhos.** Como professor, quero passar pelas
respostas de uma questão, uma por aluno, e dar nota e feedback com poucas
teclas, podendo voltar e desfazer.

**H3. Agrupar respostas iguais.** Como professor, quero corrigir de uma vez
todas as respostas idênticas (ou equivalentes depois de normalizar
espaços e caixa), para não repetir o mesmo trabalho 40 vezes.

**H4. Revisar a sugestão de um corretor.** Como professor, quero que um
corretor automático sugira nota e feedback e eu só confirme ou ajuste,
para questões em que ele acerta quase sempre mas não sempre.


## Dado

**H5. Corrigir com script próprio.** Como professor, quero corrigir uma
questão com um script meu que recebe a resposta do aluno como texto e
devolve nota e feedback, para critérios que não cabem em gabarito nem em
teste unitário (relações entre partes da resposta, formato, um segredo que
estava no enunciado da turma ou do aluno).

**H6. Corrigir regex.** Como professor, quero que o aluno entregue uma
regex e o chalk a teste contra exemplos que devem e que não devem casar,
listados no `conf.yaml`, com nota proporcional aos acertos. Uma regex que
demora demais num exemplo erra aquele exemplo e não trava a correção.

**H7. Corrigir código sem executar.** Como professor, quero corrigir um
trecho de código pela estrutura (construções exigidas ou proibidas), sem
executá-lo, com os critérios listados no `conf.yaml`.


## Código

**H8. Corrigir com testes unitários.** Como professor, quero corrigir o
projeto do aluno rodando os testes do meu template (em Python com uv, Elm,
JavaScript ou outra linguagem com test runner), com nota = testes aprovados
/ total, sem montar o sandbox a cada prova. Os testes podem ser ocultos, e
o aluno não consegue alterá-los, adicionar dependências nem forjar a nota
com um `print`.

**H9. Compilar antes de testar.** Como professor, quero corrigir Rust, C e
outras linguagens compiladas, em que a resposta precisa compilar antes dos
testes. Erro de compilação aparece como tal, com a saída do compilador, e
eu decido se vale zero ou vai para correção manual.

**H10. Comparar entrada e saída.** Como professor, quero corrigir um
programa comparando a saída com a esperada para várias entradas, no estilo
juiz online, para exercícios sem framework de teste.

**H11. Testar com rede simulada.** Como professor, quero que os testes
falem com servidores que eu subo (HTTP, banco), sem acesso à internet.


## Comuns a todas as classes

**H12. Ensaiar o corretor.** Como professor, quero rodar o corretor contra
a minha resposta de referência e contra respostas erradas que eu escrevo,
antes de corrigir a turma, para achar erro no corretor numa rodada e não em
80 notas.

**H13. Recorrigir parte da turma.** Como professor, quero recorrigir só um
aluno ou só uma questão, depois de consertar o corretor ou de um pedido de
revisão, sem refazer o resto.

**H14. Ver o resultado de cada aluno.** Como professor, quero ver, para
cada aluno, a nota, o motivo de uma nota zero (timeout, erro, não compilou,
resposta vazia), o feedback que vai para o aluno e, separado, o log
interno do corretor que só eu vejo.


## Consequências para o desenho

- O sandbox é exigência da classe **código**, não do autograder em geral.
  Script que só lê a resposta (H5) roda sem sandbox, com timeout e limite
  de memória; script que executa a resposta roda no sandbox.
- Quem declara a classe é a questão no `conf.yaml`, não uma flag na linha
  de comando. Padrão seguro: script sem declaração roda no sandbox.
- H6 e H7 viram perfis embutidos parametrizados no `conf.yaml` (`regex` e
  `ast`), como os perfis da classe código. O script livre (H5) cobre o
  resto.
- H3 e H4 ligam a correção manual à automática; hoje são caminhos
  separados.
