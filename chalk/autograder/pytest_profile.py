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
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from logging import getLogger
from pathlib import Path

from ..core.grader import DEFAULT_TIMEOUT
from .profiles import PrepareError, TestKey, install_trusted_files, read_report
from .repo import Repo
from .script_grader import ScriptGrader
from .script_runner import PASS_ENV, ChalkEnv, Result, Sandbox, ScriptRunner

__all__ = ["PytestGrader", "junit_key", "prepare_venv"]

log = getLogger(__name__)

#: Files of the template that replace the student's ones, when they exist in
#: the template, or are removed from the student's project otherwise.
TRUSTED_FILES = ("conftest.py",)

#: Name of the pytest configuration chalk writes when the template has none.
EMPTY_CONFIG = "pytest-empty.ini"


@dataclass(frozen=True)
class Prepared:
    venv: Path
    config: Path
    #: Expected tests: JUnit key -> test id.
    tests: dict[TestKey, str]


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

    def run_in(
        self,
        repo: Repo,
        /,
        *,
        env: ChalkEnv,
        timeout: float,
        on_output_line: Callable[[str], None] | None,
        capture_output: bool,
        sandbox: Sandbox | None,
    ) -> Result:
        prepared = self.prepare()
        template = self.question.get_template_path()
        assert template is not None
        overlays = install_trusted_files(repo.root, template, [*self.conf.tests, *TRUSTED_FILES])

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
        ).run()

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

    def _collect(self, venv: Path, config: Path, template: Path) -> dict[TestKey, str]:
        """
        Ids of the template tests, collected with the reference solution.
        """
        prepared = Prepared(venv, config, {})
        with self.student_repository("chalk-collect", self.solution) as repo:
            install_trusted_files(repo.root, template, [*self.conf.tests, *TRUSTED_FILES])
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
        return {junit_key(t): t for t in tests}

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
