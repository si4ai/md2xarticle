from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from md2xarticle.platform.base import Platform


class PosixPlatform(Platform):
    """Linux and macOS."""

    name = "posix"

    def font_dirs(self) -> list[Path]:
        home = Path.home()
        if sys.platform == "darwin":
            return [home / "Library" / "Fonts", Path("/Library/Fonts"), Path("/System/Library/Fonts")]
        return [home / ".local" / "share" / "fonts", home / ".fonts", Path("/usr/local/share/fonts"), Path("/usr/share/fonts")]

    def open_result(self, path: Path) -> None:
        cmd = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.run([cmd, str(path)], check=False)
