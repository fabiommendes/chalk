import contextlib
import io
import itertools
import sys
from logging import getLogger
from pathlib import Path
from typing import IO, Any, Generator, Iterable, Iterator, Literal

import opt

log = getLogger(__name__)

type StreamLike = IO[str] | Path | None


@contextlib.contextmanager
def as_stream(file: StreamLike) -> Generator[IO[str]]:
    """
    Convert a file path or file-like object to a file-like object that can be
    used inside a with block.

    If file is None, redirect to stdout.
    """
    stream: IO[str] | None = None
    try:
        if isinstance(file, Path):
            stream = file.open("w", encoding="utf-8")
            yield stream
        elif file is None:
            yield sys.stdout
        else:
            stream = file
            yield file
    finally:
        if stream is not None:
            stream.close()


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


def write_text(file: Path, data: str, *, encoding: str = "utf-8", rotate: int | bool = 5) -> int:
    """
    Write text to a file, creating parent directories if necessary.

    It rotates backups if the file already exists and rotate is set to a
    positive integer.
    """
    file.parent.mkdir(parents=True, exist_ok=True)
    if rotate is True:
        rotate = 5
    if not rotate:
        return file.write_text(data, encoding=encoding)

    saved = opt.call(file.read_text, encoding=encoding) or ""
    if saved == data:
        log.debug("write_text: no changes to %s, skipping write", file)
        return 0

    backup_rotate(file, max_backups=int(rotate))
    return file.write_text(data, encoding=encoding)


def backup_rotate(
    file: Path,
    *,
    max_backups: int = 5,
    prefix: str = ".",
    bak: str = ".bak-{}",
    start: int = 1,
) -> None:
    """
    Rotate a file by renaming it to a backup file with an incremented number.
    If the maximum number of backups is reached, the oldest backup is deleted.

    Do not create backups if the file does not exist.
    """
    backups = list(
        itertools.islice(
            iter_backup_rotations(file, prefix=prefix, bak=bak, start=start),
            max_backups,
        )
    )
    if not backups:
        return

    if backups[-1].exists():
        backups[-1].unlink()

    mapping = list(zip([file] + backups[:-1], backups))
    mapping.reverse()
    rename_all(mapping)


def iter_backup_rotations(
    file: Path, /, *, prefix: str = ".", bak: str = ".bak-{}.", start: int = 1
) -> Iterator[Path]:
    """
    Infinite iterator over rotation paths for backup files.

    iter_backup_rotations("file.txt") yields:

    - .file.bak-1.txt
    - .file.bak-2.txt
    - .file.bak-3.txt
    - ...

    """
    if "{}" not in bak:
        msg = "bak string must contain a '{}' placeholder for the rotation number"
        raise ValueError(msg)

    parent = file.parent
    stem = file.stem
    suffix = file.suffix

    for i in range(start, sys.maxsize):
        bak_part = bak.format(i)
        yield parent / f"{prefix}{stem}{bak_part}{suffix}"


def rename_all(renames: Iterable[tuple[Path, Path]], /, force: bool = False) -> None:
    """
    Rename files in a batch, ensuring that no files are overwritten.

    Skip files that do not exist and never overwrite existing files.

    Raises a ValueError if any of the renames would result in a conflict.

    If force is True, overwrite existing files outside of the renaming mapping.
    """

    indirect: list[tuple[Path, Path]] = []
    targets = set[Path]()
    msg = "Cannot rename files due to conflicts with existing files."
    error = ValueError(msg)

    def rename(src: Path, target: Path) -> None:
        log.debug("rename_all: %s => %s", src, target)
        src.rename(target)

    for src, target in renames:
        targets.add(target)

        if not src.exists():
            continue
        if target.exists():
            indirect.append((src, target))
        else:
            rename(src, target)

    while indirect:
        # Search for a valid rename that may have been opened in a previous
        # iteration of the algorithm
        for i, (src, target) in enumerate(indirect):
            if not target.exists():
                rename(src, target)
                del indirect[i]
                break
        # If we reach this point, it means that all remaining renames are blocked by
        # existing files. This is a conflict and we cannot proceed.
        else:
            if not force:
                raise error

        # We are now in the forced mode. This means we overwrite existing targets
        # if they are not part of the renaming mapping.
        for i, (src, target) in enumerate(indirect):
            if target not in targets:
                rename(src, target)
                del indirect[i]
                break
        else:
            raise error


def remove_backups(
    file: Path, /, *, prefix: str = ".", bak: str = ".bak-{}.", start: int = 1
) -> None:
    """
    Remove all backup files for a given file.
    """

    extra = 10
    for backup in iter_backup_rotations(file, prefix=prefix, bak=bak, start=start):
        if backup.exists():
            backup.unlink()
            continue
        elif extra <= 0:
            break
        else:
            extra -= 1


CompressedFormat = Literal["none", "zip", "tar.bz2", "tar.gz", "tar.xz", "tar.zst"]
_CompressedFormatValues: set[CompressedFormat] = set(CompressedFormat.__args__)  # type: ignore


def batch_save(
    data: dict[Path, str],
    /,
    *,
    output: Path,
    compression: CompressedFormat | None = None,
    exists: Literal["skip", "raise", "overwrite"] = "raise",
) -> None:
    """
    Save a batch of data to files in a directory.

    Each key in the data dictionary is used as the filename, and the value is
    written to the file.

    Args:
        data:
            A dictionary mapping file paths to their corresponding content.
        output:
            The base output path where the files will be saved. If compression is
            specified, this will be the path to the compressed file.
        compression:
            The compression format to use. If None, it will be inferred from the
            output path's suffix.
        exists:
            The action to take if the output path already exists.
    """

    for path in data.keys():
        if path.parent != Path("."):
            msg = f"Invalid path {path}. Only top-level files are allowed in batch_save."
            raise ValueError(msg)

    if compression is None:
        if (fmt := "".join(output.suffixes).removeprefix(".")) in _CompressedFormatValues:
            compression = fmt
        else:
            compression = "none"

    # Save to directory
    if compression == "none":
        output.mkdir(parents=True, exist_ok=True)

        if exists == "raise" and any((output / path).exists() for path in data.keys()):
            raise FileExistsError(f"Output directory {output} already exists.")

        for path, content in data.items():
            file_path = output / path
            write_text(file_path, content)
        return

    # Save compressed file
    if exists == "raise" and output.exists():
        raise FileExistsError(f"Output file {output} already exists.")

    output.parent.mkdir(parents=True, exist_ok=True)
    match compression:
        case "zip":
            import zipfile

            with zipfile.ZipFile(
                output,
                "w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            ) as zip:
                for path, content in data.items():
                    zip.writestr(str(path), content)

        case "tar.bz2" | "tar.gz" | "tar.lzma" | "tar.xz" | "tar.zst":
            import tarfile

            mode: Any = f"w:{compression.removeprefix('tar.')}"

            with tarfile.open(output, mode) as tar:
                for path, content in data.items():
                    raw_data = content.encode("utf-8")
                    info = tarfile.TarInfo(name=str(path))
                    info.size = len(raw_data)
                    with io.BytesIO(raw_data) as fileobj:
                        tar.addfile(info, fileobj=fileobj)

        case _:
            raise ValueError(f"Unsupported compression format: {compression!r}")
