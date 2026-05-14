from pathlib import Path

from .exceptions import Error
from .models import SPREADSHEET_EXTENSIONS, STRUCTURED_DATA_EXTENSIONS


def find_project_root(path: Path | None = None) -> Path:
    """
    Locate the root of the Chalk project by looking for the chalk.toml configuration
    or the roster file.

    Raises RuntimeError if no suitable root is found.
    """

    if path is None:
        path = Path.cwd()

    while path:
        if is_project_root(path):
            return path
        parent = path.parent
        if parent == path:
            break
        path = parent

    raise Error.CONFIG_NOT_FOUND()


def is_project_root(path: Path) -> bool:
    """
    Check if path is a project root.
    """
    if not path.is_dir():
        return False

    if (path / "chalk.toml").exists():
        return True

    for p in path.glob("roster.*"):
        if p.suffix in SPREADSHEET_EXTENSIONS or p.suffix in STRUCTURED_DATA_EXTENSIONS:
            return True

    return False


def get_conf_file(path: Path | None = None) -> Path:
    """
    Locate the chalk.toml configuration file by looking for it in the given path and its parents.

    Raises RuntimeError if no configuration file is found.
    """
    root = find_project_root(path)

    conf_file = root / "chalk.toml"
    if conf_file.exists():
        return conf_file

    raise Error.CONFIG_NOT_FOUND()


def get_roster_file(path: Path | None = None) -> Path:
    """
    Locate the roster file by looking for it in the given path and its parents.

    Raises RuntimeError if no roster file is found.
    """
    root = find_project_root(path)

    roster_files = []
    for p in root.glob("roster.*"):
        if p.suffix in SPREADSHEET_EXTENSIONS or p.suffix in STRUCTURED_DATA_EXTENSIONS:
            roster_files.append(p)

    if len(roster_files) == 1:
        return roster_files[0]
    elif len(roster_files) > 1:
        raise Error.MULTIPLE_ROSTERS_FOUND()

    raise Error.ROSTER_NOT_FOUND()
