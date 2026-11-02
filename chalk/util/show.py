from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import rich
import rich as _rich
from rich.tree import Tree

MAX_DEPTH = 2**32


#
# Helpers for __repr__ and __str__ methods of objects.
#
def pretty_repr(
    obj: Any,
    pos_args: Iterable[str] = (),
    kwargs: Iterable[str] = (),
    *,
    keep_none: bool = False,
    class_name: str | None = None,
) -> str:
    """
    Generate a pretty string representation of an object, including its class name,
    positional arguments, and keyword arguments.

    Args:
        obj: The object to represent.
        pos_args: An iterable of strings representing the positional arguments.
        kwargs: An iterable of strings representing the keyword arguments.
        keep_none: Whether to include None values in the representation.
        class_name: Optional class name to use in the representation. If None, the
            object's class name will be used.

    Returns:
        A string representation of the object.
    """
    if class_name is None:
        class_name = type(obj).__name__

    args = []
    for arg in pos_args:
        value = getattr(obj, arg, None)
        args.append(repr(value))
    for arg in kwargs:
        value = getattr(obj, arg, None)
        if keep_none or value is not None:
            args.append(f"{arg}={value!r}")
    return f"{class_name}({', '.join(args)})"


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
    *,
    pred: Callable[[Path], bool] = lambda p: _show_file(p),
    depth: int = MAX_DEPTH,
    root_label: str = "/",
    hide_root: bool = False,
) -> None:
    """
    Print the file tree starting at the given path, using rich to render the tree.
    """

    tree = render_file_tree(
        path,
        pred=pred,
        depth=depth,
        root_label=root_label,
        hide_root=hide_root,
    )
    rich.print(tree)


def render_file_tree(
    path: Path,
    *,
    pred: Callable[[Path], bool] = lambda p: _show_file(p),
    depth: int = MAX_DEPTH,
    root_label: str = "/",
    hide_root: bool = False,
) -> Tree:
    """
    Render the file tree starting at the given path, using rich to create the tree structure.
    """

    return _generate_branches(
        path,
        Tree(f"[bold blue]{root_label}", guide_style="grey50", hide_root=hide_root),
        pred=pred,
        depth=depth,
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
