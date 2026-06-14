from pathlib import Path
from typing import Callable

import rich
from rich.tree import Tree

MAX_DEPTH = 2**32


def _show_file(path: Path) -> bool:
    """
    Show the contents of a file in the console.
    """
    return not path.name.startswith(".")  # FIXME: make it work on Windows too


def print_file_tree(
    path: Path,
    pred: Callable[[Path], bool] = _show_file,
    depth: int = MAX_DEPTH,
    root_label: str = "/",
    hide_root: bool = False,
) -> None:
    """
    Print the file tree starting at the given path, using rich to render the tree.
    """

    rich.print(
        _generate_branches(
            path,
            Tree(f"[bold blue]{root_label}", guide_style="grey50", hide_root=hide_root),
            pred=pred,
            depth=depth,
        )
    )


def _generate_branches(
    path: Path,
    root: Tree,
    /,
    pred: Callable[[Path], bool] = _show_file,
    depth: int = MAX_DEPTH,
) -> Tree:
    """
    Generate a rich Tree from a filesystem path.
    """

    if depth == 0:
        return root

    for child in sorted(path.iterdir()):
        if not pred(child):
            continue

        if child.is_dir():
            node = root.add(f"[blue bold]{child.name}/")
            _generate_branches(
                child,
                node,
                pred=pred,
                depth=depth - 1,
            )
        else:
            root.add(f"[green]{child.name}")
    return root


if __name__ == "__main__":
    print_file_tree(Path.cwd())
