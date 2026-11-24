"""SnapTimer desktop interface and coordination between the timer and Windows."""

from dataclasses import replace
from functools import partial
from pathlib import Path
import tkinter as tk
from tkinter import font, messagebox, ttk


from .alerts import Audio, open_file, open_target
from .music import MediaPlayer, numbered_tracks
from .options import DISPLAY_BACKGROUND, DISPLAY_FOREGROUND, Options, font_attributes
from .settings import ASSETS, RESTART_FRACTIONS, Settings, SettingsStore, color_hex, parse_restart_fraction
from .timer import MAX_DURATION, State, Timer, format_time
from .windows import (
    GetDoubleClickTime, SetForegroundWindow, Tray, minimum_caption_width, place_window,
    pointer_over_window, window_bounds, window_handle, window_monitor,
)

TITLE = "SnapTimer"
TICKING_SOUND = ASSETS / "sounds" / "ticking" / "ticking.wav"
WEBSITE = "https://dan.hersam.com/software/snaptimer/"
WINDOW_PADDING = 3
CLOCK_PADDING = 2
DEFAULT_CLOCK_POINTS = 38
MIN_CLOCK_PIXELS = 12
PREVIOUS_DEFAULT_SIZE = (324, 212)


class SnapTimer:
    def __init__(
        self, root: tk.Tk, settings: Settings, store: SettingsStore, *,
        start_immediately: bool = False,
    ):
        self.root = root
        self.settings = settings
        self.store = store
        self.timer = Timer(settings.duration * (1 if settings.seconds_mode else 60))
        self.audio = Audio()
        self.music = MediaPlayer()
        self._interval_alarm = MediaPlayer()
        self._tracks = numbered_tracks(ASSETS / "music")
        self._track_index = 0
        self.options = None
        self.alarm = None
        self.tray = None
        self.compact = False
        self._closing = False
        self._click_job = None
        self._poll_job = None
        self._ticking_pending = False
        self._last_display = None
        self._duration = settings.duration
        self._window_position = (settings.x, settings.y)
        self._full_size = None
        self._full_focus = None
        self._caption_monitor = None
        self._caption_width = 0
        self._clock_measurements: dict[tuple[int, str], tuple[int, int]] = {}
        self._time_text = tk.StringVar(root)
        self._elapsed_text = tk.StringVar(root)
        self._entry_text = tk.StringVar(root, str(settings.duration))

        root.withdraw()
        root.title(TITLE)
        root.iconbitmap(default=str(ASSETS / "images" / "snaptimer.ico"))
        root.protocol("WM_DELETE_WINDOW", self.close)
        self._build_window()
        self._render()
        self._apply_appearance()
        saved_size = (settings.width, settings.height)
        if saved_size == PREVIOUS_DEFAULT_SIZE:
            saved_size = (0, 0)
        default_width, default_height = self._default_clock_area()
        self._restore_size((
            saved_size[0] or default_width,
            saved_size[1] or default_height + self._controls.winfo_reqheight(),
        ))
        self._apply_window_bindings()
        root.deiconify()
        root.update_idletasks()
        place_window(root.winfo_id(), settings.position, settings.x, settings.y)
        self._remember_position()
        self._pointer_inside = pointer_over_window(root.winfo_id())

        try:
            self.tray = Tray(self._tray_activated, self._tray_menu)
        except OSError:
            # The main window remains usable if Explorer has no notification area.
            pass
        self._render(force=True)
        self.entry.focus_set()
        self.entry.selection_range(0, "end")
        self._entry_text.trace_add("write", self._entry_changed)
        if start_immediately or settings.auto_start:
            self.toggle()
        self._poll_job = root.after(75, self._tick)

    def _build_window(self) -> None:
        frame = ttk.Frame(self.root, padding=WINDOW_PADDING)
        frame.pack(fill="both", expand=True)
        self._clock_font = font.Font(self.root)
        self._elapsed_font = font.Font(self.root)
        self._measure_font = font.Font(self.root)
        self._clock_area = ttk.Frame(frame)
        self._clock_area.pack_propagate(False)
        self._clock_area.pack(fill="both", expand=True)
        self._display = tk.Label(
            self._clock_area, textvariable=self._time_text, font=self._clock_font,
            borderwidth=0, highlightthickness=0, padx=CLOCK_PADDING, pady=CLOCK_PADDING,
        )
        self._display.pack(side="left", fill="both", expand=True)
        self._elapsed_display = tk.Label(
            self._clock_area, textvariable=self._elapsed_text, font=self._elapsed_font,
            borderwidth=0, highlightthickness=0, padx=CLOCK_PADDING, pady=CLOCK_PADDING,
        )

        self._controls = ttk.Frame(frame, padding=(0, 3, 0, 0))
        self._controls.pack(anchor="e")
        validation = (self.root.register(self._valid_keystroke), "%P")
        self.entry = ttk.Spinbox(
            self._controls, from_=0, to=MAX_DURATION, increment=5, width=5,
            textvariable=self._entry_text, validate="key", validatecommand=validation,
        )
        self.entry.pack(side="left", padx=(0, 3))
        self._restart_fraction = ttk.Combobox(
            self._controls, values=RESTART_FRACTIONS, width=6,
        )
        self._restart_fraction.bind("<<ComboboxSelected>>", self._restart_fraction_changed)
        self._restart_fraction.bind("<FocusOut>", self._restart_fraction_changed)
        self._restart_fraction.bind("<Return>", self._restart_fraction_entered)
        self._restart_fraction.bind("<KP_Enter>", self._restart_fraction_entered)
        self._restart_fraction.bind("<Control-Return>", partial(self._key_action, self.toggle))
        self._control_images = {
            name: tk.PhotoImage(master=self.root, file=ASSETS / "images" / f"control_{icon}.png")
            for name, icon in (("Start", "play"), ("Pause", "pause"), ("Reset", "stop"))
        }
        self._toggle_button = ttk.Button(
            self._controls, text="Start", image=self._control_images["Start"],
            compound="none", style="Toolbutton", command=self.toggle,
        )
        self._toggle_button.pack(side="left")
        ttk.Button(
            self._controls, text="Reset", image=self._control_images["Reset"],
            compound="none", style="Toolbutton", command=self.reset,
        ).pack(side="left")
        self._sync_restart_control()

        self._menu = tk.Menu(self.root, tearoff=False)
        self._file_menu = tk.Menu(self._menu, tearoff=False)
        self._file_menu.add_command(label="Start", command=self.toggle, accelerator="Ctrl+Enter", underline=0)
        self._file_menu.add_command(label="Reset", command=self.reset, accelerator="Ctrl+R", underline=0)
        self._file_menu.add_separator()
        self._file_menu.add_command(label="Exit", command=self.close, accelerator="Ctrl+Q", underline=1)
        self._menu.add_cascade(label="File", menu=self._file_menu, underline=0)
        edit = tk.Menu(self._menu, tearoff=False)
        edit.add_command(label="Options…", command=self.show_options, accelerator="Ctrl+T", underline=0)
        edit.add_command(label="Save Settings", command=self.save, accelerator="Ctrl+S", underline=0)
        self._menu.add_cascade(label="Edit", menu=edit, underline=0)
        view = tk.Menu(self._menu, tearoff=False)
        view.add_command(label="Compact mode", command=self.toggle_compact, accelerator="Ctrl+M", underline=0)
        self._menu.add_cascade(label="View", menu=view, underline=0)
        help_menu = tk.Menu(self._menu, tearoff=False)
        help_menu.add_command(label="About", command=self.show_about, underline=0)
        self._menu.add_cascade(label="Help", menu=help_menu, underline=0)
        self.root.configure(menu=self._menu)

        for display in (self._display, self._elapsed_display):
            display.bind("<Button-1>", self._schedule_click)
            display.bind("<Double-Button-1>", self._double_click)
            display.bind("<Button-3>", self._display_menu)
        self._clock_area.bind("<Configure>", self._fit_clock)

    def _apply_window_bindings(self) -> None:
        for shortcut, action in (
            ("<Return>", self.toggle), ("<KP_Enter>", self.toggle),
            ("<Control-Return>", self.toggle), ("<Control-r>", self.reset),
            ("<Control-q>", self.close), ("<Control-s>", self.save),
            ("<Control-t>", self.show_options), ("<Control-m>", self.toggle_compact),
            ("<Escape>", self.close),
        ):
            self.root.bind(shortcut, partial(self._key_action, action))
        for key, increment in (("<Up>", 5), ("<Down>", -5)):
            self.entry.bind(key, partial(self._step_entry, increment))
        self.root.bind("<Unmap>", self._window_unmapped)
        self.root.bind("<Configure>", self._window_configured)

    def _key_action(self, action, _event) -> str:
        action()
        return "break"

    @staticmethod
    def _valid_keystroke(text: str) -> bool:
        return not text or (len(text) <= 4 and text.isascii() and text.isdecimal())

    def _parse_entry(self) -> int:
        text = self._entry_text.get()
        if not text or not self._valid_keystroke(text) or int(text) > MAX_DURATION:
            raise ValueError(f"Enter a whole number from 0 to {MAX_DURATION}.")
        return int(text)

    def _step_entry(self, increment: int, _event) -> str:
        try:
            value = self._parse_entry()
        except ValueError:
            value = self._duration
        self._entry_text.set(str(min(MAX_DURATION, max(0, value + increment))))
        return "break"

    def _entry_changed(self, *_):
        try:
            value = self._parse_entry()
        except ValueError:
            self.entry.state(("invalid",))
            return
        self.entry.state(("!invalid",))
        if value != self._duration:
            self._set_preset(value)

    def _sync_restart_control(self) -> None:
        self._restart_fraction.set(self.settings.restart_fraction)
        self._restart_fraction.state(("!invalid",))
        if self.settings.auto_restart:
            self._restart_fraction.pack(side="left", before=self._toggle_button, padx=(0, 3))
        else:
            self._restart_fraction.pack_forget()

    def _accept_restart_fraction(self, *, report: bool = False) -> bool:
        if not self.settings.auto_restart:
            return True
        value = self._restart_fraction.get().strip()
        try:
            parse_restart_fraction(value)
        except ValueError as error:
            self._restart_fraction.state(("invalid",))
            if report:
                self.show_window()
                messagebox.showerror(TITLE, str(error), parent=self.root)
                if not self.compact:
                    self._restart_fraction.focus_set()
                    self._restart_fraction.selection_range(0, "end")
            return False
        self._restart_fraction.state(("!invalid",))
        if value != self.settings.restart_fraction:
            self.settings = replace(self.settings, restart_fraction=value)
        return True

    def _commit_restart_fraction(self, *, report: bool = False) -> bool:
        previous = self.settings.restart_fraction
        if not self._accept_restart_fraction(report=report):
            return False
        if self.settings.auto_save and self.settings.restart_fraction != previous:
            self.save()
        return True

    def _restart_fraction_changed(self, _event) -> None:
        if not self._closing:
            self._commit_restart_fraction()

    def _restart_fraction_entered(self, _event) -> str:
        self._commit_restart_fraction(report=True)
        return "break"

    def _set_preset(self, duration: int) -> None:
        self._duration = duration
        self.timer.preset = duration * (1 if self.settings.seconds_mode else 60)
        if self.timer.state is not State.RUNNING:
            self.timer.reset()
            self._stop_sound()
            self.music.close()
            self._interval_alarm.close()
            self._render()

    def _accept_entry(self) -> bool:
        try:
            value = self._parse_entry()
        except ValueError as error:
            self.show_window()
            messagebox.showerror(TITLE, str(error), parent=self.root)
            if not self.compact:
                self.entry.focus_set()
                self.entry.selection_range(0, "end")
            return False
        if value != self._duration:
            self._set_preset(value)
        return True

    def toggle(self) -> None:
        if self.options or self.alarm or self._closing:
            return
        if self.timer.state is State.RUNNING:
            if self.timer.advance():
                self._finish()
                return
            self.timer.pause()
            self._stop_sound()
            self._sync_music()
        elif self._accept_entry() and self._commit_restart_fraction(report=True):
            self._start()
        self._render()

    def _start(self, *, after_alarm=False) -> None:
        if after_alarm:
            self.timer.restart_after_alarm(parse_restart_fraction(self.settings.restart_fraction))
            self._track_index += 1
        else:
            self._stop_sound()
            self._interval_alarm.close()
            if self.timer.state is not State.PAUSED:
                self._track_index = 0
            self.timer.start()
        self._sync_ticking()
        self._sync_music()

    def reset(self) -> None:
        if self.options or self.alarm or not self._accept_entry():
            return
        self._stop_sound()
        self.music.close()
        self._interval_alarm.close()
        self.timer.reset()
        self._render()

    def _tick(self) -> None:
        if self.tray:
            self.tray.dispatch()
        if self._closing:
            return
        if self.timer.advance():
            self._finish()
        elif self._interval_alarm.path is not None:
            self._after_alarm()
        elif self._ticking_pending:
            self._sync_ticking()
        if self.timer.state is State.RUNNING and self.music.path is not None:
            self._sync_music()
        self._render()
        self._update_compact_mode()
        self._poll_job = self.root.after(75, self._tick)

    def _render(self, *, force=False) -> None:
        state = self.timer.state
        time_text = format_time(self.timer.seconds, self.settings.hide_seconds)
        clock_width_changed = len(time_text) != len(self._time_text.get())
        if self.settings.show_elapsed:
            elapsed = format_time(self.timer.session_seconds, self.settings.hide_seconds)
            previous = self._elapsed_text.get()
            if elapsed != previous:
                self._elapsed_text.set(elapsed)
                clock_width_changed |= len(elapsed) != len(previous)
        if state is State.RUNNING:
            caption = f"{time_text} - {TITLE}"
        else:
            caption = TITLE
        appearance = (state, time_text)
        if force or appearance != self._last_display:
            self._last_display = appearance
            button = "Pause" if state is State.RUNNING else "Start"
            self._time_text.set(time_text)
            self._toggle_button.configure(text=button, image=self._control_images[button])
            self._file_menu.entryconfigure(0, label=button)
            self.root.title(caption)
        if clock_width_changed:
            self._fit_clock()
        if self.tray:
            self.tray.update(state, time_text if state is State.RUNNING else TITLE)

    def _finish(self) -> None:
        self._stop_sound()
        self.music.close()
        self._render()
        for key in ("audio_file", "run_app", "tray_message", "message"):
            if getattr(self.settings, f"{key}_enabled"):
                self._alert(key, self.settings, self.options or self.root)
        self._after_alarm()

    def _after_alarm(self) -> None:
        if self.alarm is not None or self._closing:
            return
        if self._interval_alarm.path is not None:
            try:
                if self._interval_alarm.mode == "playing":
                    return
            except RuntimeError as error:
                messagebox.showerror("SnapTimer Alarm", str(error), parent=self.options or self.root)
            self._interval_alarm.close()
        if self.settings.auto_restart and self.timer.state is State.FINISHED:
            self._start(after_alarm=True)
            self._render()

    def _alert(self, key: str, settings: Settings, parent, *, preview=False) -> None:
        value = getattr(settings, key)
        try:
            if key == "audio_file":
                path = self.store.resolve_file(value)
                if (
                    not preview and settings.auto_restart and settings.music_enabled and self._tracks
                    and self.timer.preset > 0 and not (settings.loop_audio and settings.message_enabled)
                ):
                    # Wait for one full play before starting the next track. A looping alarm
                    # with a message box already has a dismissal that ends playback.
                    self._interval_alarm.play(path)
                else:
                    self.audio.play(path, loop=settings.loop_audio and not preview)
            elif key == "run_app":
                open_file(self.store.resolve_file(value))
            elif key == "tray_message":
                if self.tray is None or not self.tray.notify(TITLE, value):
                    raise RuntimeError("The Windows notification area is unavailable.")
            elif preview:
                messagebox.showinfo("Done", value, parent=parent)
            else:
                self._show_alarm(value)
        except (OSError, RuntimeError, ValueError) as error:
            messagebox.showerror("SnapTimer Alarm", str(error), parent=parent)

    def _show_alarm(self, text: str) -> None:
        owner = self.options or self.root
        try:
            previous_grab = owner.grab_current()
        except KeyError:
            # Tk closes its combobox popup when the alarm takes focus.
            previous_grab = self.options
        dialog = tk.Toplevel(self.root)
        self.alarm = dialog
        dialog.withdraw()
        dialog.title("SnapTimer — Done")
        dialog.attributes("-topmost", True)
        dialog.resizable(False, False)
        if owner.winfo_viewable() and self.root.state() == "normal":
            dialog.transient(owner)
        body = ttk.Frame(dialog, padding=18)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=text, wraplength=340, justify="left").pack(fill="x")
        button = ttk.Button(body, text="OK", width=10, command=partial(self._dismiss_alarm, previous_grab))
        button.pack(anchor="e", pady=(16, 0))
        dialog.protocol("WM_DELETE_WINDOW", button.invoke)
        dialog.bind("<Return>", lambda event: button.invoke())
        dialog.bind("<Escape>", lambda event: button.invoke())
        dialog.deiconify()
        dialog.update_idletasks()
        place_window(dialog.winfo_id(), 0, 0, 0)
        dialog.grab_set()
        dialog.lift()
        SetForegroundWindow(window_handle(dialog.winfo_id()))
        button.focus_force()

    def _dismiss_alarm(self, previous_grab) -> None:
        self.alarm.destroy()
        self.alarm = None
        if previous_grab is not None and previous_grab.winfo_exists():
            previous_grab.grab_set()
        self._stop_sound()
        self._after_alarm()

    def _stop_sound(self, path: Path | None = None) -> None:
        self._ticking_pending = False
        try:
            self.audio.stop(path)
        except RuntimeError:
            pass

    def _sync_ticking(self) -> None:
        self._ticking_pending = False
        if self.timer.state is not State.RUNNING:
            return
        if not self.settings.ticking:
            self._stop_sound(TICKING_SOUND)
        elif not self.audio.looping:
            try:
                self._ticking_pending = not self.audio.play(TICKING_SOUND, loop=True, interrupt=False)
            except (OSError, RuntimeError):
                self.root.bell()

    def _sync_music(self) -> None:
        if not self.settings.music_enabled or not self._tracks or self.timer.stopwatch:
            self.music.close()
            return
        track = self._tracks[self._track_index % len(self._tracks)]
        try:
            if self.timer.state is State.RUNNING:
                self.music.play(track)
            elif self.timer.state is State.PAUSED:
                self.music.pause()
        except (OSError, RuntimeError) as error:
            self.music.close()
            messagebox.showerror("SnapTimer Music", f"{track.name}\n\n{error}", parent=self.options or self.root)

    def _schedule_click(self, _event) -> str:
        if self.settings.click_time:
            if self.settings.double_click_time:
                self._click_job = self.root.after(GetDoubleClickTime(), self._single_click)
            else:
                self.toggle()
        return "break"

    def _single_click(self) -> None:
        self._click_job = None
        self.toggle()

    def _double_click(self, _event) -> str:
        if self._click_job is not None:
            self.root.after_cancel(self._click_job)
            self._click_job = None
        if self.settings.double_click_time:
            self.reset()
        elif self.settings.click_time:
            self.toggle()
        return "break"

    def _display_menu(self, event) -> None:
        menu = tk.Menu(self.root, tearoff=False)
        menu.add_command(label="Show controls" if self.compact else "Compact mode", command=self.toggle_compact)
        menu.add_command(label=self._toggle_button.cget("text"), command=self.toggle)
        menu.add_command(label="Reset", command=self.reset)
        menu.add_command(label="Options…", command=self.show_options)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
            self.root.after_idle(menu.destroy)

    def _tray_activated(self) -> None:
        if self.root.state() == "withdrawn":
            self.show_window()
        else:
            self.toggle()

    def _tray_menu(self) -> None:
        self.tray.show_menu(
            self._time_text.get(),
            (
                ("Show SnapTimer", self.show_window),
                (self._toggle_button.cget("text"), self.toggle), ("Reset", self.reset),
                ("Options…", self.show_options), None,
                ("About", self.show_about), ("Exit", self.close),
            ),
        )

    def show_window(self) -> None:
        self.root.deiconify()
        self.root.lift()
        SetForegroundWindow(window_handle(self.root.winfo_id()))

    def _window_unmapped(self, event) -> None:
        if event.widget is self.root and self.settings.minimize_to_tray:
            self.root.after_idle(self._minimize_to_tray)

    def _minimize_to_tray(self) -> None:
        if self.root.state() == "iconic" and self.tray and self.tray.available:
            self.root.withdraw()

    def _window_configured(self, event) -> None:
        if event.widget is self.root:
            self._remember_position()
            if self.root.state() == "normal":
                self._update_minimum_size()

    def _remember_position(self) -> None:
        if self.root.state() == "normal":
            bounds = window_bounds(self.root.winfo_id())
            self._window_position = (bounds.left, bounds.top)
            if not self.compact:
                self._full_size = (self.root.winfo_width(), self.root.winfo_height())

    def _restore_size(self, size: tuple[int, int]) -> None:
        min_width, min_height = self.root.minsize()
        width = min(max(size[0], min_width), self.root.winfo_screenwidth())
        height = min(max(size[1], min_height), self.root.winfo_screenheight())
        self.root.geometry(f"{width}x{height}")

    def _apply_appearance(self) -> None:
        settings = self.settings
        self.root.attributes("-topmost", settings.always_on_top)
        for clock_font in (self._clock_font, self._elapsed_font):
            clock_font.configure(**font_attributes(settings.font_name, clock_font.cget("size"), settings.font_style))
        self._measure_font.configure(**font_attributes(settings.font_name, -MIN_CLOCK_PIXELS, settings.font_style))
        self._clock_measurements.clear()
        bg = color_hex(settings.background_color, DISPLAY_BACKGROUND)
        fg = color_hex(settings.font_color, DISPLAY_FOREGROUND)
        self._display.configure(background=bg, foreground=fg)
        self._elapsed_display.configure(background=bg, foreground=fg)
        if settings.show_elapsed:
            self._elapsed_display.pack(side="right", fill="y")
        else:
            self._elapsed_display.pack_forget()
        width, height = self._clock_size(-MIN_CLOCK_PIXELS)
        self._clock_area.configure(width=width, height=height)
        self.root.update_idletasks()
        self._update_minimum_size()
        self._fit_clock()

    def _measure_clock(self, size: int, text: str) -> tuple[int, int]:
        pattern = "".join("0" if char.isdecimal() else char for char in text)
        key = (size, pattern)
        if key not in self._clock_measurements:
            self._measure_font.configure(size=size)
            widest_digit = max("0123456789", key=self._measure_font.measure)
            self._clock_measurements[key] = (
                self._measure_font.measure(pattern.replace("0", widest_digit)), self._measure_font.metrics("linespace"),
            )
        return self._clock_measurements[key]

    @staticmethod
    def _elapsed_size(size: int) -> int:
        smaller = max(1, abs(size) * 3 // 5)
        return -smaller if size < 0 else smaller

    def _clock_size(self, size: int) -> tuple[int, int]:
        width, height = self._measure_clock(size, self._time_text.get())
        padding = 2 * CLOCK_PADDING
        if self.settings.show_elapsed:
            elapsed_width, elapsed_height = self._measure_clock(self._elapsed_size(size), self._elapsed_text.get())
            width += elapsed_width + padding
            height = max(height, elapsed_height)
        return width + padding, height + padding

    def _default_clock_area(self) -> tuple[int, int]:
        width, height = self._clock_size(DEFAULT_CLOCK_POINTS)
        padding = 2 * WINDOW_PADDING
        return width + padding, height + padding

    def _fit_clock(self, _event=None) -> None:
        width = self._clock_area.winfo_width()
        height = self._clock_area.winfo_height()
        if width <= 2 * CLOCK_PADDING or height <= 2 * CLOCK_PADDING:
            return
        # Use the widest digits so the clock stays the same size as it counts.
        low, high = 1, height
        while low <= high:
            size = (low + high) // 2
            text_width, text_height = self._clock_size(-size)
            if text_width <= width and text_height <= height:
                low = size + 1
            else:
                high = size - 1
        size = -max(1, high)
        if size != self._clock_font.cget("size"):
            self._clock_font.configure(size=size)
        if self.settings.show_elapsed and self._elapsed_size(size) != self._elapsed_font.cget("size"):
            self._elapsed_font.configure(size=self._elapsed_size(size))

    def _update_minimum_size(self) -> None:
        widget_id = self.root.winfo_id()
        monitor = window_monitor(widget_id) if self.root.winfo_viewable() else None
        if monitor != self._caption_monitor or not self._caption_width:
            self._caption_monitor = monitor
            self._caption_width = minimum_caption_width(widget_id)
        width = max(self.root.winfo_reqwidth(), self._caption_width)
        minimum = (
            min(width, self.root.winfo_screenwidth()), self.root.winfo_reqheight(),
        )
        if minimum != self.root.minsize():
            self.root.minsize(*minimum)

    def _update_compact_mode(self) -> None:
        if self.root.state() != "normal" or self.options or self.alarm:
            return
        # The combobox popup is a Tcl window with no corresponding Tkinter widget.
        if self.root.tk.call("grab", "current", self.root):
            return
        inside = pointer_over_window(self.root.winfo_id())
        if inside is None:
            return
        was_inside = self._pointer_inside
        self._pointer_inside = inside
        if was_inside is not None and inside != was_inside:
            self._set_compact(not inside)

    def toggle_compact(self) -> None:
        self._set_compact(not self.compact)

    def _set_compact(self, compact: bool) -> None:
        if compact == self.compact:
            return
        self._remember_position()
        size = self._full_size
        self.compact = compact
        if compact:
            width, height = self._default_clock_area()
            compact_size = (
                min(width, self.root.winfo_width()),
                min(height, self._clock_area.winfo_height() + 2 * WINDOW_PADDING),
            )
            self._full_focus = self.root.focus_lastfor()
            self.root.configure(menu="")
            self._controls.pack_forget()
            self.root.focus_set()
        else:
            self.root.configure(menu=self._menu)
            self._controls.pack(anchor="e")
        self.root.update_idletasks()
        self._update_minimum_size()
        if compact:
            self._restore_size(compact_size)
        else:
            if size is not None:
                self._restore_size(size)
            if self._full_focus is not None:
                self._full_focus.focus_set()

    def show_options(self) -> None:
        if self.alarm:
            self.alarm.lift()
        elif self.options:
            self.options.lift()
        else:
            self.show_window()
            self.options = Options(
                self.root, self.settings, self.store, self.apply_settings,
                self._preview, self._options_closed,
            )
            self.options.show()

    def _preview(self, key: str, settings: Settings, parent) -> None:
        self._alert(key, settings, parent, preview=True)

    def _options_closed(self) -> None:
        self.options = None
        self._sync_ticking()

    def apply_settings(self, settings: Settings) -> None:
        changed_units = settings.seconds_mode != self.settings.seconds_mode
        self.settings = settings
        self._sync_restart_control()
        if changed_units:
            self._set_preset(self._duration)
        self._render(force=True)
        self._apply_appearance()
        self._sync_ticking()
        self._sync_music()
        if settings.auto_save:
            self.save()

    def show_about(self) -> None:
        if self.alarm or self.options:
            return
        self.show_window()
        visit = messagebox.askyesno(
            "About SnapTimer",
            "SnapTimer for Windows\nPython port of SnapTimer 0.2 by Dan Hersam.\n\nOpen the original project website?",
            parent=self.root,
        )
        if visit:
            try:
                open_target(WEBSITE)
            except OSError as error:
                messagebox.showerror("About SnapTimer", str(error), parent=self.root)

    def save(self) -> None:
        self._accept_restart_fraction()
        self._remember_position()
        x, y = self._window_position
        width, height = self._full_size or (self.settings.width, self.settings.height)
        try:
            self.store.save(replace(self.settings, duration=self._duration, x=x, y=y, width=width, height=height))
        except (OSError, ValueError) as error:
            self.show_window()
            messagebox.showerror("Save Settings", f"Could not save {self.store.path}\n\n{error}", parent=self.root)

    def close(self) -> None:
        if self._closing:
            return
        self._closing = True
        for job in (self._poll_job, self._click_job):
            if job is not None:
                self.root.after_cancel(job)
        self._stop_sound()
        self.music.close()
        self._interval_alarm.close()
        if self.settings.auto_save:
            self.save()
        if self.tray:
            self.tray.close()
        self.root.destroy()

