from decimal import Decimal
from pathlib import Path

import pytest

from chalk.core import Classroom
from chalk.question import MdqQuestion
from chalk.question.mdq import mdq_question_id


@pytest.fixture
def quiz(classroom: Path):
    return Classroom.load().get_quiz("p1")


class TestLoading:
    def test_question_order_follows_conf_then_files(self, quiz, classroom: Path) -> None:
        (classroom / "p1" / "questions" / "q0.md").write_text(
            "---\nid: q0\n---\n\nPergunta?\n\n- [*] Sim\n- [ ] Não\n"
        )
        assert quiz.get_question_ids() == ["q1", "q2", "q3", "q0"]

    def test_mdq_files_become_mdq_questions(self, quiz) -> None:
        assert isinstance(quiz.get_question("q1"), MdqQuestion)
        assert quiz.get_question("q1").type == "multiple-choice"
        assert quiz.get_question("q2").type == "multiple-selection"
        assert not isinstance(quiz.get_question("q3"), MdqQuestion)

    def test_conf_entry_sets_value(self, quiz) -> None:
        assert quiz.get_question("q2").value == Decimal(2)
        assert quiz.get_question("q1").value == Decimal(1)

    def test_conf_entry_cannot_declare_type_of_mdq_question(self, quiz, classroom: Path) -> None:
        conf = classroom / "p1" / "conf.yaml"
        conf.write_text(conf.read_text().replace("  - id: q1\n", "  - id: q1\n    type: text\n"))
        quiz = Classroom.load().get_quiz("p1")
        with pytest.raises(ValueError, match="cannot declare a type"):
            quiz.get_question("q1")

    def test_id_must_match_file_name(self, quiz, classroom: Path) -> None:
        path = classroom / "p1" / "questions" / "q1.md"
        path.write_text(path.read_text().replace("id: q1", "id: other"))
        with pytest.raises(ValueError, match="does not match"):
            quiz.get_question("q1")

    def test_question_without_stem_is_rejected(self, quiz, classroom: Path) -> None:
        path = classroom / "p1" / "questions" / "q2.yaml"
        path.write_text(path.read_text().replace("stem: Quais são números primos?\n", ""))
        with pytest.raises(ValueError, match="stem"):
            quiz.get_question("q2")

    def test_duplicate_question_files(self, quiz, classroom: Path) -> None:
        (classroom / "p1" / "questions" / "q1.yaml").write_text("")
        with pytest.raises(ValueError, match="defined twice"):
            quiz.get_question_files()

    @pytest.mark.parametrize(
        "name, expected",
        [
            ("q1.md", "q1"),
            ("q1.mdq.md", "q1"),
            ("q1.yaml", "q1"),
            ("q1.json", "q1"),
            ("q1.txt", None),
            (".md", None),
        ],
    )
    def test_mdq_question_id(self, name: str, expected: str | None) -> None:
        assert mdq_question_id(Path(name)) == expected


class TestAnswers:
    @pytest.mark.parametrize("answer", ["df", " df ", "Brasília"])
    def test_multiple_choice_accepts_id_or_text(self, quiz, answer: str) -> None:
        assert quiz.get_question("q1").validate_answer(answer) == "df"

    def test_multiple_choice_rejects_unknown_choice(self, quiz) -> None:
        with pytest.raises(ValueError):
            quiz.get_question("q1").validate_answer("xx")

    @pytest.mark.parametrize("answer", ["dois, tres", "[dois, tres]", ("dois", "tres"), "2, 3"])
    def test_multiple_selection_formats(self, quiz, answer) -> None:
        assert quiz.get_question("q2").validate_answer(answer) == ["dois", "tres"]

    def test_empty_answer_is_rejected(self, quiz) -> None:
        with pytest.raises(ValueError):
            quiz.get_question("q1").validate_answer("  ")


class TestGrading:
    def test_correct_choice(self, quiz) -> None:
        graded = quiz.get_question("q1").grade_answer("df")
        assert graded.score == Decimal(1)

    def test_wrong_choice_follows_mdq_default_grading(self, quiz) -> None:
        # mdq grades multiple choice with "symmetric" outside an exam.
        graded = quiz.get_question("q1").grade_answer("sp")
        assert graded.score == Decimal("-0.5")

    def test_partial_selection(self, quiz) -> None:
        graded = quiz.get_question("q2").grade_answer(["tres"])
        assert 0 < graded.score < 1

    def test_grader_uses_mdq(self, quiz) -> None:
        grader = quiz.get_question("q2").get_grader()
        assert grader("0001", ["dois", "tres"]).score == Decimal(1)


class TestSource:
    """conf.yaml entries can point to mdq files outside <quiz>/questions/."""

    BANK = "---\nid: capitais/brasil\n---\n\nCapital do Brasil?\n\n- [*] [df] Brasília\n- [ ] [sp] São Paulo\n"

    def _use_source(self, classroom: Path, source: str) -> None:
        conf = classroom / "p1" / "conf.yaml"
        entry = f"  - id: q3\n    source: {source}\n"
        conf.write_text(conf.read_text().replace("  - id: q3\n", entry))

    def test_source_loads_question_from_bank(self, classroom: Path) -> None:
        bank = classroom / "questions" / "capitais"
        bank.mkdir(parents=True)
        (bank / "brasil.md").write_text(self.BANK)
        self._use_source(classroom, "../questions/capitais/brasil.md")

        quiz = Classroom.load().get_quiz("p1")
        question = quiz.get_question("q3")
        assert isinstance(question, MdqQuestion)
        assert question.type == "multiple-choice"
        assert question.document.id == "q3"
        assert quiz.get_question_ids() == ["q1", "q2", "q3"]

    def test_missing_source(self, classroom: Path) -> None:
        self._use_source(classroom, "../questions/nope.md")
        with pytest.raises(ValueError, match="not found"):
            Classroom.load().get_quiz("p1").get_question("q3")

    def test_source_conflicts_with_local_file(self, classroom: Path) -> None:
        (classroom / "questions").mkdir()
        (classroom / "questions" / "x.md").write_text(self.BANK)
        conf = classroom / "p1" / "conf.yaml"
        conf.write_text(
            conf.read_text().replace("  - id: q1\n", "  - id: q1\n    source: ../questions/x.md\n")
        )
        with pytest.raises(ValueError, match="defined twice"):
            Classroom.load().get_quiz("p1").get_question_files()
