from pathlib import Path
from typing import Any, Callable

import rich
import rich as _rich
from rich.tree import Tree

MAX_DEPTH = 2**32


#
# Generic print/display functions.
#
def rich_print(value: Any, *, rich: bool = True, style: str | None = None) -> None:
    """
    A wrapper around rich.print that can be used to print rich content vs
    plain text.
    """
    if rich:
        if style is not None:
            _rich.print(f"[{style}]{value}[/{style}]")
        else:
            _rich.print(value)
    else:
        print(value)


def display_field(name: str, value: Any, rich: bool = True) -> None:
    """
    Display a field of a question in a consistent format.
    """
    if value is not None and value is not False:
        rich_print(f"  - [italic]{name}:[/] [yellow]{value}[/]", rich=rich)
    if value is True:
        rich_print(f"  - [italic]{name}[/]", rich=rich)


#
# Specialized printers
#
def print_file_tree(
    path: Path,
    pred: Callable[[Path], bool] = lambda p: _show_file(p),
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


def _show_file(path: Path) -> bool:
    """
    Show the contents of a file in the console.
    """
    return not path.name.startswith(".")  # FIXME: make it work on Windows too


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
