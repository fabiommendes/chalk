"""
`chalk codehood autograde`: grader discovery, which submissions are graded,
what is written back, and the safety checks before grading a class.

The server is tests/fake_codehood.py. The code is graded for real, with the
prolog-plunit profile, so these tests need swipl.

Interface the tests assume (module `chalk/codehood_autograde.py`):

    find_graders(root: Path) -> dict[str, FoundGrader]
        # keyed by the question slug (frontmatter `id`)
    FoundGrader(slug: str, folder: Path, question: Path, conf: models.Autograder)
        # conf.profile is filled from the question's `highlight` when
        # grader.yaml has no `profile`
    GraderLayoutError(ValueError)

The command is `chalk codehood autograde` in the current directory, which
holds `codehood.toml` ([course] discipline/instructor/edition, [server] url).
"""

import re
import shutil
from fractions import Fraction
from pathlib import Path

import mdq
import pytest
from typer.testing import CliRunner

from chalk.cli import app
from tests.fake_codehood import FakeCodehood

needs_swipl = pytest.mark.skipif(not shutil.which("swipl"), reason="swipl is needed")


def find_graders(root: Path):
    """
    Imported late, so a missing module fails these tests and not the whole file.
    """
    from chalk.codehood_autograde import find_graders as find

    return find(root)


def layout_error() -> type[Exception]:
    from chalk.codehood_autograde import GraderLayoutError

    return GraderLayoutError


SLUG = "prolog-fatorial-com-is"

TESTS = """\
:- begin_tests(fatorial).
test(fat5) :- fat(5, F), F == 120.
test(inverso) :- \\+ catch((fat(X, 120), X == 5), _, fail).
:- end_tests(fatorial).
"""
CORRECT = "fat(0,1).\nfat(N,F):- N > 0, N1 is N-1, fat(N1,F1), F is N*F1.\n"
WRONG = "fat(_, 1).\n"
NOT_LOADING = "fat(0,1\nfat(N,F) :- .\n"
HALTS = CORRECT + ":- initialization(halt(0)).\n"
LOOPS_ON_LOAD = "loop :- loop.\n:- loop.\n" + CORRECT

GRADER_YAML = """\
answer: answer.pl
sandbox: none
timeout: 20
vars:
  test_timeout: "1"
"""


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def question_text(slug: str, highlight: str | None = "prolog") -> str:
    """
    A question file that mdq accepts. `highlight` is only valid in a code
    question, and a question needs a body tag (`[essay]`) to have a stem.
    """
    front = f"id: {slug}\n" + (f"content: code\nhighlight: {highlight}\n" if highlight else "")
    return f"---\n{front}---\n\nEscreva fat/2.\n\n[essay]\n"


def add_question(
    root: Path,
    slug: str = SLUG,
    *,
    where: str = "logico/aritmetica/fatorial-com-is",
    highlight: str | None = "prolog",
    grader_yaml: str = GRADER_YAML,
    solution: str | None = CORRECT,
    tests: str = TESTS,
) -> Path:
    """
    questions/<where>.md and graders/<where>/ with the layout of the design.
    """
    path = root / "questions" / f"{where}.md"
    write(path, question_text(slug, highlight))
    loaded = mdq.load(path, kind="question", ids="fill")
    assert loaded.document is not None, loaded.diagnostics
    folder = root / "graders" / where
    write(folder / "grader.yaml", grader_yaml)
    write(folder / "template" / "tests.pl", tests)
    if solution is not None:
        write(folder / "solution" / "answer.pl", solution)
    return folder


@pytest.fixture
def course(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "curso"
    root.mkdir()
    write(
        root / "codehood.toml",
        '[course]\ndiscipline = "paradigmas"\ninstructor = "ada"\nedition = "2026-1"\n\n'
        '[server]\nurl = "http://127.0.0.1:1"\n',
    )
    write(root / "chalk.toml", '[chalk]\nclassroom = "turma"\nteacher = "Professor"\n')
    monkeypatch.chdir(root)
    monkeypatch.setenv("CHALK_DEBUG", "1")
    monkeypatch.setenv("COLUMNS", "200")
    monkeypatch.delenv("CODEHOOD_BOT_KEY", raising=False)
    return root


@pytest.fixture
def server() -> FakeCodehood:
    with FakeCodehood() as fake:
        yield fake


def autograde(server: FakeCodehood, *args: str, key: str | None = None):
    """
    Run the command against the fake server with the bot key in the
    environment.
    """
    env = {"CODEHOOD_BOT_KEY": key or server.token}
    return CliRunner().invoke(
        app, ["codehood", "autograde", "--server", server.url, *args], env=env
    )


def feedback_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip()]


#
# Discovery
#
class TestFindGraders:
    def test_pairs_question_and_grader_and_uses_the_frontmatter_id(self, course) -> None:
        folder = add_question(course, "slug-differs-from-file", where="logico/a/b")
        found = find_graders(course)
        assert list(found) == ["slug-differs-from-file"]
        assert found["slug-differs-from-file"].folder == folder
        assert found["slug-differs-from-file"].question == course / "questions/logico/a/b.md"

    def test_several_graders_at_different_depths(self, course) -> None:
        add_question(course, "q-top", where="top")
        add_question(course, "q-deep", where="a/b/c/deep")
        assert set(find_graders(course)) == {"q-top", "q-deep"}

    def test_question_without_grader_is_not_an_error(self, course) -> None:
        add_question(course)
        write(course / "questions" / "manual.md", "---\nid: manual\n---\n\nTexto.\n\n[essay]\n")
        assert set(find_graders(course)) == {SLUG}

    def test_grader_without_question_is_an_error(self, course) -> None:
        add_question(course)
        orphan = add_question(course, "ghost", where="logico/ghost")
        (course / "questions/logico/ghost.md").unlink()
        with pytest.raises(layout_error(), match="ghost"):
            find_graders(course)
        assert orphan.exists()

    def test_profile_defaults_from_highlight(self, course) -> None:
        add_question(course, highlight="prolog")
        assert find_graders(course)[SLUG].conf.profile == "prolog-plunit"

    def test_explicit_profile_wins_over_highlight(self, course) -> None:
        add_question(course, highlight="prolog", grader_yaml=GRADER_YAML + "profile: stdio\n")
        assert find_graders(course)[SLUG].conf.profile == "stdio"

    def test_grader_yaml_is_an_autograder_block(self, course) -> None:
        add_question(course)
        conf = find_graders(course)[SLUG].conf
        assert conf.answer == "answer.pl"
        assert conf.sandbox == "none"
        assert conf.timeout == 20
        assert conf.vars == {"test_timeout": "1"}

    def test_no_profile_and_no_known_highlight_is_an_error(self, course) -> None:
        add_question(course, highlight=None)
        with pytest.raises(layout_error(), match=SLUG):
            find_graders(course)


#
# Selection of submissions
#
@needs_swipl
class TestSelection:
    def test_grades_only_the_submissions_the_bot_owns(self, course, server) -> None:
        add_question(course)
        server.add_exam("p1", [SLUG])
        P, G, M, W = "PENDING_GRADE", "GRADED_AUTOMATICALLY", "GRADED_MANUALLY", "WILL_NOT_GRADE"
        (ana,) = server.add_attempt("ana", "p1", [(SLUG, CORRECT, P)])
        (auto,) = server.add_attempt("auto", "p1", [(SLUG, CORRECT, G)])
        (manual,) = server.add_attempt("manual", "p1", [(SLUG, CORRECT, M)])
        (skip,) = server.add_attempt("skip", "p1", [(SLUG, CORRECT, W)])

        result = autograde(server, "p1")

        assert result.exit_code == 0, result.output
        assert {sid for sid, _ in server.puts} == {ana, auto}
        assert server.fraction(ana) == 1
        assert manual not in server.feedback and skip not in server.feedback

    def test_only_the_newest_submission_of_an_attempt_is_graded(self, course, server) -> None:
        add_question(course)
        server.add_exam("p1", [SLUG])
        old, new = server.add_attempt(
            "bia", "p1", [(SLUG, CORRECT, "PENDING_GRADE"), (SLUG, WRONG, "PENDING_GRADE")]
        )
        autograde(server, "p1")
        assert [sid for sid, _ in server.puts] == [new]
        assert server.fraction(new) == Fraction(1, 2)
        assert old not in server.feedback

    def test_attempts_still_accepting_submissions_are_left_alone(self, course, server) -> None:
        add_question(course)
        server.add_exam("p1", [SLUG])
        (open_,) = server.add_attempt(
            "caio", "p1", [(SLUG, CORRECT, "PENDING_GRADE")], closed=False
        )
        (closed,) = server.add_attempt("dani", "p1", [(SLUG, CORRECT, "PENDING_GRADE")])
        autograde(server, "p1")
        assert [sid for sid, _ in server.puts] == [closed]
        assert open_ not in server.feedback

    def test_human_feedback_is_never_overwritten_or_duplicated(self, course, server) -> None:
        add_question(course)
        server.add_exam("p1", [SLUG])
        (human,) = server.add_attempt("eva", "p1", [(SLUG, WRONG, "PENDING_GRADE")])
        server.add_feedback(human, "ada", "1", grader="ada")
        (plain,) = server.add_attempt("fabi", "p1", [(SLUG, WRONG, "PENDING_GRADE")])

        result = autograde(server, "p1")

        assert result.exit_code == 0, result.output
        assert [sid for sid, _ in server.puts] == [plain]
        assert set(server.feedback[human]) == {"ada"}

    def test_human_feedback_on_an_older_submission_does_not_block_the_newest(
        self, course, server
    ) -> None:
        add_question(course)
        server.add_exam("p1", [SLUG])
        old, new = server.add_attempt(
            "gabi", "p1", [(SLUG, WRONG, "PENDING_GRADE"), (SLUG, CORRECT, "PENDING_GRADE")]
        )
        server.add_feedback(old, "ada", "0", grader="ada")
        autograde(server, "p1")
        assert [sid for sid, _ in server.puts] == [new]

    def test_questions_without_grader_are_skipped_without_error(self, course, server) -> None:
        add_question(course)
        server.add_exam("p1", [SLUG, "manual-question"])
        (manual,) = server.add_attempt(
            "hugo", "p1", [("manual-question", "texto", "PENDING_GRADE")]
        )
        (code,) = server.add_attempt("iris", "p1", [(SLUG, CORRECT, "PENDING_GRADE")])
        result = autograde(server, "p1")
        assert result.exit_code == 0, result.output
        assert [sid for sid, _ in server.puts] == [code]
        assert manual not in server.feedback

    def test_question_option_restricts_to_one_question(self, course, server) -> None:
        add_question(course)
        add_question(course, "other-q", where="logico/outra")
        server.add_exam("p1", [SLUG, "other-q"])
        (a, b) = server.add_attempt(
            "joao", "p1", [(SLUG, CORRECT, "PENDING_GRADE"), ("other-q", CORRECT, "PENDING_GRADE")]
        )
        autograde(server, "p1/other-q")
        assert [sid for sid, _ in server.puts] == [b]
        assert a not in server.feedback

    def test_other_exams_are_not_touched(self, course, server) -> None:
        add_question(course)
        server.add_exam("p1", [SLUG])
        server.add_exam("p2", [SLUG])
        (p1,) = server.add_attempt("kai", "p1", [(SLUG, CORRECT, "PENDING_GRADE")])
        (p2,) = server.add_attempt("kai", "p2", [(SLUG, CORRECT, "PENDING_GRADE")])
        autograde(server, "p1")
        assert [sid for sid, _ in server.puts] == [p1]
        assert p2 not in server.feedback


#
# What is written
#
@needs_swipl
class TestWriting:
    def grade_one(self, course, server, answer: str, **question):
        add_question(course, **question)
        server.add_exam("p1", [SLUG])
        (sid,) = server.add_attempt("lia", "p1", [(SLUG, answer, "PENDING_GRADE")])
        result = autograde(server, "p1")
        assert result.exit_code == 0, result.output
        return sid, server.written(sid)

    def test_score_is_a_fraction_and_feedback_marks_each_test(self, course, server) -> None:
        sid, written = self.grade_one(course, server, WRONG)
        assert Fraction(written["score"]) == Fraction(1, 2)
        lines = feedback_lines(written["feedback"])
        fat5 = next(line for line in lines if "fat5" in line)
        inverso = next(line for line in lines if "inverso" in line)
        assert "✗" in fat5 and "✓" not in fat5
        assert "✓" in inverso and "✗" not in inverso
        assert written["bot"] == "runner" and written["grader"] is None

    def test_full_score_marks_every_test_as_passed(self, course, server) -> None:
        sid, written = self.grade_one(course, server, CORRECT)
        assert Fraction(written["score"]) == 1
        assert "✓" in written["feedback"] and "✗" not in written["feedback"]
        assert not written["notes"]

    def test_ref_is_a_slug_and_the_same_for_every_submission(self, course, server) -> None:
        add_question(course)
        server.add_exam("p1", [SLUG])
        server.add_attempt("ana", "p1", [(SLUG, CORRECT, "PENDING_GRADE")])
        server.add_attempt("bia", "p1", [(SLUG, WRONG, "PENDING_GRADE")])
        autograde(server, "p1")
        refs = {body["ref"] for _, body in server.puts}
        assert len(refs) == 1
        assert re.fullmatch(r"[a-z0-9][a-z0-9-]{0,39}", refs.pop())

    def test_no_grader_field_is_sent(self, course, server) -> None:
        self.grade_one(course, server, CORRECT)
        assert all(not body.get("grader") for _, body in server.puts)

    def test_rerun_updates_the_same_pass(self, course, server) -> None:
        add_question(course)
        server.add_exam("p1", [SLUG])
        (sid,) = server.add_attempt("mia", "p1", [(SLUG, WRONG, "PENDING_GRADE")])
        autograde(server, "p1")
        first = server.written(sid)["ref"]
        assert server.fraction(sid) == Fraction(1, 2)

        # With only fat5 in the tests, the same answer now scores 0.
        only_fat5 = "\n".join(line for line in TESTS.splitlines() if "inverso" not in line)
        add_question(course, tests=only_fat5 + "\n")
        autograde(server, "p1")

        assert len(server.puts) == 2
        assert list(server.feedback[sid]) == [first]
        assert server.fraction(sid) == 0

    def test_build_error_writes_zero_with_the_message(self, course, server) -> None:
        _, written = self.grade_one(course, server, NOT_LOADING)
        assert Fraction(written["score"]) == 0
        assert written["feedback"]

    def test_refused_code_writes_zero_and_the_refusal_goes_to_the_notes(
        self, course, server
    ) -> None:
        _, written = self.grade_one(course, server, HALTS)
        assert Fraction(written["score"]) == 0
        assert "halt" in written["notes"] or "initialization" in written["notes"]
        assert written["notes"] not in written["feedback"]

    def test_all_or_nothing_writes_zero_for_a_half_right_answer(self, course, server) -> None:
        yaml = GRADER_YAML + "scoring: all-or-nothing\n"
        _, written = self.grade_one(course, server, WRONG, grader_yaml=yaml)
        assert Fraction(written["score"]) == 0
        lines = feedback_lines(written["feedback"])
        assert "✗" in next(line for line in lines if "fat5" in line)
        assert "✓" in next(line for line in lines if "inverso" in line)

    def test_failing_scoring_script_writes_nothing(self, course, server) -> None:
        yaml = GRADER_YAML + "scoring: script\nscoring_script: score.py\n"
        add_question(course, grader_yaml=yaml)
        write(course / "graders/logico/aritmetica/fatorial-com-is/score.py", "raise SystemExit(2)")
        server.add_exam("p1", [SLUG])
        (sid,) = server.add_attempt("lia", "p1", [(SLUG, WRONG, "PENDING_GRADE")])
        autograde(server, "p1")
        assert sid not in server.feedback

    def test_timeout_writes_zero(self, course, server) -> None:
        yaml = GRADER_YAML.replace("timeout: 20", "timeout: 3")
        _, written = self.grade_one(course, server, LOOPS_ON_LOAD, grader_yaml=yaml)
        assert Fraction(written["score"]) == 0
        assert written["feedback"]


@needs_swipl
class TestDryRun:
    def test_nothing_is_written(self, course, server) -> None:
        add_question(course)
        server.add_exam("p1", [SLUG])
        server.add_attempt("ana", "p1", [(SLUG, CORRECT, "PENDING_GRADE")])
        server.add_attempt("bia", "p1", [(SLUG, WRONG, "PENDING_GRADE")])
        result = autograde(server, "p1", "--dry-run")
        assert result.exit_code == 0, result.output
        assert server.puts == []
        assert server.feedback == {}
        assert {m for m, *_ in server.requests} == {"GET"}

    def test_it_still_reads_the_submissions(self, course, server) -> None:
        add_question(course)
        server.add_exam("p1", [SLUG])
        server.add_attempt("ana", "p1", [(SLUG, CORRECT, "PENDING_GRADE")])
        autograde(server, "p1", "--dry-run")
        assert any("/submission" in path for _, path, _ in server.requests)


#
# Errors
#
@needs_swipl
class TestSafetyChecks:
    def test_reference_solution_without_full_score_aborts_the_question(
        self, course, server
    ) -> None:
        add_question(course, solution=WRONG)
        add_question(course, "good-q", where="logico/boa")
        server.add_exam("p1", [SLUG, "good-q"])
        (bad, good) = server.add_attempt(
            "ana", "p1", [(SLUG, CORRECT, "PENDING_GRADE"), ("good-q", CORRECT, "PENDING_GRADE")]
        )
        result = autograde(server, "p1")
        assert [sid for sid, _ in server.puts] == [good]
        assert bad not in server.feedback
        assert SLUG in result.output

    def test_reference_solution_that_does_not_load_aborts_the_question(
        self, course, server
    ) -> None:
        add_question(course, solution=NOT_LOADING)
        server.add_exam("p1", [SLUG])
        server.add_attempt("ana", "p1", [(SLUG, CORRECT, "PENDING_GRADE")])
        result = autograde(server, "p1")
        assert server.puts == []
        assert SLUG in result.output

    def test_infrastructure_error_writes_nothing_and_is_reported(self, course, server) -> None:
        add_question(course, grader_yaml=GRADER_YAML + "profile: no-such-profile\n")
        add_question(course, "good-q", where="logico/boa")
        server.add_exam("p1", [SLUG, "good-q"])
        (bad, good) = server.add_attempt(
            "ana", "p1", [(SLUG, CORRECT, "PENDING_GRADE"), ("good-q", CORRECT, "PENDING_GRADE")]
        )
        result = autograde(server, "p1")
        assert [sid for sid, _ in server.puts] == [good]
        assert bad not in server.feedback
        assert "no-such-profile" in result.output


#
# Server and key
#
@needs_swipl
class TestServerAndKey:
    def prepare(self, course, server) -> str:
        add_question(course)
        server.add_exam("p1", [SLUG])
        (sid,) = server.add_attempt("ana", "p1", [(SLUG, CORRECT, "PENDING_GRADE")])
        return sid

    def test_key_from_the_environment(self, course, server) -> None:
        sid = self.prepare(course, server)
        assert autograde(server, "p1").exit_code == 0
        assert server.fraction(sid) == 1

    def test_key_from_a_file_with_a_trailing_newline(self, course, server, tmp_path) -> None:
        sid = self.prepare(course, server)
        key = write(tmp_path / "bot.key", server.token + "\n")
        result = CliRunner().invoke(
            app,
            [
                "codehood",
                "autograde",
                "--server",
                server.url,
                "--key-file",
                str(key),
                "p1",
            ],
        )
        assert result.exit_code == 0, result.output
        assert server.fraction(sid) == 1

    def test_server_url_comes_from_codehood_toml(self, course, server) -> None:
        sid = self.prepare(course, server)
        text = (course / "codehood.toml").read_text().replace("http://127.0.0.1:1", server.url)
        write(course / "codehood.toml", text)
        result = CliRunner().invoke(
            app,
            ["codehood", "autograde", "p1"],
            env={"CODEHOOD_BOT_KEY": server.token},
        )
        assert result.exit_code == 0, result.output
        assert server.fraction(sid) == 1

    def test_missing_key_fails_before_touching_the_server(self, course, server) -> None:
        self.prepare(course, server)
        result = CliRunner().invoke(app, ["codehood", "autograde", "--server", server.url, "p1"])
        assert result.exit_code == 1
        assert "CODEHOOD_BOT_KEY" in result.output
        assert server.requests == []

    def test_wrong_key_writes_nothing_and_fails(self, course, server) -> None:
        self.prepare(course, server)
        result = autograde(server, "p1", key="wrong")
        assert result.exit_code == 1
        assert [m for m, *_ in server.requests] != []  # it did try
        assert server.puts == [] and server.feedback == {}

    def test_the_key_never_appears_in_the_output(self, course, server) -> None:
        self.prepare(course, server)
        result = autograde(server, "p1")
        assert result.exit_code == 0, result.output
        assert server.token not in result.output


#
# --check and --try
#
@needs_swipl
class TestCheckAndTry:
    def test_check_accepts_a_good_solution_without_a_server(self, course) -> None:
        folder = add_question(course)
        result = CliRunner().invoke(app, ["codehood", "autograde", "--check", str(folder)])
        assert result.exit_code == 0, result.output

    def test_check_rejects_a_solution_without_full_score(self, course) -> None:
        folder = add_question(course, solution=WRONG)
        result = CliRunner().invoke(app, ["codehood", "autograde", "--check", str(folder)])
        assert result.exit_code == 1, result.output

    def test_try_grades_a_local_file(self, course, tmp_path) -> None:
        folder = add_question(course)
        wrong = write(tmp_path / "wrong.pl", WRONG)
        good = write(tmp_path / "good.pl", CORRECT)
        r_wrong = CliRunner().invoke(
            app, ["codehood", "autograde", "--try", str(folder), str(wrong)]
        )
        r_good = CliRunner().invoke(app, ["codehood", "autograde", "--try", str(folder), str(good)])
        assert r_wrong.exit_code == 0, r_wrong.output
        assert r_good.exit_code == 0, r_good.output
        assert "fat5" in r_wrong.output
        assert "fat5" not in r_good.output
