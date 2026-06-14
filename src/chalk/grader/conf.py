from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel


class AutograderConf(BaseModel):
    answer: Path | None = None
    path: Path | None = None
    timeout: float | None = 10.0

    #: If true, the autograder will automatically apply syntax validators based
    #: on the file extension of the answer or the given extension.
    validate_syntax: bool | str = True

    @classmethod
    def from_conf_path(cls, conf_path: Path) -> AutograderConf:
        with conf_path.open("rb") as f:
            data = tomllib.load(f)
        try:
            data = data["autograde"]
        except KeyError:
            raise ValueError(
                "Invalid autograder configuration: missing 'autograde' section"
            ) from None

        data["path"] = conf_path
        return cls.model_validate(data)
