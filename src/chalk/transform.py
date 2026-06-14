from dataclasses import dataclass
from pathlib import Path
from typing import IO, Iterator

from .builtin_scripts import TRANSFORM_REGISTRY
from .builtin_scripts import Transform as TransformFn
from .conf import find_project_root
from .core import Answer

ASSETS_BASE = Path(__file__).parent / "assets"


@dataclass
class Transform:
    name: str
    description: str
    transform: TransformFn
    path: Path | None = None

    @classmethod
    def from_script(cls, path: Path) -> "Transform":
        transform_fn = _from_script(path)
        description = f"Custom transform from {path.name}"
        name = path.stem.removesuffix("-transform")

        return cls(
            name=name,
            description=description,
            transform=transform_fn,
            path=path,
        )

    def __call__(self, answer: Answer | None) -> Answer | None:
        return self.transform(answer)

    def __str__(self) -> str:
        return self.name


def list_transforms(
    root: Path | None = None, *, registry: bool = True, custom: bool = True
) -> Iterator[Transform]:
    """
    List available transformations in the speciified root.
    """

    root = find_project_root(root)

    if registry:
        for name, transform_fn in TRANSFORM_REGISTRY.items():
            description = "No description provided"
            if transform_fn.__doc__:
                description = transform_fn.__doc__.strip().replace("_", " ")
            yield Transform(name=name, description=description, transform=transform_fn)

    if custom:
        scripts_dir = root / "scripts"
        if not scripts_dir.exists():
            return

        for script_path in scripts_dir.iterdir():
            if script_path.is_file() and script_path.suffix in {".py", ".sh"}:
                yield Transform.from_script(script_path)


def create_script(
    name: str, *, root: Path | None = None, suffix: str = "py"
) -> Transform:
    """
    Create a new transformation script with the specified name in the given root.
    """
    root = find_project_root(root)

    script_path = root / "scripts" / f"{name}-transform.{suffix}"
    if script_path.exists():
        script_path = script_path.relative_to(root)
        raise FileExistsError(
            f"A transform script named '{name}' already exists at {script_path}"
        )
    script_path.parent.mkdir(exist_ok=True)
    script_path.touch()
    script_path.chmod(script_path.stat().st_mode | 0o111)  # Make the script executable

    with script_path.open("w") as f:
        dump_default_script_content(f, suffix)

    return Transform.from_script(script_path)


def _from_script(path: Path) -> TransformFn:
    """
    Load a transformation from a script at the specified path.
    """

    def transform(answer: Answer | None) -> Answer | None:
        raise NotImplementedError

    return transform


def dump_default_script_content(file: IO[str], suffix: str) -> None:
    """
    Dump default content for a new transformation script based on the specified suffix.
    """
    asset = ASSETS_BASE / f"transform-example.{suffix}"
    if asset.exists():
        with asset.open() as f:
            file.write(f.read())


def load_transform(name: str) -> TransformFn | None:
    """
    Load a transformation by name from the registry or custom scripts.
    """
    for transform in list_transforms():
        if transform.name == name:
            return transform.transform
    return None
