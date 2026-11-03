import shutil
import subprocess
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import pytest

from chalk.autograder.profiles import PrepareError
from chalk.autograder.rust_profile import CargoGrader
from chalk.core import disqualification as dq
from chalk.core import models
from tests.test_autograder_sandbox import needs_bwrap

pytestmark = pytest.mark.skipif(
    not (shutil.which("cargo") and shutil.which("cargo-nextest")),
    reason="cargo and cargo-nextest are needed",
)

CARGO_TOML = """
[package]
name = "calc"
version = "0.1.0"
edition = "2021"

[dependencies]
"""

TESTS = """
use calc::{add, sub};

#[test]
fn add_ok() { assert_eq!(add(1, 2), 3); }

#[test]
fn add_zero() { assert_eq!(add(0, 0), 0); }

#[test]
fn sub_ok() { assert_eq!(sub(3, 2), 1); }

mod more {
    #[test]
    fn sub_neg() { assert_eq!(calc::sub(0, 1), -1); }
}
"""

SOLUTION = (
    "pub fn add(a: i32, b: i32) -> i32 { a + b }\npub fn sub(a: i32, b: i32) -> i32 { a - b }\n"
)


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("q") / "template"
    (path / "tests").mkdir(parents=True)
    (path / "Cargo.toml").write_text(CARGO_TOML)
    (path / "tests" / "calc.rs").write_text(TESTS)
    (path / "src").mkdir()
    (path / "src" / "lib.rs").write_text("")
    lock = subprocess.run(
        ["cargo", "generate-lockfile", "--offline"], cwd=path, capture_output=True, text=True
    )
    if lock.returncode != 0:
        pytest.skip(f"cannot lock the template offline: {lock.stderr}")
    shutil.rmtree(path / "src")
    return path


@pytest.fixture(scope="module")
def cache(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("cache")


@pytest.fixture
def solution(tmp_path: Path) -> Path:
    return crate(tmp_path / "solution", SOLUTION)


def crate(root: Path, lib: str, files: dict[str, str] | None = None) -> Path:
    (root / "src").mkdir(parents=True)
    (root / "src" / "lib.rs").write_text(lib)
    for name, content in (files or {}).items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(content)
    return root


def make_grader(template: Path, cache: Path, solution: Path | None, **conf) -> CargoGrader:
    question = SimpleNamespace(
        id="q1",
        quiz=SimpleNamespace(id="p1"),
        root=template.parent,
        get_template_path=lambda: template,
    )
    conf = {"profile": "rust-cargo", "timeout": 120, **conf}
    return CargoGrader(
        script=None,
        question=question,  # type: ignore[arg-type]
        conf=models.Autograder(**conf),
        solution=solution,
        cache_dir=cache,
    )


class Cases:
    sandbox = "none"

    def grade(self, template, cache, solution, root, **conf):
        grader = make_grader(template, cache, solution, sandbox=self.sandbox, **conf)
        return grader("s1", root)

    def test_solution_gets_full_score(self, template, cache, solution) -> None:
        assert self.grade(template, cache, solution, solution).score == 1

    def test_partial_score(self, template, cache, solution, tmp_path) -> None:
        root = crate(
            tmp_path / "s",
            "pub fn add(a: i32, b: i32) -> i32 { a + b }\npub fn sub(_: i32, _: i32) -> i32 { 0 }\n",
        )
        graded = self.grade(template, cache, solution, root)
        assert graded.score == Fraction(2, 4)
        assert "calc::calc sub_ok" in (graded.feedback or "")

    def test_build_error(self, template, cache, solution, tmp_path) -> None:
        root = crate(tmp_path / "s", "pub fn add(a: i32, b: i32) -> i32 { a + }\n")
        graded = self.grade(template, cache, solution, root)
        assert graded.score == dq.BuildError()
        assert "does not compile" in (graded.feedback or "")
        assert "error" in (graded.feedback or "")

    def test_build_error_as_zero(self, template, cache, solution, tmp_path) -> None:
        root = crate(tmp_path / "s", "this is not rust\n")
        assert self.grade(template, cache, solution, root, on_build_error="zero").score == 0

    def test_build_error_to_manual_grading(self, template, cache, solution, tmp_path) -> None:
        root = crate(tmp_path / "s", "this is not rust\n")
        assert self.grade(template, cache, solution, root, on_build_error="manual") is None

    def test_student_build_config_is_replaced(self, template, cache, solution, tmp_path) -> None:
        files = {
            "Cargo.toml": CARGO_TOML + 'evil = "1"\n',
            ".cargo/config.toml": '[target.x86_64-unknown-linux-gnu]\nrunner = "true"\n',
            "tests/calc.rs": "",
            "tests/fake.rs": "#[test] fn fake() {}\n",
        }
        root = crate(
            tmp_path / "s",
            "pub fn add(a: i32, b: i32) -> i32 { 0 }\npub fn sub(a: i32, b: i32) -> i32 { 0 }\n",
            files,
        )
        assert self.grade(template, cache, solution, root).score == Fraction(1, 4)


class TestWithoutSandbox(Cases):
    def test_cache_is_reused(self, template, cache, solution) -> None:
        self.grade(template, cache, solution, solution)
        self.grade(template, cache, solution, solution)
        assert len(list(cache.glob("cargo-*"))) == 1

    def test_template_without_lock(self, tmp_path, cache) -> None:
        template = tmp_path / "template"
        template.mkdir()
        (template / "Cargo.toml").write_text(CARGO_TOML)
        with pytest.raises(PrepareError, match=r"Cargo\.lock"):
            make_grader(template, cache, None, sandbox="none").prepare()


@needs_bwrap
class TestWithSandbox(Cases):
    sandbox = "bwrap"

    def test_tests_are_read_only(self, template, cache, solution, tmp_path) -> None:
        build_rs = 'fn main() { let _ = std::fs::write("tests/calc.rs", "#[test] fn ok() {}"); }\n'
        files = {"build.rs": build_rs}
        root = crate(
            tmp_path / "s",
            "pub fn add(a: i32, b: i32) -> i32 { 0 }\npub fn sub(a: i32, b: i32) -> i32 { 0 }\n",
            files,
        )
        assert self.grade(template, cache, solution, root).score == Fraction(1, 4)


def test_parse_build_error() -> None:
    assert dq.parse(str(dq.BuildError())) == dq.BuildError()
