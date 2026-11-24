"""The single Windows WAV channel shared by ticking, alarms, and previews."""

from pathlib import Path
import os
import sys
import winsound

from .windows import SetDllDirectory


class Audio:
    def __init__(self):
        self._current: tuple[Path, bool] | None = None

    @property
    def looping(self) -> bool:
        return self._current is not None and self._current[1]

    def play(self, path: Path, *, loop: bool = False, restart: bool = True, interrupt: bool = True) -> bool:
        if not path.is_file():
            raise FileNotFoundError(path)
        sound = (path, loop)
        if not restart and sound == self._current:
            return True
        flags = winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT
        if loop:
            flags |= winsound.SND_LOOP
        if not interrupt and self._current is not None:
            flags |= winsound.SND_NOSTOP
        try:
            winsound.PlaySound(str(path), flags)
        except RuntimeError:
            if flags & winsound.SND_NOSTOP:
                return False
            raise
        self._current = sound
        return True

    def stop(self, path: Path | None = None) -> None:
        if self._current is not None and (path is None or self._current[0] == path):
            try:
                winsound.PlaySound(None, 0)
            finally:
                self._current = None


def open_file(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(path)
    open_target(str(path), cwd=str(path.parent))


def open_target(target: str, *, cwd: str | None = None) -> None:
    bundle = getattr(sys, "_MEIPASS", None)
    # Programs launched from the portable app should use their own DLL search path.
    if bundle is not None:
        SetDllDirectory(None)
    try:
        os.startfile(target, "open", cwd=cwd)
    finally:
        if bundle is not None:
            SetDllDirectory(bundle)

