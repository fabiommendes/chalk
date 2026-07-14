import os
from pathlib import Path


def open_editor(path: Path) -> None:
    """
    Open the specified file in the user's default editor.

    This function replaces the current process with the editor, so it does not return.
    """

    editor = os.getenv("EDITOR", "vi").strip("'\"")
    os.execvp(editor, [editor, str(path)])
