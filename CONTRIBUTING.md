[CONTRIBUTING.md](https://github.com/user-attachments/files/35348801/CONTRIBUTING.md)
# Contributing to Trail Cam Tagger

Welcome! We're happy you want to help. Trail Cam Tagger is a community project, and contributions of every size are welcome: bug reports, ideas, documentation, testing on your computer, and code.

Please follow our [Code of Conduct](CODE_OF_CONDUCT.md) in all project spaces.

## Table of contents
- [The basics](#the-basics)
- [Reporting bugs](#reporting-bugs)
- [Suggesting features](#suggesting-features)
- [Prerequisites](#prerequisites)
- [Development](#development)
- [Project structure](#project-structure)
- [Guidelines for changes](#guidelines-for-changes)
- [Testing your change](#testing-your-change)
- [Example: adding an animal button to the defaults](#example-adding-an-animal-button-to-the-defaults)
- [Documentation](#documentation)
- [Pull requests](#pull-requests)
- [AI-assisted contributions](#ai-assisted-contributions)
- [Release process](#release-process)
- [License](#license)

## The basics

- **Small fixes** (typos, clear bugs, wording): just open a pull request.
- **Bigger changes** (new features, changed behavior, new dependencies): please [open an issue](../../issues) first so we can agree on the approach before you spend time on it.
- **Looking for something to do?** Check issues labeled `good first issue` or `help wanted`.
- **Not a programmer?** Testing on your own computer (especially macOS and Linux), improving the docs, and good bug reports are just as valuable.

## Reporting bugs

Open an issue and include:
1. Your operating system (Windows 10/11, macOS version, Linux distribution).
2. Your Python version (`python --version`, or `python3 --version`).
3. What you did, what you expected, and what happened instead.
4. The contents of `TrailCamTagger/error_log.txt`, if there is one.
5. Your camera model and file type (e.g. `.AVI`, `.JPG`), if the problem is with a clip.

Please don't attach clips or `tagger_data.json` unless asked, since they may include private information.

## Suggesting features

Open an issue describing the problem you want solved (not just the solution), for example: *"I run 12 cameras and the camera list is hard to use"*. Screenshots or sketches help. Keep in mind the project's goal: **simple enough for anyone to use, with no setup beyond installing Python.**

## Prerequisites

- **Python 3.10 or newer** with Tkinter:
  - **Windows / macOS:** use the installer from [python.org](https://www.python.org/downloads/). It includes Tkinter.
  - **Linux:** `sudo apt install python3 python3-tk python3-venv` (Fedora: `sudo dnf install python3 python3-tkinter`).
- **Git**, plus a GitHub account to send pull requests.
- **[Ruff](https://docs.astral.sh/ruff/)** for code checks: `python -m pip install ruff`.

## Development

1. Fork the repository on GitHub, then clone your fork:
   ```bash
   git clone https://github.com/<your-username>/<repo-name>.git
   cd <repo-name>
   ```
2. (Recommended) create a virtual environment and install the dependencies:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate        # Windows: .venv\Scripts\activate
   python -m pip install opencv-python pillow openpyxl ruff
   ```
3. Run the program from the repository folder:
   ```bash
   python "Trail Cam Tagger.pyw"
   ```
   The repository *is* a working Trail Cams folder. Put a few test clips in `Raw/CAM1` and tag away. Your settings, tag data, spreadsheet and clips are already excluded by `.gitignore`, so they won't be committed.
4. Create a branch for your change:
   ```bash
   git checkout -b fix-burst-split
   ```
5. Check the code before committing:
   ```bash
   ruff check TrailCamTagger
   ```

## Project structure

```
Trail Cam Tagger.pyw            Launcher: installs add-ons on first start, then opens the app
Start on Mac.command            macOS starter
Start on Linux.sh               Linux starter
TrailCamTagger/
├── core.py                     All logic, no user interface (see below)
├── trailcam_tagger.py          The app window (Tkinter)
├── tutorial.py                 Step-by-step guide and "What's this?" mode
├── Start Tagger.bat            Windows backup starter (shows errors)
├── ruff.toml                   Code check settings
├── docs/                       Source of Getting Started.pdf, plus screenshots
└── tools/make_release.py       Builds the release zip
Raw/, Output/                   Empty camera folders (kept with .gitkeep files)
```

**`core.py`** has no user interface code and is the place for anything that isn't on screen:
- file naming: `build_name`, `animal_part`, back-to-back numbering in `sync_names`;
- the tag store (`Store`, saved to `TrailCamTagger/tagger_data.json`);
- tagging, editing and untagging files: `tag_files`, `update_tags`, `send_back`;
- noticing changes made in the file manager: `reconcile`;
- animal statistics: `animal_stats`, `known_rack`;
- the spreadsheet: `export_xlsx`;
- default settings and animal buttons.

**`trailcam_tagger.py`** is the user interface:
- `MediaView`: video and photo viewer, zoom, bursts;
- `TagRow` / `TagPanel`: the animal lines and buttons;
- `SettingsDialog` and `AnimalEditor`: the Settings window;
- `App`: the Tag, Review and Animals pages, menus and tools.

**`tutorial.py`** holds the guided tour steps (`Tutorial.steps`) and the *What's this?* mode. Help text for each button is registered in `App.register_help`.

## Guidelines for changes

- **Keep it simple for users.** Plain words on screen, no jargon, and sensible defaults. If a feature needs explaining, add it to the tutorial or *What's this?* help.
- **Never lose anyone's clips or tags.** Files are only moved or renamed through `core` functions, which write the tag store first and keep a backup. Don't rename or delete user files anywhere else.
- **Stay backward compatible.** Older `tagger_data.json` and `settings.json` files must keep working. New fields need defaults (see `DEFAULT_SETTINGS` and how records use `.get()`).
- **Keep logic in `core.py`** and screens in `trailcam_tagger.py`, so the logic stays easy to test without a window.
- **Work on Windows, macOS and Linux.** Wrap platform-specific code in a check (`sys.platform`, `os.name`) and keep Windows behavior unchanged unless that's the point of the change.
- **No new dependencies** without discussing it in an issue first. Every add-on is something users have to download.
- **Style:** follow the existing code, 4-space indents, lines up to 120 characters, and `ruff check TrailCamTagger` must pass.
- **License header:** new source files start with the same short AGPL header as the existing ones.

## Testing your change

There's no automated test suite yet (contributions welcome!), so please test by hand on your computer. Use a **copy** of some clips, never your only copy. Run through whatever your change touches, and if in doubt this short checklist:

- [ ] Tag a clip with a buck (points, left × right, nickname), save, and check the new file name.
- [ ] Press **Empty** on a clip and check it lands in `Output/CAMx/Empty`.
- [ ] **Undo** (`Ctrl+Z`) the last save.
- [ ] Edit a clip in **Review / edit tagged** and save.
- [ ] Open the **Animals** page.
- [ ] Open **Tools → Settings** and close it.
- [ ] Check `Clip Log.xlsx` updates.
- [ ] Start once with a fresh folder (no `settings.json`) and check the step-by-step guide appears.

Say in your pull request which operating system(s) you tested on.

## Example: adding an animal button to the defaults

Users can add their own buttons in Settings, but to change the defaults that new installs start with:

1. In `TrailCamTagger/core.py`, find `DEFAULT_SPECIES`.
2. Add an entry with the `_sp` helper:
   ```python
   _sp("", "Badger", "Badger"),                                  # in the "Other" group
   _sp("Deer", "Elk", "Elk", True, ["Bugling", "Wallowing"]),    # group, button, file word, antlers, details
   ```
   - The **file word** goes into file names, so keep it short: letters, digits and dashes only.
   - Never change an existing file word; people's clips are already named with it.
3. If you added a new group, add it to `"groups"` in `DEFAULT_SETTINGS` to control its row order.
4. Start the program with a fresh `settings.json` (rename yours temporarily) and check the button appears and tags correctly.

## Documentation

- **`README.md`:** the project page on GitHub and the quick reference in the download.
- **`Getting Started.pdf`:** built from `TrailCamTagger/docs/getting-started.html`. Edit the HTML, open it in Chrome or Edge, choose **Print → Save as PDF** with *Background graphics* turned on, and save it over `Getting Started.pdf` in the main folder.
- When a change affects what users see, update both, plus the tutorial text in `tutorial.py` and the help text in `App.register_help`.
- Anything that differs between computers is labeled **Windows / macOS / Linux** inside the step it belongs to, not in a separate section.

## Pull requests

1. Keep each pull request focused on one change.
2. Write a clear title and description: what changed, why, and how you tested it (with your OS).
3. Include before/after screenshots for anything visible.
4. Make sure `ruff check TrailCamTagger` passes.
5. A maintainer will review it. Please be patient; this is a volunteer project. You may be asked for changes, which is normal and not a judgment on your work.
6. Once approved, a maintainer merges it.

## AI-assisted contributions

AI-assisted contributions are welcome. This project itself was developed with the help of Claude, an AI assistant made by Anthropic. If AI tools helped write your change:
- say so in your pull request description;
- make sure you've read, understood and tested every part of it yourself, because you're responsible for what you submit;
- don't submit code you can't explain in review.

Every pull request is reviewed by a person before it's merged, whether or not AI was involved.

## Release process

For maintainers:

1. Update `VERSION` in `TrailCamTagger/core.py` (e.g. `1.1.0`).
2. If anything visible changed, update `README.md` and rebuild `Getting Started.pdf`.
3. Build the zip from a clean clone:
   ```bash
   python TrailCamTagger/tools/make_release.py
   ```
   This writes `Trail Cams.zip` next to the repository folder. It leaves out personal files and keeps the Mac/Linux starters runnable.
4. On GitHub: **Releases → Draft a new release**, tag `v1.1.0`, list the changes, and attach `Trail Cams.zip`.

## License

Trail Cam Tagger is licensed under the [GNU Affero General Public License v3.0 or later](LICENSE). By contributing, you agree that your contributions are licensed under the same license.
