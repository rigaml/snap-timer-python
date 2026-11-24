"""Numbered countdown tracks and native Windows audio playback."""

import ctypes as ct
from pathlib import Path
import re
from uuid import uuid4

from .windows import GetMediaError, SendMediaCommand


def numbered_tracks(folder: Path) -> tuple[Path, ...]:
    tracks = []
    for path in folder.glob("*"):
        match = re.match(r"[0-9]+", path.name)
        if match and path.suffix.lower() in (".mp3", ".wav") and path.is_file():
            tracks.append((int(match[0]), path.name.casefold(), path))
    return tuple(path for _, _, path in sorted(tracks))


class MediaPlayer:
    def __init__(self) -> None:
        self.path: Path | None = None
        self._alias = f"snaptimer{uuid4().hex}"

    @staticmethod
    def _command(command: str) -> str:
        result = ct.create_unicode_buffer(256)
        error = SendMediaCommand(command, result, len(result), None)
        if error:
            if not GetMediaError(error, result, len(result)):
                raise RuntimeError(f"Windows audio error {error}.")
            raise RuntimeError(result.value)
        return result.value

    @property
    def mode(self) -> str:
        return "closed" if self.path is None else self._command(f"status {self._alias} mode")

    def play(self, path: Path) -> None:
        if self.path != path:
            self.close()
            if not path.is_file():
                raise FileNotFoundError(path)
            device = "waveaudio" if path.suffix.lower() in (".wav", ".wave") else "mpegvideo"
            self._command(f'open "{path.resolve()}" type {device} alias {self._alias}')
            self.path = path
        else:
            mode = self.mode
            if mode == "paused":
                self._command(f"resume {self._alias}")
                return
            if mode != "stopped":
                return
        self._command(f"play {self._alias} from 0")

    def pause(self) -> None:
        if self.mode == "playing":
            self._command(f"pause {self._alias}")

    def close(self) -> None:
        if self.path is not None:
            try:
                self._command(f"close {self._alias}")
            except RuntimeError:
                pass
            finally:
                self.path = None
