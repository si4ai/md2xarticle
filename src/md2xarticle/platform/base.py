from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class Platform(ABC):
    """What differs between operating systems: fonts, output folder, opening, notes."""

    name: str = ""

    @abstractmethod
    def font_dirs(self) -> list[Path]:
        """Folders that may hold system fonts. They need not exist."""

    def default_output_dir(self) -> Path:
        return Path("out")

    @abstractmethod
    def open_result(self, path: Path) -> None:
        """Open ``path`` in the system file browser or viewer."""

    def notes(self) -> list[str]:
        """Hints to print after a run."""
        return []
