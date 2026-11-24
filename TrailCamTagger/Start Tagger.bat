@echo off
rem Trail Cam Tagger - Copyright (C) 2026 Trail Cam Tagger contributors
rem SPDX-License-Identifier: AGPL-3.0-or-later
rem Backup way to start, with a console window that shows any errors.
cd /d "%~dp0.."
where py >nul 2>nul && (py "Trail Cam Tagger.pyw" & pause & exit /b)
python "Trail Cam Tagger.pyw"
pause
