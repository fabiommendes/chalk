import shutil
from collections.abc import Callable
from functools import partial
from logging import getLogger
from pathlib import Path
from typing import Any, Literal, cast

import gitignore
from rich.console import RenderableType

from ..util.show import render_file_tree

log = getLogger(__name__)


class Repo:
    """
    A repository of files related to a single response.

    It tracks all created files and directories. Files created by external
    processes are not tracked.
    """

    @property
    def root(self) -> Path:
        """
        The root directory of the repository.
        """
        return self._root

    def __init__(self, root: Path, /) -> None:
        self._root = root
        self._tracked: set[Path] = set()

    def sync_template(
        self,
        *,
        template: Path | None = None,
        student_repo: Path | None = None,
        copy_mode: Literal["copy", "link", "symlink"] = "copy",
    ) -> None:
        """
        Copy files from both the template and student repository.

        It honors the .chalkignore and .chalkoverwrite, .chalkskip files in the
        template repository by skipping files that are ignored and overwriting
        files, even when they exist in the student repository.

        The ignore files have a .gitignore-like syntax, and semantics and they
        control the following aspects of the cloning operation:

        * .chalkignore:
            files from the template repository that are ignored and
            not copied to the repo.
        * .chalkoverwrite:
            files that are always copied from the template
            repository, even if they exist in the student repository.
        * .chalkskip:
            files that are ignored from the student repository.

        Args:
            template:
                The path to the template repository.
            student_repo:
                The path to the student repository.
            copy_mode:
                The mode to use when copying files from the template repository.
                * "copy" will copy the files
                * "symlink" will create symbolic links.
                * "link" will try tocreate hard links, and fallback to copying.
        """
        # Validate and collect the ignore files, if they exist
        template_ignore: Callable[[str], bool] = always_false
        template_overwrite: Callable[[str], bool] = always_false
        repo_skip: Callable[[str], bool] = always_false
        repo_overwrite: Callable[[str], bool] = always_false

        if template is not None and template.exists() and template.is_dir():
            if (ignorefile := template / ".chalkignore").exists():
                try:
                    template_ignore = gitignore.load(ignorefile)
                except ValueError as e:
                    log.warning(f"Invalid .chalkignore file at {ignorefile}: {e}")
            if (overwritefile := template / ".chalkoverwrite").exists():
                try:
                    template_overwrite = gitignore.load(overwritefile)
                except ValueError as e:
                    log.warning(f"Invalid .chalkoverwrite file at {overwritefile}: {e}")

                if student_repo is not None:
                    repo_overwrite = gitignore.load(overwritefile.open(), base=student_repo)

            if (skipfile := template / ".chalkskip").exists():
                try:
                    repo_skip = gitignore.load(skipfile.open(), base=student_repo)
                except ValueError as e:
                    log.warning(f"Invalid .chalkskip file at {skipfile}: {e}")
        elif template is not None:
            msg = f"Template path {template} does not exist or is not a directory."
            raise ValueError(msg)

        if student_repo is not None and (not student_repo.exists() or not student_repo.is_dir()):
            msg = f"Student repository path {student_repo} does not exist or is not a directory."
            raise ValueError(msg)

        # Now we collect all files in student and template repositories
        template_paths: set[str] = set()
        overwrite_paths: set[str] = set()
        repo_paths: set[str] = set()

        if template is not None:
            for base, dirs, files in template.walk():
                base_str = str(base) + "/"

                if template_overwrite(base_str):
                    overwrite_paths.add(base_str)
                elif not template_ignore(base_str):
                    template_paths.add(base_str)
                else:
                    dirs.clear()
                    continue

                for file in files:
                    file = str(base / file)
                    if template_overwrite(file) or template_overwrite(base_str):
                        overwrite_paths.add(file)
                    elif not template_ignore(file):
                        template_paths.add(file)

        if student_repo is not None:
            for base, dirs, files in student_repo.walk():
                base_str = str(base) + "/"

                if repo_skip(base_str) or repo_overwrite(base_str):
                    dirs.clear()
                    continue
                else:
                    repo_paths.add(base_str)

                for file in files:
                    file = str(base / file)
                    if not repo_skip(file) and not repo_overwrite(file):
                        repo_paths.add(file)

        copyfile = partial(copy_file, mode=copy_mode)

        # Write files and directories to the destination repository
        for name in sorted(template_paths):
            rel_path = Path(name).relative_to(cast(Path, template))
            if name.endswith("/"):
                (self.root / rel_path).mkdir(parents=True, exist_ok=True)
            else:
                copyfile(name, self.root / rel_path)

        for name in sorted(repo_paths):
            rel_path = Path(name).relative_to(cast(Path, student_repo))
            if name.endswith("/"):
                (self.root / rel_path).mkdir(parents=True, exist_ok=True)
            else:
                copyfile(name, self.root / rel_path)

        for name in sorted(overwrite_paths):
            rel_path = Path(name).relative_to(cast(Path, template))
            if name.endswith("/"):
                (self.root / rel_path).mkdir(parents=True, exist_ok=True)
            else:
                copyfile(name, self.root / rel_path)

    def copy_tree(self, source: Path, link: bool = False) -> None:
        """
        Copy the given source file to the destination directory, and keep track
        of the copied file for later cleanup.
        """
        if not source.exists() or not source.is_dir():
            msg = f"Source path {source} does not exist or is not a directory."
            raise FileNotFoundError(msg)

        for base, _, filenames in source.walk():
            for filename in filenames:
                source_file = base / filename
                dest_file = self.root / source_file.relative_to(source)
                dest_file.parent.mkdir(parents=True, exist_ok=True)

                if source_file.is_dir():
                    dest_file.mkdir(exist_ok=True)
                elif link:
                    dest_file.symlink_to(source_file)
                else:
                    dest_file.write_bytes(source_file.read_bytes())

                self._tracked.add(dest_file)

    def write_file(
        self, relative_path: Path | str, content: str | bytes, track: bool = True
    ) -> None:
        """
        Write the given content to a file at the specified relative path within
        the destination directory.
        """
        full_path = self.root / relative_path
        full_path.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(content, str):
            full_path.write_text(content)
        else:
            full_path.write_bytes(content)

        if track:
            self._tracked.add(full_path)

    def remove(self, relative_path: Path | str) -> None:
        """
        Remove file or directory.
        """
        path = Path(relative_path)
        full_path = self.root / path
        self._tracked.discard(full_path)

        if full_path.exists():
            if full_path.is_dir():
                shutil.rmtree(full_path)
            else:
                full_path.unlink()

    def clear_tracked(self, force: bool = False) -> None:
        """
        Remove all files that were previously written to the destination
        directory.

        If force is True, also remove any files created outside of the
        FileWriter's control (e.g. files that were copied but not tracked).
        """
        remove_dirs = {self.root}
        while self._tracked:
            file = self._tracked.pop()
            if file.exists():
                if file.is_dir():
                    remove_dirs.add(file)
                else:
                    file.unlink()
                    parent = file.parent
                    while parent != self.root:
                        remove_dirs.add(parent)
                        parent = parent.parent

        for dir in sorted(remove_dirs, key=lambda p: (-len(p.parts), p.parts)):
            try:
                dir.rmdir()
            except OSError:
                pass

    def clear_all(self) -> None:
        """
        Remove repository from filesystem.
        """
        shutil.rmtree(self.root, ignore_errors=True)

    def __rich__(self) -> RenderableType:
        return render_file_tree(self.root)


def always_false(x: Any, /) -> bool:
    return False


def copy_file(src: Path | str, dst: Path | str, mode: str) -> None:
    if mode == "copy":
        shutil.copyfile(src, dst)
    elif mode == "symlink":
        Path(dst).symlink_to(src)
    elif mode == "link":
        try:
            Path(dst).hardlink_to(src)
        except OSError:
            shutil.copyfile(src, dst)
    else:
        raise ValueError(f"Invalid copy mode: {mode}")
