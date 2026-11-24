"""Countdown and stopwatch state, independent of the desktop interface."""

from collections.abc import Callable
from enum import Enum, auto
from fractions import Fraction
from math import ceil, floor
from time import monotonic

MAX_DURATION = 5999
MIN_RESTART_SECONDS = 60


class State(Enum):
    READY = auto()
    RUNNING = auto()
    PAUSED = auto()
    FINISHED = auto()


class Timer:
    def __init__(self, preset: int, clock: Callable[[], float] = monotonic):
        self._clock = clock
        self.preset = preset
        self._session_started: float | None = None
        self._stopped_session_seconds = 0
        self.reset()

    @property
    def stopwatch(self) -> bool:
        return self._duration == 0

    @property
    def seconds(self) -> int:
        elapsed = max(0.0, self._elapsed_now())
        if self.stopwatch:
            return floor(elapsed)
        return max(0, ceil(self._duration - elapsed))

    @property
    def session_seconds(self) -> int:
        if self._session_started is None:
            return self._stopped_session_seconds
        return max(0, floor(self._clock() - self._session_started))

    def reset(self) -> None:
        self._stopped_session_seconds = self.session_seconds
        self._session_started = None
        self._reset_series()

    def _reset_series(self) -> None:
        self._series_preset = self.preset
        self._reset_interval(self.preset)

    def _reset_interval(self, duration: int) -> None:
        self.state = State.READY
        self._duration = duration
        self._elapsed = 0.0
        self._started = 0.0

    def start(self) -> None:
        if self.state is State.RUNNING:
            return
        if self.state is State.FINISHED:
            self._reset_series()
        now = self._clock()
        if self.state is State.READY:
            self._session_started = now
        self._start_interval(now)

    def _start_interval(self, now: float) -> None:
        self._started = now
        self.state = State.RUNNING

    def restart_after_alarm(self, fraction: Fraction) -> None:
        if self.state is not State.FINISHED:
            return
        if fraction < 1 and self.preset == self._series_preset:
            self._reset_interval(max(MIN_RESTART_SECONDS, floor(self._duration * fraction)))
        else:
            self._reset_series()
        self._start_interval(self._clock())

    def pause(self) -> None:
        if self.state is State.RUNNING:
            self._elapsed = self._elapsed_now()
            self.state = State.PAUSED

    def advance(self) -> bool:
        """Return true once when a countdown expires."""
        if (
            self.state is State.RUNNING
            and not self.stopwatch
            and self._elapsed_now() >= self._duration
        ):
            self._elapsed = float(self._duration)
            self.state = State.FINISHED
            return True
        return False

    def _elapsed_now(self) -> float:
        if self.state is State.RUNNING:
            return self._elapsed + self._clock() - self._started
        return self._elapsed


def format_time(seconds: int, hide_seconds: bool = False) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    time_text = f"{hours:02}:{minutes:02}"
    return time_text if hide_seconds else f"{time_text}:{seconds:02}"

