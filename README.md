[README.md](https://github.com/user-attachments/files/35345026/README.md)
# Trail-Cam-Tagger
Trail camera clip organizer: watch each video or photo, tag deer (points, left×right, nicknames), turkeys and more, and it renames files, sorts them into folders, and logs everything to a spreadsheet. Tracks individual bucks across seasons. Free and offline, for Windows/Mac/Linux.

![License: AGPL v3](https://img.shields.io/badge/license-AGPL%20v3-blue)
![Platforms](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)
![Python](https://img.shields.io/badge/python-3.10%2B-yellow)

![Tagging a buck in Trail Cam Tagger](TrailCamTagger/screenshots/app_tagged.png)

```
IMAG0042.AVI  →  2026-11-20_0614_Hilite_Buck-10pt-5x5-Droptine_Doe-x3_CAM2.avi
```

Free, offline and private: your clips never leave your computer.

---

## Contents
- [Features](#features)
- [Quick start](#quick-start)
- [Folder layout](#folder-layout)
- [Using it](#using-it)
- [Keyboard shortcuts](#keyboard-shortcuts)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

## Features

- **Fast tagging.** One click per animal, `Enter` to save and open the next clip. Videos (AVI, MP4, MOV…) and photos (JPG, PNG), with photo bursts grouped and tagged in one go.
- **Deer details.** Points, left × right, non-typical, unknown points, button bucks, and nicknames for individual deer. Picking a known buck fills in his rack.
- **Smart file names.** Date and time first so folders stay in order, then animals, highlight and camera. The order and formats are fully customizable with drag-and-drop.
- **Spreadsheet log.** `Clip Log.xlsx`: one row per animal with filters, clickable file links, and an Animals sheet.
- **Track individual animals.** First and last seen, clips per camera, rack history, and harvested / found dead status.
- **Review and edit** any tagged clip later. The file is renamed to match.
- **Plays well with your file manager.** Delete, restore or rename clips by hand and the log keeps up.
- **Customizable animal buttons and groups.** Drag and drop, add your own species and details.
- **Built-in tutorials.** A step-by-step guide on first start, plus a *What's this?* mode that explains any button you click.
- **Portable.** The whole folder can live on a PC, USB drive or NAS and be moved anywhere.

## Quick start

> 📄 New to this? **[Getting Started.pdf](Getting%20Started.pdf)** walks through every step with pictures.

**1. Install Python 3.10 or newer (one time)**

| | |
|---|---|
| **Windows** | Download from [python.org](https://www.python.org/downloads/) and run the installer. **Tick “Add python.exe to PATH”** on the first screen. |
| **macOS** | Download the macOS installer from [python.org](https://www.python.org/downloads/) and run it. |
| **Linux** | `sudo apt install python3 python3-tk python3-venv`  (Fedora: `sudo dnf install python3 python3-tkinter`) |

**2. Download the program**

Download the latest **Trail Cams.zip** from the [Releases](../../releases) page (or **Code → Download ZIP**) and extract it anywhere.

**3. Start it**

| | |
|---|---|
| **Windows** | Double-click **`Trail Cam Tagger.pyw`** |
| **macOS** | Double-click **`Start on Mac.command`**. The first time, macOS may block it: right-click → **Open** → **Open**. |
| **Linux** | Run **`Start on Linux.sh`** (or `python3 "Trail Cam Tagger.pyw"`) |

On first start it downloads three free add-ons ([OpenCV](https://opencv.org/), [Pillow](https://python-pillow.org/), [openpyxl](https://openpyxl.readthedocs.io/)), which needs internet once, then opens with the step-by-step guide.

## Folder layout

```
Trail Cams/
├── Trail Cam Tagger.pyw     Windows: double-click to start
├── Start on Mac.command     macOS: double-click to start
├── Start on Linux.sh        Linux: run to start
├── Clip Log.xlsx            the spreadsheet (created automatically)
├── Getting Started.pdf      setup guide with pictures
├── Raw/                     ← copy SD cards here, one folder per camera
│   ├── CAM1/ … CAM4/
├── Output/                  ← tagged clips end up here, renamed
│   ├── CAM1/
│   │   └── Empty/           clips with nothing in them
│   └── …
└── TrailCamTagger/          program files, settings and tag data
```

Rename the camera folders (e.g. `EastRidge`) or add more. A new folder in either `Raw` or `Output` gets its partner created automatically and appears in the camera list.

## Using it

### Tag new clips
1. Copy an SD card into its `Raw/CAMx` folder.
2. Pick that camera at the top. The first clip plays.
3. Click each animal you see. Each click adds a line with Count, Details and ✕. Bucks also get Points, Left × Right, NonTyp, Unknown pts and Button buck. Add a Nickname from the list or type a new one.
4. **★ Hilite** marks a great clip. **Notes** go in the spreadsheet.
5. **Save & Next** (`Enter`), **Empty** (`E`), **Skip** (`S`) or **Undo** (`Ctrl+Z`).

Zoom with the mouse wheel and step frame by frame to count points.

### File names
```
2026-11-20_0614_Hilite_Buck-10pt-5x5-NonTyp-Droptine_Doe-x3_CAM2.avi
2026-11-20_0614-1_Turkey-Tom-x4_CAM2.jpg        (-1, -2… = same minute)
2026-11-20_1830_Empty_CAM2.avi                  (in Output/CAM2/Empty)
```
Search the Output folder for `Buck`, `10pt`, `5x5`, `NonTyp`, `UnkPts`, `Button`, `Hilite`, a nickname or a camera.

| Search in | How |
|---|---|
| **Windows** | File Explorer's search box (top right) |
| **macOS** | Finder: `⌘F`, choose **“Output”** (not “This Mac”) |
| **Linux** | File manager: `Ctrl+F` |

### Review / edit tagged
Filter by camera, Hilite, empties, text or dates. Click a clip, change anything and save; the file is renamed for you. **Send back to Raw** removes the tags.

### Animals
Every nicknamed animal with first/last seen, clip count, cameras, latest rack and most points. Set a status (Active, Harvested, Found dead, Presumed gone) with date, by and notes, jump to all of its clips, or merge two nicknames that turned out to be the same deer.

### Menus (left to right)
- **File:** open the Trail Cams, Raw and Output folders and the spreadsheet.
- **Tools:**
  - **Settings:** file name blocks and formats, folders and burst time, animal buttons and groups;
  - rename a nickname everywhere, re-apply file names, check the log, forget deleted clips, rebuild the spreadsheet.
- **Help:** step-by-step guide, *What's this?*, keyboard shortcuts, About.
- **❓ Tutorial** (top right): the guide, *What's this?* mode (Shift+click to really click something) and whether the guide shows at start.

### Deleting clips
Delete old clips or empties in your file manager any time. The program notices when it starts or regains focus. Deleted clips stay in the spreadsheet as grey history rows until you use **Tools → Forget deleted clips**. Restored or hand-renamed files are matched back up automatically.

## Keyboard shortcuts

| Key | Action |
|---|---|
| `Enter` | Save & next (or save changes in Review) |
| `E` | Empty |
| `S` | Skip |
| `H` | Hilite on/off |
| `Ctrl+Z` (macOS: also `⌘Z`) | Undo last save (clip goes back to Raw with its tags filled in) |
| `Space` | Play / pause |
| `,` `.` | Step one frame back / forward |
| `←` `→` | Previous / next photo in a burst |
| `F5` | Rescan the Raw folder |
| Mouse wheel / drag / double-click | Zoom / move / reset zoom |

## Troubleshooting

| | Problem | Fix |
|---|---|---|
| **Windows** | `Trail Cam Tagger.pyw` opens in Notepad | Right-click → **Open with** → **Python**, or use `TrailCamTagger/Start Tagger.bat` |
| **Windows** | “Python is not installed” | Reinstall Python with **Add python.exe to PATH** ticked |
| **macOS** | “Start on Mac.command can't be opened” | Right-click → **Open** → **Open** (first time only) |
| **Linux** | Message about *tkinter*, *venv* or *ensurepip* | `sudo apt install python3-tk python3-venv` |
| **Linux** | `Start on Linux.sh` opens in a text editor | `chmod +x "Start on Linux.sh"` then `./"Start on Linux.sh"` |
| All | “Couldn't install the add-ons” | Check the internet connection; try the previous Python version if you're on a brand-new one |
| All | Spreadsheet doesn't update | Close `Clip Log.xlsx` in your spreadsheet app |
| All | Anything else | See `TrailCamTagger/error_log.txt` and include it in an issue |

Tag data lives in `TrailCamTagger/tagger_data.json` (a `.bak` backup is kept next to it). On macOS and Linux the add-ons are installed into `TrailCamTagger/pyenv`; delete that folder to reinstall them.

## Contributing

Contributions are welcome: bug reports, ideas, documentation and code.

- **Bugs and ideas:** open an [issue](../../issues). For bugs, include your OS, Python version, what you did, and `TrailCamTagger/error_log.txt` if there is one.
- **Code:** fork the repo, make your change on a branch, and open a pull request with a short description and how you tested it. Please keep changes focused and test on your OS.

### Running from source
```bash
git clone <this repo>
cd <repo folder>
python3 -m pip install opencv-python pillow openpyxl   # or let the launcher install them
python3 "Trail Cam Tagger.pyw"                          # Windows: double-click it, or: py "Trail Cam Tagger.pyw"
```

### Project structure
| File | What it does |
|---|---|
| `Trail Cam Tagger.pyw` | Launcher: installs add-ons on first start, then opens the app |
| `TrailCamTagger/core.py` | All logic, no UI: naming, the tag store, renaming, Explorer-change detection, the spreadsheet export |
| `TrailCamTagger/trailcam_tagger.py` | The app window (Tkinter): media viewer, tagging panel, Review, Animals, Settings |
| `TrailCamTagger/tutorial.py` | Step-by-step guide and *What's this?* mode |
| `Start on Mac.command`, `Start on Linux.sh`, `TrailCamTagger/Start Tagger.bat` | Platform starters |

Dependencies: Python 3.10+ with Tkinter, [opencv-python](https://pypi.org/project/opencv-python/), [Pillow](https://pypi.org/project/pillow/), [openpyxl](https://pypi.org/project/openpyxl/).

## License

Trail Cam Tagger is free software, licensed under the **[GNU Affero General Public License v3.0 or later](LICENSE)** (AGPL-3.0-or-later).

You may use, study, share and modify it freely, including for your own business. If you distribute a modified version, **or let others use a modified version over a network** (e.g. as a website or online service), you must make your complete source code available under the same license. This keeps the project and every improvement to it open for everyone.

It comes with no warranty; see [LICENSE](LICENSE) for the full terms.
