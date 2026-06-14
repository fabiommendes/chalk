import shutil
from pathlib import Path


class Repo:
    def __init__(self, dest: Path) -> None:
        self.base_path = dest
        self._written_files: set[Path] = set()

    def copy_source(self, source: Path, link: bool = False) -> None:
        """
        Copy the given source file to the destination directory, and keep track of the copied file for later cleanup.
        """
        if not source.exists() or not source.is_dir():
            msg = f"Source path {source} does not exist or is not a directory."
            raise FileNotFoundError(msg)

        for base, _, filenames in source.walk():
            for filename in filenames:
                source_file = base / filename
                dest_file = self.base_path / source_file.relative_to(source)
                dest_file.parent.mkdir(parents=True, exist_ok=True)

                if source_file.is_dir():
                    dest_file.mkdir(exist_ok=True)
                elif link:
                    dest_file.symlink_to(source_file)
                else:
                    dest_file.write_bytes(source_file.read_bytes())

                self._written_files.add(dest_file)

    def write_file(self, relative_path: Path | str, content: str | bytes) -> None:
        """
        Write the given content to a file at the specified relative path within
        the destination directory.
        """
        full_path = self.base_path / relative_path
        full_path.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(content, str):
            full_path.write_text(content)
        else:
            full_path.write_bytes(content)

        self._written_files.add(full_path)

    def force_remove(self, relative_path: Path | str) -> None:
        """
        Forcefully remove the file or directory within the destination directory,
        even if it was not created by this FileWriter.
        """
        path = Path(relative_path)
        full_path = self.base_path / path
        self._written_files.discard(full_path)

        if full_path.exists():
            if full_path.is_dir():
                shutil.rmtree(full_path)
            else:
                full_path.unlink()

    def clear(self, force: bool = False) -> None:
        """
        Remove all files that were previously written to the destination
        directory.

        If force is True, also remove any files created outside of the
        FileWriter's control (e.g. files that were copied but not tracked).
        """
        remove_dirs = {self.base_path}
        while self._written_files:
            file = self._written_files.pop()
            if file.exists():
                if file.is_dir():
                    remove_dirs.add(file)
                else:
                    file.unlink()
                    parent = file.parent
                    while parent != self.base_path:
                        remove_dirs.add(parent)
                        parent = parent.parent

        for dir in sorted(remove_dirs, key=lambda p: (-len(p.parts), p.parts)):
            try:
                dir.rmdir()
            except OSError:
                pass
