#!/bin/bash
# Trail Cam Tagger - Copyright (C) 2026 Trail Cam Tagger contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
# Trail Cam Tagger for Mac: double-click this file to start.
# (Windows users: use "Trail Cam Tagger.pyw" instead.)
cd "$(dirname "$0")" || exit 1
PY=""
for p in /Library/Frameworks/Python.framework/Versions/Current/bin/python3 /usr/local/bin/python3 /opt/homebrew/bin/python3 python3; do
  if command -v "$p" >/dev/null 2>&1 && "$p" -c "import sys; sys.exit(sys.version_info < (3, 10))" 2>/dev/null; then PY="$p"; break; fi
done
if [ -z "$PY" ]; then
  echo "Python 3.10 or newer is not installed."
  echo "Download it from https://www.python.org/downloads/ , install it, then double-click this file again."
  read -r -p "Press Enter to close..."
  exit 1
fi
echo "Starting Trail Cam Tagger... (you can leave this window open or minimize it)"
"$PY" "Trail Cam Tagger.pyw" || read -r -p "Something went wrong (see above). Press Enter to close..."
