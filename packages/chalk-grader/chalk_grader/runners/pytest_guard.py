"""
pytest plugin of the python-pytest profile, loaded with `-p pytest_guard`.

The student's code runs in the pytest process, so it could rewrite the JUnit
report after pytest writes it (an atexit handler is enough). This plugin
installs an audit hook (PEP 578), which cannot be removed once installed,
that refuses:

- any access to the report directory, except by pytest's junitxml plugin
  with no student code in the call stack;
- writes under /proc, subprocesses, ctypes and the gc functions that find
  live objects (such as this hook), when the student's code is in the call
  stack.

Student code is code from a file of the working directory that is not one
of the test paths or the root conftest.py, or code compiled from a string.

This raises the bar; it is not a sandbox. Each refusal is printed to stderr
with the prefix "chalk-guard:", and chalk turns those lines into notes for
the teacher.

It also refuses to run when a module of the student was loaded before the
plugin, which happens when a file has the name of a module of the standard
library that pytest uses (random.py, xml/) or is a sitecustomize.py.

Environment: CHALK_GUARD=off disables it; CHALK_GUARD_TRUSTED lists the test
paths, separated by spaces; CHALK_RESULT is the report file.
"""

import os
import sys

#: Prefix of the lines chalk reads from the output.
PREFIX = "chalk-guard: "

#: Name of the directory of the report: chalk's ScriptRunner creates it with
#: tempfile.mkdtemp(prefix="chalk-result-").
REPORT_DIR = "chalk-result-"

_EVENTS_WITH_PATHS = frozenset(
    {
        "open",
        "os.rename",
        "os.link",
        "os.symlink",
        "os.remove",
        "os.rmdir",
        "os.mkdir",
        "os.truncate",
        "os.chmod",
        "os.chown",
        "os.utime",
        "os.chdir",
        "os.listdir",
        "os.scandir",
        "shutil.copyfile",
        "shutil.copymode",
        "shutil.copystat",
        "shutil.copytree",
        "shutil.move",
        "shutil.rmtree",
    }
)
_STUDENT_EVENTS = frozenset(
    {
        "subprocess.Popen",
        "os.system",
        "os.exec",
        "os.posix_spawn",
        "os.spawn",
        "pty.spawn",
        "gc.get_objects",
        "gc.get_referrers",
        "gc.get_referents",
    }
)
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC

#: Modules of the student loaded before this plugin.
early: list[str] = []


def _install() -> None:
    if os.environ.get("CHALK_GUARD", "on") == "off":
        return

    cwd = os.getcwd()
    roots = tuple({os.path.join(cwd, ""), os.path.join(os.path.realpath(cwd), "")})
    trusted = []
    for name in [*os.environ.get("CHALK_GUARD_TRUSTED", "").split(), "conftest.py"]:
        for root in roots:
            path = os.path.normpath(os.path.join(root, name))
            trusted += [path + os.sep, path]
    trusted_paths = tuple(trusted)
    junitxml = os.path.join("_pytest", "junitxml.py")
    getframe = sys._getframe
    write = os.write
    # pytest captures fd 2 during the tests; a copy made now still reaches
    # the output chalk reads.
    err = os.dup(2)
    fspath = os.fspath

    def is_student(filename: str) -> bool:
        if filename.startswith("<"):
            return not filename.startswith("<frozen")
        return filename.startswith(roots) and not filename.startswith(trusted_paths)

    def callers() -> tuple[bool, bool]:
        """
        (student code in the stack, junitxml in the stack).
        """
        student = junit = False
        frame = getframe(2)
        while frame is not None:
            filename = frame.f_code.co_filename
            if is_student(filename):
                student = True
            elif filename.endswith(junitxml):
                junit = True
            frame = frame.f_back
        return student, junit

    def refuse(event: str, args: tuple) -> None:
        # pytest may be in the middle of a line of progress dots.
        text = f"\n{PREFIX}refused {event}{_show(args)}\n"
        try:
            write(err, text.encode(errors="replace"))
        except OSError:
            pass
        raise PermissionError(f"{event} is not allowed while grading")

    def hook(event: str, args: tuple) -> None:
        if event in _EVENTS_WITH_PATHS:
            paths = [a for a in args if isinstance(a, str | bytes | os.PathLike)]
            text = [p if isinstance(p, str) else os.fsdecode(fspath(p)) for p in paths]
            if any(REPORT_DIR in p for p in text):
                student, junit = callers()
                if student or not junit:
                    refuse(event, args)
            elif event == "open" and any(p.startswith("/proc/") for p in text):
                mode, flags = args[1], args[2]
                writes = (mode and any(c in mode for c in "wax+")) or (flags or 0) & _WRITE_FLAGS
                if writes and callers()[0]:
                    refuse(event, args)
        elif event in _STUDENT_EVENTS or event.startswith("ctypes."):
            if callers()[0]:
                refuse(event, args)

    for name, module in list(sys.modules.items()):
        filename = getattr(module, "__file__", None)
        if isinstance(filename, str) and is_student(filename) and not filename.startswith("<"):
            early.append(f"{name} ({os.path.relpath(filename, cwd)})")

    sys.addaudithook(hook)


def _show(args: tuple) -> str:
    text = repr(args)
    return text if len(text) <= 200 else text[:197] + "..."


def pytest_configure(config) -> None:  # noqa: ANN001
    if early:
        import pytest

        names = ", ".join(early)
        msg = (
            f"modules of the project were loaded before the tests: {names}. A file with the "
            "name of a Python standard module (such as random.py) must be renamed."
        )
        os.write(2, f"{PREFIX}{msg}\n".encode())
        raise pytest.UsageError(msg)


_install()
