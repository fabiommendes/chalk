from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, NamedTuple, cast

import rich

from ..core import StudentId
from ..roster import read_roster

if TYPE_CHECKING:
    from ..core import Assignment, Question, Response


class AssignmentAndQuestion(NamedTuple):
    assignment: Assignment
    question: Question


class AssignmentQuestionAndResponse(NamedTuple):
    assignment: Assignment
    question: Question
    response: Response


class AssignmentQuestionAndResponses(NamedTuple):
    assignment: Assignment
    question: Question
    responses: dict[StudentId, Response]


def safe[R, **P](func: Callable[P, R]) -> Callable[P, R]:
    """
    A decorator that wraps a function in a try-except block and prints any exceptions that occur.
    """
    import functools
    import traceback

    from ..core import ChalkError

    @functools.wraps(func)
    def wrapper(*args, **kwargs):  # type: ignore
        try:
            return func(*args, **kwargs)
        except ChalkError as e:
            e.print()
        except Exception as e:
            rich.print(f"An unexpected error occurred: {e}")
            traceback.print_exc()

    return cast(Callable[P, R], wrapper)


def validate_options(
    vars: dict[str, Any] | set[str],
    valid_options: set[str],
    /,
    msg: str = "Invalid option: {option}",
) -> None:
    """
    Validate that the given options are in the set of valid options.
    """
    from ..core import SystemError

    keys = vars.keys() if isinstance(vars, dict) else vars
    for option in keys - valid_options:
        raise SystemError.INVALID_FIELD(msg.format(option=option))


def read_assignment_and_question(
    assignment_id: str | None,
    question_id: str | None,
) -> AssignmentAndQuestion:
    from ..core import Assignment, SystemError

    assignment = Assignment.prompt(assignment_id)
    question = assignment.prompt_question(question_id)

    if question is None:
        msg = f"Question {question_id} not found in {assignment_id}"
        raise SystemError.RESOURCE_NOT_FOUND(msg)

    return AssignmentAndQuestion(assignment, question)


def read_assignment_question_and_response(
    assignment_id: str | None,
    question_id: str | None,
    student_id: str | None,
) -> AssignmentQuestionAndResponse:
    """
    Read the assignment, question, and student from the given IDs.

    Raises RuntimeError if any of the resources cannot be found.
    """
    from ..core import SystemError

    assignment, question = read_assignment_and_question(assignment_id, question_id)
    roster = read_roster()

    student = roster.prompt_student(student_id)
    if student is None:
        msg = f"Student {student_id} not found in roster"
        raise SystemError.RESOURCE_NOT_FOUND(msg)

    submission = assignment.get_submission(student)
    if submission is None:
        msg = f"Response for student {student_id} not found in {assignment_id}"
        raise SystemError.RESOURCE_NOT_FOUND(msg)

    response = submission.responses.get(question.id)
    if response is None:
        response = Response()

    return AssignmentQuestionAndResponse(assignment, question, response)


def read_assignment_question_and_responses(
    assignment_id: str | None,
    question_id: str | None,
    student_id: str | None,
) -> AssignmentQuestionAndResponses:
    """
    Read the assignment, question, and responses for the given IDs.

    If student_id is provided, only returns the response for that student. Otherwise,
    returns the responses for all students who submitted a response to the question.

    Raises RuntimeError if any of the resources cannot be found.
    """
    assignment, question = read_assignment_and_question(assignment_id, question_id)

    if student_id is not None:
        response = assignment.get_response(student_id, question)
        responses: dict[StudentId, Response] = (
            {student_id: response} if response is not None else {}
        )
    else:
        responses = assignment.get_responses_for_question(question)

    return AssignmentQuestionAndResponses(assignment, question, responses)


def __getattr__(name: str) -> Any:
    models = ("Assignment", "Question", "Response", "SystemError")
    if name in models:
        from .. import core

        return getattr(core, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
