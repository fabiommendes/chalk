import pytest

from chalk.core import Grade
from chalk.core import adjustment as adj
from chalk.core import disqualification as dq

zero = Grade(0)


class TestGrade:
    def test_render_simple_grades(self) -> None:
        assert str(Grade(0)) == "0"
        assert str(Grade(0.5)) == "0.5"
        assert str(Grade(0.01)) == "0.01"
        assert str(Grade("0.01")) == "0.01"

    def test_render_disqualified_grades(self) -> None:
        grade = Grade(1.5)
        zero = Grade(0)

        assert str(grade.disqualify(dq.Timeout())) == "timeout (1.5)"
        assert str(zero.disqualify(dq.Timeout())) == "timeout"
        assert str(zero.disqualify(dq.Plagiarism("123"))) == "plagiarism[123]"
        assert (
            str(zero.disqualify(dq.merge(dq.Timeout(), dq.Plagiarism("123"))))
            == "disqualified: timeout, plagiarism[123]"
        )

    @pytest.mark.parametrize(
        "grade",
        [
            Grade(0),
            Grade(1.5),
            Grade(0).disqualify(dq.Timeout()),
            Grade(0).disqualify(dq.Plagiarism("123")),
            Grade(0).adjust(adj.Adjustment(0.5)),
            Grade(0).adjust(adj.Adjustment(relative=0.5)),
            Grade(0).adjust(adj.Adjustment(override=10)),
            Grade(0).adjust(adj.Adjustment("50%")),
        ],
    )
    def test_render_parse_round_trip(self, grade: Grade) -> None:
        as_str = str(grade)
        parsed = Grade.parse(as_str)
        assert parsed == grade

    # @given(cst.grade())
    # def test_fuzz_render_parse_round_trip(self, grade: Grade) -> None:
    #     self.test_render_parse_round_trip(grade)
