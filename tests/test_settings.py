from dataclasses import replace
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from snaptimer.settings import ASSETS, Settings, SettingsStore, color_hex, color_value, parse_restart_fraction


class SettingsTests(unittest.TestCase):
    def test_every_setting_round_trips_through_the_legacy_schema(self):
        with TemporaryDirectory() as folder:
            store = SettingsStore(Path(folder) / "preferences" / "timer.ini")
            self.assertEqual(store.load(), Settings())
            wanted = Settings(
                duration=90, always_on_top=True, minimize_to_tray=True, auto_start=True,
                hide_seconds=True, show_elapsed=True, click_time=False, double_click_time=False,
                auto_restart=True, restart_fraction="0.91", loop_audio=True, ticking=True, auto_save=False,
                seconds_mode=True, message="100% prêt", message_enabled=False,
                tray_message="⏰", tray_message_enabled=True, audio_file=r".\a.wav",
                audio_file_enabled=True, music_enabled=True, run_app=r"C:\A B\test.exe", run_app_enabled=True,
                width=531, height=286, x=-350, y=84, position=1,
                font_name="Arial", font_charset=1, font_size=30, font_style=11,
                font_color=12345, background_color=54321,
            )
            store.save(wanted)
            self.assertEqual(store.load(), wanted)
            self.assertEqual(list(store.path.parent.iterdir()), [store.path])

    def test_old_values_and_unrelated_sections_are_retained(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "snaptimer.ini"
            path.write_bytes(
                b"[main]\r\nMinutes=9000\r\nSecondsMode=1\r\nAutoStart=bad\r\n"
                b"[Placement]\r\nWinPosition=777\r\nWinLeft=-1500\r\n"
                b"[Fonts]\r\nColor=8388608\r\n[Other]\r\nKeep=1\r\n"
            )
            store = SettingsStore(path)
            settings = store.load()
            self.assertEqual(settings.duration, 5999)
            self.assertTrue(settings.seconds_mode)
            self.assertFalse(settings.auto_start)
            self.assertFalse(settings.show_elapsed)
            self.assertEqual(settings.restart_fraction, "None")
            self.assertEqual(settings.x, -1500)
            self.assertEqual(settings.position, 5)
            self.assertEqual(color_hex(settings.font_color, "black"), "#000080")
            store.save(replace(settings, duration=42))
            self.assertIn("[Other]\nKeep=1", path.read_text(encoding="utf-8"))
            self.assertEqual(store.load().duration, 42)

    def test_restart_fraction_migrates_and_validates_old_and_new_values(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "timer.ini"
            store = SettingsStore(path)
            path.write_text("[Main]\nRestartDivisor=3\n", encoding="utf-8")
            self.assertEqual(store.load().restart_fraction, "1/3")
            path.write_text("[Main]\nRestartDivisor=3\nRestartFraction=1.5\n", encoding="utf-8")
            self.assertEqual(store.load().restart_fraction, "None")
        self.assertEqual(parse_restart_fraction("None"), Fraction(1))
        self.assertEqual(parse_restart_fraction("1/5"), Fraction(1, 5))
        self.assertEqual(parse_restart_fraction(" 0.91 "), Fraction(91, 100))
        for invalid in ("", "0", "1.01", "-0.1", "NaN", "1e-2", "1/0"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                parse_restart_fraction(invalid)

    def test_legacy_wav_path_uses_portable_override_then_bundled_asset(self):
        with TemporaryDirectory() as folder:
            store = SettingsStore(Path(folder) / "snaptimer.ini")
            relative = Path("sounds") / "alarm_clock_bell.wav"
            asset = ASSETS / relative
            self.assertTrue(asset.is_file())
            self.assertEqual(store.resolve_file(str(relative)), asset)
            self.assertEqual(store.store_file(asset), str(relative))
            custom = store.path.parent / relative
            custom.parent.mkdir()
            custom.write_bytes(b"override")
            self.assertEqual(store.resolve_file(str(relative)), custom)

    def test_lazarus_bgr_conversion_round_trip(self):
        self.assertEqual(color_hex(color_value("#316ad1"), ""), "#316ad1")
        self.assertEqual(color_hex(0x1FFFFFFF, "#eeeeee"), "#eeeeee")

