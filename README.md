# SnapTimer for Windows

SnapTimer is a compact countdown timer and stopwatch for Windows 10 and 11. This project is a Python port of Dan Hersam’s [original SnapTimer 0.2 for Lazarus](https://github.com/jaden/SnapTimer).

## Run SnapTimer

To run the portable executable, follow the build instructions below, then open **dist/SnapTimer.exe** from File Explorer. The portable x86 executable bundles Python, Tk, icons, and sounds. It targets standard Windows desktop PCs with x86, x64, or ARM64 processors. Windows on ARM runs it through its built-in x86 emulation. Use a regular Windows desktop session with Explorer for the notification area features.

To run from source, install [Python for Windows](https://www.python.org/downloads/windows/) with Tcl/Tk. Python 3.15 is recommended. The app also runs from source on Python 3.11 and later. Double-click **SnapTimer.pyw** or run:

    python -m snaptimer

The source has no third-party runtime dependencies. Both launchers accept a duration in the configured units. Omit it to use the saved duration.

    .\dist\SnapTimer.exe 20 --start
    python -m snaptimer 0
    python -m snaptimer 5 --ini .\break.ini

## Use the timer

- Enter 0 for a stopwatch or 1–5999 for a countdown. Use **Up** and **Down** to change the value by five. Set seconds mode in **Edit → Options → General** to enter seconds.
- Press **Enter** to start or pause. Click the time to start or pause and double-click to reset. **Ctrl+R** also resets. **Esc** closes the app.
- Enable **Show elapsed time** in **Edit → Options → General** to see a smaller clock to the right of the countdown. It counts from the first Start through pauses and automatic restarts. Stop/Reset freezes that total and the next Start begins at zero.
- Enable **Restart the countdown after the alarm** in **Edit → Options → General** to show the restart fraction beside the duration. Choose **None** to repeat the original duration, pick **1/2**, **1/3**, **1/4**, or **1/5**, or enter a decimal greater than 0 and at most 1. Press **Enter** or leave the field to apply it. Each shortened restart uses that fraction of the previous duration, rounded down to a whole second with a one-minute minimum. Reset returns to the starting duration.
- Use **Edit → Options** to select message, Windows notification, WAV, and program/file alarms. Use **Test** beside each alarm to try it immediately. Windows controls where notification icons appear and can suppress notification pop-ups when Do Not Disturb is on.
- To use **Play music during the countdown** in **Edit → Options → Alarms**, create `snaptimer/assets/music` and add your own numbered MP3 or WAV files, such as `1-track.mp3`. The repository contains no countdown music. SnapTimer reads the files in numeric order. Each countdown gets one looping track, and the playlist wraps after the last track. Pause holds the track at its current position, and Reset returns to the first track. An automatic restart with music waits for the WAV alarm before starting the next countdown. Without a message box to dismiss, that alarm plays once.
- Right-click the notification icon to see the time and controls. Click it to restore a window minimized to the notification area or to pause or resume a visible timer.
- Moving the pointer out of the timer window switches to compact mode. Move it back over the clock to restore the controls. Use **Ctrl+M** or right-click the time to switch modes manually.
- Resize the window to change the clock text size. Set the font family, style, and colors in **Edit → Options → Appearance**.

Settings are saved automatically by default to **%LOCALAPPDATA%\SnapTimer\snaptimer.ini**. For a portable setup, launch once with **--portable** from a writable folder. Subsequent launches use the INI beside the executable when it exists. You can also copy in an existing SnapTimer INI or use **--ini PATH** to give an instance its own settings. Relative alarm paths are first resolved beside the INI, then beside the executable or source launcher, and then against the bundled assets.

## Project structure

| Module | Responsibility |
| --- | --- |
| timer.py | Countdown and stopwatch state. Fractional time survives pause and resume, and expiration fires once. |
| settings.py | Original INI keys, defaults, path resolution, and atomic writes. |
| app.py, options.py | Main timer window, commands, and three-tab options dialog. |
| windows.py, alerts.py | Native notification icon, window placement, WAV playback, and opening configured files. |

The port fixes the original countdown’s off-by-one display, applies appearance changes without resetting an active timer, and restores the controls when exiting compact mode.

## Verify and build

Run the behavioral and INI tests from a PowerShell prompt at the project root:

    python -B -m unittest discover -s tests -v

On an interactive Windows desktop with an audio device and Explorer, enable the desktop integration checks before running the same suite:

    $env:SNAPTIMER_GUI_TESTS = '1'
    python -B -m unittest discover -s tests -v

To reproduce the portable x86 build, run the following with a **32-bit** installation of Python with Tcl/Tk. Use an interpreter matching the desired architecture to build a native x64 or ARM64 version.

    python -m venv .build-env
    .\.build-env\Scripts\python.exe -m pip install -r requirements-build.txt
    .\.build-env\Scripts\python.exe build.py

The build writes **dist/SnapTimer.exe**. Temporary build files stay outside the project. To build an executable without countdown music, build from a fresh checkout. When distributing the executable, include this README for attribution.

## Attribution

The original [SnapTimer](https://github.com/jaden/SnapTimer) was written by Dan Hersam and described as freeware in the original readme. The bundled sounds and icons come from the supplied source. The original project credits [Freesound](https://freesound.org/), A1 Free Sound Effects, and FatCow's icon collection.

