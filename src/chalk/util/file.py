import contextlib
import sys
from pathlib import Path
from typing import IO, Generator

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
