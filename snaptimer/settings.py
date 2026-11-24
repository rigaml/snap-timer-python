"""Lazarus-compatible INI settings and paths for installed and portable use."""

import configparser
import locale
import os
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
import re
import sys
from tempfile import NamedTemporaryFile

from .timer import MAX_DURATION

ASSETS = Path(__file__).resolve().parent / "assets"
APP_DIR = (
    Path(sys.executable).resolve().parent if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent.parent
)
INI_NAME = "snaptimer.ini"
POSITIONS = ("Centered", "Remember position", "Top left", "Top right", "Bottom left", "Bottom right")
RESTART_FRACTIONS = ("None", "1/2", "1/3", "1/4", "1/5")
NO_COLOR = 0x1FFFFFFF


@dataclass(frozen=True)
class Settings:
    duration: int = 15
    always_on_top: bool = False
    minimize_to_tray: bool = False
    auto_start: bool = False
    hide_seconds: bool = False
    show_elapsed: bool = False
    click_time: bool = True
    double_click_time: bool = True
    auto_restart: bool = False
    restart_fraction: str = "None"
    loop_audio: bool = False
    ticking: bool = False
    auto_save: bool = True
    seconds_mode: bool = False

    message: str = "Time's up"
    message_enabled: bool = True
    tray_message: str = "Countdown completed"
    tray_message_enabled: bool = False
    audio_file: str = r".\sounds\alarm_clock_bell.wav"
    audio_file_enabled: bool = False
    music_enabled: bool = False
    run_app: str = ""
    run_app_enabled: bool = False

    width: int = 0
    height: int = 0
    x: int = 0
    y: int = 0
    position: int = 0

    font_name: str = "Segoe UI"
    font_charset: int = 0
    font_size: int = 38
    font_style: int = 0
    font_color: int = 0x3D2516
    background_color: int = NO_COLOR


INI_KEYS = {
    "Main": {
        "duration": "Minutes", "always_on_top": "AlwaysOnTop",
        "minimize_to_tray": "MinToTray", "auto_start": "AutoStart",
        "hide_seconds": "HideSeconds", "show_elapsed": "ShowElapsed", "click_time": "ClickTime",
        "double_click_time": "DoubleClickTime", "auto_restart": "AutoRestart",
        "restart_fraction": "RestartFraction",
        "loop_audio": "LoopAudio", "ticking": "TickingEnabled",
        "auto_save": "AutoSave", "seconds_mode": "SecondsMode",
    },
    "Alarms": {
        "message": "Message", "message_enabled": "MessageEnabled",
        "tray_message": "TrayMessage", "tray_message_enabled": "TrayMessageEnabled",
        "audio_file": "AudioFile", "audio_file_enabled": "AudioFileEnabled",
        "music_enabled": "MusicEnabled",
        "run_app": "RunApp", "run_app_enabled": "RunAppEnabled",
    },
    "Placement": {
        "width": "WinWidth", "height": "WinHeight", "x": "WinLeft",
        "y": "WinTop", "position": "WinPosition",
    },
    "Fonts": {
        "font_name": "Name", "font_charset": "Charset", "font_size": "Size",
        "font_style": "Style", "font_color": "Color", "background_color": "BgColor",
    },
}


def parse_restart_fraction(value: str) -> Fraction:
    text = value.strip()
    if text.casefold() == "none":
        return Fraction(1)
    if text in RESTART_FRACTIONS or re.fullmatch(r"(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)", text):
        fraction = Fraction(text)
        if 0 < fraction <= 1:
            return fraction
    raise ValueError("Choose a preset or enter a decimal greater than 0 and at most 1.")


def color_hex(value: int, fallback: str) -> str:
    if not 0 <= value <= 0xFFFFFF:
        return fallback
    return f"#{value & 255:02x}{value >> 8 & 255:02x}{value >> 16 & 255:02x}"


def color_value(hex_color: str) -> int:
    return int.from_bytes(bytes.fromhex(hex_color[1:]), "little")


def settings_path(explicit: Path | None, portable: bool) -> Path:
    if explicit is not None:
        return explicit.expanduser().resolve()
    sidecar = APP_DIR / INI_NAME
    if portable or sidecar.is_file():
        return sidecar
    profile = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    return profile / "SnapTimer" / INI_NAME


class SettingsStore:
    def __init__(self, path: Path):
        self.path = path

    def _read(self) -> configparser.ConfigParser:
        ini = configparser.ConfigParser(interpolation=None, strict=False)
        ini.optionxform = str
        try:
            data = self.path.read_bytes()
        except FileNotFoundError:
            return ini
        if data.startswith((b"\xff\xfe", b"\xfe\xff")):
            text = data.decode("utf-16")
        else:
            try:
                text = data.decode("utf-8-sig")
            except UnicodeDecodeError:
                text = data.decode(locale.getpreferredencoding(False), errors="replace")
        ini.read_string(text, source=str(self.path))
        return ini

    def load(self) -> Settings:
        ini = self._read()
        defaults = Settings()
        sections = {name.casefold(): name for name in ini.sections()}
        values = {}
        for section, keys in INI_KEYS.items():
            source = sections.get(section.casefold())
            if source is None:
                continue
            options = {key.casefold(): value for key, value in ini.items(source)}
            if section == "Main" and "restartfraction" not in options:
                try:
                    divisor = int(options.get("restartdivisor", "1"))
                except ValueError:
                    divisor = 1
                if 1 <= divisor <= len(RESTART_FRACTIONS):
                    values["restart_fraction"] = RESTART_FRACTIONS[divisor - 1]
            for field, key in keys.items():
                raw = options.get(key.casefold())
                if raw is None:
                    continue
                default = getattr(defaults, field)
                try:
                    if isinstance(default, bool):
                        values[field] = ini.BOOLEAN_STATES[raw.casefold()]
                    elif isinstance(default, int):
                        values[field] = int(raw)
                    else:
                        values[field] = raw.strip("\0")
                except (KeyError, ValueError):
                    continue

        limits = {
            "duration": (0, MAX_DURATION), "position": (0, len(POSITIONS) - 1),
            "width": (0, 32767), "height": (0, 32767), "font_size": (8, 96),
            "font_style": (0, 15), "x": (-32768, 32767), "y": (-32768, 32767),
        }
        for field, (low, high) in limits.items():
            value = values.get(field, getattr(defaults, field))
            values[field] = min(high, max(low, value))
        if "restart_fraction" in values:
            try:
                parse_restart_fraction(values["restart_fraction"])
            except ValueError:
                values["restart_fraction"] = defaults.restart_fraction
        return Settings(**values)

    def save(self, settings: Settings) -> None:
        try:
            ini = self._read()
        except (configparser.Error, UnicodeError):
            ini = configparser.ConfigParser(interpolation=None)
            ini.optionxform = str
        sections = {name.casefold(): name for name in ini.sections()}
        for section, keys in INI_KEYS.items():
            target = sections.get(section.casefold(), section)
            if target not in ini:
                ini.add_section(target)
            existing_keys = {key.casefold(): key for key in ini[target]}
            for field, key in keys.items():
                old_key = existing_keys.get(key.casefold(), key)
                value = getattr(settings, field)
                ini[target][old_key] = str(int(value) if isinstance(value, bool) else value)

        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with NamedTemporaryFile(
                mode="w", encoding="utf-8", newline="\n", suffix=".tmp",
                dir=self.path.parent, delete=False,
            ) as handle:
                temporary = Path(handle.name)
                ini.write(handle, space_around_delimiters=False)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def resolve_file(self, value: str) -> Path:
        path = Path(os.path.expandvars(value.strip().strip('"'))).expanduser()
        if path.is_absolute():
            return path
        locations = (self.path.parent, APP_DIR, ASSETS)
        return next(
            (base / path for base in locations if (base / path).is_file()),
            self.path.parent / path,
        )

    def store_file(self, path: Path) -> str:
        for base in (self.path.parent, ASSETS):
            if path.is_relative_to(base):
                return str(path.relative_to(base))
        return str(path)

