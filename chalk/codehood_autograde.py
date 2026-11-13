"""
Grade the answers of a Codehood exam: the code answers with the autograder
profiles, and the objective ones (multiple choice, true or false...) with the
answer key of the mdq question.

The course repository holds `codehood.toml`, `questions/<path>.md` and
`graders/<path>/` for each question that has a grader:

    graders/<path>/
    ├── grader.yaml     the `autograder:` block of a question
    ├── template/       tests and trusted files
    └── solution/       reference solution, a file or a directory

The server slug of a question is the `id` of its frontmatter. The answers
are read and the grades written through the REST API, see codehood_api.py.

A question without a grader is objective when `questions/` has an mdq file
with its `id` and mdq can grade it. The local file must be the one the server
has: its md5 is compared with the `version` of the question.
"""

from __future__ import annotations

import hashlib
import os
import re
import tomllib
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from fractions import Fraction
from functools import partial
from pathlib import Path
from typing import Any

import mdq.models as mdqm
import pydantic
import yaml
from mdq.errors import NotAutoGradable, ResponseError
from rich import get_console
from rich.text import Text

from chalk_grader.profile_grader import ProfileGrader, resolve_profile
from chalk_grader.profiles import PrepareError
from chalk_grader.task import Task

from .codehood_api import ApiError, CodehoodClient
from .core import disqualification as dq
from .core import models
from .core.grader import Graded
from .question.mdq import check_references, load_mdq_document

__all__ = [
    "BOT_KEY_VAR",
    "CourseConfig",
    "FoundGrader",
    "GraderLayoutError",
    "QuestionReport",
    "Report",
    "autograde_exam",
    "extract_code",
    "find_course_root",
    "find_graders",
    "find_objective_questions",
    "find_question_grader",
    "grade_answer",
    "grade_objective",
    "load_course",
    "make_grader",
    "read_key",
    "verify_reference",
]

#: Environment variable with the key of the grading bot.
BOT_KEY_VAR = "CODEHOOD_BOT_KEY"

#: `ref` of the feedback written by the runner. The server fills in the bot.
REF = "chalk"

#: Profile used when grader.yaml has none, by the `highlight` of the question.
PROFILE_BY_HIGHLIGHT = {
    "prolog": "prolog-plunit",
    "elm": "elm-test",
    "python": "python-pytest",
}

#: Statuses of the submissions the runner may grade.
STATUSES = ("PENDING_GRADE", "GRADED_AUTOMATICALLY")

_FENCE = re.compile(r"^[ \t]*```[^\n`]*\n(.*?)^[ \t]*```[ \t]*$", re.DOTALL | re.MULTILINE)


class GraderLayoutError(ValueError):
    """
    The graders/ and questions/ folders of the course do not match.
    """


@dataclass(frozen=True)
class FoundGrader:
    slug: str
    #: graders/<path>/
    folder: Path
    #: questions/<path>.md
    question: Path
    conf: models.Autograder


@dataclass(frozen=True)
class CourseConfig:
    root: Path
    discipline: str
    instructor: str
    edition: str
    url: str | None

    @property
    def course(self) -> str:
        return f"{self.instructor}_{self.edition}"


@dataclass
class QuestionReport:
    slug: str
    graded: int = 0
    human: int = 0
    manual: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    scores: Counter[str] = field(default_factory=Counter)
    suspicious: int = 0
    #: Why the whole question was not graded, if so.
    aborted: str | None = None


@dataclass
class Report:
    questions: list[QuestionReport] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return any(q.aborted or q.errors for q in self.questions)


#
# Layout
#
def find_graders(root: Path) -> dict[str, FoundGrader]:
    """
    The graders of the course, by question slug.

    Raises:
        GraderLayoutError: a grader has no question, a question has no `id`,
            or there is no profile for the grader.
    """
    base = root / "graders"
    found: dict[str, FoundGrader] = {}
    if not base.is_dir():
        return found

    for conf_path in sorted(base.rglob("grader.yaml")):
        grader = _load_grader(root, conf_path)
        if grader.slug in found:
            raise GraderLayoutError(
                f"question {grader.slug!r} has two graders: {found[grader.slug].folder}"
            )
        found[grader.slug] = grader
    return found


def find_course_root(path: Path, /) -> Path | None:
    """
    The nearest ancestor of path (path itself excluded) with a codehood.toml,
    or None. Does not read the file.
    """
    for parent in path.parents:
        if (parent / "codehood.toml").is_file():
            return parent
    return None


def find_question_grader(question: Path, /) -> FoundGrader | None:
    """
    The grader of a question file of a codehood course: for
    <root>/questions/<path>.md, the one in <root>/graders/<path>/grader.yaml.

    None when the file is not under questions/ of a course or there is no
    grader.yaml. Does not scan the other graders, so a broken grader of
    another question does not get in the way.

    Raises:
        GraderLayoutError: the grader.yaml is invalid, the question has no
            `id`, or there is no profile (same rules as find_graders).
    """
    root = find_course_root(question)
    if root is None or question.suffix != ".md":
        return None
    try:
        relative = question.relative_to(root / "questions")
    except ValueError:
        return None
    conf_path = root / "graders" / relative.with_suffix("") / "grader.yaml"
    if not conf_path.is_file():
        return None
    return _load_grader(root, conf_path)


def _load_grader(root: Path, conf_path: Path) -> FoundGrader:
    """
    The grader of a graders/<path>/grader.yaml, with its question.
    """
    base = root / "graders"
    folder = conf_path.parent
    relative = folder.relative_to(base)
    if relative == Path("."):
        raise GraderLayoutError(f"{conf_path}: a grader lives in graders/<path>/")
    question = (root / "questions" / relative).with_name(relative.name + ".md")
    if not question.is_file():
        raise GraderLayoutError(f"grader {folder} has no question (expected {question})")

    front = _frontmatter(question)
    slug = front.get("id")
    if not isinstance(slug, str) or not slug:
        raise GraderLayoutError(f"{question} has no `id` in its frontmatter")

    try:
        conf = models.Autograder.model_validate(yaml.safe_load(conf_path.read_text()) or {})
    except (yaml.YAMLError, pydantic.ValidationError) as e:
        raise GraderLayoutError(f"{conf_path} (question {slug}): {e}") from None
    if conf.profile is None:
        profile = PROFILE_BY_HIGHLIGHT.get(str(front.get("highlight")))
        if profile is None:
            known = ", ".join(PROFILE_BY_HIGHLIGHT)
            raise GraderLayoutError(
                f"question {slug}: no `profile` in {conf_path} and the `highlight` "
                f"of the question is not one of: {known}"
            )
        conf = conf.model_copy(update={"profile": profile})
    return FoundGrader(slug, folder, question, conf)


def _frontmatter(path: Path) -> dict[str, Any]:
    text = path.read_text()
    if not text.startswith("---"):
        return {}
    _, _, rest = text.partition("\n")
    block, sep, _ = rest.partition("\n---")
    if not sep:
        return {}
    try:
        data = yaml.safe_load(block)
    except yaml.YAMLError as e:
        raise GraderLayoutError(f"{path}: invalid frontmatter: {e}") from None
    return data if isinstance(data, dict) else {}


def load_course(root: Path) -> CourseConfig:
    """
    Read codehood.toml.

    Raises:
        ValueError: the file is missing or lacks a required key.
    """
    path = root / "codehood.toml"
    if not path.is_file():
        raise ValueError(f"{path} not found: run the command at the root of the course")
    data = tomllib.loads(path.read_text())
    course = data.get("course", {})
    missing = [k for k in ("discipline", "instructor", "edition") if not course.get(k)]
    if missing:
        raise ValueError(f"{path}: [course] lacks {', '.join(missing)}")
    url = data.get("server", {}).get("url")
    return CourseConfig(
        root, str(course["discipline"]), str(course["instructor"]), str(course["edition"]), url
    )


def read_key(key_file: Path | None) -> str:
    """
    The key of the grading bot, from the file or from CODEHOOD_BOT_KEY.

    Raises:
        ValueError: there is no key.
    """
    if key_file is not None:
        key = key_file.read_text().strip()
    else:
        key = os.environ.get(BOT_KEY_VAR, "").strip()
    if not key:
        raise ValueError(f"no key for the grading bot: set {BOT_KEY_VAR} or use --key-file")
    return key


#
# Grading one answer
#
def extract_code(text: str) -> str:
    """
    The contents of the fenced code blocks of the text, joined, or the text
    itself when it has none.
    """
    blocks = _FENCE.findall(text)
    return "\n".join(blocks) if blocks else text


def make_grader(
    found: FoundGrader,
    root: Path,
    *,
    quiz_id: str = "codehood",
    question_id: str | None = None,
) -> ProfileGrader:
    """
    The profile grader of a question. root is the course root: profiles come
    from its chalk.toml and the cache goes to <root>/.chalk/cache.
    question_id defaults to found.slug. Both ids only label the run.
    """
    folder = found.folder
    template = folder / (found.conf.template or Path("template"))
    task = Task(
        question_id=question_id or found.slug,
        quiz_id=quiz_id,
        root=folder,
        template=template if template.is_dir() else None,
    )
    assert found.conf.profile is not None
    profile = resolve_profile(found.conf.profile, _user_profiles(root))
    return ProfileGrader(
        script=None,
        task=task,
        conf=found.conf,
        name=found.conf.profile,
        profile=profile,
        solution=_solution(found),
        cache_dir=root / ".chalk" / "cache",
    )


def _user_profiles(root: Path) -> dict[str, dict[str, Any]]:
    path = root / "chalk.toml"
    if not path.is_file():
        return {}
    return tomllib.loads(path.read_text()).get("profiles", {})


def _solution(found: FoundGrader) -> str | Path | None:
    """
    The reference solution: the text of the answer file, or a directory.
    """
    folder = found.folder / "solution"
    if (answer := folder / found.conf.answer).is_file():
        return answer.read_text()
    if folder.is_file():
        return folder.read_text()
    if folder.is_dir():
        files = [p for p in folder.iterdir() if p.is_file()]
        if len(files) == 1 and not any(p.is_dir() for p in folder.iterdir()):
            return files[0].read_text()
        return folder
    return None


def verify_reference(grader: ProfileGrader) -> Graded:
    """
    Grade the reference solution.

    Raises:
        PrepareError: there is no solution, or the profile cannot run it.
        ValueError: the solution does not get the full score.
    """
    if grader.solution is None:
        raise PrepareError("the grader has no solution/ folder")
    graded = grader("solution", grader.solution)
    if graded is None:
        raise ValueError("the reference solution was not graded")
    if graded.score != 1:
        detail = graded.feedback or ""
        raise ValueError(f"the reference solution scores {graded.score}, not 1\n{detail}".rstrip())
    return graded


def grade_answer(grader: ProfileGrader, student: str, text: str) -> Graded | None:
    """
    Grade the text of an answer. None sends the answer to manual grading.
    """
    safe = re.sub(r"[^\w-]", "_", student)
    return grader(safe, extract_code(text))


def to_feedback(graded: Graded, tests: dict[Any, str]) -> tuple[str, str, str | None] | None:
    """
    The (score, feedback, notes) to write for a graded answer, with the score
    as a fraction `n/d`. None when the grading was an error of the
    infrastructure, which writes nothing.
    """
    score = graded.score
    notes = graded.notes or None
    if isinstance(score, Fraction):
        build_failed = (graded.feedback or "").startswith(BUILD_PREFIX)
        if build_failed:
            return _fraction(score), _build_message(graded.feedback), notes
        return _fraction(score), _test_lines(graded.feedback, list(tests.values())), notes
    if score == dq.Error():
        return None
    if score == dq.BuildError():
        return "0/1", _build_message(graded.feedback), notes
    if score == dq.Timeout():
        return "0/1", "O programa excedeu o tempo limite.", notes
    return "0/1", graded.feedback or str(score.message()), notes


#: Start of the feedback of a build error.
BUILD_PREFIX = "The code does not compile:"


def _fraction(score: Fraction) -> str:
    return f"{score.numerator}/{score.denominator}"


def _build_message(feedback: str | None) -> str:
    detail = (feedback or "").removeprefix(BUILD_PREFIX).strip()
    return "O programa não pôde ser carregado." + (f"\n{detail}" if detail else "")


def _test_lines(feedback: str | None, names: list[str]) -> str:
    """
    One line per test, with ✓ or ✗ and the reason of the failure.
    """
    failures: dict[str, str] = {}
    for line in (feedback or "").splitlines():
        if not line.startswith("- "):
            continue
        rest = line[2:]
        for name in names:
            if rest == name or rest.startswith((f"{name}:", f"{name} (")):
                reason = rest[len(name) :].removeprefix(":").strip()
                failures[name] = "não executado" if reason == "(not run)" else reason
                break
    return "\n".join(
        f"✗ {name}" + (f": {failures[name]}" if failures[name] else "")
        if name in failures
        else f"✓ {name}"
        for name in names
    )


#
# The exam
#
def autograde_exam(
    client: CodehoodClient,
    graders: dict[str, FoundGrader],
    course: CourseConfig,
    exam: str,
    *,
    question: str | None = None,
    dry_run: bool = False,
    log: Callable[[str], None] = lambda _: None,
) -> Report:
    """
    Grade the pending answers of the exam to the questions that have a grader.

    Raises:
        ApiError: the server refused a request that affects the whole run.
        ValueError: the question is not in the exam.
    """
    slugs = [q["slug"] for q in client.get(f"exam/{exam}")["questions"]]
    if question is not None:
        if question not in slugs:
            raise ValueError(f"question {question!r} is not in exam {exam!r}")
        slugs = [question]
    objective = find_objective_questions(course.root, [s for s in slugs if s not in graders])
    slugs = [s for s in slugs if s in graders or s in objective]

    report = Report()
    if not slugs:
        return report

    # An attempt closed for submissions, with the newest submission of
    # each question.
    newest: dict[tuple[str, str], tuple[str, str]] = {}
    for response in client.get("response", exam=exam, acceptingSubmissions=False, practice=False):
        for sub in response.get("submissions", []):
            key = (response["publicId"], sub["question"])
            if key not in newest or sub["createdAt"] > newest[key][0]:
                newest[key] = (sub["createdAt"], sub["publicId"])

    for slug in slugs:
        item = QuestionReport(slug)
        report.questions.append(item)
        if slug in graders:
            log(f"{slug}: preparing the grader")
            try:
                grader = make_grader(graders[slug], course.root)
                prepared = grader.prepare()
                verify_reference(grader)
            except (PrepareError, ValueError, RuntimeError, OSError, NotImplementedError) as e:
                item.aborted = str(e)
                continue
            grade = partial(_grade_one, client, grader, prepared.tests, item=item, dry_run=dry_run)

        else:
            try:
                document = _published_document(client, slug, objective[slug])
            except (ValueError, ApiError) as e:
                item.aborted = str(e)
                continue

            grade = partial(_grade_objective_one, client, document, item=item, dry_run=dry_run)

        submissions = client.get("submission", exam=exam, question=slug, statuses=list(STATUSES))
        for sub in submissions:
            sid = sub["publicId"]
            if newest.get((sub["response"], slug), ("", ""))[1] != sid:
                continue
            if _has_human_feedback(client, sid):
                item.human += 1
                continue
            grade(sub)
            log(f"{slug}: {item.graded + len(item.manual) + len(item.errors)} done")
    return report


#
# Objective questions
#
def find_objective_questions(root: Path, slugs: list[str]) -> dict[str, list[Path]]:
    """
    The mdq files of questions/ whose frontmatter `id` is one of the slugs,
    by slug. Only Markdown files are looked at, and the ones with an invalid
    frontmatter are ignored.
    """
    found: dict[str, list[Path]] = {}
    base = root / "questions"
    if not slugs or not base.is_dir():
        return found
    for path in sorted(base.rglob("*.md")):
        try:
            slug = _frontmatter(path).get("id")
        except (GraderLayoutError, OSError, UnicodeDecodeError):
            continue
        if isinstance(slug, str) and slug in slugs:
            found.setdefault(slug, []).append(path)

    # Essays and code without tests are not for the runner.
    return {
        slug: paths
        for slug, paths in found.items()
        if len(paths) > 1 or _is_objective(paths[0], slug)
    }


def _is_objective(path: Path, slug: str) -> bool:
    try:
        document = load_mdq_document(path, slug)
    except ValueError:
        return True  # reported when the question is graded
    return document.type != "code" and document.automation != "manual"


def _published_document(client: CodehoodClient, slug: str, paths: list[Path]) -> mdqm.Question:
    """
    The mdq document of the local file of a question, if it is the version
    published on the server.

    Raises:
        ValueError: there are two files for the question, the file is invalid
            or it is not the published version.
        ApiError: the server refused the request.
    """
    if len(paths) > 1:
        raise ValueError(f"question {slug!r} has two files: {', '.join(map(str, paths))}")
    path = paths[0]
    document = load_mdq_document(path, slug)
    local = f"md5:{hashlib.md5(path.read_bytes()).hexdigest()}"
    server = client.get(f"question/{slug}").get("version")
    if server != local:
        raise ValueError(
            f"{path} is not the version on the server ({local} here, {server} there): "
            "push the question first. Not graded"
        )
    return document


def grade_objective(document: mdqm.Question, response: Any) -> Graded | None:
    """
    Grade the response of a codehood submission (already in the response
    shapes of mdq) with the answer key of the document. None leaves the answer
    for manual grading.

    Raises:
        ValueError: the response is not valid for the question.
    """
    try:
        check_references(document, response)
        result = document.score_response(response)
    except NotAutoGradable:
        return None
    except ResponseError as e:
        raise ValueError(f"invalid answer: {e}") from None
    return Graded(Fraction(str(result.score)).limit_denominator(1000), "\n".join(result.feedback))


def _has_human_feedback(client: CodehoodClient, sid: str) -> bool:
    """
    Whether a human already graded the submission.

    Human feedback is an item with `grader` set and a `ref` other than `REF`
    (the chalk's own feedback, which a new run overwrites). Items of other
    submissions are ignored, since some servers list feedback regardless of
    the submission in the path; an item without `submission` is kept.
    """
    return any(
        f.get("grader") and f.get("ref") != REF
        for f in client.get(f"submission/{sid}/feedback")
        if f.get("submission", sid) == sid
    )


def _grade_one(
    client: CodehoodClient,
    grader: ProfileGrader,
    tests: dict[Any, str],
    sub: dict[str, Any],
    item: QuestionReport,
    dry_run: bool,
) -> None:
    sid = sub["publicId"]
    payload = sub.get("payload")
    if not isinstance(payload, str):
        item.errors.append(f"{sid}: the answer is not a text")
        return
    try:
        graded = grade_answer(grader, sid, payload)
    except (PrepareError, ValueError, RuntimeError, OSError) as e:
        item.errors.append(f"{sid}: {e}")
        return
    if graded is None:
        item.manual.append(sid)
        return
    written = to_feedback(graded, tests)
    if written is None:
        item.errors.append(f"{sid}: {graded.feedback or 'error while grading'}")
        return
    score, feedback, notes = written
    if not dry_run:
        body: dict[str, Any] = {"ref": REF, "score": score, "feedback": feedback}
        if notes:
            body["notes"] = notes
        try:
            client.put(f"submission/{sid}/feedback", body)
        except ApiError as e:
            item.errors.append(f"{sid}: {e}")
            return
    item.graded += 1
    item.scores[_bucket(Fraction(score))] += 1
    if notes:
        item.suspicious += 1


def _grade_objective_one(
    client: CodehoodClient,
    document: mdqm.Question,
    sub: dict[str, Any],
    item: QuestionReport,
    dry_run: bool,
) -> None:
    sid = sub["publicId"]
    try:
        graded = grade_objective(document, sub.get("payload"))
    except ValueError as e:
        item.errors.append(f"{sid}: {e}")
        return
    if graded is None:
        item.manual.append(sid)
        return
    score = _fraction(Fraction(graded.score))
    if not dry_run:
        body: dict[str, Any] = {"ref": REF, "score": score}
        if graded.feedback:
            body["feedback"] = graded.feedback
        try:
            client.put(f"submission/{sid}/feedback", body)
        except ApiError as e:
            item.errors.append(f"{sid}: {e}")
            return
    item.graded += 1
    item.scores[_bucket(Fraction(score))] += 1


def _bucket(score: Fraction) -> str:
    """
    The label of a score in the distribution: 0, 1 or a range in tenths.
    """
    if score < 0:
        return "<0"
    if score == 0:
        return "0"
    if score >= 1:
        return "1"
    low = int(score * 10) / 10
    return f"{low:.1f}-{low + 0.1:.1f}"


#
# Commands
#
def _find(root: Path, folder: Path) -> FoundGrader:
    graders = find_graders(root)
    for found in graders.values():
        if found.folder.resolve() == folder.resolve():
            return found
    raise ValueError(f"{folder} is not a grader of this course (graders/<path>/)")


def run_check(root: Path, folder: Path) -> None:
    """
    Grade the reference solution of a grader and exit with 1 unless it gets
    the full score. Nothing is sent to the server.
    """
    import typer

    found = _find(root, folder)
    grader = make_grader(found, load_course(root).root)
    try:
        graded = verify_reference(grader)
    except (PrepareError, ValueError) as e:
        _say(Text.assemble((f"{found.slug}: ", "red"), str(e)))
        raise typer.Exit(1) from None
    _say(
        Text.assemble((f"{found.slug}: ", "green"), f"the reference solution scores {graded.score}")
    )


def run_try(root: Path, folder: Path, file: Path) -> None:
    """
    Grade a local file with a grader, as an answer, and show the result.
    """
    found = _find(root, folder)
    grader = make_grader(found, load_course(root).root)
    graded = grade_answer(grader, "try", file.read_text())
    if graded is None:
        _say(Text("Left for manual grading.", style="yellow"))
        return
    _say(Text(f"Score: {graded.score}"))
    if graded.feedback:
        _say(Text(graded.feedback))
    if graded.notes:
        _say(Text.assemble(("Notes (teacher only):\n", "yellow"), graded.notes))


def run_autograde(
    root: Path,
    exam: str,
    *,
    question: str | None,
    dry_run: bool,
    server: str | None,
    key_file: Path | None,
) -> None:
    """
    Grade the exam and print the report. Exit with 1 when something was not
    graded because of an error.
    """
    import typer

    course = load_course(root)
    url = server or course.url
    if not url:
        raise ValueError("no server: set [server] url in codehood.toml or use --server")
    key = read_key(key_file)
    graders = find_graders(root)

    client = CodehoodClient(url, course.discipline, course.course, key)
    report = autograde_exam(
        client,
        graders,
        course,
        exam,
        question=question,
        dry_run=dry_run,
        log=lambda line: _say(Text(line, style="dim")),
    )
    print_report(report, dry_run)
    if report.failed:
        raise typer.Exit(1)


def _say(text: Text) -> None:
    get_console().print(text, highlight=False)


def print_report(report: Report, dry_run: bool) -> None:
    if not report.questions:
        _say(Text("No question of the exam has a grader or an answer key."))
    for q in report.questions:
        _say(Text.assemble((q.slug, "bold"), (" (dry run)", "dim") if dry_run else ""))
        if q.aborted:
            _say(Text.assemble(("  not graded: ", "red"), q.aborted))
            continue
        _say(
            Text(
                f"  graded {q.graded}, skipped (human feedback) {q.human}, "
                f"manual {len(q.manual)}, errors {len(q.errors)}, with notes {q.suspicious}"
            )
        )
        if q.scores:
            dist = ", ".join(f"{label}: {n}" for label, n in sorted(q.scores.items()))
            _say(Text(f"  scores: {dist}"))
        if q.manual:
            _say(Text.assemble(("  manual: ", "yellow"), ", ".join(q.manual)))
        for error in q.errors:
            _say(Text.assemble(("  error: ", "red"), error))
