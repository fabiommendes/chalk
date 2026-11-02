from pathlib import Path

import pytest

from chalk.core import Classroom


def roster_text(classroom: Path) -> str:
    return (classroom / "roster.csv").read_text()


class TestSharedSchema:
    def test_school_id_is_the_student_id(self, classroom: Path) -> None:
        roster = Classroom.load().roster
        assert list(roster) == ["0001", "0002", "0003"]
        assert roster["0001"].name == "Alice Anderson"
        assert roster["0001"].extra["username"] == "alice"
        assert roster["0001"].github == "alice"

    def test_status(self, classroom: Path) -> None:
        roster = Classroom.load().roster
        assert roster["0001"].active
        assert roster["0003"].status == "dropped"
        assert not roster["0003"].active

    def test_save_round_trips_the_file(self, classroom: Path) -> None:
        before = roster_text(classroom)
        Classroom.load().roster.save()
        assert roster_text(classroom) == before

    def test_save_keeps_rows_without_id_and_unknown_columns(self, classroom: Path) -> None:
        path = classroom / "roster.csv"
        lines = path.read_text().splitlines()
        lines = [lines[0] + ",turma"] + [line + ",A" for line in lines[1:]]
        path.write_text("\n".join(lines) + "\n")

        roster = Classroom.load().roster
        roster["0002"].email = "bob@new.example.com"
        roster.save()

        text = roster_text(classroom)
        assert text.splitlines()[0] == "school_id,username,name,email,github,status,turma"
        assert ",dave,Dave Davis,dave@example.com,,active,A" in text
        assert "0002,bob,Bob Brown,bob@new.example.com,bob,active,A" in text

    def test_duplicate_ids_are_rejected(self, classroom: Path) -> None:
        path = classroom / "roster.csv"
        path.write_text(path.read_text() + "0001,alice2,Alice Again,,,active\n")
        with pytest.raises(ValueError, match="Duplicate"):
            Classroom.load().get_roster()


class TestIdColumn:
    def test_legacy_id_column(self, classroom: Path) -> None:
        (classroom / "roster.csv").write_text("id,name\n0001,Alice\n0002,Bob\n")
        roster = Classroom.load().roster
        assert list(roster) == ["0001", "0002"]
        roster.save()
        assert roster_text(classroom) == "id,name\n0001,Alice\n0002,Bob\n"

    def test_student_id_option(self, classroom: Path) -> None:
        toml = classroom / "chalk.toml"
        toml.write_text(toml.read_text() + 'student_id = "username"\n')
        roster = Classroom.load().roster
        assert list(roster) == ["alice", "bob", "carol", "dave"]
        assert roster["alice"].extra["school_id"] == "0001"

    def test_missing_id_column(self, classroom: Path) -> None:
        toml = classroom / "chalk.toml"
        toml.write_text(toml.read_text() + 'student_id = "matricula"\n')
        with pytest.raises(ValueError, match="matricula"):
            Classroom.load().get_roster()


def test_init_writes_shared_header(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from typer.testing import CliRunner

    from chalk.cli import app

    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["init", "-c", "turma", "-t", "Professor"])
    assert result.exit_code == 0, result.output
    header = (tmp_path / "roster.csv").read_text()
    assert header == "school_id,username,name,email,github,status\n"
