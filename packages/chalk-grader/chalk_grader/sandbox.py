"""
Run autograder scripts inside a bubblewrap (bwrap) sandbox.

The sandbox uses a block list instead of an allow list: the whole file system
is mounted read only, and the places where secrets usually live (home
directories, /run, /tmp) are replaced by empty tmpfs mounts. System packages
stay visible without configuration. A few paths inside the hidden places are
mounted back read only: the directories in PATH, the Python running chalk,
the script, and the paths listed in `autograder.mounts`.

The working directory and the result directory are the only writable places
besides the tmpfs mounts. The network is off unless `autograder.network` is
"host".
"""

from __future__ import annotations

import functools
import os
import shutil
import subprocess
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path

__all__ = ["HIDDEN", "BwrapUnavailable", "bwrap_command", "check_bwrap"]

#: Directories replaced by empty tmpfs mounts inside the sandbox.
HIDDEN = ("/home", "/root", "/run", "/tmp", "/var/tmp", "/mnt", "/media")


class BwrapUnavailable(RuntimeError):
    pass


@functools.cache
def check_bwrap() -> str:
    """
    Path to a bwrap executable that can create a sandbox.

    Raises BwrapUnavailable otherwise, with a message that tells how to fix it.
    """
    bwrap = shutil.which("bwrap")
    if bwrap is None:
        msg = "bwrap not found: install bubblewrap or set `autograder.sandbox: none`"
        raise BwrapUnavailable(msg)

    probe = subprocess.run(
        [bwrap, "--ro-bind", "/", "/", "--unshare-all", "--", "true"],
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0:
        msg = f"bwrap cannot create a sandbox: {probe.stderr.strip()}"
        raise BwrapUnavailable(msg)
    return bwrap


# r2: adr-0005
def bwrap_command(
    command: str,
    *,
    workdir: Path,
    writable: Iterable[Path] = (),
    readable: Iterable[Path] = (),
    overlays: Iterable[tuple[Path, Path]] = (),
    network: bool = False,
    env: dict[str, str] | None = None,
    hidden: Iterable[Path] = (),
) -> list[str]:
    """
    Command line that runs the shell command inside the sandbox.

    Args:
        command: shell command, run with /bin/sh -c.
        workdir: writable working directory, also the current directory.
        writable: other directories mounted read and write.
        readable: paths mounted back read only, when they are inside a hidden
            directory.
        overlays: (source, target) pairs mounted read only after the writable
            directories, to protect files inside the working directory.
        network: share the host network.
        env: environment of the command, used to find PATH and HOME.
        hidden: other directories replaced by empty tmpfs mounts.
    """
    env = os.environ if env is None else env
    home = env.get("HOME")
    hidden = [*HIDDEN, *(str(p.resolve()) for p in hidden)]
    if home and not _inside(Path(home), hidden):
        hidden.append(home)

    args = [check_bwrap(), "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc"]
    for path in hidden:
        if Path(path).is_dir():
            args += ["--tmpfs", path]

    reexposed = [*_path_dirs(env), *_python_dirs(), *readable]
    for path in _dedup(p.resolve() for p in reexposed):
        if path.exists() and _inside(path, hidden):
            args += ["--ro-bind", str(path), str(path)]

    # A symlink inside a hidden directory (uv links cpython-3.13 to
    # cpython-3.13.5) is recreated, so paths through it still work.
    for path in _dedup(Path(os.path.abspath(p)) for p in reexposed):
        if path.is_symlink() and _inside(path, hidden):
            args += ["--symlink", os.readlink(path), str(path)]

    for path in _dedup(p.resolve() for p in [workdir, *writable]):
        args += ["--bind", str(path), str(path)]

    for source, target in overlays:
        args += ["--ro-bind", str(source.resolve()), str(target)]

    if network and Path("/run/systemd/resolve").is_dir():
        # /etc/resolv.conf usually links here, and /run is hidden.
        args += ["--ro-bind", "/run/systemd/resolve", "/run/systemd/resolve"]

    args += ["--unshare-all", "--die-with-parent", "--new-session"]
    if network:
        args += ["--share-net"]
    args += ["--chdir", str(workdir.resolve()), "--", "/bin/sh", "-c", command]
    return args


def _path_dirs(env: dict[str, str] | os._Environ[str]) -> list[Path]:
    return [Path(p) for p in env.get("PATH", "").split(os.pathsep) if p]


def _python_dirs() -> list[Path]:
    return [Path(sys.prefix), Path(sys.base_prefix), Path(sys.executable).resolve().parent]


def _inside(path: Path, roots: Sequence[str]) -> bool:
    return any(path == Path(root) or path.is_relative_to(root) for root in roots)


def _dedup(paths: Iterable[Path]) -> list[Path]:
    """
    Remove repeated paths and paths inside another one in the list.
    """
    result: list[Path] = []
    for path in sorted(set(paths), key=lambda p: len(p.parts)):
        if not any(path.is_relative_to(other) for other in result):
            result.append(path)
    return result
