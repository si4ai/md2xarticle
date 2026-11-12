from __future__ import annotations

import os
from pathlib import Path

from md2xarticle.platform.base import Platform


class WindowsPlatform(Platform):
    name = "windows"

    def font_dirs(self) -> list[Path]:
        dirs = []
        windir = os.environ.get("WINDIR")
        if windir:
            dirs.append(Path(windir) / "Fonts")
        local = os.environ.get("LOCALAPPDATA")
        if local:
            dirs.append(Path(local) / "Microsoft" / "Windows" / "Fonts")
        return dirs

    def open_result(self, path: Path) -> None:
        startfile = getattr(os, "startfile", None)
        if startfile is not None:
            startfile(str(path))
