"""
Grader for the profiles written as data: the built-in ones in profiles.toml
and the [profiles] tables of chalk.toml.

Steps, with different levels of trust:

1. Prepare (trusted, outside the sandbox, with network): the probes find the
   toolchain, and the prepare commands fill a cache directory selected by
   the hash of the key files, the probes and the profile. The commands run in
   a copy of the template with the reference solution.
2. Reference run: the build and test steps run on the reference solution, in
   the sandbox, as for a student. The tests in its report are the expected
   tests. This runs once per grader, so changes to the tests or the solution
   need no cache invalidation.
3. Build (untrusted, in the sandbox, offline, optional): a failure gives the
   `build-error` result, with the compiler output as feedback.
4. Test (untrusted, in the sandbox, offline): writes a JUnit report to
   $CHALK_RESULT. The services of the profile, if any, run during this step
   in sandboxes of their own (see services.py), and their reports join the
   test report.
5. Score (trusted, in chalk): only the expected tests count, and a test
   missing from the report counts as a failure.

The test directories and the trusted files come from the template: the
student's copies are replaced, and mounted read only during the run.
"""

from __future__ import annotations

import fcntl
import hashlib
import os
import re
import shlex
import shutil
import subprocess
import sys
import tomllib
import xml.etree.ElementTree as ET
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from fractions import Fraction
from functools import cache
from importlib import resources
from logging import getLogger
from pathlib import Path
from typing import Any

from . import disqualification as dq
from . import models
from .graded import DEFAULT_TIMEOUT, Graded
from .profiles import (
    PrepareError,
    TestKey,
    check_relative,
    install_trusted_files,
    read_report,
    read_stdio_report,
    stdio_keys,
)
from .repo import Repo
from .result_extractor import MAX_RESULT_SIZE
from .scoring import make_scorer
from .script_grader import ScriptGrader
from .script_runner import ChalkEnv, Result, Sandbox, ScriptRunner
from .services import RUNNERS, Services
from .suspicious import MAX_MATCHES, scan

__all__ = ["ProfileGrader", "builtin_profiles", "render", "resolve_profile", "seed_workdir"]

log = getLogger(__name__)

#: Largest compiler output kept as feedback, in characters.
MAX_BUILD_FEEDBACK = 8000

#: Profiles implemented in Python, not as data.
CODE_PROFILES = ("script", "regex")

#: Reads the report of the test step, given the reports of the services.
type Reader = Callable[[Path, Sequence[str]], Graded]

#: Prefix of the lines of the pytest guard (runners/pytest_guard.py).
GUARD_PREFIX = "chalk-guard: "

_VARIABLE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_NAME = re.compile(r"[a-z0-9][a-z0-9_-]*")


@cache
def builtin_profiles() -> dict[str, dict[str, Any]]:
    """
    The profiles shipped with chalk, as written in profiles.toml.
    """
    text = resources.files(__package__).joinpath("profiles.toml").read_text()
    return tomllib.loads(text)


def resolve_profile(
    name: str, user: Mapping[str, Mapping[str, Any]] | None = None
) -> models.Profile:
    """
    The profile with the given name, from the [profiles] tables of chalk.toml
    or the built-in ones, with `extends` resolved.

    A table in chalk.toml with the name of a built-in profile replaces it;
    `extends` with its own name refers to the built-in one.
    """
    data = _resolve(name, dict(user or {}), seen=())
    return models.Profile.model_validate(data)


def _resolve(name: str, user: dict[str, Mapping[str, Any]], seen: tuple[str, ...]) -> dict:
    if not _NAME.fullmatch(name):
        raise ValueError(f"invalid profile name: {name!r}")
    if name in seen and name in user:
        raise ValueError(f"profiles extend each other in a loop: {' -> '.join([*seen, name])}")
    if name in user:
        data = dict(user[name])
        rest = {k: v for k, v in user.items() if k != name}
    elif name in builtin_profiles():
        data = dict(builtin_profiles()[name])
        rest = {}
    else:
        known = sorted({*builtin_profiles(), *user, *CODE_PROFILES})
        raise ValueError(f"unknown profile {name!r}; known profiles: {', '.join(known)}")

    parent = data.pop("extends", None)
    if parent is None:
        return data
    base = _resolve(parent, rest if parent == name else user, (*seen, name))
    return _merge(base, data)


def _merge(base: dict, child: Mapping) -> dict:
    out = dict(base)
    for key, value in child.items():
        if isinstance(value, Mapping) and isinstance(out.get(key), Mapping):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def render(text: str, variables: Mapping[str, str]) -> str:
    """
    Replace the {name} variables in text. Unknown names, such as shell
    expansions like ${HOME}, are kept.
    """
    return _VARIABLE.sub(lambda m: variables.get(m[1], m[0]), text)


@dataclass(frozen=True)
class Prepared:
    cache: Path
    #: Probes and built-in variables, except workdir.
    variables: dict[str, str]
    #: Expected tests: JUnit key -> name shown in the feedback.
    tests: dict[TestKey, str]


@dataclass(frozen=True)
class ProfileGrader(ScriptGrader):
    """
    Grades a project with the steps of a data profile.
    """

    name: str = "profile"
    profile: models.Profile | None = None
    #: Reference solution: a directory for repository questions or the text
    #: of the answer for textual ones.
    solution: str | Path | None = None
    #: Defaults to .chalk/cache in the task root.
    cache_dir: Path | None = None
    #: Holds the result of prepare(), which runs once per grader.
    _prepared: list[Prepared] = field(default_factory=list, compare=False, repr=False)

    @property
    def spec(self) -> models.Profile:
        assert self.profile is not None
        return self.profile

    @property
    def tests(self) -> list[str]:
        return self.conf.tests if self.conf.tests is not None else self.spec.tests

    def prepare(self) -> Prepared:
        """
        Fill the cache and collect the expected tests from a run of the
        reference solution, once per grader.
        """
        if self._prepared:
            return self._prepared[0]

        template = self._template()
        for name in self.spec.key:
            if not (template / name).is_file():
                raise PrepareError(f"the {self.name} profile needs {name} in the template")

        with self.student_repository("chalk-prepare", self.solution) as repo:
            install_trusted_files(repo.root, template, self._trusted())
            variables = {
                "template": str(template),
                "tests": " ".join(self.tests),
                "PATH": os.environ.get("PATH", ""),
                "python": sys.executable,
                "runners": str(RUNNERS),
                **self.spec.vars,
                **self.conf.vars,
            }
            variables.update(self._probe(repo.root, variables))
            cache_dir = self._fill_cache(template, variables, repo.root)
            variables["cache"] = str(cache_dir)
            prepared = Prepared(cache_dir, variables, {})
            tests = self._collect(repo, prepared)

        self._prepared.append(replace(prepared, tests=tests))
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
        found = scan(
            repo.root,
            template=self._template(),
            patterns=self.spec.suspicious,
            skip=self._trusted(),
        )
        result = self._run_steps(
            repo,
            prepared,
            reader=self._reader(prepared),
            env=env,
            timeout=timeout,
            on_output_line=on_output_line,
            capture_output=capture_output,
            sandbox=sandbox,
        )
        refused = [
            line.partition(GUARD_PREFIX)[2].strip()
            for line in (result.stdout or "").splitlines()
            if GUARD_PREFIX in line
        ][:MAX_MATCHES]
        if refused and result.score == dq.Error():
            # Such as a file with the name of a standard module.
            feedback = "\n".join([result.feedback or "", *refused]).strip()
            result = replace(result, feedback=feedback)
        return replace(result, notes=_notes(found, refused))

    def _reader(self, prepared: Prepared) -> Reader:
        expected = prepared.tests
        scorer = make_scorer(self.conf, self.task.root)
        if self.spec.report == "stdio":
            template = self._template()
            mode = prepared.variables.get("compare", "lines")
            return lambda path, extra: read_stdio_report(
                path, expected, template, mode, extra, scorer
            )
        return lambda path, extra: read_report(path, expected, extra, scorer)

    def _run_steps(
        self,
        repo: Repo,
        prepared: Prepared,
        *,
        reader: Reader,
        env: ChalkEnv,
        timeout: float,
        on_output_line: Callable[[str], None] | None,
        capture_output: bool,
        sandbox: Sandbox | None,
    ) -> Result:
        overlays = install_trusted_files(repo.root, self._template(), self._trusted())
        for pattern in self.spec.hide:
            check_relative(pattern)
            for path in list(repo.root.glob(pattern)):
                if path.is_file() or path.is_symlink():
                    path.unlink()
        variables = {**prepared.variables, "workdir": str(repo.root)}

        if sandbox is not None:
            readable = [Path(render(p, variables)).expanduser() for p in self.spec.readable]
            sandbox = replace(
                sandbox,
                readable=(*sandbox.readable, *readable),
                overlays=(*sandbox.overlays, *overlays),
            )
        run: dict[str, Any] = dict(
            env=env,
            extra_env=self._env(variables),
            on_output_line=on_output_line,
            capture_output=capture_output,
            sandbox=sandbox,
        )

        if (build := self.spec.build) is not None:
            seed_workdir(
                repo.root, {dest: Path(render(src, variables)) for dest, src in build.seed.items()}
            )
            result = ScriptRunner(
                None,
                repo,
                command=self._command(build.command, variables),
                timeout=self.conf.build.timeout or build.timeout or timeout,
                limits=self.conf.build.limits or build.limits or self.conf.limits,
                log_name="chalk.build",
                expect_result=False,
                **run,
            ).run()
            if result.score == dq.Timeout():
                return replace(result, feedback="The build took too long.")
            if result.return_code != 0:
                return self._build_error(result)

        test = self.spec.test
        command = self._command(test.command, variables)
        services = None
        if self.spec.services:
            if sandbox is None:
                raise PrepareError(f"the services of the {self.name} profile need the sandbox")
            services = Services(
                self.spec.services,
                template=self._template(),
                render=lambda text, extra: render(text, {**variables, **extra}),
                readable=[Path(render(p, variables)).expanduser() for p in self.spec.readable],
                env={
                    "CHALK_STUDENT": env.student_id,
                    "CHALK_QUESTION": env.question_id,
                    "CHALK_ASSIGNMENT": env.assignment_id,
                },
            )
            if (error := services.start()) is not None:
                services.stop(repo)
                return Result(return_code=1, score=dq.Error(), feedback=error)
            run["sandbox"] = replace(
                sandbox,
                readable=(*sandbox.readable, services.sockets, RUNNERS),
                hidden=(*sandbox.hidden, services.root),
            )
            command = services.forward(command)

        def read(path: Path) -> Graded:
            return reader(path, services.stop(repo) if services else [])

        try:
            return ScriptRunner(
                None,
                repo,
                command=command,
                result_reader=read,
                timeout=test.timeout or timeout,
                limits=test.limits or self.conf.limits,
                **run,
            ).run()
        finally:
            if services is not None:
                services.stop(repo)

    def _build_error(self, build: Result) -> Result:
        # Lines of the guard are for the teacher and go to the notes.
        output = "\n".join(
            line for line in (build.stdout or "").splitlines() if GUARD_PREFIX not in line
        )
        if len(output) > MAX_BUILD_FEEDBACK:
            output = output[:MAX_BUILD_FEEDBACK] + "\n[...]"
        feedback = f"The code does not compile:\n{output}".rstrip()
        match self.conf.on_build_error:
            case "zero":
                return replace(build, score=Fraction(0), feedback=feedback)
            case "manual":
                return replace(build, score=None, feedback=feedback)
            case _:
                return replace(build, score=dq.BuildError(), feedback=feedback)

    def _probe(self, cwd: Path, variables: Mapping[str, str]) -> dict[str, str]:
        values: dict[str, str] = {}
        for name, command in self.spec.probe.items():
            command = self._command(command, {**variables, "workdir": str(cwd)})
            proc = _run(command, cwd=cwd, env=dict(os.environ), timeout=60)
            if proc.returncode != 0:
                raise PrepareError(
                    f"probe {name!r} of the {self.name} profile failed: {command}\n"
                    f"{proc.stdout}{proc.stderr}".rstrip()
                )
            values[name] = proc.stdout.strip()
        return values

    def _fill_cache(self, template: Path, variables: dict[str, str], workdir: Path) -> Path:
        """
        Cache directory of the profile, filled by the prepare commands when
        it is not ready yet.
        """
        digest = hashlib.sha256()
        spec = self.spec.model_dump_json(
            include={"key", "probe", "env", "unset", "files", "prepare"}
        )
        digest.update(spec.encode() + b"\0")
        for name in self.spec.key:
            digest.update((template / name).read_bytes() + b"\0")
        for name in sorted(variables):
            if name not in ("template", "PATH"):
                digest.update(f"{name}={variables[name]}".encode() + b"\0")

        root = self._cache_root()
        path = root / f"{self.name}-{digest.hexdigest()[:16]}"
        with (root / f"{path.name}.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if (path / ".ready").exists():
                return path

            shutil.rmtree(path, ignore_errors=True)
            path.mkdir()
            variables = {**variables, "cache": str(path), "workdir": str(workdir)}
            for name, content in self.spec.files.items():
                check_relative(name)
                (path / name).parent.mkdir(parents=True, exist_ok=True)
                (path / name).write_text(content)

            env = {**os.environ, **self._env(variables)}
            for name in self.spec.unset:
                env.pop(name, None)
            for command in self.spec.prepare.commands:
                command = self._command(command, variables)
                timeout = self.spec.prepare.timeout or DEFAULT_TIMEOUT * 10
                proc = _run(command, cwd=workdir, env=env, timeout=timeout)
                if proc.returncode != 0:
                    shutil.rmtree(path, ignore_errors=True)
                    raise PrepareError(
                        f"prepare command of the {self.name} profile failed{self._hint()}: "
                        f"{command}\n{proc.stdout}{proc.stderr}".rstrip()
                    )
            (path / ".ready").write_text("")
        log.info(f"Prepared cache {path}")
        return path

    def _collect(self, repo: Repo, prepared: Prepared) -> dict[TestKey, str]:
        """
        Tests in the report of the reference run.
        """
        keys: list[TestKey] = []

        parse = stdio_keys if self.spec.report == "stdio" else junit_keys

        def collect(path: Path, extra: Sequence[str]) -> Graded:
            if path.stat().st_size <= MAX_RESULT_SIZE:
                keys.extend(parse(path.read_text(errors="replace")))
            for src in extra:
                keys.extend(junit_keys(src))
            return Graded(Fraction(1))

        result = self._run_steps(
            repo,
            prepared,
            reader=collect,
            env=ChalkEnv(
                answer="",
                answer_path=self._answer_path(),
                question_id=self.task.question_id,
                assignment_id=self.task.assignment_id,
                student_id="solution",
                pass_env=tuple(self.conf.pass_env),
            ),
            timeout=self.conf.timeout or DEFAULT_TIMEOUT,
            on_output_line=None,
            capture_output=True,
            sandbox=self._sandbox(),
        )
        if not keys:
            details = result.feedback or result.stdout or ""
            raise PrepareError(
                f"the reference run of the {self.name} profile has no tests in its "
                f"report{self._hint()}:\n{details}".rstrip()
            )
        return {key: key[1] if key[0] == "stdio" else "::".join(key) for key in dict.fromkeys(keys)}

    def _env(self, variables: Mapping[str, str]) -> dict[str, str | None]:
        env: dict[str, str | None] = {k: render(v, variables) for k, v in self.spec.env.items()}
        env.update(dict.fromkeys(self.spec.unset))
        return env

    def _command(self, command: str, variables: Mapping[str, str]) -> str:
        quoted = {k: shlex.quote(v) for k, v in variables.items()}
        quoted["tests"] = " ".join(map(shlex.quote, self.tests))
        return render(command, quoted)

    def _hint(self) -> str:
        return " (add the reference solution to the question)" if self.solution is None else ""

    def _template(self) -> Path:
        template = self.task.template
        if template is None:
            raise PrepareError(f"the {self.name} profile needs a template directory")
        return template

    def _trusted(self) -> list[str]:
        return [*self.tests, *self.spec.trusted]

    def _cache_root(self) -> Path:
        path = self.cache_dir if self.cache_dir is not None else self.task.root / ".chalk" / "cache"
        path.mkdir(parents=True, exist_ok=True)
        return path


def _notes(found: list[str], refused: list[str]) -> str | None:
    lines: list[str] = []
    if found:
        lines += ["Suspicious code (the score was not changed):", *(f"- {f}" for f in found)]
    if refused:
        lines += ["Refused by the guard:", *(f"- {r}" for r in refused)]
    return "\n".join(lines) or None


def junit_keys(src: str) -> list[TestKey]:
    """
    The (classname, name) pairs of the tests in a JUnit report, without the
    entries for collection errors, which have no class name.
    """
    try:
        root = ET.fromstring(src)
    except ET.ParseError:
        return []
    keys: dict[TestKey, None] = {}
    for case in root.iter("testcase"):
        if classname := case.get("classname"):
            keys[(classname, case.get("name") or "")] = None
    return list(keys)


def seed_workdir(root: Path, seeds: Mapping[str, Path]) -> None:
    """
    Copy each source to its path in root, keeping the modification times,
    and touch the other files of root. Build tools such as cargo rebuild a
    file when it is newer than the last build; the student's files may be
    older than the copy, so they are touched to force the rebuild.

    On file systems with reflinks (btrfs, xfs) the copy is instant.
    """
    if not seeds:
        return
    for name, source in seeds.items():
        check_relative(name)
        target = root / name
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        elif target.exists() or target.is_symlink():
            target.unlink()
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["cp", "-a", "--reflink=auto", str(source), str(target)], check=True)

    seeded = {root / name for name in seeds}
    for base, dirs, files in root.walk():
        dirs[:] = [d for d in dirs if base / d not in seeded]
        for name in files:
            if base / name not in seeded:
                os.utime(base / name, follow_symlinks=False)


def _run(
    command: str, *, cwd: Path, env: dict[str, str], timeout: float
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise PrepareError(f"{command} timed out") from e
