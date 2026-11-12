"""
`chalk codehood autograde`: code fenced in markdown and `on_build_error`.
"""

from fractions import Fraction

import pytest

from chalk.codehood_autograde import extract_code
from tests.test_codehood_autograde import (  # noqa: F401
    CORRECT,
    GRADER_YAML,
    NOT_LOADING,
    SLUG,
    WRONG,
    add_question,
    autograde,
    course,
    needs_swipl,
    server,
)


class TestExtractCode:
    def test_text_without_fences_is_kept(self) -> None:
        assert extract_code("fat(0, 1).\n") == "fat(0, 1).\n"

    def test_only_the_fenced_blocks_are_kept(self) -> None:
        text = (
            "Segue a resposta:\n```prolog\nfat(0, 1).\n```\nE a outra:\n```\nfat(1, 1).\n```\nFim."
        )
        assert extract_code(text) == "fat(0, 1).\n\nfat(1, 1).\n"

    def test_fence_without_language(self) -> None:
        assert extract_code("```\na.\n```") == "a.\n"

    def test_unclosed_fence_is_not_a_block(self) -> None:
        assert extract_code("```prolog\na.\n") == "```prolog\na.\n"


@needs_swipl
class TestFencedAnswers:
    def test_prose_around_the_code_is_ignored(self, course, server) -> None:  # noqa: F811
        add_question(course)
        server.add_exam("p1", [SLUG])
        answer = f"Minha solucao:\n\n```prolog\n{CORRECT}```\n\nEspero que esteja certo!\n"
        (sid,) = server.add_attempt("ana", "p1", [(SLUG, answer, "PENDING_GRADE")])
        result = autograde(server, "p1")
        assert result.exit_code == 0, result.output
        assert server.fraction(sid) == 1


@needs_swipl
class TestOnBuildError:
    def test_manual_writes_nothing_and_is_listed(self, course, server) -> None:  # noqa: F811
        yaml = GRADER_YAML + "on_build_error: manual\n"
        add_question(course, grader_yaml=yaml)
        server.add_exam("p1", [SLUG])
        (broken, fine) = server.add_attempt(
            "bia", "p1", [(SLUG, NOT_LOADING, "PENDING_GRADE")]
        ) + server.add_attempt("caio", "p1", [(SLUG, WRONG, "PENDING_GRADE")])
        result = autograde(server, "p1")
        assert result.exit_code == 0, result.output
        assert [sid for sid, _ in server.puts] == [fine]
        assert broken not in server.feedback
        assert "manual" in result.output and broken in result.output

    @pytest.mark.parametrize("mode", ["zero", "build-error"])
    def test_other_modes_write_zero(self, course, server, mode) -> None:  # noqa: F811
        add_question(course, grader_yaml=GRADER_YAML + f"on_build_error: {mode}\n")
        server.add_exam("p1", [SLUG])
        (sid,) = server.add_attempt("dani", "p1", [(SLUG, NOT_LOADING, "PENDING_GRADE")])
        result = autograde(server, "p1")
        assert result.exit_code == 0, result.output
        assert server.fraction(sid) == Fraction(0)
        assert server.written(sid)["feedback"]
