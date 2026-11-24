# Trail Cam Tagger
# Copyright (C) 2026 Trail Cam Tagger contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under the
# terms of the GNU Affero General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later version.
# It is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
# PURPOSE. See the LICENSE file for details.

"""Trail Cam Tagger - double-click this file to start (Windows).
Mac: double-click "Start on Mac.command".  Linux: run "Start on Linux.sh"."""
import os
import subprocess
import sys
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP = HERE / "TrailCamTagger"
LOG = APP / "error_log.txt"
NEEDED = ["opencv-python", "pillow", "openpyxl"]
WINDOWS = os.name == "nt"
PYENV = APP / "pyenv"  # Mac/Linux only: private folder for the add-ons (Windows doesn't use it)

if sys.stdout is None or sys.stderr is None:  # no console window: send messages to the log
    try:
        sys.stdout = sys.stderr = open(LOG, "a", encoding="utf-8", buffering=1)
    except OSError:
        sys.stdout = sys.stderr = open(os.devnull, "w")
sys.path.insert(0, str(APP))


def pyenv_python():
    return PYENV / "bin" / "python3"


def restart_with(python):
    os.execv(str(python), [str(python), str(Path(__file__).resolve())] + sys.argv[1:])


if not WINDOWS:
    # Mac/Linux: run inside the private add-on folder once it exists
    if pyenv_python().exists() and Path(sys.prefix).resolve() != PYENV.resolve():
        restart_with(pyenv_python())
    try:
        import tkinter  # noqa: F401
    except ImportError:
        print("\nTrail Cam Tagger needs Python's window toolkit (tkinter), which isn't installed.\n"
              "  Mac:    install Python from https://www.python.org/downloads/ (it includes it),\n"
              "          or with Homebrew:  brew install python-tk\n"
              "  Linux:  sudo apt install python3-tk     (Fedora: sudo dnf install python3-tkinter)\n")
        sys.exit(1)


def libraries_missing():
    try:
        import cv2, openpyxl  # noqa: F401
        from PIL import Image, ImageTk  # noqa: F401
        return False
    except ImportError:
        return True


def install_commands():
    pip_args = ["-m", "pip", "install", "--disable-pip-version-check", *NEEDED]
    if WINDOWS:
        exe = Path(sys.executable)
        if exe.with_name("python.exe").exists():
            exe = exe.with_name("python.exe")
        return [[str(exe), *pip_args]]
    # Mac/Linux: many systems refuse system-wide installs, so use a private folder
    if Path(sys.prefix).resolve() == PYENV.resolve():  # folder exists from an earlier try
        return [[sys.executable, *pip_args]]
    return [[sys.executable, "-m", "venv", str(PYENV)],
            [str(pyenv_python()), *pip_args]]


def install_libraries():
    import tkinter as tk
    from tkinter import messagebox, ttk
    root = tk.Tk()
    root.title("Trail Cam Tagger")
    ttk.Label(root, text="First start: installing a few free add-ons.\nThis takes a minute or two...",
              padding=20, justify="center").pack()
    bar = ttk.Progressbar(root, mode="indeterminate", length=320)
    bar.pack(padx=20, pady=(0, 20))
    bar.start(12)
    result = {}

    def work():
        try:
            for cmd in install_commands():
                r = subprocess.run(cmd, capture_output=True, text=True,
                                   creationflags=0x08000000 if WINDOWS else 0)
                result["r"] = r
                if r.returncode != 0:
                    break
        except Exception as e:
            result["err"] = str(e)
        root.after(0, root.destroy)

    threading.Thread(target=work, daemon=True).start()
    root.mainloop()
    r = result.get("r")
    if r is None or r.returncode != 0:
        details = (result.get("err", "") + (r.stdout if r else "") + (r.stderr if r else ""))
        print(details)
        hint = ""
        if not WINDOWS and ("venv" in details or "ensurepip" in details):
            hint = ("\n\nLinux: install the missing piece with\n  sudo apt install python3-venv\n"
                    "then start the program again.")
        msg = tk.Tk()
        msg.withdraw()
        messagebox.showerror("Trail Cam Tagger", "Couldn't install the add-ons. Is the internet connected?"
                             f"{hint}\n\nDetails are in:\n{LOG}")
        if not WINDOWS and PYENV.exists() and not pyenv_python().exists():
            import shutil
            shutil.rmtree(PYENV, ignore_errors=True)
        sys.exit(1)
    if not WINDOWS:
        restart_with(pyenv_python())  # continue inside the private add-on folder
    import importlib
    importlib.invalidate_caches()


if libraries_missing():
    install_libraries()

import trailcam_tagger  # noqa: E402

trailcam_tagger.main()
