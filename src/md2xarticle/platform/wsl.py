from __future__ import annotations

import subprocess
from pathlib import Path

from md2xarticle.platform.posix import PosixPlatform

WSL_NOTE = (
    "WSL: output is in the Linux filesystem. To paste from a Windows browser, "
    "write to the Windows side (-o /mnt/c/<folder>/out) or open the folder "
    "through the \\\\wsl$ share."
)


class WslPlatform(PosixPlatform):
    name = "wsl"

    def font_dirs(self) -> list[Path]:
        return super().font_dirs() + [Path("/mnt/c/Windows/Fonts")]

    def open_result(self, path: Path) -> None:
        try:
            win = subprocess.run(
                ["wslpath", "-w", str(path)], capture_output=True, text=True, check=True
            ).stdout.strip()
            subprocess.run(["explorer.exe", win], check=False)
        except (OSError, subprocess.CalledProcessError):
            super().open_result(path)

    def notes(self) -> list[str]:
        return [WSL_NOTE]
