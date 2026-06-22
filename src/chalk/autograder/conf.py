from __future__ import annotations

import tomllib
from logging import getLogger
from pathlib import Path
from typing import Annotated, Protocol, Self, cast

from pydantic import BaseModel, Field, computed_field

from ..protocols import HasParams, WithParams
from ..util.path import get_path_from_names

log = getLogger("chalk.autograder")
AUTOGRADER_PATH_NAMES = ("_autograde.conf", "autograde.conf")
TIMEOUT_DEFAULT = 10.0  # in seconds
CLEAR_TEMPORARIES_DEFAULT = True
PREFER_LINKS_DEFAULT = False
VALIDATE_SYNTAX_DEFAULT = True
DEFAULT_ALWAYS_REMOVE_PATHS = {
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    ".git",
    ".venv",
}


class AutograderParams(Protocol):
    @property
    def timeout(self) -> float: ...
    @property
    def clear_temporaries(self) -> bool: ...
    @property
    def prefer_links(self) -> bool: ...
    @property
    def validate_syntax(self) -> bool | str: ...


class GlobalParams(AutograderParams):
    """
    Global parameters for autograding, which can be overridden by question-specific
    configurations.
    """

    @property
    def timeout(self) -> float:
        return TIMEOUT_DEFAULT

    @property
    def clear_temporaries(self) -> bool:
        return CLEAR_TEMPORARIES_DEFAULT

    @property
    def prefer_links(self) -> bool:
        return PREFER_LINKS_DEFAULT

    @property
    def validate_syntax(self) -> bool | str:
        return VALIDATE_SYNTAX_DEFAULT


class AutograderParamsBase[P: HasParams[AutograderParams]](BaseModel):
    """
    Parameters for autograding a student's answer.

    This class is separated from AutograderConf to be reused in the global
    configuration for the course or activity.
    """

    _timeout: Annotated[
        float | None,
        Field(
            alias="timeout",
            description=(
                "Timeout (in seconds) for grading each response. This is applicable to potentially "
                "CPU intensive grading tasks such as running test cases or executing student code."
            ),
        ),
    ] = None
    _clear_temporaries: Annotated[
        bool | None,
        Field(
            alias="clear_temporaries",
            description=(
                "If true, the autograder will automatically clean up any temporary files or "
                "directories created during the grading process."
            ),
        ),
    ] = None
    _prefer_links: Annotated[
        bool | None,
        Field(
            alias="prefer_links",
            description=(
                "If true, the autograder will prefer creating hard links instead of copying files "
                "when setting up the grading environment. This can improve performance and reduce "
                "disk space usage, but may not be supported on all file systems."
            ),
        ),
    ] = None
    _validate_syntax: Annotated[
        bool | str | None,
        Field(
            alias="validate_syntax",
            description=(
                "If true, the autograder will automatically apply syntax validators based on the "
                "file extension of the answer or the given extension."
            ),
        ),
    ] = None
    _parent: Annotated[
        P | WithParams[GlobalParams] | None,
        Field(
            exclude=True,
            repr=False,
        ),
    ] = None

    def _get_from_params[T](self, name: str, default: T, /) -> T:
        value = getattr(self, f"_{name}", None)
        if value is not None:
            return cast("T", value)
        # Why is Pydantic not initialising the _parent field?
        if not hasattr(self, "_parent") or self._parent is None:
            self._parent = WithParams(GlobalParams())
        return cast("T", getattr(self._parent.params, name))

    @computed_field(repr=True)  # type: ignore[prop-decorator]
    @property
    def timeout(self) -> float:
        return self._get_from_params("timeout", TIMEOUT_DEFAULT)

    @computed_field(repr=True)  # type: ignore[prop-decorator]
    @property
    def clear_temporaries(self) -> bool:
        return self._get_from_params("clear_temporaries", CLEAR_TEMPORARIES_DEFAULT)

    @computed_field(repr=True)  # type: ignore[prop-decorator]
    @property
    def prefer_links(self) -> bool:
        return self._get_from_params("prefer_links", PREFER_LINKS_DEFAULT)

    @computed_field(repr=True)  # type: ignore[prop-decorator]
    @property
    def validate_syntax(self) -> bool | str:
        return self._get_from_params("validate_syntax", VALIDATE_SYNTAX_DEFAULT)


class AutograderConf(AutograderParamsBase[WithParams[GlobalParams]]):
    """
    The script autograder configuration file.
    """

    #: The path in the local grading repository in which the student's answer
    #: is saved before the grading process begins.
    answer: Path | None = None

    #: Path to the autograder configuration.
    path: Path | None = None

    clear: set[str] = Field(
        default_factory=DEFAULT_ALWAYS_REMOVE_PATHS.copy,
    )

    @classmethod
    def from_root_path(cls, root_path: Path) -> Self | None:
        """
        Find the autograder configuration file within the given root path and
        load it.
        """
        conf_path = get_conf_path(root_path)
        if conf_path is None:
            return None

        try:
            with conf_path.open("rb") as f:
                data = tomllib.load(f)
            data = data["autograde"]
        except OSError as e:
            log.warning(f"Error reading autograder configuration at {conf_path}: {e}")
            return None
        except KeyError:
            msg = f"Invalid autograder configuration at {conf_path}: missing 'autograde' section"
            log.warning(msg)
            return None

        data["path"] = conf_path
        return cls.model_validate(data)


def get_conf_path(
    base: Path,
) -> Path | None:
    """
    Get the path to the autograder configuration file, if it exists.

    Acceptable paths for the configuration file:
        * <base>/autograde.conf
        * <base>/_autograde.conf
    """
    return get_path_from_names(base, AUTOGRADER_PATH_NAMES, accept_base=True)
