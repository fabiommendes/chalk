"""
`chalk clear` removes what chalk generates and nothing the teacher wrote.
"""

from typer.testing import CliRunner

from chalk.cli import app


def test_clear_removes_the_profile_cache(classroom) -> None:
    cache = classroom / ".chalk" / "cache" / "python-pytest-0123"
    cache.mkdir(parents=True)
    (cache / "file").write_text("x")
    old = classroom / "p1" / "q1" / "tmp-old"
    old.mkdir(parents=True)

    result = CliRunner().invoke(app, ["clear"])
    assert result.exit_code == 0, result.output
    assert not (classroom / ".chalk" / "cache").exists()
    assert not old.exists()
    assert (classroom / "roster.csv").exists()
