"""
The rust-cargo profile: build the student's crate and run the template's
integration tests with cargo nextest.

Steps:

1. Prepare (trusted, once per question, cached): `cargo fetch --locked`
   downloads the dependencies of the template lock file to a CARGO_HOME in
   the cache, and `cargo build --tests` of the template plus the reference
   solution fills a target directory in the cache. Then `cargo nextest list`
   collects the expected tests.
2. Build (untrusted, once per student, in the sandbox, offline): the cached
   target directory is copied to the project, so only the student's crate
   compiles. A failure gives the `build-error` result, with the compiler
   output as feedback.
3. Test (untrusted, in the sandbox, offline): `cargo nextest run` writes a
   JUnit report.
4. Score (trusted, in chalk): as in python-pytest, only the collected tests
   count.

Cargo.toml, Cargo.lock, `.cargo/`, `.config/` and the test directories come
from the template: the student cannot add dependencies, change the build
configuration or the test runner.
"""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from fractions import Fraction
from logging import getLogger
from pathlib import Path

from ..core import disqualification as dq
from ..core.grader import DEFAULT_TIMEOUT
from .profiles import PrepareError, TestKey, install_trusted_files, read_report
from .repo import Repo
from .script_grader import ScriptGrader
from .script_runner import ChalkEnv, Result, Sandbox, ScriptRunner

__all__ = ["CargoGrader"]

log = getLogger(__name__)

#: Files of the template that replace the student's ones, or are removed
#: from the student's project when the template does not have them.
TRUSTED_FILES = ("Cargo.toml", "Cargo.lock", ".cargo", ".config")

#: Only integration tests (the tests/ directory) count.
FILTER = "kind(test)"

#: Default timeout of the build step, in seconds.
BUILD_TIMEOUT = 120.0

#: Largest compiler output kept as feedback, in characters.
MAX_BUILD_FEEDBACK = 8000

NEXTEST_CONFIG = '[profile.chalk]\nfail-fast = false\n\n[profile.chalk.junit]\npath = "junit.xml"\n'


@dataclass(frozen=True)
class Toolchain:
    sysroot: Path
    nextest: Path

    @property
    def cargo(self) -> Path:
        return self.sysroot / "bin" / "cargo"

    def env(self, cargo_home: Path) -> dict[str, str]:
        path = os.pathsep.join([str(self.sysroot / "bin"), str(self.nextest.parent)])
        return {
            "CARGO_HOME": str(cargo_home),
            "RUSTC": str(self.sysroot / "bin" / "rustc"),
            "PATH": f"{path}{os.pathsep}{os.environ.get('PATH', '')}",
            "CARGO_TERM_COLOR": "never",
        }


@dataclass(frozen=True)
class Prepared:
    toolchain: Toolchain
    cache: Path
    tests: dict[TestKey, str]

    @property
    def home(self) -> Path:
        return self.cache / "home"

    @property
    def target(self) -> Path:
        return self.cache / "target"

    @property
    def config(self) -> Path:
        return self.cache / "nextest.toml"


@dataclass(frozen=True)
class CargoGrader(ScriptGrader):
    """
    Grades a Rust crate with the integration tests of the template.
    """

    #: Reference solution: a directory, or the text of the answer.
    solution: str | Path | None = None
    cache_dir: Path | None = None
    _prepared: list[Prepared] = field(default_factory=list, compare=False, repr=False)

    def prepare(self) -> Prepared:
        """
        Fetch the dependencies, build the reference solution and collect the
        expected tests, once per grader.
        """
        if self._prepared:
            return self._prepared[0]

        template = self._template()
        toolchain = find_toolchain(template)
        cache = self._prepare_cache(template, toolchain)
        tests = self._collect(toolchain, cache, template)
        self._prepared.append(Prepared(toolchain, cache, tests))
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
        overlays = install_trusted_files(repo.root, self._template(), self._trusted())
        copy_target(prepared.target, repo.root / "target")

        if sandbox is not None:
            sandbox = replace(
                sandbox,
                readable=(
                    *sandbox.readable,
                    prepared.home,
                    prepared.config,
                    prepared.toolchain.sysroot,
                    prepared.toolchain.nextest,
                ),
                overlays=(*sandbox.overlays, *overlays),
            )
        extra_env: dict[str, str | None] = {**prepared.toolchain.env(prepared.home)}
        extra_env["CARGO_TARGET_DIR"] = None
        run = dict(
            env=env,
            extra_env=extra_env,
            on_output_line=on_output_line,
            capture_output=capture_output,
            sandbox=sandbox,
        )

        build = ScriptRunner(
            None,
            repo,
            command="cargo build --tests --offline --locked",
            timeout=self.conf.build.timeout or BUILD_TIMEOUT,
            limits=self.conf.build.limits or self.conf.limits,
            log_name="chalk.build",
            **run,  # type: ignore[arg-type]
        ).run()
        if build.score == dq.Timeout():
            return replace(build, feedback="The build took too long.")
        if build.return_code != 0:
            return self._build_error(build)

        expected = prepared.tests
        command = (
            f"cargo nextest run --offline --locked --profile chalk "
            f"--config-file {shlex.quote(str(prepared.config))} -E {shlex.quote(FILTER)}; "
            'cp target/nextest/chalk/junit.xml "$CHALK_RESULT"'
        )
        return ScriptRunner(
            None,
            repo,
            command=command,
            result_reader=lambda path: read_report(path, expected),
            timeout=timeout,
            limits=self.conf.limits,
            **run,  # type: ignore[arg-type]
        ).run()

    def _build_error(self, build: Result) -> Result:
        output = build.stdout or ""
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

    def _prepare_cache(self, template: Path, toolchain: Toolchain) -> Path:
        """
        Directory with CARGO_HOME, the target directory of the reference
        solution and the nextest configuration, reused while the manifest,
        the lock file and the compiler do not change. A changed solution
        does not matter: its crate is rebuilt for each student anyway.
        """
        for name in ("Cargo.toml", "Cargo.lock"):
            if not (template / name).is_file():
                raise PrepareError(f"the rust-cargo profile needs {name} in the template")

        version = subprocess.run(
            [toolchain.sysroot / "bin" / "rustc", "-vV"], capture_output=True, text=True
        ).stdout
        digest = hashlib.sha256()
        for data in [
            (template / "Cargo.toml").read_bytes(),
            (template / "Cargo.lock").read_bytes(),
            version.encode(),
        ]:
            digest.update(data + b"\0")
        cache = self._cache_root() / f"cargo-{digest.hexdigest()[:16]}"
        ready = cache / "ready"
        if ready.exists():
            return cache

        shutil.rmtree(cache, ignore_errors=True)
        (cache / "home").mkdir(parents=True)
        (cache / "nextest.toml").write_text(NEXTEST_CONFIG)
        env = {**os.environ, **toolchain.env(cache / "home")}
        env.pop("CARGO_TARGET_DIR", None)
        cargo = str(toolchain.cargo)

        fetch = _run([cargo, "fetch", "--locked"], cwd=template, env=env)
        if fetch.returncode != 0:
            shutil.rmtree(cache, ignore_errors=True)
            raise PrepareError(f"cargo fetch failed for the template:\n{fetch.stderr.strip()}")

        with self.student_repository("chalk-prepare", self.solution) as repo:
            install_trusted_files(repo.root, template, self._trusted())
            env["CARGO_TARGET_DIR"] = str(cache / "target")
            build = _run(
                [cargo, "build", "--tests", "--offline", "--locked"], cwd=repo.root, env=env
            )
        if build.returncode != 0:
            shutil.rmtree(cache, ignore_errors=True)
            hint = (
                "" if self.solution is not None else " (add the reference solution to the question)"
            )
            raise PrepareError(f"building the template failed{hint}:\n{build.stderr.strip()}")

        ready.write_text("")
        log.info(f"Prepared cargo cache {cache}")
        return cache

    def _collect(self, toolchain: Toolchain, cache: Path, template: Path) -> dict[TestKey, str]:
        """
        The integration tests of the template, built with the reference
        solution.
        """
        env = {**os.environ, **toolchain.env(cache / "home")}
        env["CARGO_TARGET_DIR"] = str(cache / "target")
        command = [
            str(toolchain.cargo),
            "nextest",
            "list",
            "--offline",
            "--locked",
            "--message-format",
            "json",
            "-E",
            FILTER,
        ]
        with self.student_repository("chalk-collect", self.solution) as repo:
            install_trusted_files(repo.root, template, self._trusted())
            proc = _run(command, cwd=repo.root, env=env, timeout=self.conf.timeout)

        try:
            suites = json.loads(proc.stdout)["rust-suites"]
        except (json.JSONDecodeError, KeyError, TypeError):
            suites = None
        if proc.returncode != 0 or suites is None:
            raise PrepareError(f"listing the template tests failed:\n{proc.stderr.strip()}")

        tests = {
            (binary, name): f"{binary} {name}"
            for binary, suite in suites.items()
            for name in suite.get("testcases", {})
        }
        if not tests:
            raise PrepareError("the template has no integration tests")
        return tests

    def _template(self) -> Path:
        template = self.question.get_template_path()
        if template is None:
            raise PrepareError("the rust-cargo profile needs a template directory")
        return template

    def _trusted(self) -> list[str]:
        return [*self.conf.tests, *TRUSTED_FILES]

    def _cache_root(self) -> Path:
        if self.cache_dir is not None:
            path = self.cache_dir
        else:
            path = self.question.quiz.classroom.root / ".chalk" / "cache"
        path.mkdir(parents=True, exist_ok=True)
        return path


def find_toolchain(template: Path) -> Toolchain:
    """
    The Rust toolchain for the template (rustup honors its
    rust-toolchain.toml) and cargo-nextest.

    The sandbox calls the toolchain binaries directly, because the rustup
    proxies need the rustup home, which is hidden.
    """
    rustc = shutil.which("rustc")
    if rustc is None:
        raise PrepareError("rustc not found: install Rust to use the rust-cargo profile")
    proc = subprocess.run(
        [rustc, "--print", "sysroot"], cwd=template, capture_output=True, text=True
    )
    if proc.returncode != 0:
        raise PrepareError(f"rustc --print sysroot failed:\n{proc.stderr.strip()}")
    nextest = shutil.which("cargo-nextest")
    if nextest is None:
        raise PrepareError("cargo-nextest not found: run `cargo install cargo-nextest --locked`")
    return Toolchain(Path(proc.stdout.strip()), Path(nextest))


def copy_target(source: Path, target: Path) -> None:
    """
    Copy the cached target directory to the student's project, keeping the
    modification times cargo uses to decide what to rebuild. On file systems
    with reflinks (btrfs, xfs) the copy is instant.
    """
    if target.is_dir() and not target.is_symlink():
        shutil.rmtree(target)
    elif target.exists() or target.is_symlink():
        target.unlink()
    subprocess.run(["cp", "-a", "--reflink=auto", str(source), str(target)], check=True)

    # Cargo rebuilds a crate when a source file is newer than the last
    # build. The student's files may be older than the cache (they are
    # copied before the cache is prepared, or keep old times), so they are
    # touched to force the rebuild of the student's crate.
    for base, dirs, files in target.parent.walk():
        if base == target.parent:
            dirs[:] = [d for d in dirs if d != target.name]
        for name in files:
            os.utime(base / name)


def _run(
    command: list[str], *, cwd: Path, env: dict[str, str], timeout: float | None = None
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout or DEFAULT_TIMEOUT * 10,
        )
    except subprocess.TimeoutExpired as e:
        raise PrepareError(f"{' '.join(command[:3])} timed out") from e
