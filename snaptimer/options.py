"""Options dialog with an editable draft and a live font preview."""

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
import tkinter as tk
from tkinter import colorchooser, filedialog, font, ttk

from .settings import ASSETS, NO_COLOR, POSITIONS, Settings, SettingsStore, color_hex, color_value

DISPLAY_BACKGROUND = "#eaf0f7"
DISPLAY_FOREGROUND = "#16253d"
GENERAL_OPTIONS = (
    ("always_on_top", "Keep the window on top"),
    ("minimize_to_tray", "Minimize to the notification area"),
    ("auto_start", "Start the timer when SnapTimer opens"),
    ("auto_restart", "Restart the countdown after the alarm"),
    ("hide_seconds", "Hide seconds on the display"),
    ("show_elapsed", "Show elapsed time"),
    ("seconds_mode", "Enter durations in seconds"),
    ("click_time", "Click the time to start or pause"),
    ("double_click_time", "Double-click the time to reset"),
    ("ticking", "Play a ticking sound while running"),
    ("auto_save", "Save settings automatically"),
)
ALARM_OPTIONS = (
    ("message", "Message box"),
    ("tray_message", "Windows notification"),
    ("audio_file", "Play a WAV file"),
    ("run_app", "Open a program or file"),
)
FONT_STYLES = ("Bold", "Italic", "Underline", "Strikeout")


def font_attributes(family: str, size: int, style: int) -> dict:
    return {
        "family": family,
        "size": size,
        "weight": "bold" if style & 1 else "normal",
        "slant": "italic" if style & 2 else "roman",
        "underline": bool(style & 4),
        "overstrike": bool(style & 8),
    }


class Options(tk.Toplevel):
    def __init__(
        self, parent: tk.Tk, settings: Settings, store: SettingsStore,
        apply: Callable, preview: Callable, close: Callable,
    ):
        super().__init__(parent)
        self.withdraw()
        self.title("SnapTimer Options")
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.resizable(False, False)
        self._original = settings
        self._store = store
        self._apply = apply
        self._preview = preview
        self._on_close = close
        self._values = {}
        self._foreground = settings.font_color
        self._background = settings.background_color
        self._style_flags = [
            tk.BooleanVar(self, bool(settings.font_style & (1 << index)))
            for index in range(len(FONT_STYLES))
        ]

        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        tabs = ttk.Notebook(body)
        tabs.pack(fill="both", expand=True)
        for title, build in (
            ("General", self._general), ("Alarms", self._alarms), ("Appearance", self._appearance),
        ):
            page = ttk.Frame(tabs, padding=15)
            build(page)
            tabs.add(page, text=title)
        tabs.enable_traversal()

        buttons = ttk.Frame(body, padding=(0, 12, 0, 0))
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Cancel", command=self.close).pack(side="right")
        ttk.Button(buttons, text="OK", command=self._accept).pack(side="right", padx=8)
        self.bind("<Escape>", lambda event: self.close())
        self.bind("<Return>", lambda event: self._accept())
        self.bind("<KP_Enter>", lambda event: self._accept())
        self._tabs = tabs

    def show(self) -> None:
        self.deiconify()
        self.update_idletasks()
        self.grab_set()
        self._tabs.focus_set()

    def _variable(self, key: str, variable_type=tk.StringVar):
        variable = variable_type(self, getattr(self._original, key))
        self._values[key] = variable
        return variable

    def _general(self, page: ttk.Frame) -> None:
        for row, (key, title) in enumerate(GENERAL_OPTIONS):
            ttk.Checkbutton(
                page, text=title, variable=self._variable(key, tk.BooleanVar),
            ).grid(row=row, column=0, columnspan=2, sticky="w", pady=2)
        self._position = tk.StringVar(self, POSITIONS[self._original.position])
        ttk.Label(page, text="Startup position").grid(row=len(GENERAL_OPTIONS), sticky="w", pady=(12, 0))
        ttk.Combobox(
            page, values=POSITIONS, textvariable=self._position, state="readonly", width=19,
        ).grid(row=len(GENERAL_OPTIONS), column=1, sticky="w", padx=(10, 0), pady=(12, 0))

    def _alarms(self, page: ttk.Frame) -> None:
        page.columnconfigure(0, weight=1)
        for row, (key, title) in enumerate(ALARM_OPTIONS):
            enabled = self._variable(f"{key}_enabled", tk.BooleanVar)
            value = self._variable(key)
            check = ttk.Checkbutton(page, text=title, variable=enabled)
            check.grid(row=row * 2, column=0, columnspan=3, sticky="w", pady=(7, 1))

            if key == "audio_file":
                sounds = sorted((ASSETS / "sounds").glob("*.wav"))
                entry = ttk.Combobox(
                    page, textvariable=value, width=38,
                    values=[str(sound.relative_to(ASSETS)) for sound in sounds],
                )
            else:
                entry = ttk.Entry(page, textvariable=value, width=40)
            entry.grid(row=row * 2 + 1, column=0, sticky="ew", pady=(0, 4))
            controls = [entry]
            if key in ("audio_file", "run_app"):
                browse = ttk.Button(
                    page, text="Browse…", command=lambda key=key: self._browse(key),
                )
                browse.grid(row=row * 2 + 1, column=1, padx=6)
                controls.append(browse)
            test = ttk.Button(
                page, text="Test", command=lambda key=key: self._preview(key, self._draft(), self),
            )
            test.grid(row=row * 2 + 1, column=2, sticky="e", padx=(6, 0))
            controls.append(test)

            def sync_controls(*_, enabled=enabled, controls=controls):
                for control in controls:
                    control.state(("!disabled",) if enabled.get() else ("disabled",))

            enabled.trace_add("write", sync_controls)
            sync_controls()

        ttk.Checkbutton(
            page, text="Loop alarm audio", variable=self._variable("loop_audio", tk.BooleanVar),
        ).grid(row=len(ALARM_OPTIONS) * 2, column=0, sticky="w", pady=(12, 0))
        ttk.Checkbutton(
            page, text="Play music during the countdown", variable=self._variable("music_enabled", tk.BooleanVar),
        ).grid(row=len(ALARM_OPTIONS) * 2 + 1, column=0, sticky="w", pady=(4, 0))

    def _browse(self, key: str) -> None:
        existing = self._store.resolve_file(self._values[key].get())
        audio = key == "audio_file"
        folder = existing.parent if existing.is_file() else self._store.path.parent
        if audio and not existing.is_file():
            folder = ASSETS / "sounds"
        if not folder.is_dir():
            folder = Path.home()
        filetypes = [("Wave audio", "*.wav")] if audio else [("Programs", "*.exe"), ("All files", "*.*")]
        chosen = filedialog.askopenfilename(parent=self, initialdir=folder, filetypes=filetypes)
        if chosen:
            self._values[key].set(self._store.store_file(Path(chosen)))

    def _appearance(self, page: ttk.Frame) -> None:
        page.columnconfigure(1, weight=1)
        self._font_name = self._variable("font_name")
        self._sample_font = font.Font(self, size=23)
        self._sample = tk.Label(page, text="00:15:00", font=self._sample_font, pady=8)
        self._sample.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        families = sorted({name for name in font.families(self) if not name.startswith("@")}, key=str.casefold)

        ttk.Label(page, text="Font family").grid(row=1, column=0, sticky="w")
        ttk.Combobox(page, textvariable=self._font_name, values=families).grid(
            row=1, column=1, sticky="ew", pady=3,
        )
        flags = ttk.Frame(page)
        flags.grid(row=2, column=0, columnspan=2, sticky="w", pady=9)
        for title, value in zip(FONT_STYLES, self._style_flags):
            ttk.Checkbutton(flags, text=title, variable=value, command=self._update_sample).pack(
                side="left", padx=(0, 9),
            )

        colors = ttk.Frame(page)
        colors.grid(row=3, column=0, columnspan=2, sticky="w")
        ttk.Button(colors, text="Text color…", command=lambda: self._choose_color(False)).pack(side="left")
        ttk.Button(colors, text="Background…", command=lambda: self._choose_color(True)).pack(side="left", padx=8)
        ttk.Button(colors, text="Restore appearance defaults", command=self._reset_appearance).pack(side="left")
        self._font_name.trace_add("write", self._update_sample)
        self._update_sample()

    def _style(self) -> int:
        return sum(1 << index for index, flag in enumerate(self._style_flags) if flag.get())

    def _update_sample(self, *_) -> None:
        family = self._font_name.get().strip() or Settings.font_name
        self._sample_font.configure(**font_attributes(family, 23, self._style()))
        self._sample.configure(
            foreground=color_hex(self._foreground, DISPLAY_FOREGROUND),
            background=color_hex(self._background, DISPLAY_BACKGROUND),
        )

    def _choose_color(self, background: bool) -> None:
        initial = (
            color_hex(self._background, DISPLAY_BACKGROUND) if background
            else color_hex(self._foreground, DISPLAY_FOREGROUND)
        )
        _, chosen = colorchooser.askcolor(initial, parent=self, title="Choose timer color")
        if chosen:
            if background:
                self._background = color_value(chosen)
            else:
                self._foreground = color_value(chosen)
            self._update_sample()

    def _reset_appearance(self) -> None:
        self._foreground = Settings.font_color
        self._background = NO_COLOR
        self._font_name.set(Settings.font_name)
        for flag in self._style_flags:
            flag.set(False)
        self._update_sample()

    def _draft(self) -> Settings:
        values = {key: variable.get() for key, variable in self._values.items()}
        return replace(
            self._original, **(values | {
                "position": POSITIONS.index(self._position.get()),
                "font_name": values["font_name"].strip() or Settings.font_name,
                "font_color": self._foreground,
                "background_color": self._background,
                "font_style": self._style(),
            }),
        )

    def _accept(self) -> None:
        settings = self._draft()
        self.close()
        self._apply(settings)

    def close(self) -> None:
        self.destroy()
        self._on_close()

