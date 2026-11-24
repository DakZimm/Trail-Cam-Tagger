#!/bin/bash
# Trail Cam Tagger - Copyright (C) 2026 Trail Cam Tagger contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
# Trail Cam Tagger for Linux: run this file (double-click and choose "Run", or: ./Start\ on\ Linux.sh)
# (Windows users: use "Trail Cam Tagger.pyw" instead.)
cd "$(dirname "$0")" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is not installed. Install it with your package manager, e.g.:"
  echo "  sudo apt install python3 python3-tk python3-venv"
  read -r -p "Press Enter to close..."
  exit 1
fi
python3 "Trail Cam Tagger.pyw" || read -r -p "Something went wrong (see above). Press Enter to close..."
