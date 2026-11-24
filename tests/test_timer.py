from fractions import Fraction
import unittest

from snaptimer.timer import State, Timer, format_time


class Clock:
    now = 0.0

    def __call__(self) -> float:
        return self.now


class TimerTests(unittest.TestCase):
    def test_session_time_includes_pauses_and_automatic_restarts_until_reset(self):
        clock = Clock()
        timer = Timer(10, clock)
        self.assertEqual(timer.session_seconds, 0)
        timer.start()
        clock.now = 2.5
        timer.pause()
        clock.now = 12.5
        self.assertEqual(timer.session_seconds, 12)
        self.assertEqual(timer.seconds, 8)
        timer.start()
        clock.now = 20
        self.assertTrue(timer.advance())

        clock.now = 23
        timer.restart_after_alarm(Fraction(1))
        self.assertEqual(timer.session_seconds, 23)
        self.assertEqual(timer.seconds, 10)
        clock.now = 28.8
        timer.reset()
        clock.now = 100
        self.assertEqual(timer.session_seconds, 28)
        self.assertEqual(timer.seconds, 10)
        timer.start()
        self.assertEqual(timer.session_seconds, 0)
        clock.now += 1.5
        self.assertEqual(timer.session_seconds, 1)

    def test_pausing_preserves_fractional_seconds(self):
        clock = Clock()
        timer = Timer(2, clock)
        timer.start()
        clock.now = 1.75
        self.assertEqual(timer.seconds, 1)
        timer.pause()
        clock.now = 1000.0
        self.assertEqual(timer.seconds, 1)
        timer.start()
        clock.now += 0.25
        self.assertTrue(timer.advance())
        self.assertEqual(timer.seconds, 0)
        self.assertEqual(timer.state, State.FINISHED)
        self.assertFalse(timer.advance())

    def test_expiration_can_restart_with_new_preset(self):
        clock = Clock()
        timer = Timer(5, clock)
        timer.start()
        timer.preset = 10
        clock.now = 15
        self.assertTrue(timer.advance())
        timer.start()
        self.assertEqual(timer.seconds, 10)
        timer.preset = 0
        timer.reset()
        self.assertEqual(timer.state, State.READY)
        self.assertTrue(timer.stopwatch)

    def test_automatic_restarts_shorten_previous_interval_to_a_minute_floor(self):
        for value, intervals in (
            ("1", (960, 960)),
            ("1/2", (480, 240, 120, 60, 60)),
            ("1/3", (320, 106, 60, 60)),
            ("1/4", (240, 60, 60)),
            ("1/5", (192, 60, 60)),
            ("0.91", (873, 794)),
            ("0.01", (60, 60)),
        ):
            with self.subTest(value=value):
                clock = Clock()
                timer = Timer(16 * 60, clock)
                timer.start()
                duration = timer.seconds
                for next_duration in intervals:
                    clock.now += duration
                    self.assertTrue(timer.advance())
                    timer.restart_after_alarm(Fraction(value))
                    self.assertEqual(timer.seconds, next_duration)
                    self.assertEqual(timer.session_seconds, clock.now)
                    duration = next_duration

                clock.now += duration
                self.assertTrue(timer.advance())
                timer.start()
                self.assertEqual(timer.seconds, 960)
                self.assertEqual(timer.session_seconds, 0)

    def test_automatic_restarts_use_a_new_preset_before_shortening(self):
        clock = Clock()
        timer = Timer(30, clock)
        timer.start()
        clock.now = 30
        self.assertTrue(timer.advance())
        timer.restart_after_alarm(Fraction(1, 2))
        self.assertEqual(timer.seconds, 60)

        timer.preset = 300
        clock.now += 60
        self.assertTrue(timer.advance())
        timer.restart_after_alarm(Fraction(1, 2))
        self.assertEqual(timer.seconds, 300)
        clock.now += 300
        self.assertTrue(timer.advance())
        timer.restart_after_alarm(Fraction(1, 2))
        self.assertEqual(timer.seconds, 150)
        timer.reset()
        self.assertEqual(timer.seconds, 300)

    def test_stopwatch_resumes_without_counting_time_paused(self):
        clock = Clock()
        timer = Timer(0, clock)
        timer.start()
        clock.now = 1.5
        timer.pause()
        clock.now = 30
        timer.start()
        clock.now = 31.5
        self.assertFalse(timer.advance())
        self.assertEqual(timer.seconds, 3)

    def test_display_format(self):
        self.assertEqual(format_time(0), "00:00:00")
        self.assertEqual(format_time(3661), "01:01:01")
        self.assertEqual(format_time(3661, hide_seconds=True), "01:01")
        self.assertEqual(format_time(360000), "100:00:00")

