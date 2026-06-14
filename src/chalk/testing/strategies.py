from hypothesis import strategies as st

from chalk.core import Grade
from chalk.core import adjustment as adj
from chalk.core import disqualification as dq

student_id = st.from_regex(r"[a-zA-Z0-9-]{2,}", fullmatch=True)
question_id = st.from_regex(r"q?[a-zA-Z0-9-]{2,4}", fullmatch=True)
assignment_id = st.from_regex(r"q?[a-zA-Z0-9-]{2,4}", fullmatch=True)


#
# Grade-related strategies
#
_disqualification = st.sampled_from([dq.Timeout(), dq.Invalid()]) | student_id.map(
    dq.Plagiarism
)


@st.composite
def disqualification(draw: st.DrawFn, single: bool = False) -> dq.Disqualification:
    """
    Strategy for generating random disqualifications, including timeouts,
    invalids, and plagiarism.

    If single=True, only generates a single disqualification. Otherwise, it may
    generate multiple disqualifications merged together.
    """
    if single or draw(st.booleans()):
        return draw(_disqualification)
    else:
        a = draw(disqualification())
        b = draw(disqualification())
        return dq.merge(a, b)


_decimals = st.decimals(allow_infinity=False, allow_nan=False)
_adjustment = (
    # absolute
    _decimals.map(adj.Adjustment)
    # relative
    | _decimals.map(lambda x: adj.Adjustment(relative=x))
    # override
    | _decimals.map(lambda x: adj.Adjustment(override=x))
)


@st.composite
def adjustment(draw: st.DrawFn) -> adj.Adjustment:
    """
    Strategy for generating random adjustments, including absolute, relative,
    and override adjustments.
    """
    return draw(_adjustment)


@st.composite
def grade(draw: st.DrawFn) -> Grade:
    """
    Strategy for generating random grades, including plain grades, grades with
    adjustments, and grades with disqualifications.
    """
    match draw(st.sampled_from(["plain", "adjustment", "disqualification"])):
        case "plain":
            return Grade(draw(_decimals))
        case "adjustment":
            return Grade(
                draw(_decimals),
                adjustment=draw(adjustment()),
            )
        case "disqualification":
            return Grade(
                draw(_decimals),
                disqualification=draw(disqualification()),
            )
        case _:
            raise RuntimeError
