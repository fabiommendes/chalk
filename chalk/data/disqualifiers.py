import subprocess
import tempfile
from collections.abc import Callable
from logging import getLogger
from pathlib import Path

import opt

from ..core import Disqualification, StudentId, disqualification
from ..question import AnyAnswer

type ResponseDisqualifier = Callable[[StudentId, AnyAnswer], Disqualification | None]
type Disqualifier[T] = Callable[[T], Disqualification | None]

VALIDATOR_REGISTRY: dict[str, ResponseDisqualifier] = {}
EXTENSION_MAPPINGS: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
}
log = getLogger(__name__)


def register(
    name: str | None = None,
) -> Callable[[ResponseDisqualifier], ResponseDisqualifier]:
    """
    A decorator to register a validator function in the VALIDATOR_REGISTRY.
    """

    def decorator(fn: ResponseDisqualifier) -> ResponseDisqualifier:
        validator_name = name or fn.__name__
        VALIDATOR_REGISTRY[validator_name] = fn
        return fn

    return decorator


def get_disqualifier(name: str) -> ResponseDisqualifier | None:
    """
    Get a validator function from the VALIDATOR_REGISTRY by name.
    """
    return VALIDATOR_REGISTRY.get(name)


def get_disqualifier_from_extension(suffix: str) -> ResponseDisqualifier | None:
    """
    Get a validator function based on the file extension of the answer file.
    """
    suffix = "." + suffix.lower().removeprefix(".")
    return opt.map(get_disqualifier, EXTENSION_MAPPINGS.get(suffix))


def string_based(
    disqualifier: Callable[[str], Disqualification | None],
) -> ResponseDisqualifier:
    """
    A helper function to create a ResponseDisqualifier from a simple string
    disqualification function.
    """

    def validator_fn(student_id: StudentId, answer: AnyAnswer) -> Disqualification | None:
        if isinstance(answer, str):
            return disqualifier(answer)
        return disqualification.InvalidInput()

    validator_fn.__name__ = disqualifier.__name__
    return validator_fn


def temp_file_disqualifier(
    file_name: str,
) -> Callable[[Disqualifier[Path]], ResponseDisqualifier]:
    """
    A helper function to create a ResponseDisqualifier from a disqualification function that
    operates on a temporary file.

    This is useful to wrap external tools like compilers, linters, etc. that
    expect file input. The file is automatically cleaned up after the disqualifier
    function is called.
    """

    def decorator(disqualifier: Disqualifier[Path]) -> ResponseDisqualifier:
        @string_based
        def disqualifier_fn(code: str) -> Disqualification | None:
            prefix, sep, suffix = file_name.partition(".")
            suffix = sep + suffix if sep else ""

            with tempfile.NamedTemporaryFile(
                mode="w+",
                delete=True,
                prefix=prefix,
                suffix=suffix,
            ) as tmp_file:
                tmp_file.write(code)
                tmp_file.flush()
                return disqualifier(Path(tmp_file.name))

        disqualifier_fn.__name__ = disqualifier.__name__
        return disqualifier_fn

    return decorator


# ==============================================================================
# Code syntax validators
# ==============================================================================
@register("python")
@register("py")
@string_based
def python_syntax_validator(code: str) -> Disqualification | None:
    """
    Ensure that the response contains valid Python code.
    """

    try:
        compile(code, "<string>", "exec")
    except SyntaxError:
        return disqualification.InvalidInput()

    return None


@register("js")
@register("javascript")
@temp_file_disqualifier("script.js")
def javascript_syntax_validator(
    path: Path,
) -> Disqualification | None:
    """
    Ensure that the response contains valid JavaScript code.
    """

    try:
        result = subprocess.run(
            ["node", "--check", "-e", str(path)],
            check=True,
            capture_output=True,
            text=True,
        )
        log.debug(f"node: {result.stdout}")
    except subprocess.SubprocessError:
        return disqualification.InvalidInput()

    return None
