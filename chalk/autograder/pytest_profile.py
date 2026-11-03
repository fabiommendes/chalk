"""
The python-pytest profile: run the template tests against the student's
project and grade by the list of tests collected from the template.

Three steps, with different levels of trust:

1. Prepare (trusted, once per question): `uv sync --frozen` installs the
   template dependencies in a venv cached by the hash of `pyproject.toml` and
   `uv.lock`. Then pytest collects the test ids from the template, together
   with the reference solution when there is one.
2. Test (untrusted, once per student): pytest runs in the sandbox with the
   venv mounted read only. The tests, `conftest.py` and the pytest
   configuration come from the template; the student's versions are
   replaced and mounted over read only.
3. Score (trusted, in chalk): the JUnit report is read and only the tests
   collected in step 1 count. The denominator is the size of that list, and
   a test missing from the report counts as a failure.
"""

from __future__ import annotations

import hashlib
import os
import re
import shlex
import shutil
import subprocess
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from fractions import Fraction
from logging import getLogger
from pathlib import Path

from ..core import disqualification as dq
from ..core.grader import DEFAULT_TIMEOUT, Graded
from .repo import Repo
from .result_extractor import MAX_RESULT_SIZE
from .script_grader import ScriptGrader
from .script_runner import PASS_ENV, ChalkEnv, Sandbox, ScriptRunner

__all__ = ["PytestGrader", "junit_key", "prepare_venv", "score_report"]

log = getLogger(__name__)

#: Files of the template that replace the student's ones, when they exist in
#: the template, or are removed from the student's project otherwise.
TRUSTED_FILES = ("conftest.py",)

#: Name of the pytest configuration chalk writes when the template has none.
EMPTY_CONFIG = "pytest-empty.ini"


class PrepareError(RuntimeError):
    """
    The template cannot be prepared: missing lock file, failed dependency
    install or failed test collection.
    """


@dataclass(frozen=True)
class Prepared:
    venv: Path
    config: Path
    tests: tuple[str, ...]


@dataclass(frozen=True)
class PytestGrader(ScriptGrader):
    """
    Grades a Python project with the pytest tests of the template.
    """

    #: Reference solution: a directory for repository questions or the text
    #: of the answer for textual ones.
    solution: str | Path | None = None
    cache_dir: Path | None = None
    #: Holds the result of prepare(), which runs once per grader.
    _prepared: list[Prepared] = field(default_factory=list, compare=False, repr=False)

    def prepare(self) -> Prepared:
        """
        Install the venv and collect the expected tests, once per grader.
        """
        if self._prepared:
            return self._prepared[0]

        template = self.question.get_template_path()
        if template is None:
            raise PrepareError("the python-pytest profile needs a template directory")
        cache = self._cache_dir()
        venv = prepare_venv(template, cache)
        config = self._config(template, cache)
        tests = self._collect(venv, config, template)
        self._prepared.append(Prepared(venv, config, tests))
        return self._prepared[0]

    def runner(
        self,
        repo: Repo,
        /,
        *,
        env: ChalkEnv,
        timeout: float,
        on_output_line: Callable[[str], None] | None,
        capture_output: bool,
        sandbox: Sandbox | None,
    ) -> ScriptRunner:
        prepared = self.prepare()
        template = self.question.get_template_path()
        assert template is not None
        overlays = install_trusted_files(repo.root, template, self.conf.tests)

        if sandbox is not None:
            sandbox = replace(
                sandbox,
                readable=(
                    *sandbox.readable,
                    prepared.venv,
                    python_home(prepared.venv),
                    prepared.config,
                ),
                overlays=(*sandbox.overlays, *overlays),
            )
        command = self._pytest_command(prepared, repo.root)
        command += ' --junit-xml="$CHALK_RESULT"'
        expected = prepared.tests
        return ScriptRunner(
            None,
            repo,
            env=env,
            command=command,
            extra_env=pytest_env(repo.root),
            result_reader=lambda path: read_report(path, expected),
            timeout=timeout,
            on_output_line=on_output_line,
            capture_output=capture_output,
            limits=self.conf.limits,
            sandbox=sandbox,
        )

    def _pytest_command(self, prepared: Prepared, root: Path, *args: str) -> str:
        python = prepared.venv / "bin" / "python"
        parts = [
            str(python),
            "-m",
            "pytest",
            "-c",
            str(prepared.config),
            "--rootdir",
            str(root),
            "-p",
            "no:cacheprovider",
            *args,
            *self.conf.tests,
        ]
        return " ".join(map(shlex.quote, parts))

    def _collect(self, venv: Path, config: Path, template: Path) -> tuple[str, ...]:
        """
        Ids of the template tests, collected with the reference solution.
        """
        prepared = Prepared(venv, config, ())
        with self.student_repository("chalk-collect", self.solution) as repo:
            install_trusted_files(repo.root, template, self.conf.tests)
            command = self._pytest_command(prepared, repo.root, "--collect-only", "-q")
            env = {k: os.environ[k] for k in PASS_ENV if k in os.environ}
            env.update({k: v for k, v in pytest_env(repo.root).items() if v is not None})
            env.pop("PYTHONHOME", None)
            try:
                proc = subprocess.run(
                    command,
                    shell=True,
                    cwd=repo.root,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=self.conf.timeout or DEFAULT_TIMEOUT,
                )
            except subprocess.TimeoutExpired as e:
                raise PrepareError("collecting the template tests timed out") from e

        tests = parse_collection(proc.stdout)
        if proc.returncode != 0 or not tests:
            hint = (
                "" if self.solution is not None else " (add the reference solution to the question)"
            )
            msg = f"collecting the template tests failed{hint}:\n{proc.stdout}{proc.stderr}"
            raise PrepareError(msg.rstrip())
        return tests

    def _config(self, template: Path, cache: Path) -> Path:
        """
        The pytest configuration of the template, or an empty one.
        """
        ini = template / "pytest.ini"
        if ini.is_file():
            return ini.resolve()
        pyproject = template / "pyproject.toml"
        if re.search(r"^\[tool\.pytest(\.ini_options)?\]", pyproject.read_text(), re.M):
            return pyproject.resolve()
        empty = cache / EMPTY_CONFIG
        if not empty.exists():
            empty.write_text("[pytest]\n")
        return empty.resolve()

    def _cache_dir(self) -> Path:
        if self.cache_dir is not None:
            path = self.cache_dir
        else:
            path = self.question.quiz.classroom.root / ".chalk" / "cache"
        path.mkdir(parents=True, exist_ok=True)
        return path


def prepare_venv(template: Path, cache: Path) -> Path:
    """
    Install the template dependencies with `uv sync --frozen` in a venv inside
    the cache directory and return its path.

    The venv is reused while `pyproject.toml` and `uv.lock` do not change.
    """
    pyproject = template / "pyproject.toml"
    lock = template / "uv.lock"
    if not pyproject.is_file() or not lock.is_file():
        raise PrepareError(
            "the python-pytest profile needs pyproject.toml and uv.lock in the template"
        )

    digest = hashlib.sha256(pyproject.read_bytes() + b"\0" + lock.read_bytes()).hexdigest()
    venv = cache / f"venv-{digest[:16]}"
    if (venv / "pyvenv.cfg").is_file():
        return venv

    uv = shutil.which("uv")
    if uv is None:
        raise PrepareError("uv not found: the python-pytest profile installs the template with uv")
    tmp = cache / f"{venv.name}.tmp-{os.getpid()}"
    shutil.rmtree(tmp, ignore_errors=True)
    proc = subprocess.run(
        [uv, "sync", "--frozen", "--no-install-project", "--project", str(template)],
        env={**os.environ, "UV_PROJECT_ENVIRONMENT": str(tmp)},
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        shutil.rmtree(tmp, ignore_errors=True)
        raise PrepareError(f"uv sync failed for the template:\n{proc.stderr.strip()}")

    try:
        tmp.rename(venv)
    except OSError:
        # Another chalk process created it first.
        shutil.rmtree(tmp, ignore_errors=True)
    log.info(f"Prepared venv {venv}")
    return venv


def python_home(venv: Path) -> Path:
    """
    Installation directory of the Python the venv uses, without resolving
    symlinks: the venv refers to it by this path.
    """
    for line in (venv / "pyvenv.cfg").read_text().splitlines():
        key, _, value = line.partition("=")
        if key.strip() == "home":
            return Path(value.strip()).parent
    return (venv / "bin" / "python").resolve().parent.parent


def pytest_env(root: Path) -> dict[str, str | None]:
    """
    Environment changes for a pytest run in the given project.

    Plugins are not loaded automatically: the student could add a dist-info
    with a pytest11 entry point to the project. The template's conftest.py
    can load the plugins it needs with `pytest_plugins`.
    """
    paths = [root / "src", root] if (root / "src").is_dir() else [root]
    return {
        "PYTHONPATH": os.pathsep.join(map(str, paths)),
        "PYTHONHOME": None,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    }


def install_trusted_files(
    root: Path, template: Path, tests: Iterable[str]
) -> list[tuple[Path, Path]]:
    """
    Replace the tests and conftest.py of the project in root by the
    template's, and return the (source, target) pairs to mount read only
    over the working directory.
    """
    overlays: list[tuple[Path, Path]] = []
    for name in [*tests, *TRUSTED_FILES]:
        if name.startswith("-") or Path(name).is_absolute() or ".." in Path(name).parts:
            raise ValueError(f"test path must be relative to the template: {name}")
        source = template / name
        target = root / name
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        elif target.exists() or target.is_symlink():
            target.unlink()

        if source.is_dir():
            shutil.copytree(source, target, symlinks=False)
        elif source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        else:
            continue
        overlays.append((source, target))
    return overlays


def parse_collection(output: str) -> tuple[str, ...]:
    """
    Test ids from the output of `pytest --collect-only -q`.
    """
    ids: list[str] = []
    for line in output.splitlines():
        if not line.strip():
            break
        if "::" in line:
            ids.append(line.strip())
    return tuple(ids)


def junit_key(nodeid: str) -> tuple[str, str]:
    """
    The (classname, name) pair pytest writes to JUnit for the given test id.

    Same rules as `mangle_test_address` in `_pytest.junitxml`.
    """
    path, bracket, params = nodeid.partition("[")
    names = path.split("::")
    names[0] = names[0].replace("/", ".")
    names[0] = re.sub(r"\.py$", "", names[0])
    names[-1] += bracket + params
    return ".".join(names[:-1]), names[-1]


def read_report(path: Path, expected: tuple[str, ...]) -> Graded:
    if path.stat().st_size > MAX_RESULT_SIZE:
        return Graded(dq.Error(), feedback="Test report is too large.")
    return score_report(path.read_text(errors="replace"), expected)


def score_report(src: str, expected: tuple[str, ...]) -> Graded:
    """
    Score a JUnit report against the expected test ids.

    A test passes when it is in the report without failure, error or skip.
    Missing tests, tests skipped by the student's code and repeated entries
    with a failure count as failures. Tests not in the expected list are
    ignored.
    """
    try:
        root = ET.fromstring(src)
    except ET.ParseError as e:
        return Graded(dq.Error(), feedback=f"Invalid JUnit report: {e}")

    outcomes: dict[tuple[str, str], bool] = {}
    errors: list[str] = []
    for case in root.iter("testcase"):
        key = (case.get("classname") or "", case.get("name") or "")
        ok = all(case.find(tag) is None for tag in ("failure", "error", "skipped"))
        outcomes[key] = outcomes.get(key, True) and ok
        if not key[0] and (error := case.find("error")) is not None:
            errors.append(f"- {key[1]}: {error.get('message') or 'error'}")

    keys = {junit_key(n): n for n in expected}
    unknown = [k for k in outcomes if k not in keys and k[0]]
    if unknown:
        log.warning(f"Report has {len(unknown)} tests that are not in the template: {unknown[:5]}")

    failed = [n for k, n in keys.items() if outcomes.get(k) is not True]
    passed = len(keys) - len(failed)
    lines: list[str] = []
    if failed:
        lines += ["Failed tests:"]
        lines += [f"- {n}" + ("" if junit_key(n) in outcomes else " (not run)") for n in failed]
    if errors:
        lines += ["Errors:", *errors]
    return Graded(Fraction(passed, len(keys)), feedback="\n".join(lines) or None)
