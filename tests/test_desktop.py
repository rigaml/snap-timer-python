"""Opt-in integration checks with a real Windows desktop and Explorer."""

from dataclasses import replace
import os
from pathlib import Path
from shutil import copyfile
import sys
from tempfile import TemporaryDirectory
from time import monotonic, sleep
import unittest
from unittest.mock import patch


@unittest.skipUnless(sys.platform == "win32" and os.environ.get("SNAPTIMER_GUI_TESTS") == "1",
                     "set SNAPTIMER_GUI_TESTS=1 on an interactive Windows desktop")
class DesktopTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from snaptimer.app import SnapTimer
        from snaptimer.settings import Settings, SettingsStore
        from snaptimer.windows import SetProcessDPIAware

        SetProcessDPIAware()
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.store = SettingsStore(Path(folder.name) / "settings.ini")
        self.pointer = self.enterContext(patch("snaptimer.app.pointer_over_window", return_value=False))
        self.root = tk.Tk()
        self.app = SnapTimer(
            self.root,
            Settings(duration=1, seconds_mode=True, minimize_to_tray=True),
            self.store,
        )
        self.addCleanup(self.app.close)
        callback_errors = []
        self.root.report_callback_exception = lambda *args: callback_errors.append(args[1])
        self.addCleanup(lambda: self.assertEqual(callback_errors, []))

    def wait_for(self, condition, timeout=3.0):
        deadline = monotonic() + timeout
        while monotonic() < deadline:
            self.root.update()
            if condition():
                return
            sleep(0.015)
        self.fail("Expected desktop state was not reached")

    def test_small_window_keeps_the_clock_and_icon_controls_visible(self):
        from snaptimer.timer import State

        self.root.geometry("1x1")
        self.root.update()
        self.assertLess(self.root.winfo_width(), 324)
        self.assertLess(self.root.winfo_height(), 212)
        display = self.app._display
        self.assertGreaterEqual(display.winfo_width(), display.winfo_reqwidth())
        self.assertGreaterEqual(display.winfo_height(), display.winfo_reqheight())
        entry, toggle, reset = self.app._controls.pack_slaves()
        self.assertIs(entry, self.app.entry)
        for button in (toggle, reset):
            self.assertEqual(str(button.cget("compound")), "none")
            self.assertTrue(button.winfo_ismapped())
        play_image = toggle.cget("image")
        toggle.invoke()
        self.assertEqual(self.app.timer.state, State.RUNNING)
        self.assertNotEqual(toggle.cget("image"), play_image)
        reset.invoke()
        self.assertEqual(self.app.timer.state, State.READY)
        self.assertEqual(toggle.cget("image"), play_image)

    def test_pointer_crossings_toggle_compact_mode_and_restore_right_aligned_controls(self):
        self.root.geometry("420x255")
        self.root.update()
        controls = self.app._controls
        full_size = (self.root.winfo_width(), self.root.winfo_height())
        clock_size = self.app._clock_font.cget("size")
        self.assertTrue(controls.winfo_ismapped())

        self.pointer.return_value = True
        self.wait_for(lambda: self.app._pointer_inside)
        self.pointer.return_value = False
        self.wait_for(lambda: not controls.winfo_ismapped())
        self.assertTrue(self.app.compact)
        self.assertLess(self.root.winfo_height(), full_size[1])
        self.assertEqual(self.app._clock_font.cget("size"), clock_size)
        self.assertEqual(str(self.root.cget("menu")), "")

        self.pointer.return_value = None
        self.app._update_compact_mode()
        self.assertTrue(self.app.compact)

        self.pointer.return_value = True
        self.wait_for(lambda: controls.winfo_ismapped())
        self.assertFalse(self.app.compact)
        self.assertEqual((self.root.winfo_width(), self.root.winfo_height()), full_size)
        self.assertEqual(self.app._clock_font.cget("size"), clock_size)
        self.assertEqual(str(self.root.cget("menu")), str(self.app._menu))
        display = self.app._display
        self.assertEqual(
            controls.winfo_rootx() + controls.winfo_width(), display.winfo_rootx() + display.winfo_width(),
        )

    def test_clock_fits_both_dimensions_in_full_and_compact_modes(self):
        display = self.app._display
        clock_font = self.app._clock_font
        for compact in (False, True):
            with self.subTest(compact=compact):
                if compact:
                    self.app.toggle_compact()
                self.root.update()
                min_width, min_height = self.root.minsize()
                sizes = []
                for width, height in ((480, 220), (min_width, 220), (480, min_height)):
                    self.root.geometry(f"{width}x{height}")
                    self.root.update()
                    self.assertGreaterEqual(display.winfo_width(), display.winfo_reqwidth())
                    self.assertGreaterEqual(display.winfo_height(), display.winfo_reqheight())
                    sizes.append(abs(clock_font.cget("size")))
                large, narrow, short = sizes
                self.assertGreater(large, narrow)
                self.assertGreater(large, short)

    def test_elapsed_clock_is_smaller_and_tracks_time_while_paused(self):
        from snaptimer.timer import State

        elapsed = self.app._elapsed_display
        self.assertFalse(elapsed.winfo_ismapped())
        self.app._entry_text.set("40")
        now = 0
        self.app.timer._clock = lambda: now
        self.app.toggle()
        now = 5
        self.app.toggle()
        now = 20
        self.app.show_options()
        self.app.options._values["show_elapsed"].set(True)
        self.app.options._accept()
        self.root.update()
        self.assertTrue(self.store.load().show_elapsed)
        self.assertEqual(self.app.timer.state, State.PAUSED)
        self.assertEqual(self.app._time_text.get(), "00:00:35")
        self.assertEqual(self.app._elapsed_text.get(), "00:00:20")

        for compact in (False, True):
            if compact:
                self.app.toggle_compact()
            self.root.geometry("1x1")
            self.root.update()
            display = self.app._display
            self.assertTrue(elapsed.winfo_ismapped())
            self.assertGreaterEqual(elapsed.winfo_rootx(), display.winfo_rootx() + display.winfo_width())
            self.assertLess(abs(self.app._elapsed_font.cget("size")), abs(self.app._clock_font.cget("size")))
            for clock in (display, elapsed):
                self.assertGreaterEqual(clock.winfo_width(), clock.winfo_reqwidth())
                self.assertGreaterEqual(clock.winfo_height(), clock.winfo_reqheight())

        now = 22
        self.wait_for(lambda: self.app._elapsed_text.get() == "00:00:22")
        self.assertEqual(self.app._time_text.get(), "00:00:35")
        self.app.reset()
        now = 100
        self.app._render()
        self.assertEqual(self.app._elapsed_text.get(), "00:00:22")
        self.assertEqual(self.app._time_text.get(), "00:00:40")
        self.app.toggle()
        self.assertEqual(self.app._elapsed_text.get(), "00:00:00")

    def test_minimum_width_keeps_a_draggable_caption_and_minimize_button(self):
        from ctypes import addressof, sizeof
        from snaptimer.windows import SendMessage, TitleBarInfo, WM_GETTITLEBARINFOEX, window_bounds, window_handle

        for compact in (False, True):
            with self.subTest(compact=compact):
                if compact:
                    self.app.toggle_compact()
                self.root.geometry("1x1")
                self.root.update()
                window = window_handle(self.root.winfo_id())
                info = TitleBarInfo(size=sizeof(TitleBarInfo))
                SendMessage(window, WM_GETTITLEBARINFOEX, 0, addressof(info))
                button = info.buttons[2]
                bounds = window_bounds(self.root.winfo_id())
                self.assertGreater(button.left, info.bounds.left)
                self.assertLessEqual(button.right, bounds.right)
                y = (button.top + button.bottom) // 2
                hits = [
                    SendMessage(window, 0x0084, 0, (x & 0xFFFF) | ((y & 0xFFFF) << 16))
                    for x in range(info.bounds.left, info.bounds.right)
                ]
                self.assertGreaterEqual(hits.count(2), 8)  # HTCAPTION
                self.assertIn(8, hits)  # HTMINBUTTON

    def test_countdown_options_alarm_and_automatic_restart(self):
        from snaptimer.timer import State

        self.assertEqual(self.app._time_text.get(), "00:00:01")
        self.app.apply_settings(replace(self.app.settings, auto_restart=True))
        self.app.toggle()
        self.assertTrue(self.root.title().endswith(" - SnapTimer"))
        self.app.show_options()
        self.assertIsNotNone(self.app.options)
        self.assertNotIn("font_size", self.app.options._values)
        self.wait_for(lambda: self.app.alarm is not None)
        self.assertEqual(self.app.timer.state, State.FINISHED)
        self.assertEqual(self.app._time_text.get(), "00:00:00")
        owner = self.app.options
        self.app._dismiss_alarm(owner)
        self.assertEqual(self.root.grab_current(), owner)
        self.assertEqual(self.app.timer.state, State.RUNNING)
        owner.close()
        self.app.toggle()
        self.assertEqual(self.app.timer.state, State.PAUSED)
        self.app.reset()
        self.assertEqual(self.app._time_text.get(), "00:00:01")
        self.assertTrue(self.store.load().auto_restart)

    def test_restart_dropdown_shortens_after_the_alarm_and_reset_restores_the_preset(self):
        from snaptimer.timer import State

        fraction = self.app._restart_fraction
        self.assertFalse(fraction.winfo_ismapped())
        self.app.show_options()
        self.app.options._values["auto_restart"].set(True)
        self.app.options._values["seconds_mode"].set(False)
        self.app.options._accept()
        self.root.update()
        self.assertTrue(fraction.winfo_ismapped())
        self.assertEqual(self.app._controls.pack_slaves()[:2], [self.app.entry, fraction])
        self.assertEqual(tuple(fraction.cget("values")), ("None", "1/2", "1/3", "1/4", "1/5"))
        self.assertFalse(fraction.instate(("readonly",)))
        fraction.focus_force()
        self.root.update()
        fraction.delete(0, "end")
        fraction.insert(0, "0.91")
        fraction.event_generate("<Return>")
        self.assertEqual(self.store.load().restart_fraction, "0.91")
        self.assertEqual(self.app.timer.state, State.READY)
        fraction.current(1)
        fraction.event_generate("<<ComboboxSelected>>")
        self.assertEqual(self.store.load().restart_fraction, "1/2")

        now = 0
        self.app._entry_text.set("16")
        self.app.timer._clock = lambda: now
        self.app.toggle()
        self.assertEqual(self.app._time_text.get(), "00:16:00")
        self.root.focus_force()
        self.root.tk.call("ttk::combobox::Post", fraction)
        self.root.update()
        self.assertTrue(self.root.tk.call("grab", "current", self.root))
        self.app._update_compact_mode()
        now = 960
        self.wait_for(lambda: self.app.alarm is not None)
        self.assertEqual(self.app.timer.state, State.FINISHED)
        self.app._dismiss_alarm(None)
        self.assertEqual(self.app._time_text.get(), "00:08:00")
        self.assertEqual(self.app.entry.get(), "16")

        self.app.toggle()
        self.assertEqual(self.app.timer.state, State.PAUSED)
        self.app.toggle()
        self.assertEqual(self.app._time_text.get(), "00:08:00")
        self.app.reset()
        self.assertEqual(self.app.timer.state, State.READY)
        self.assertEqual(self.app._time_text.get(), "00:16:00")
        self.app.apply_settings(replace(self.app.settings, auto_restart=False))
        self.root.update()
        self.assertFalse(fraction.winfo_ismapped())

    def test_tray_activation_and_compact_round_trip(self):
        from snaptimer.timer import State
        from snaptimer.windows import NIN_SELECT, WM_LBUTTONUP, WM_TRAY, PostMessage

        tray = self.app.tray
        self.assertIsNotNone(tray)
        self.wait_for(lambda: tray.available)
        self.app.toggle_compact()
        self.root.update()
        self.assertFalse(self.app._controls.winfo_ismapped())
        self.app.toggle_compact()
        self.root.update()
        self.assertTrue(self.app._controls.winfo_ismapped())
        self.root.iconify()
        self.wait_for(lambda: self.root.state() == "withdrawn")
        event = NIN_SELECT if tray._version4 else WM_LBUTTONUP
        self.assertTrue(PostMessage(tray._window, WM_TRAY, 0, event))
        self.wait_for(lambda: self.root.state() == "normal")
        self.assertTrue(PostMessage(tray._window, WM_TRAY, 0, event))
        self.wait_for(lambda: self.app.timer.state is State.RUNNING)
        self.assertTrue(tray.notify("SnapTimer test", "Test notification"))

    def test_audio_and_settings_changes_keep_active_timer_running(self):
        from snaptimer.app import TICKING_SOUND
        from snaptimer.timer import State

        self.app._entry_text.set("59")
        self.app.toggle()
        self.app.apply_settings(replace(self.app.settings, ticking=True, seconds_mode=False, hide_seconds=True))
        self.assertEqual(self.app.audio._current, (TICKING_SOUND, True))
        self.assertEqual(self.app.timer.state, State.RUNNING)
        self.assertLessEqual(self.app.timer.seconds, 59)
        self.assertEqual(self.app._time_text.get(), "00:00")
        self.app.reset()
        self.assertIsNone(self.app.audio._current)
        self.assertEqual(self.app.timer.seconds, 59 * 60)

    def test_automatic_restart_lets_the_wav_finish_before_ticking_resumes(self):
        from snaptimer.app import TICKING_SOUND
        from snaptimer.settings import ASSETS
        from snaptimer.timer import State

        wav = Path("sounds") / "alarm_03.wav"
        self.app.apply_settings(replace(
            self.app.settings, auto_restart=True, message_enabled=False, audio_file_enabled=True,
            audio_file=str(wav),
        ))
        now = 0
        self.app.timer._clock = lambda: now
        self.app.toggle()
        now = 1
        self.wait_for(lambda: self.app.audio._current == (ASSETS / wav, False))
        self.assertEqual(self.app.timer.state, State.RUNNING)
        self.assertIsNone(self.app.alarm)
        self.app.apply_settings(replace(self.app.settings, ticking=True))
        self.assertEqual(self.app.audio._current, (ASSETS / wav, False))
        self.assertTrue(self.app._ticking_pending)
        self.wait_for(lambda: self.app.audio._current == (TICKING_SOUND, True))
        self.assertFalse(self.app._ticking_pending)

    def test_countdown_music_loops_and_follows_numbered_intervals(self):
        from snaptimer.music import numbered_tracks
        from snaptimer.settings import ASSETS
        from snaptimer.timer import State

        folder = self.store.path.parent / "music"
        folder.mkdir()
        first, second = folder / "2-first.wav", folder / "10-second.wav"
        copyfile(ASSETS / "sounds" / "alarm_03.wav", second)
        copyfile(ASSETS / "sounds" / "siren.wav", first)
        copyfile(first, folder / "unnumbered.wav")
        self.app._tracks = numbered_tracks(folder)
        self.assertEqual(self.app._tracks, (first, second))

        self.app.apply_settings(replace(self.app.settings, auto_restart=True, message_enabled=False))
        self.app.show_options()
        self.app.options._values["music_enabled"].set(True)
        self.app.options._accept()
        self.assertTrue(self.store.load().music_enabled)
        now = 0
        self.app.timer._clock = lambda: now
        with patch.object(self.app.music, "_command", wraps=self.app.music._command) as command:
            self.app.toggle()
            self.assertEqual(self.app.music.path, first)
            self.app.toggle()
            self.assertEqual(self.app.timer.state, State.PAUSED)
            self.assertEqual(self.app.music.mode, "paused")
            self.app.toggle()
            self.assertEqual(self.app.music.mode, "playing")
            self.wait_for(lambda: sum(call.args[0].startswith("play ") for call in command.call_args_list) == 2)
        self.assertEqual(self.app.music.path, first)
        now = 1
        self.wait_for(lambda: self.app.music.path == second)
        now = 2
        self.wait_for(lambda: self.app.music.path == first)
        self.app.reset()
        self.assertIsNone(self.app.music.path)
        self.app.toggle()
        self.assertEqual(self.app.music.path, first)
        self.app.apply_settings(replace(self.app.settings, music_enabled=False))
        self.assertIsNone(self.app.music.path)
        self.assertEqual(self.app.timer.state, State.RUNNING)

    def test_music_waits_for_the_full_wav_alarm_before_the_next_interval(self):
        from snaptimer.settings import ASSETS
        from snaptimer.timer import State

        first = ASSETS / "sounds" / "siren.wav"
        second = ASSETS / "sounds" / "teapot.wav"
        self.app._tracks = (first, second)
        self.app.apply_settings(replace(
            self.app.settings, auto_restart=True, message_enabled=False, audio_file_enabled=True,
            audio_file=str(Path("sounds") / "alarm_03.wav"), loop_audio=True, music_enabled=True,
        ))
        now = 0
        self.app.timer._clock = lambda: now
        self.app.toggle()
        self.assertEqual(self.app.music.path, first)
        now = 1
        self.wait_for(lambda: self.app._interval_alarm.mode == "playing")
        self.assertIsNone(self.app.music.path)
        self.assertEqual(self.app.timer.state, State.FINISHED)
        self.wait_for(lambda: self.app.music.path == second)
        self.assertEqual(self.app._interval_alarm.mode, "closed")
        self.assertEqual(self.app.timer.state, State.RUNNING)
        self.assertEqual(self.app.timer.seconds, 1)

