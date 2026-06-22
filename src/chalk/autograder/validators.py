import subprocess
import tempfile
from logging import getLogger
from pathlib import Path
from typing import Callable

import opt

from ..core import Disqualification, Response, StudentId, disqualification

type ResponseValidator = Callable[[Response, StudentId], Disqualification | None]
type ValidatorFn[T] = Callable[[T], Disqualification | None]

VALIDATOR_REGISTRY: dict[str, ResponseValidator] = {}
EXTENSION_MAPPINGS: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
}
log = getLogger(__name__)


def register(
    name: str | None = None,
) -> Callable[[ResponseValidator], ResponseValidator]:
    """
    A decorator to register a validator function in the VALIDATOR_REGISTRY.
    """

    def decorator(fn: ResponseValidator) -> ResponseValidator:
        validator_name = name or fn.__name__
        VALIDATOR_REGISTRY[validator_name] = fn
        return fn

    return decorator


def get_validator(name: str) -> ResponseValidator | None:
    """
    Get a validator function from the VALIDATOR_REGISTRY by name.
    """
    return VALIDATOR_REGISTRY.get(name)


def get_validator_from_extension(suffix: str) -> ResponseValidator | None:
    """
    Get a validator function based on the file extension of the answer file.
    """
    suffix = "." + suffix.lower().removeprefix(".")
    return opt.map(get_validator, EXTENSION_MAPPINGS.get(suffix))


def string_validator(
    validator: Callable[[str], Disqualification | None],
) -> ResponseValidator:
    """
    A helper function to create a ValidatorFn from a simple string validation function.
    """

    def validator_fn(
        response: Response, student_id: StudentId
    ) -> Disqualification | None:
        if (answer := response.answer) is None:
            return None
        if isinstance(answer, str):
            return validator(answer)
        return disqualification.Invalid()

    validator_fn.__name__ = validator.__name__
    return validator_fn


def temp_file_validator(
    file_name: str,
) -> Callable[[ValidatorFn[Path]], ResponseValidator]:
    """
    A helper function to create a ValidatorFn from a validation function that
    operates on a temporary file.

    This is useful to wrap external tools like compilers, linters, etc. that
    expect file input. The file is automatically cleaned up after the validator
    function is called.
    """

    def decorator(validator: ValidatorFn[Path]) -> ResponseValidator:
        @string_validator
        def validator_fn(code: str) -> Disqualification | None:
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
                return validator(Path(tmp_file.name))

        validator_fn.__name__ = validator.__name__
        return validator_fn

    return decorator


# ==============================================================================
# Code syntax validators
# ==============================================================================
@register("python")
@register("py")
@string_validator
def python_syntax_validator(code: str) -> Disqualification | None:
    """
    Ensure that the response contains valid Python code.
    """

    try:
        compile(code, "<string>", "exec")
    except SyntaxError:
        return disqualification.Invalid()

    return None


@register("js")
@register("javascript")
@temp_file_validator("script.js")
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
        return disqualification.Invalid()

    return None
