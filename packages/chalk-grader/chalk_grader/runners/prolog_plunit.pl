/*  Trusted side of the prolog-plunit profile.

    swipl -q -f none prolog_plunit.pl -- check (on|off) ANSWER
        Read the student's program without running it. With `on`, every
        clause body and directive must pass safe_goal/1 of library(sandbox).
        Prints a line "chalk-guard: ..." for each refusal and exits with 1
        when the program is refused or does not read.

    swipl -q -f none prolog_plunit.pl -- list TESTFILE...
        Print "Unit<TAB>Test" for each test of the (trusted) test files.

    swipl -q -f none prolog_plunit.pl -- test ANSWER UNIT TEST TESTFILE...
        Load the program and the tests and run one test. The runner sends a
        secret on stdin; the verdict is the line "chalk-plunit SECRET pass"
        or "... fail", which only this code prints.
*/

:- module(chalk_plunit, []).
:- use_module(library(sandbox)).
:- use_module(library(lists)).
:- use_module(library(readutil)).

:- initialization(main, main).

:- dynamic deferred/2, body/2, secret/1.

main :-
    current_prolog_flag(argv, Argv),
    (   Argv = [First|_], memberchk(First, [check, list, test])
    ->  Args = Argv
    ;   Argv = [_|Args]
    ),
    (   run(Args) -> true ; halt(2) ).

run([check, Safe, Answer]) :- !, check(Safe, Answer).
run([list|Files]) :- !, list(Files).
run([test, Answer, Unit, Test|Files]) :- !, test(Answer, Unit, Test, Files).

%
% check
%
check(Safe, File) :-
    Mod = chalk_student,
    flag(chalk_refused, _, 0),
    flag(chalk_errors, _, 0),
    setup_call_cleanup(open(File, read, S, [encoding(utf8)]),
                       read_program(S, Safe, Mod),
                       close(S)),
    (   Safe == on
    ->  forall(body(L, B), ignore(safe(Mod:B, L))),
        forall(deferred(L, G), ignore(safe(Mod:G, L)))
    ;   true
    ),
    flag(chalk_refused, Refused, Refused),
    flag(chalk_errors, Errors, Errors),
    (   Refused > 0
    ->  format("The program uses code that is not allowed in this exercise.~n")
    ;   true
    ),
    (   Refused + Errors =:= 0 -> true ; halt(1) ).

read_program(S, Safe, Mod) :-
    repeat,
    catch(read_term(S, T, [module(Mod), term_position(P), syntax_errors(error)]),
          E, syntax_error(E, T)),
    (   T == end_of_file
    ->  !
    ;   T == '$error'
    ->  fail
    ;   stream_position_data(line_count, P, L),
        term(T, L, Safe, Mod),
        fail
    ).

syntax_error(E, '$error') :-
    E = error(syntax_error(_), _),
    !,
    print_message(error, E),
    flag(chalk_errors, N, N+1).
syntax_error(E, _) :-
    throw(E).

term((:- D), L, Safe, Mod) :- !, directive(D, L, Safe, Mod).
term((?- D), L, Safe, Mod) :- !, directive(D, L, Safe, Mod).
term(T, L, Safe, Mod) :-
    (   catch(expand_term(T, X), E, (failed(L, Safe, E), fail))
    ->  true
    ;   X = []
    ),
    (   is_list(X) -> Cs = X ; Cs = [X] ),
    forall(member(C, Cs), clause_term(C, L, Safe, Mod)).

clause_term((:- D), L, Safe, Mod) :- !, directive(D, L, Safe, Mod).
clause_term(C0, L, Safe, Mod) :-
    (   C0 = (H0 :- B0) -> true ; H0 = C0, B0 = true ),
    (   nonvar(H0), H0 = Q:H1
    ->  (   memberchk(Q, [user, Mod])
        ->  true
        ;   failed(L, Safe, defines_in_module(Q)), fail
        )
    ;   H1 = H0
    ),
    (   var(H1)
    ->  failed(L, Safe, instantiation_error)
    ;   (   var(B0) -> B = call(B0) ; B = B0 ),
        (   catch(assertz(Mod:(H1 :- B)), E, (failed(L, Safe, E), fail))
        ->  assertz(body(L, B))
        ;   true
        )
    ),
    !.
clause_term(_, _, _, _).

%  Directives that change how the rest of the file is read run now.
eager(op(_, _, _)).
eager(use_module(_)).
eager(use_module(_, _)).
eager(ensure_loaded(_)).
eager(set_prolog_flag(_, _)).
eager(module(_, _)).

%  Declarations about the program's own predicates need no check.
declaration(dynamic(_)).
declaration(discontiguous(_)).
declaration(multifile(_)).
declaration(table(_)).
declaration(non_terminal(_)).

directive(D, _, _, Mod) :-
    nonvar(D),
    declaration(D),
    !,
    catch(call(Mod:D), E, (print_message(error, E), flag(chalk_errors, N, N+1))).
directive(D, L, Safe, Mod) :-
    nonvar(D),
    eager(D),
    !,
    (   Safe == on, \+ safe(user:D, L)
    ->  true
    ;   catch(call(Mod:D), E, (print_message(error, E), flag(chalk_errors, N, N+1)))
    ).
directive(D, L, _, _) :-
    (   nonvar(D), ( D = initialization(G) ; D = initialization(G, _) ), nonvar(G)
    ->  %  The wrapper reads the source location; what runs is the goal.
        assertz(deferred(L, G))
    ;   assertz(deferred(L, D))
    ).

%  Succeeds when the goal is safe; otherwise reports the refusal.
safe(Goal, L) :-
    catch(( safe_goal(Goal) -> Ok = true ; Ok = false ), E, Ok = error(E)),
    (   Ok == true
    ->  true
    ;   Ok = error(E)
    ->  refuse(L, E), fail
    ;   refuse(L, not_safe), fail
    ).

failed(L, on, E) :- !, refuse(L, E).
failed(_, off, E) :-
    print_message(error, E),
    flag(chalk_errors, N, N+1).

refuse(L, E) :-
    flag(chalk_refused, N, N+1),
    (   E = error(permission_error(call, sandboxed, G), _),
        callable(G)
    ->  functor(G, Name, Arity),
        format("chalk-guard: line ~w: calls ~q/~w, which is not allowed~n", [L, Name, Arity])
    ;   format("chalk-guard: line ~w: ~W~n", [L, E, [quoted(true), max_depth(6)]])
    ).

%
% list
%
list(Files) :-
    use_module(library(plunit)),
    forall(member(F, Files), load_files(user:F, [silent(true)])),
    forall(plunit:current_test(U, T, _, _, _), format("~w\t~w~n", [U, T])).

%
% test
%
test(Answer, Unit, Test, Files) :-
    read_line_to_string(user_input, Secret),
    assertz(secret(Secret)),
    use_module(library(plunit)),
    load_files(user:Answer, [silent(true)]),
    forall(member(F, Files), load_files(user:F, [silent(true)])),
    (   catch(plunit:run_tests(Unit:Test), _, fail)
    ->  Verdict = pass
    ;   Verdict = fail
    ),
    secret(S),
    format("~nchalk-plunit ~w ~w~n", [S, Verdict]),
    halt(0).
