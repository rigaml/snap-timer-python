"""Command line and desktop startup."""

import argparse
import configparser
from pathlib import Path
import sys
from dataclasses import replace

from .settings import Settings, SettingsStore, settings_path
from .timer import MAX_DURATION


class DesktopArguments(argparse.ArgumentParser):
    def _print_message(self, message, file=None):
        if message and sys.platform == "win32" and sys.stderr is None:
            desktop_message(message)
        else:
            super()._print_message(message, file)


def desktop_message(text: str) -> None:
    from ctypes import windll
    windll.user32.MessageBoxW(None, text, "SnapTimer", 0x00010000)


def duration_argument(value: str) -> int:
    try:
        duration = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("enter a whole number") from None
    if not 0 <= duration <= MAX_DURATION:
        raise argparse.ArgumentTypeError(f"duration must be between 0 and {MAX_DURATION}")
    return duration


def main(argv: list[str] | None = None) -> int:
    parser = DesktopArguments(description="SnapTimer countdown and stopwatch")
    parser.add_argument(
        "duration", nargs="?", type=duration_argument,
        help="initial duration in the configured units (0 starts in stopwatch mode)",
    )
    parser.add_argument("--start", action="store_true", help="start the timer immediately")
    storage = parser.add_mutually_exclusive_group()
    storage.add_argument("--ini", type=Path, help="use this settings file")
    storage.add_argument("--portable", action="store_true", help="save settings beside the app")
    args = parser.parse_args(argv)
    if sys.platform != "win32":
        parser.error("SnapTimer requires a Windows desktop.")

    store = SettingsStore(settings_path(args.ini, args.portable))
    warning = None
    try:
        settings = store.load()
    except (OSError, configparser.Error, UnicodeError) as error:
        settings = Settings()
        warning = f"Could not read {store.path}\n\n{error}"
        settings = replace(settings, auto_save=False)
    if args.duration is not None:
        settings = replace(settings, duration=args.duration)

    try:
        import tkinter as tk
        from tkinter import messagebox

        from .app import SnapTimer
        from .windows import SetProcessDPIAware

        SetProcessDPIAware()
        root = tk.Tk()
        SnapTimer(root, settings, store, start_immediately=args.start)
        if warning:
            root.after_idle(lambda: messagebox.showwarning("SnapTimer Settings", warning, parent=root))
        root.mainloop()
    except Exception as error:
        if sys.stderr is not None:
            raise
        desktop_message(f"SnapTimer could not start.\n\n{error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

