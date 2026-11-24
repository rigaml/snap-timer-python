"""Build a standalone, windowed Windows executable with PyInstaller."""

import importlib.metadata
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory


def main() -> None:
    if sys.platform != "win32":
        sys.exit("Build the executable on Windows.")
    import tkinter
    from snaptimer.music import numbered_tracks

    tkinter.Tcl()

    project = Path(__file__).resolve().parent
    assets_target = "snaptimer/assets"
    assets = project / assets_target

    with TemporaryDirectory(prefix="snaptimer-build-") as workspace:
        command = [
            sys.executable, "-m", "PyInstaller",
            "--noconfirm", "--onefile", "--windowed", "--noupx", "--name", "SnapTimer",
            "--icon", str(assets / "images" / "snaptimer.ico"),
            "--distpath", str(project / "dist"),
            "--specpath", workspace,
            "--workpath", str(Path(workspace) / "work"),
        ]
        for asset in assets.iterdir():
            if asset.name != "music":
                destination = f"{assets_target}/{asset.name}" if asset.is_dir() else assets_target
                command.extend(("--add-data", f"{asset}:{destination}"))
        for track in numbered_tracks(assets / "music"):
            command.extend(("--add-data", f"{track}:{assets_target}/music"))
        python_license = Path(sys.base_prefix) / "LICENSE.txt"
        if python_license.is_file():
            command.extend(("--add-data", f"{python_license}:licenses"))
        pyinstaller = importlib.metadata.distribution("pyinstaller")
        for item in pyinstaller.files or ():
            if item.name == "COPYING.txt":
                command.extend(("--add-data", f"{pyinstaller.locate_file(item)}:licenses"))
                break
        subprocess.run([*command, str(project / "SnapTimer.pyw")], cwd=project, check=True)


if __name__ == "__main__":
    main()

