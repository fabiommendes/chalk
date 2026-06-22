from pathlib import Path
from typing import Iterable


def get_path_from_names(
    base: Path,
    names: Iterable[str],
    /,
    accept_dir: bool = False,
    accept_base: bool = False,
) -> Path | None:
    """
    Get the path to the first existing file or directory with the given names
    within the base path.

    Args:
        base:
            The base path to search within.
        names:
            The names of the files or directories to search for, in order of preference.
        is_dir:
            Whether to look for directories instead of files.
        accept_base:
            Whether to accept the base path itself when a file is required and
            base is a file.
    """
    if accept_base and not accept_dir and base.is_file():
        return base

    for name in names:
        path = base / name
        if path.exists() and path.is_dir() == accept_dir:
            return path
    return None
