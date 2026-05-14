import sys
from pathlib import Path
from typing import Annotated, Literal

import rich
import typer

from .. import assignments, constants, env, roster
from ..conf import find_project_root, is_project_root
from ..exceptions import Error
from ..models import Question, SimpleAssignment, Student
from . import list_resources as list_cmd
from .util import safe, validate_options

app = typer.Typer(name="Chalk")


ADD_STUDENT_OPTIONS = {"email", "github", "name", "force"}
ADD_SIMPLE_ASSIGNMENT_OPTIONS = {
    "name",
    "start",
    "end",
    "questions",
    "format",
    "split",
    "force",
}


@app.command()
@safe
def init(
    classroom: Annotated[
        str | None,
        typer.Option(
            ...,
            "-c",
            "--classroom",
            help="Classroom name",
        ),
    ] = None,
    teacher: Annotated[
        str | None,
        typer.Option(
            ...,
            "-t",
            "--teacher",
            help="Teacher's name",
        ),
    ] = None,
    interactive: Annotated[
        bool | None,
        typer.Option(
            ...,
            "--interactive",
            "-i",
            is_flag=True,
            help="Enable interactive mode",
        ),
    ] = None,
):
    """
    Initialize a new project.
    """
    if is_project_root(Path.cwd()):
        msg = "[b red]Project already initialized in this directory[/]"
        rich.print(msg, file=sys.stderr)
        raise SystemExit(1)

    classroom = env.get_env_classroom(classroom, interactive=interactive)
    teacher = env.get_env_teacher(teacher, interactive=interactive)
    data = constants.chalk_toml(teacher=teacher, classroom=classroom)

    # Write files
    base = Path.cwd()
    (base / "chalk.toml").write_text(data)
    if not (roster := base / "roster.csv").exists():
        roster.write_text("id,name")
    if not (assignments := base / "assignments").exists():
        assignments.mkdir()
    if not (reports := base / "reports").exists():
        reports.mkdir()


@app.command()
@safe
def add(
    assignment: Annotated[
        str | None,
        typer.Option(
            ...,
            "-a",
            "--assignment",
            help="Assignment name",
        ),
    ] = None,
    student: Annotated[
        str | None,
        typer.Option(
            ...,
            "-s",
            "--student",
            help="Student identifier",
        ),
    ] = None,
    name: Annotated[
        str | None,
        typer.Option(
            ...,
            "-n",
            "--name",
            help="Student/assignment name",
        ),
    ] = None,
    email: Annotated[
        str | None,
        typer.Option(
            ...,
            "-e",
            "--email",
            help="Student's email",
        ),
    ] = None,
    github: Annotated[
        str | None,
        typer.Option(
            ...,
            "-g",
            "--github",
            help="Student's GitHub username",
        ),
    ] = None,
    questions: Annotated[
        list[str] | None,
        typer.Option(
            ...,
            "-q",
            "--questions",
            help="Number of questions or list of question IDs",
        ),
    ] = None,
    format: Annotated[
        Literal["csv", "json", "yaml", "xlsx"],
        typer.Option(
            ...,
            "--format",
            "-f",
            help="File format to save assignment in (csv, json, yaml, xlsx)",
        ),
    ] = "csv",
    interactive: Annotated[
        bool | None,
        typer.Option(
            ...,
            "--interactive",
            "-i",
            is_flag=True,
            help="Enable interactive mode",
        ),
    ] = None,
    split: Annotated[
        bool,
        typer.Option(
            ...,
            "--split",
            is_flag=True,
            help="Split assignment spreadsheet into separate files for each question (only applies to csv and xlsx formats)",
        ),
    ] = False,
    force: Annotated[
        bool,
        typer.Option(
            ...,
            "--force",
            is_flag=True,
            help="Force overwrite of existing resource",
        ),
    ] = False,
):
    """
    Add a new resource to the project.
    """

    vars = {k for k, v in locals().items() if v is not None}
    vars = vars - {"assignment", "student", "interactive"}

    # Error cases
    if student and assignment:
        rich.print(
            "[b red]Cannot add both a student and an assignment at the same time[/]",
            file=sys.stderr,
        )
        raise SystemExit(1)

    elif not student and not assignment:
        rich.print(
            "[b red]Must specify either a student or an assignment to add[/]",
            file=sys.stderr,
        )
        raise SystemExit(1)

    # Student
    elif student:
        validate_options(
            vars,
            ADD_STUDENT_OPTIONS,
            msg="Invalid student option: {option}",
        )

        students = roster.read_roster()
        if student in students and not force:
            rich.print(f"[b red]Student {student} already exists[/]", file=sys.stderr)
            raise SystemExit(1)

        student_model = Student(
            id=student,
            name=env.ask_optional_string(
                "Name", name, default=student, interactive=interactive
            ),
            email=env.ask_optional_string(
                "Email", email, default=None, interactive=interactive
            ),
            github=env.ask_optional_string(
                "GitHub", github, default=None, interactive=interactive
            ),
        )

        roster.add_students([student_model], force=force)

    # Simple assignment
    elif assignment:
        validate_options(
            vars,
            ADD_SIMPLE_ASSIGNMENT_OPTIONS,
            msg="Invalid assignment option: {option}",
        )

        for id, loader in assignments.read_assignments():
            if id == assignment and not force:
                rich.print("[b red]Assignment already exists[/]", file=sys.stderr)
                raise SystemExit(1)

        path = find_project_root() / "assignments" / f"{assignment}.{format}"
        if questions:
            if len(questions) == 1 and questions[0].isdigit():
                questions = [f"q{i + 1}" for i in range(int(questions[0]))]
            else:
                questions = [q.strip() for q in questions]

        assignment_model = SimpleAssignment(
            id=assignment,
            path=path,
            name=env.ask_optional_string(
                "Name", name, default=assignment, interactive=interactive
            ),
            data={},
            questions={id: Question(id=id, grade=1.0) for id in questions}
            if questions
            else None,
        )

        assignments.save_assignment(assignment_model, split=split)


@app.command()
@safe
def load(
    students: Annotated[
        Path | None,
        typer.Option(
            ...,
            "--students",
            "-s",
            help="Load students from file and add them to the classroom roster",
        ),
    ] = None,
):
    """
    Load an assignment from the assignments directory and print its contents.
    """
    if students:
        if not students.exists():
            raise Error.RESOURCE_NOT_FOUND(f"File {students} does not exist")

        data = roster.read_roster_like(students).data
        roster.add_students(list(data.values()))

    else:
        msg = "For now, you can only load a roster file with this command"
        raise NotImplementedError(msg)


app.add_typer(list_cmd.app, name="list", help="List resources in the project.")


@app.command()
@safe
def info(
    student: Annotated[
        str | None,
        typer.Option(
            ...,
            "-s",
            "--student",
            help="Student identifier",
        ),
    ] = None,
):
    """
    Print detailed information about some specific resource.
    """


def main():
    app()
