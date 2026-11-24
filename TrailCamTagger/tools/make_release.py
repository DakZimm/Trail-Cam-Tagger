# Trail Cam Tagger
# Copyright (C) 2026 Trail Cam Tagger contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Build "Trail Cams.zip" for a GitHub release.

    python TrailCamTagger/tools/make_release.py [output.zip]

Run it from a clone of the repository. Personal files (settings, tag data,
logs, the spreadsheet, clips in Raw/Output) are left out, and the Mac/Linux
starters are marked as runnable inside the zip. By default the zip is written
next to the repository folder, not inside it.
"""

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # the repository / "Trail Cams" folder
TOP = "Trail Cams"                           # folder name people get when they unzip
SKIP = {"settings.json", "error_log.txt", "Clip Log.xlsx", "__pycache__", "pyenv", ".git",
        ".DS_Store", "Thumbs.db", "desktop.ini"}
RUNNABLE = {".command", ".sh", ".pyw"}


def keep(rel):
    if any(part in SKIP for part in rel.parts):
        return False
    if rel.name.startswith(("tagger_data.json", "~tmp_")) or rel.suffix == ".zip":
        return False
    if rel.parts[0] in ("Raw", "Output") and rel.name != ".gitkeep":
        return False  # never ship anyone's clips
    return True


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / f"{TOP}.zip"
    count = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(ROOT.rglob("*")):
            rel = path.relative_to(ROOT)
            if not path.is_file() or not keep(rel):
                continue
            info = zipfile.ZipInfo.from_file(path, f"{TOP}/{rel.as_posix()}")
            info.external_attr = (0o100755 if path.suffix in RUNNABLE else 0o100644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, path.read_bytes())
            count += 1
    print(f"Wrote {out} ({count} files)")


if __name__ == "__main__":
    main()
