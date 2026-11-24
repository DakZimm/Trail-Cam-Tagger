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

"""
Trail Cam Tagger
Started by "Trail Cam Tagger.pyw" in the main folder:

    Trail Cams\\
        Trail Cam Tagger.pyw  <- double-click to start
        Clip Log.xlsx         <- the spreadsheet
        Raw\\CAM1 ...         <- dump each SD card into its camera's folder
        Output\\CAM1 ...      <- tagged clips
        TrailCamTagger\\      <- this program, settings, tag data, error log
"""

import os
import subprocess
import sys
import time
import tkinter as tk
import traceback
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

LOG_PATH = Path(__file__).resolve().parent / "error_log.txt"
if sys.stdout is None or sys.stderr is None:  # started without a console window (pythonw)
    try:
        sys.stdout = sys.stderr = open(LOG_PATH, "a", encoding="utf-8", buffering=1)
    except OSError:
        sys.stdout = sys.stderr = open(os.devnull, "w")

try:
    import cv2
    import numpy as np
    import openpyxl  # noqa: F401  (needed by core.export_xlsx)
    from PIL import Image, ImageTk
except ImportError as e:
    _r = tk.Tk()
    _r.withdraw()
    messagebox.showerror("Trail Cam Tagger", f"A library is missing ({e}).\n\nOpen a Command Prompt and run:\n"
                         "py -m pip install opencv-python pillow openpyxl")
    sys.exit(1)

import core  # noqa: E402  (after the library check above)
import tutorial  # noqa: E402

APP_DIR = Path(__file__).resolve().parent
ROOT = APP_DIR.parent  # the main "Trail Cams" folder
SETTINGS_PATH = APP_DIR / "settings.json"
DATA_PATH = APP_DIR / core.DATA_NAME
XLSX_PATH = ROOT / core.XLSX_NAME

FONT = "Segoe UI"  # falls back to the system font on Mac/Linux
MAC = sys.platform == "darwin"
HILITE_BG = "#ffe9a8"


def resolve(folder):
    p = Path(folder)
    return p if p.is_absolute() else ROOT / p


def rel_to_root(path):
    try:
        return Path(path).resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def read_image(path):
    data = np.fromfile(str(path), dtype=np.uint8)  # works with any characters in the path
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def is_text_widget(w):
    return isinstance(w, (tk.Entry, ttk.Entry, tk.Spinbox, tk.Text))


# =========================================================================
#  Media viewer: video player / photo + burst filmstrip, with zoom & pan
# =========================================================================
class MediaView(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.files = []
        self.photo_idx = 0
        self.cap = None
        self.after_id = None
        self.playing = False
        self.frame = None
        self.tkimg = None
        self.fps = 30.0
        self.updating_scale = False
        self.zoom, self.cx, self.cy = 1.0, 0.5, 0.5
        self.geom = None
        self.press = None
        self.thumbs = []

        self.canvas = tk.Canvas(self, bg="black", highlightthickness=0, cursor="fleur")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self.redraw())
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Double-Button-1>", lambda e: self.reset_zoom())
        self.canvas.bind("<MouseWheel>", lambda e: self.on_wheel(e, 1 if e.delta > 0 else -1))
        self.canvas.bind("<Button-4>", lambda e: self.on_wheel(e, 1))
        self.canvas.bind("<Button-5>", lambda e: self.on_wheel(e, -1))

        # burst filmstrip
        self.strip = ttk.Frame(self)
        self.strip_inner = ttk.Frame(self.strip)
        self.strip_inner.pack(side="left")
        self.split_btn = ttk.Button(self.strip, text="Split burst here", takefocus=False, command=self.app.split_burst)
        self.split_btn.pack(side="right", padx=4)

        # video controls
        self.vctl = ttk.Frame(self, padding=(0, 4))
        ttk.Button(self.vctl, text="◀ frame", width=8, takefocus=False, command=lambda: self.step(-1)).pack(side="left")
        self.play_btn = ttk.Button(self.vctl, text="Pause", width=7, takefocus=False, command=self.toggle_play)
        self.play_btn.pack(side="left", padx=4)
        ttk.Button(self.vctl, text="frame ▶", width=8, takefocus=False, command=lambda: self.step(1)).pack(side="left")
        self.speed_var = tk.StringVar(value="1x")
        ttk.Combobox(self.vctl, values=["0.25x", "0.5x", "1x", "2x"], width=5, state="readonly",
                     textvariable=self.speed_var, takefocus=False).pack(side="right")
        ttk.Label(self.vctl, text="Speed").pack(side="right", padx=4)
        self.scale_var = tk.DoubleVar()
        self.scale = ttk.Scale(self.vctl, from_=0, to=1, variable=self.scale_var)
        self.scale.pack(side="left", fill="x", expand=True, padx=8)
        # grabbing the bar pauses the video; click or drag jumps straight to that spot
        self.scale.bind("<ButtonPress-1>", self.scrub)
        self.scale.bind("<B1-Motion>", self.scrub)
        self.scale.bind("<ButtonRelease-1>", lambda e: "break")

        self.info = ttk.Label(self, text="", font=(FONT, 10))
        self.info.pack(fill="x", side="bottom")
        ttk.Label(self, text="Scroll = zoom · drag = move · double-click = reset zoom",
                  foreground="gray").pack(side="bottom", anchor="e")

    # ---------------------------------------------------------- loading
    def load(self, files, info=""):
        self.close()
        self.files = [Path(f) for f in files]
        self.photo_idx = 0
        self.reset_zoom(redraw=False)
        self.info.config(text=info)
        self.strip.pack_forget()
        self.vctl.pack_forget()
        if not self.files:
            self.message("")
            return
        if core.is_photo(self.files[0]):
            if len(self.files) > 1:
                self.strip.pack(fill="x", before=self.info, pady=(4, 0))
                self.build_strip()
            self.show_photo(0)
        else:
            self.vctl.pack(fill="x", before=self.info)
            self.open_video(self.files[0])

    def message(self, text):
        self.frame = None
        self.canvas.delete("all")
        w, h = max(self.canvas.winfo_width(), 400), max(self.canvas.winfo_height(), 300)
        self.canvas.create_text(w // 2, h // 2, text=text, fill="white", font=(FONT, 16), justify="center")

    def close(self):
        if self.after_id:
            self.after_cancel(self.after_id)
            self.after_id = None
        if self.cap is not None:
            self.cap.release()  # must release before the file can be renamed on Windows
            self.cap = None
        self.frame = None
        self.playing = False

    # ---------------------------------------------------------- photos
    def build_strip(self):
        for w in self.strip_inner.winfo_children():
            w.destroy()
        self.thumbs = []
        for i, f in enumerate(self.files):
            try:
                im = Image.open(f)
                im.thumbnail((110, 70))
                tkim = ImageTk.PhotoImage(im)
            except Exception:
                tkim = None
            self.thumbs.append(tkim)
            b = tk.Button(self.strip_inner, image=tkim, text=str(i + 1), compound="top", bd=3,
                          relief="flat", takefocus=0, command=lambda i=i: self.show_photo(i))
            b.pack(side="left", padx=2)

    def show_photo(self, i):
        if not self.files or not core.is_photo(self.files[0]):
            return
        self.photo_idx = max(0, min(i, len(self.files) - 1))
        img = read_image(self.files[self.photo_idx])
        if img is None:
            self.message("Could not open this photo.")
            return
        self.frame = img
        for j, b in enumerate(self.strip_inner.winfo_children()):
            b.config(relief="solid" if j == self.photo_idx else "flat", bg="#3584e4" if j == self.photo_idx else self.cget_bg())
        self.split_btn.config(state="normal" if self.photo_idx > 0 else "disabled")
        self.redraw()

    def cget_bg(self):
        return self.strip.winfo_toplevel().cget("bg")

    def next_photo(self, d):
        if len(self.files) > 1 and core.is_photo(self.files[0]):
            self.show_photo(self.photo_idx + d)

    # ----------------------------------------------------------- video
    def open_video(self, path):
        self.cap = cv2.VideoCapture(str(path))
        if not self.cap.isOpened():
            self.cap = None
            self.message("Could not play this video.\n(Try opening it in Windows Media Player.)")
            return
        fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.fps = fps if 1 <= fps <= 240 else 30.0
        n = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.scale.config(to=max(n - 1, 1))
        self.playing = True
        self.play_btn.config(text="Pause")
        self.read_frame()
        self.schedule()

    def schedule(self, elapsed_ms=0):
        speed = float(self.speed_var.get().rstrip("x"))
        self.after_id = self.after(max(1, int(1000 / (self.fps * speed) - elapsed_ms)), self.tick)

    def tick(self):
        self.after_id = None
        if self.cap is None or not self.playing:
            return
        t0 = time.perf_counter()
        self.read_frame()
        self.schedule((time.perf_counter() - t0) * 1000)

    def read_frame(self):
        ok, frame = self.cap.read()
        if not ok:  # loop
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self.cap.read()
            if not ok:
                return
        self.frame = frame
        self.redraw()
        self.updating_scale = True
        self.scale_var.set(self.cap.get(cv2.CAP_PROP_POS_FRAMES) - 1)
        self.updating_scale = False

    def toggle_play(self):
        if self.cap is None:
            return
        self.playing = not self.playing
        self.play_btn.config(text="Pause" if self.playing else "Play")
        if self.playing and not self.after_id:
            self.schedule()

    def step(self, d):
        if self.cap is None:
            return
        if self.playing:
            self.toggle_play()
        pos = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES)) - 1
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, pos + d))
        self.read_frame()

    def scrub(self, e):
        if self.cap is None:
            return "break"
        if self.playing:
            self.toggle_play()
        w = max(self.scale.winfo_width(), 1)
        frac = min(max((e.x - 6) / max(w - 12, 1), 0.0), 1.0)  # 6px slider margins
        target = int(round(frac * float(self.scale.cget("to"))))
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, target)
        self.read_frame()
        return "break"

    # ------------------------------------------------- drawing & zoom
    def redraw(self):
        if self.frame is None:
            return
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        if cw < 10 or ch < 10:
            return
        h, w = self.frame.shape[:2]
        sw, sh = w / self.zoom, h / self.zoom
        x0 = min(max(self.cx * w - sw / 2, 0), w - sw)
        y0 = min(max(self.cy * h - sh / 2, 0), h - sh)
        self.cx, self.cy = (x0 + sw / 2) / w, (y0 + sh / 2) / h
        crop = self.frame[int(y0):int(y0 + sh), int(x0):int(x0 + sw)]
        s = min(cw / crop.shape[1], ch / crop.shape[0])
        nw, nh = max(1, int(crop.shape[1] * s)), max(1, int(crop.shape[0] * s))
        img = cv2.resize(crop, (nw, nh), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)
        self.tkimg = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)))
        self.canvas.delete("all")
        self.canvas.create_image(cw // 2, ch // 2, image=self.tkimg)
        if self.zoom > 1:
            self.canvas.create_text(10, 10, anchor="nw", fill="yellow", text=f"{self.zoom:.1f}x", font=(FONT, 11, "bold"))
        self.geom = ((cw - nw) / 2, (ch - nh) / 2, s, x0, y0, w, h)

    def reset_zoom(self, redraw=True):
        self.zoom, self.cx, self.cy = 1.0, 0.5, 0.5
        if redraw:
            self.redraw()

    def on_wheel(self, e, direction):
        if self.frame is None or not self.geom:
            return
        ox, oy, s, x0, y0, w, h = self.geom
        ix, iy = x0 + (e.x - ox) / s, y0 + (e.y - oy) / s  # image point under cursor
        new = min(8.0, max(1.0, self.zoom * (1.25 if direction > 0 else 0.8)))
        f = self.zoom / new
        self.cx = (ix + (self.cx * w - ix) * f) / w
        self.cy = (iy + (self.cy * h - iy) * f) / h
        self.zoom = new
        self.redraw()

    def on_press(self, e):
        self.press = (e.x, e.y, self.cx, self.cy, False)

    def on_drag(self, e):
        if not self.press or not self.geom:
            return
        px, py, cx, cy, _ = self.press
        if abs(e.x - px) + abs(e.y - py) > 4:
            self.press = (px, py, cx, cy, True)
            _, _, s, _, _, w, h = self.geom
            self.cx = cx - (e.x - px) / s / w
            self.cy = cy - (e.y - py) / s / h
            self.redraw()

    def on_release(self, e):
        if self.press and not self.press[4] and self.cap is not None:
            self.toggle_play()  # plain click = pause / play
        self.press = None


# =========================================================================
#  One animal line in the "In this clip" list
# =========================================================================
class TagRow:
    def __init__(self, panel, parent, sp, data=None):
        data = data or {}
        self.panel, self.sp = panel, sp
        self.count = tk.StringVar(value=str(data.get("count") or 1))
        self.total = tk.StringVar(value=str(data.get("total") or ""))
        self.left = tk.StringVar(value="" if data.get("left") is None else str(data["left"]))
        self.right = tk.StringVar(value="" if data.get("right") is None else str(data["right"]))
        self.nontyp = tk.BooleanVar(value=bool(data.get("nontyp")))
        self.unk = tk.BooleanVar(value=bool(data.get("unk_pts")))
        self.button = tk.BooleanVar(value=bool(data.get("button")))
        self.pt_boxes = []
        self.nick = tk.StringVar(value=data.get("nick", ""))
        desc_names = list(dict.fromkeys(sp["desc"] + panel.app.settings["common_desc"]))
        for d in data.get("desc", []):
            if d not in desc_names:
                desc_names.append(d)
        self.desc = {d: tk.BooleanVar(value=d in data.get("desc", [])) for d in desc_names}

        f = self.frame = tk.Frame(parent, bd=1, relief="groove", padx=4, pady=3)
        f.pack(fill="x", pady=2, padx=(0, 4))
        top = tk.Frame(f)
        top.pack(fill="x")
        title = sp["label"] if not sp["group"] or sp["label"].startswith(sp["group"]) else f"{sp['group']} {sp['label']}"
        ttk.Label(top, text=title.replace(" ?", " (unsure)"), font=(FONT, 10, "bold")).pack(side="left")
        ttk.Button(top, text="✕", width=3, takefocus=False, command=lambda: panel.remove_row(self)).pack(side="right")
        mb = self.desc_btn = ttk.Menubutton(top, text="Details", takefocus=False)
        menu = tk.Menu(mb, tearoff=0)
        for i, (d, v) in enumerate(self.desc.items()):
            if i == len(sp["desc"]) and sp["desc"]:
                menu.add_separator()
            menu.add_checkbutton(label=d, variable=v, command=lambda d=d, v=v: self.desc_clicked(d, v))
        mb["menu"] = menu
        mb.pack(side="right", padx=4)
        ttk.Label(top, text="Count").pack(side="left", padx=(12, 2))
        ttk.Spinbox(top, from_=1, to=99, width=3, textvariable=self.count).pack(side="left")

        if sp["points"]:
            r2 = tk.Frame(f)
            r2.pack(fill="x", pady=(3, 0))
            ttk.Label(r2, text="Points").pack(side="left")
            for var, top, lbl in ((self.total, 40, "Left"), (self.left, 20, "x  Right"), (self.right, 20, None)):
                sb = ttk.Spinbox(r2, from_=0, to=top, width=3, textvariable=var)
                sb.pack(side="left", padx=(2, 4 if lbl == "x  Right" else 8))
                self.pt_boxes.append(sb)
                if lbl:
                    ttk.Label(r2, text=lbl).pack(side="left")
            r2b = tk.Frame(f)
            r2b.pack(fill="x", pady=(2, 0))
            ttk.Checkbutton(r2b, text="NonTyp", variable=self.nontyp, takefocus=False,
                            command=self.changed).pack(side="left", padx=(0, 14))
            ttk.Checkbutton(r2b, text="Unknown pts (can't count)", variable=self.unk, takefocus=False,
                            command=lambda: self.points_mode(self.unk)).pack(side="left", padx=(0, 14))
            ttk.Checkbutton(r2b, text="Button buck", variable=self.button, takefocus=False,
                            command=lambda: self.points_mode(self.button)).pack(side="left")
            if self.unk.get() or self.button.get():
                self.points_mode(self.button if self.button.get() else self.unk)
            self.left.trace_add("write", self.auto_total)
            self.right.trace_add("write", self.auto_total)

        r3 = tk.Frame(f)
        r3.pack(fill="x", pady=(3, 0))
        ttk.Label(r3, text="Nickname").pack(side="left")
        self.nick_box = ttk.Combobox(r3, textvariable=self.nick, width=22,
                                     values=panel.app.nick_choices(sp["token"]),
                                     postcommand=lambda: self.nick_box.config(values=panel.app.nick_choices(sp["token"])))
        self.nick_box.pack(side="left", padx=4, fill="x", expand=True)
        tut = getattr(panel.app, "tutorial", None)
        if tut:
            tut.register(self.nick_box, "Nickname", "Pick an animal you've named before, or type a new name. "
                         "Picking a known buck fills in his rack.")
            tut.register(self.desc_btn, "Details", "Tick details that describe this animal (drop tine, fighting…). "
                         "They go in the spreadsheet only.")
        if sp["points"]:  # picking a known deer fills in its rack
            self.nick_box.bind("<<ComboboxSelected>>", lambda e: self.fill_rack())
            self.nick_box.bind("<FocusOut>", lambda e: self.fill_rack())
        ttk.Label(r3, text="▼ pick or type", foreground="gray").pack(side="left")
        for v in (self.count, self.total, self.left, self.right, self.nick):
            v.trace_add("write", lambda *a: self.changed())
        self.changed()

    @staticmethod
    def num(var):
        v = var.get().strip()
        return int(v) if v.isdigit() else None

    def auto_total(self, *a):
        left, right = self.num(self.left), self.num(self.right)
        if left is not None and right is not None:
            self.total.set(str(left + right))

    def desc_clicked(self, name, var):
        tut = self.panel.app.tutorial
        if tut.mode == "whats":
            var.set(not var.get())  # don't actually change anything
            tut.explain(self.desc_btn, f"Details: {name}", "Tick details that describe this animal. "
                        "They go in the spreadsheet only, not the file name.")
            return
        self.changed()

    def changed(self):
        n = sum(v.get() for v in self.desc.values())
        self.desc_btn.config(text=f"Details ({n})" if n else "Details")
        self.panel.update_preview()

    def fill_rack(self):
        """Copy the rack from this deer's other clip closest in date, if the point boxes are still empty."""
        if self.unk.get() or self.button.get() or any(v.get().strip() for v in (self.total, self.left, self.right)):
            return
        app = self.panel.app
        taken, exclude = app.current_taken()
        if not taken:
            return
        found = core.known_rack(app.store, self.sp["token"], self.nick.get(), taken, exclude)
        if not found:
            return
        f, date = found
        if f.get("button"):
            self.button.set(True)
            self.points_mode(self.button)
        else:
            if f.get("left") is not None and f.get("right") is not None:
                self.left.set(str(f["left"]))
                self.right.set(str(f["right"]))
            self.total.set(str(f["total"]))
            self.nontyp.set(bool(f.get("nontyp")))
        app.status(f"Filled {core.rack_text(f)} from {core.clean(self.nick.get())}'s clip on {date} — change it if needed.")
        self.changed()

    def points_mode(self, clicked):
        """Unknown (can't count) or Button buck: clear and lock the point boxes. Only one at a time."""
        other = self.button if clicked is self.unk else self.unk
        if clicked.get():
            other.set(False)
            for v in (self.total, self.left, self.right):
                v.set("")
            self.nontyp.set(False)
        locked = self.unk.get() or self.button.get()
        for sb in self.pt_boxes:
            sb.config(state="disabled" if locked else "normal")
        self.changed()

    def data(self):
        d = {"token": self.sp["token"], "label": self.sp["label"], "points": self.sp["points"],
             "count": max(1, self.num(self.count) or 1), "nick": core.clean(self.nick.get()),
             "desc": [k for k, v in self.desc.items() if v.get()]}
        if self.sp["points"]:
            d["total"] = self.num(self.total) or None
            left, right = self.num(self.left), self.num(self.right)
            d["left"], d["right"] = (left, right) if left is not None and right is not None else (None, None)
            d["nontyp"] = self.nontyp.get()
            d["unk_pts"] = self.unk.get()
            d["button"] = self.button.get()
            if d["unk_pts"] or d["button"]:
                d["total"], d["left"], d["right"], d["nontyp"] = None, None, None, False
        return d


# =========================================================================
#  Right-hand tagging panel
# =========================================================================
class TagPanel(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=(6, 0, 8, 6), width=500)
        self.pack_propagate(False)
        self.app = app
        self.rows = []
        self.hilite = tk.BooleanVar()
        self.notes = tk.StringVar()

        self.title = ttk.Label(self, text="What's in it?  (click each animal)", font=(FONT, 11, "bold"))
        self.title.pack(anchor="w")
        self.btns = ttk.Frame(self)
        self.btns.pack(fill="x", pady=4)
        self.build_buttons()

        ttk.Separator(self).pack(fill="x", pady=4)
        ttk.Label(self, text="In this clip:", font=(FONT, 11, "bold")).pack(anchor="w")
        holder = ttk.Frame(self)
        holder.pack(fill="both", expand=True)
        self.rows_canvas = tk.Canvas(holder, highlightthickness=0)
        sb = ttk.Scrollbar(holder, orient="vertical", command=self.rows_canvas.yview)
        self.rows_frame = tk.Frame(self.rows_canvas)
        self.rows_frame.bind("<Configure>", lambda e: self.rows_canvas.configure(scrollregion=self.rows_canvas.bbox("all")))
        self.rows_win = self.rows_canvas.create_window(0, 0, window=self.rows_frame, anchor="nw")
        self.rows_canvas.bind("<Configure>", lambda e: self.rows_canvas.itemconfigure(self.rows_win, width=e.width))
        self.rows_canvas.configure(yscrollcommand=sb.set)
        self.rows_canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.hint = ttk.Label(self.rows_frame, text="(nothing yet)", foreground="gray")
        self.hint.pack(anchor="w")

        clip = ttk.Frame(self)
        clip.pack(fill="x", pady=(4, 0))
        self.hl_check = tk.Checkbutton(clip, text="★ Hilite  (H)", variable=self.hilite, takefocus=0,
                                       font=(FONT, 10, "bold"), command=self.update_preview, indicatoron=False,
                                       padx=8, pady=2, selectcolor=HILITE_BG)
        self.hl_check.pack(side="left")
        ttk.Label(clip, text="Notes").pack(side="left", padx=(12, 2))
        self.notes_entry = ttk.Entry(clip, textvariable=self.notes)
        self.notes_entry.pack(side="left", fill="x", expand=True)

        ttk.Label(self, text="New file name:").pack(anchor="w", pady=(6, 0))
        self.preview = ttk.Label(self, text="", foreground="#1a5fb4", wraplength=480, font=("Consolas", 10))
        self.preview.pack(anchor="w", fill="x")
        self.baseline = None  # tags as loaded in Review, to spot unsaved edits
        self.unsaved = tk.Label(self, text="● Unsaved changes — press Enter or Save changes",
                                fg="#c64600", font=(FONT, 10, "bold"))

        self.actions = ttk.Frame(self)
        self.actions.pack(fill="x", pady=(6, 0))

    def build_buttons(self):
        for w in self.btns.winfo_children():
            w.destroy()
        species = self.app.settings["species"]
        r = 0
        for g in core.group_order(self.app.settings):
            members = [s for s in species if s["group"] == g]
            if not members:
                continue
            ttk.Label(self.btns, text=g, font=(FONT, 9, "bold"), width=9).grid(row=r, column=0, sticky="nw")
            for i, sp in enumerate(members):
                ttk.Button(self.btns, text=sp["label"], takefocus=False, command=lambda sp=sp: self.add_row(sp)
                           ).grid(row=r + i // 4, column=1 + i % 4, sticky="we", padx=1, pady=1)
            r += (len(members) + 3) // 4
        others = [s for s in species if not s["group"]] + [None]
        ttk.Label(self.btns, text="Other", font=(FONT, 9, "bold"), width=9).grid(row=r, column=0, sticky="nw")
        for i, sp in enumerate(others):
            if sp is None:
                b = ttk.Button(self.btns, text="+ Add…", takefocus=False, command=self.add_other)
            else:
                b = ttk.Button(self.btns, text=sp["label"], takefocus=False, command=lambda sp=sp: self.add_row(sp))
            b.grid(row=r + i // 4, column=1 + i % 4, sticky="we", padx=1, pady=1)
        for c in range(1, 5):
            self.btns.columnconfigure(c, weight=1)

    def set_actions(self, buttons):
        for w in self.actions.winfo_children():
            w.destroy()
        for i, (text, cmd, big) in enumerate(buttons):
            b = ttk.Button(self.actions, text=text, command=cmd, takefocus=False, style="Big.TButton" if big else "TButton")
            self.app.help_action(b, text)
            if big:
                b.grid(row=i, column=0, columnspan=2, sticky="we", pady=2)
            else:
                b.grid(row=i, column=0, columnspan=2, sticky="we", pady=1)
        self.actions.columnconfigure(0, weight=1)

    def add_row(self, sp, data=None):
        if not self.app.has_item():
            return
        self.hint.pack_forget()
        self.rows.append(TagRow(self, self.rows_frame, sp, data))
        self.update_preview()
        self.after_idle(lambda: self.rows_canvas.yview_moveto(1.0))

    def add_other(self):
        name = simpledialog.askstring("Add an animal button", "Animal name (e.g. Mink, Badger, Owl):", parent=self)
        token = core.clean((name or "").strip().title().replace(" ", ""))
        if not token:
            return
        species = self.app.settings["species"]
        sp = next((s for s in species if s["token"].lower() == token.lower()), None)
        if sp is None:
            sp = core._sp("", name.strip().title(), token)
            species.append(sp)
            self.app.save_settings()
            self.build_buttons()
        self.add_row(sp)

    def remove_row(self, row):
        row.frame.destroy()
        self.rows.remove(row)
        if not self.rows:
            self.hint.pack(anchor="w")
        self.update_preview()

    def clear(self):
        self.baseline = None
        for r in self.rows:
            r.frame.destroy()
        self.rows = []
        self.hint.pack(anchor="w")
        self.hilite.set(False)
        self.notes.set("")
        self.update_preview()

    def load(self, tags):
        self.clear()
        by_token = {s["token"]: s for s in self.app.settings["species"]}
        for a in tags.get("animals", []):
            sp = by_token.get(a["token"]) or core._sp("", a.get("label", a["token"]), a["token"], a.get("points", False))
            self.add_row(sp, a)
        self.hilite.set(bool(tags.get("hilite")))
        self.notes.set(tags.get("notes", ""))
        self.update_preview()

    def tags(self, empty=False):
        return {"animals": [] if empty else [r.data() for r in self.rows], "empty": empty,
                "hilite": self.hilite.get(), "notes": self.notes.get().strip()}

    def update_preview(self):
        self.hl_check.config(bg=HILITE_BG if self.hilite.get() else self.cget_bg())
        text = self.app.preview_name(self.tags()) if self.rows else "(click the animals, or press Empty)"
        self.preview.config(text=text or "")
        if self.app.review_dirty():
            if not self.unsaved.winfo_manager():
                self.unsaved.pack(anchor="w", after=self.preview, pady=(2, 0))
        else:
            self.unsaved.pack_forget()

    def cget_bg(self):
        return self.winfo_toplevel().cget("bg")


# =========================================================================
#  Animal button editor (Settings tab)
# =========================================================================
OTHER = ""  # the "Other" group


class AnimalDialog(tk.Toplevel):
    """Add or edit one animal button."""

    def __init__(self, parent, groups, sp=None, group=OTHER, taken_tokens=()):
        super().__init__(parent)
        self.title("Edit animal button" if sp else "Add animal button")
        self.transient(parent)
        self.resizable(False, False)
        self.result = None
        self.taken = {t.lower() for t in taken_tokens}
        sp = sp or {"label": "", "token": "", "points": False, "desc": []}
        self.label = tk.StringVar(value=sp["label"])
        self.token = tk.StringVar(value=sp["token"])
        self.points = tk.BooleanVar(value=sp["points"])
        self.desc = tk.StringVar(value=", ".join(sp["desc"]))
        self.group_names = ["(Other)"] + groups
        self.group = tk.StringVar(value=group or "(Other)")
        self.auto_token = not sp["token"]
        f = ttk.Frame(self, padding=14)
        f.pack(fill="both", expand=True)
        rows = [("Button text", ttk.Entry(f, textvariable=self.label, width=30)),
                ("Word in file names", ttk.Entry(f, textvariable=self.token, width=30)),
                ("Group", ttk.Combobox(f, textvariable=self.group, values=self.group_names, state="readonly", width=28)),
                ("Details (comma separated)", ttk.Entry(f, textvariable=self.desc, width=50))]
        for i, (text, w) in enumerate(rows):
            ttk.Label(f, text=text).grid(row=i, column=0, sticky="w", pady=4)
            w.grid(row=i, column=1, sticky="we", padx=6)
        ttk.Checkbutton(f, text="Has antlers (show Points / Left x Right / NonTyp / Unknown / Button)",
                        variable=self.points).grid(row=len(rows), column=1, sticky="w", pady=4)
        ttk.Label(f, text="The file-name word may contain letters, numbers and dashes (e.g. Turkey-Tom).",
                  foreground="gray").grid(row=len(rows) + 1, column=0, columnspan=2, sticky="w")
        b = ttk.Frame(f)
        b.grid(row=len(rows) + 2, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(b, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(b, text="OK", command=self.ok).pack(side="right", padx=6)
        self.label.trace_add("write", self.label_changed)
        self.token.trace_add("write", lambda *a: setattr(self, "auto_token", False) if self.focus_get() else None)
        self.bind("<Return>", lambda e: self.ok())
        self.bind("<Escape>", lambda e: self.destroy())
        rows[0][1].focus_set()
        self.grab_set()
        self.wait_window()

    def label_changed(self, *a):
        if self.auto_token:  # new button: suggest the file word from the button text
            self.token.set(core.clean(self.label.get().title(), "-"))
            self.auto_token = True

    def ok(self):
        label = self.label.get().strip()
        token = core.clean(self.token.get().strip() or label.title(), "-").strip("-")
        if not label or not token:
            messagebox.showerror("Missing", "Please fill in the button text.", parent=self)
            return
        if token.lower() in self.taken:
            messagebox.showerror("Already used", f"Another button already uses '{token}' in file names.", parent=self)
            return
        g = self.group.get()
        self.result = ({"group": OTHER if g == "(Other)" else g, "label": label, "token": token,
                        "points": self.points.get(),
                        "desc": [d.strip() for d in self.desc.get().split(",") if d.strip()]})
        self.destroy()


class AnimalEditor(ttk.Frame):
    """Tree of groups and animal buttons: drag, move up/down, add, edit, delete, new group."""

    def __init__(self, master, settings):
        super().__init__(master)
        self.load(settings["species"], core.group_order(settings))
        self.token_renames = {}  # old file word -> new file word

        left = ttk.Frame(self)
        left.pack(side="left", fill="both", expand=True)
        self.tv = ttk.Treeview(left, columns=("word", "pts", "desc"), selectmode="browse")
        self.tv.heading("#0", text="Group / button")
        self.tv.heading("word", text="Word in file names")
        self.tv.heading("pts", text="Antlers")
        self.tv.heading("desc", text="Details")
        self.tv.column("#0", width=170)
        self.tv.column("word", width=140)
        self.tv.column("pts", width=60, anchor="center")
        self.tv.column("desc", width=260)
        self.tv.tag_configure("group", font=(FONT, 10, "bold"), background="#e8eef6")
        sb = ttk.Scrollbar(left, orient="vertical", command=self.tv.yview)
        self.tv.configure(yscrollcommand=sb.set)
        self.tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tv.bind("<ButtonPress-1>", self.drag_start)
        self.tv.bind("<B1-Motion>", self.drag_motion)
        self.tv.bind("<ButtonRelease-1>", self.drag_end)
        self.tv.bind("<Double-1>", lambda e: self.edit())
        self.drag = None

        right = ttk.Frame(self, padding=(8, 0, 0, 0))
        right.pack(side="right", fill="y")
        for text, cmd in (("▲ Move up", lambda: self.move(-1)), ("▼ Move down", lambda: self.move(1)),
                          (None, None), ("Add animal…", self.add), ("Edit…", self.edit),
                          ("Delete", self.delete), (None, None), ("New group…", self.new_group),
                          ("Rename group…", self.rename_group)):
            if text is None:
                ttk.Separator(right).pack(fill="x", pady=6)
            else:
                ttk.Button(right, text=text, command=cmd, width=16).pack(fill="x", pady=1)
        ttk.Separator(right).pack(fill="x", pady=6)
        ttk.Label(right, text="Move to group:").pack(anchor="w")
        self.target = tk.StringVar()
        self.target_box = ttk.Combobox(right, textvariable=self.target, state="readonly", width=16)
        self.target_box.pack(fill="x")
        self.target_box.bind("<<ComboboxSelected>>", lambda e: self.move_to(self.target.get()))
        ttk.Label(right, text="Tip: drag buttons and\ngroups to rearrange.\nDouble-click to edit.",
                  foreground="gray").pack(anchor="w", pady=(10, 0))
        self.refresh()

    # ---------------------------------------------------------- data
    def load(self, species, groups):
        self.groups = list(groups)
        self.items = {g: [] for g in self.groups + [OTHER]}
        for sp in species:
            g = sp["group"] if sp["group"] in self.items else OTHER
            self.items[g].append(dict(sp, desc=list(sp["desc"])))

    def get(self):
        species = []
        for g in self.groups + [OTHER]:
            for sp in self.items[g]:
                species.append(dict(sp, group=g))
        return species, list(self.groups)

    def all_groups(self):
        return self.groups + [OTHER]

    @staticmethod
    def giid(g):
        return "g|" + g

    def refresh(self, select=None):
        self.tv.delete(*self.tv.get_children())
        self.sp_of = {}
        for g in self.all_groups():
            gi = self.giid(g)
            n = len(self.items[g])
            self.tv.insert("", "end", iid=gi, text=(g or "Other") + f"   ({n})", open=True, tags=("group",))
            for sp in self.items[g]:
                iid = f"s|{id(sp)}"
                self.sp_of[iid] = (sp, g)
                self.tv.insert(gi, "end", iid=iid, text=sp["label"],
                               values=(sp["token"], "yes" if sp["points"] else "", ", ".join(sp["desc"])))
        self.target_box.config(values=["(Other)"] + self.groups)
        if select is not None:
            iid = select if isinstance(select, str) else f"s|{id(select)}"
            if self.tv.exists(iid):
                self.tv.selection_set(iid)
                self.tv.see(iid)

    def selected(self):
        sel = self.tv.selection()
        if not sel:
            return None
        if sel[0].startswith("g|"):
            return ("group", sel[0][2:])
        sp, g = self.sp_of[sel[0]]
        return ("animal", sp, g)

    # ------------------------------------------------------ actions
    def move(self, d):
        s = self.selected()
        if not s:
            return
        if s[0] == "group":
            g = s[1]
            if g == OTHER:
                return  # Other always stays last
            i = self.groups.index(g)
            j = i + d
            if 0 <= j < len(self.groups):
                self.groups[i], self.groups[j] = self.groups[j], self.groups[i]
            self.refresh(self.giid(g))
            return
        _, sp, g = s
        lst = self.items[g]
        i = lst.index(sp)
        j = i + d
        if 0 <= j < len(lst):
            lst[i], lst[j] = lst[j], lst[i]
        else:  # past the end of its group: hop into the neighbouring group
            gs = self.all_groups()
            k = gs.index(g) + d
            if 0 <= k < len(gs):
                lst.remove(sp)
                if d < 0:
                    self.items[gs[k]].append(sp)
                else:
                    self.items[gs[k]].insert(0, sp)
        self.refresh(sp)

    def move_to(self, name):
        s = self.selected()
        g = OTHER if name == "(Other)" else name
        if s and s[0] == "animal" and g in self.items:
            self.items[s[2]].remove(s[1])
            self.items[g].append(s[1])
            self.refresh(s[1])
        self.target.set("")

    def tokens(self, exclude=None):
        return [sp["token"] for g in self.all_groups() for sp in self.items[g] if sp is not exclude]

    def add(self):
        s = self.selected()
        group = s[1] if s and s[0] == "group" else (s[2] if s else OTHER)
        d = AnimalDialog(self, self.groups, group=group, taken_tokens=self.tokens())
        if d.result:
            sp = d.result
            g = sp.pop("group")
            self.items[g].append(sp)
            self.refresh(sp)

    def edit(self):
        s = self.selected()
        if not s:
            return
        if s[0] == "group":
            self.rename_group()
            return
        _, sp, g = s
        d = AnimalDialog(self, self.groups, sp=sp, group=g, taken_tokens=self.tokens(exclude=sp))
        if not d.result:
            return
        new = d.result
        new_g = new.pop("group")
        if new["token"] != sp["token"]:
            old = sp["token"]
            first = next((k for k, v in self.token_renames.items() if v == old), old)
            self.token_renames[first] = new["token"]
        sp.update(new)
        if new_g != g:
            self.items[g].remove(sp)
            self.items[new_g].append(sp)
        self.refresh(sp)

    def delete(self):
        s = self.selected()
        if not s:
            return
        if s[0] == "group":
            g = s[1]
            if g == OTHER:
                messagebox.showinfo("Other", "The Other group can't be deleted.", parent=self)
                return
            n = len(self.items[g])
            if not messagebox.askyesno("Delete group", f"Delete the group '{g}'?" +
                                       (f"\n\nIts {n} buttons will move to Other." if n else ""), parent=self):
                return
            self.items[OTHER] += self.items.pop(g)
            self.groups.remove(g)
            self.refresh()
            return
        _, sp, g = s
        if messagebox.askyesno("Delete button", f"Remove the '{sp['label']}' button?\n\n"
                               "Clips already tagged with it keep their tags.", parent=self):
            self.items[g].remove(sp)
            self.refresh(self.giid(g))

    def ask_group_name(self, title, initial=""):
        name = simpledialog.askstring(title, "Group name:", initialvalue=initial, parent=self)
        name = (name or "").strip()
        if not name:
            return None
        if name.lower() == "other" or any(name.lower() == g.lower() for g in self.groups if g != initial):
            messagebox.showerror("Group", f"There's already a group called '{name}'.", parent=self)
            return None
        return name

    def new_group(self):
        name = self.ask_group_name("New group")
        if name:
            s = self.selected()
            at = len(self.groups)
            if s:
                g = s[1] if s[0] == "group" else s[2]
                if g in self.groups:
                    at = self.groups.index(g) + 1
            self.groups.insert(at, name)
            self.items[name] = []
            self.refresh(self.giid(name))

    def rename_group(self):
        s = self.selected()
        if not s:
            return
        g = s[1] if s[0] == "group" else s[2]
        if g == OTHER:
            messagebox.showinfo("Other", "The Other group can't be renamed.", parent=self)
            return
        name = self.ask_group_name("Rename group", g)
        if name and name != g:
            self.groups[self.groups.index(g)] = name
            self.items[name] = self.items.pop(g)
            self.refresh(self.giid(name))

    # ----------------------------------------------------- dragging
    def drag_start(self, e):
        iid = self.tv.identify_row(e.y)
        self.drag = iid or None
        self.drag_moved = False

    def drag_motion(self, e):
        if self.drag:
            self.drag_moved = True
            self.tv.configure(cursor="hand2")
            target = self.tv.identify_row(e.y)
            if target:
                self.tv.selection_set(target)

    def drag_end(self, e):
        self.tv.configure(cursor="")
        src, self.drag = self.drag, None
        target = self.tv.identify_row(e.y)
        if not src or not self.drag_moved or not target or target == src:
            if src:
                self.tv.selection_set(src)
            return
        t_group = target[2:] if target.startswith("g|") else self.sp_of[target][1]
        if src.startswith("g|"):  # reorder groups
            g = src[2:]
            if g == OTHER:
                self.refresh(src)
                return
            self.groups.remove(g)
            at = self.groups.index(t_group) if t_group in self.groups else len(self.groups)
            self.groups.insert(at, g)
            self.refresh(src)
            return
        sp, g = self.sp_of[src]
        self.items[g].remove(sp)
        if target.startswith("g|"):
            self.items[t_group].append(sp)  # dropped on a group: goes to the end of it
        else:
            dest = self.items[t_group]
            dest.insert(dest.index(self.sp_of[target][0]), sp)  # dropped on a button: goes before it
        self.refresh(sp)

# =========================================================================
#  Settings window
# =========================================================================
class SettingsDialog(tk.Toplevel):
    SAMPLE = {"taken": "2026-11-20T06:14:22", "camera": "CAM2", "original": "IMAG0042.AVI", "hilite": True,
              "empty": False, "animals": [
                  {"token": "Buck", "points": True, "count": 1, "total": 10, "left": 5, "right": 5,
                   "nontyp": True, "nick": "Droptine"},
                  {"token": "Doe", "count": 3}]}

    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.s = dict(app.settings)
        self.title("Settings")
        self.geometry("940x640")
        self.transient(app.root)
        self.grab_set()
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        # ---- file name tab
        t1 = ttk.Frame(nb, padding=10)
        nb.add(t1, text="File name")
        ttk.Label(t1, text="Drag the blocks to arrange your file name. Drag a block down to "
                           "'Not used' to leave it out.", wraplength=760).pack(anchor="w")
        self.blocks_cv = tk.Canvas(t1, height=160, bg="#f4f4f4", highlightthickness=1, highlightbackground="#bbb")
        self.blocks_cv.pack(fill="x", pady=6)
        self.used = list(self.s["name_blocks"])
        self.unused = [b for b in core.BLOCKS if b not in self.used]
        self.drag = None
        self.blocks_cv.bind("<ButtonPress-1>", self.drag_start)
        self.blocks_cv.bind("<B1-Motion>", self.drag_move)
        self.blocks_cv.bind("<ButtonRelease-1>", self.drag_end)
        self.blocks_cv.bind("<Configure>", lambda e: self.draw_blocks())

        g = ttk.Frame(t1)
        g.pack(fill="x", pady=6)
        self.sep = self.combo(g, 0, "Separator", core.SEPARATORS, self.s["separator"])
        self.datef = self.combo(g, 1, "Date format", [(lbl, f) for lbl, f, _ in core.DATE_FORMATS], self.s["date_format"])
        self.timef = self.combo(g, 2, "Time format", [(lbl, f) for lbl, f, _ in core.TIME_FORMATS], self.s["time_format"])
        ttk.Label(g, text="Hilite word").grid(row=3, column=0, sticky="w", pady=3)
        self.hlword = tk.StringVar(value=self.s["hilite_word"])
        ttk.Entry(g, textvariable=self.hlword, width=15).grid(row=3, column=1, sticky="w")
        self.hlword.trace_add("write", lambda *a: self.update_preview())

        ttk.Label(t1, text="Example:", font=(FONT, 10, "bold")).pack(anchor="w", pady=(10, 0))
        self.ex = ttk.Label(t1, text="", font=("Consolas", 10), foreground="#1a5fb4", wraplength=760)
        self.ex.pack(anchor="w")
        self.warn = ttk.Label(t1, text="", foreground="#c01c28", wraplength=760)
        self.warn.pack(anchor="w", pady=4)

        # ---- folders tab
        t2 = ttk.Frame(nb, padding=10)
        nb.add(t2, text="Folders & photos")
        ttk.Label(t2, text=f"Main trail cam folder:  {ROOT}", font=(FONT, 10, "bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        self.raw = tk.StringVar(value=self.s["raw_folder"])
        self.out = tk.StringVar(value=self.s["output_folder"])
        for r, (lbl, var) in enumerate([("Raw (dump) folder", self.raw), ("Output folder", self.out)], 1):
            ttk.Label(t2, text=lbl).grid(row=r, column=0, sticky="w", pady=4)
            ttk.Entry(t2, textvariable=var, width=60).grid(row=r, column=1, padx=6)
            ttk.Button(t2, text="Browse…", command=lambda v=var: self.browse(v)).grid(row=r, column=2)
        ttk.Label(t2, text="Folders inside the main folder are saved as relative paths, so the whole main "
                           "folder can be moved or copied and keep working.", foreground="gray",
                  wraplength=700).grid(row=3, column=0, columnspan=3, sticky="w", pady=(0, 14))
        ttk.Label(t2, text="Photos taken this many seconds apart or less count as one burst").grid(row=4, column=0, columnspan=2, sticky="w")
        self.burst = tk.StringVar(value=str(self.s["burst_seconds"]))
        ttk.Spinbox(t2, from_=0, to=120, width=5, textvariable=self.burst).grid(row=4, column=2, sticky="w")
        ttk.Label(t2, text="(0 = never group photos)", foreground="gray").grid(row=5, column=0, sticky="w")

        # ---- animals tab
        t3 = ttk.Frame(nb, padding=10)
        nb.add(t3, text="Animal buttons")
        ttk.Label(t3, text="Groups and buttons, in the order they appear on the tagging screen. "
                           "'Details' are the checkboxes that go in the spreadsheet only.", wraplength=880).pack(anchor="w")
        self.editor = AnimalEditor(t3, self.s)
        self.editor.pack(fill="both", expand=True, pady=6)
        o = ttk.Frame(t3)
        o.pack(fill="x", pady=(0, 4))
        ttk.Label(o, text="When a clip has several animals, list them in the file name:").pack(side="left")
        self.order = tk.StringVar(value=self.s.get("animal_order", "bucks_first"))
        ttk.Radiobutton(o, text="bucks first, then in the order clicked", value="bucks_first",
                        variable=self.order).pack(side="left", padx=8)
        ttk.Radiobutton(o, text="in the button order above", value="buttons",
                        variable=self.order).pack(side="left")
        f = ttk.Frame(t3)
        f.pack(fill="x")
        ttk.Label(f, text="Details for every animal:").pack(side="left")
        self.common = tk.StringVar(value=", ".join(self.s["common_desc"]))
        ttk.Entry(f, textvariable=self.common).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(t3, text="Reset animal list to defaults", command=self.reset_species).pack(anchor="w", pady=4)

        bar = ttk.Frame(self, padding=8)
        bar.pack(fill="x")
        ttk.Button(bar, text="Save", style="Big.TButton", command=self.save).pack(side="right")
        ttk.Button(bar, text="Cancel", command=self.destroy).pack(side="right", padx=6)
        self.update_preview()

    def combo(self, parent, row, label, options, current):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
        labels = [lbl for lbl, _ in options]
        var = tk.StringVar(value=next((lbl for lbl, v in options if v == current), labels[0]))
        cb = ttk.Combobox(parent, values=labels, textvariable=var, state="readonly", width=48)
        cb.grid(row=row, column=1, sticky="w", padx=6)
        cb.bind("<<ComboboxSelected>>", lambda e: self.update_preview())
        var.options = dict(options)
        return var

    def browse(self, var):
        d = filedialog.askdirectory(parent=self, initialdir=str(resolve(var.get())))
        if d:
            var.set(rel_to_root(d))

    def reset_species(self):
        if messagebox.askyesno("Reset", "Put the animal buttons and groups back to the original list?", parent=self):
            self.editor.load(core.DEFAULT_SPECIES, core.DEFAULT_SETTINGS["groups"])
            self.editor.refresh()
            self.common.set(", ".join(core.COMMON_DESC))

    # ------- drag & drop blocks
    def chip_layout(self):
        """Return list of (block, row, x0, y0, x1, y1)."""
        out = []
        for row, blocks, y in ((0, self.used, 42), (1, self.unused, 120)):
            x = 14
            for b in blocks:
                w = 18 + 9 * len(core.BLOCKS[b])
                out.append((b, row, x, y - 16, x + w, y + 16))
                x += w + 10
        return out

    def draw_blocks(self, dragging=None, pos=None):
        c = self.blocks_cv
        c.delete("all")
        c.create_text(8, 4, anchor="nw", text="File name  (left → right)", fill="#555", font=(FONT, 8))
        c.create_line(0, 75, 2000, 75, fill="#bbb", dash=(3, 3))
        c.create_text(8, 80, anchor="nw", text="Not used", fill="#555", font=(FONT, 8))
        for b, row, x0, y0, x1, y1 in self.chip_layout():
            if b == dragging:
                continue
            self.chip(b, x0, y0, x1, y1, row == 0)
        if dragging and pos:
            w = 18 + 9 * len(core.BLOCKS[dragging])
            self.chip(dragging, pos[0] - w / 2, pos[1] - 16, pos[0] + w / 2, pos[1] + 16, True, True)

    def chip(self, b, x0, y0, x1, y1, used, floating=False):
        fill = "#3584e4" if used else "#c0bfbc"
        if floating:
            fill = "#1a5fb4"
        self.blocks_cv.create_rectangle(x0, y0, x1, y1, fill=fill, outline="", width=0)
        self.blocks_cv.create_text((x0 + x1) / 2, (y0 + y1) / 2, text=core.BLOCKS[b], fill="white", font=(FONT, 10, "bold"))

    def drag_start(self, e):
        for b, _row, x0, y0, x1, y1 in self.chip_layout():
            if x0 <= e.x <= x1 and y0 <= e.y <= y1:
                self.drag = b
                self.draw_blocks(b, (e.x, e.y))
                return

    def drag_move(self, e):
        if self.drag:
            self.draw_blocks(self.drag, (e.x, e.y))

    def drag_end(self, e):
        b = self.drag
        self.drag = None
        if not b:
            return
        for lst in (self.used, self.unused):
            if b in lst:
                lst.remove(b)
        target = self.used if e.y < 75 else self.unused
        idx = len(target)
        for i, (_b, _row, x0, _y0, x1, _y1) in enumerate([c for c in self.chip_layout() if (c[1] == 0) == (target is self.used)]):
            if e.x < (x0 + x1) / 2:
                idx = i
                break
        target.insert(idx, b)
        if "animals" not in self.used:  # animals must always be in the name
            self.unused.remove("animals")
            self.used.append("animals")
        self.draw_blocks()
        self.update_preview()

    def current(self):
        s = dict(self.s)
        s["name_blocks"] = list(self.used)
        s["separator"] = self.sep.options[self.sep.get()]
        s["date_format"] = self.datef.options[self.datef.get()]
        s["time_format"] = self.timef.options[self.timef.get()]
        s["hilite_word"] = core.clean(self.hlword.get()) or "Hilite"
        return s

    def update_preview(self):
        s = self.current()
        a = core.build_name(self.SAMPLE, s)
        b = core.build_name(dict(self.SAMPLE, hilite=False, animals=[{"token": "Turkey-Tom", "count": 4}]), s, seq=2)
        self.ex.config(text=a + "\n" + b + "   (2nd clip in the same minute)")
        w = core.format_ok(s)
        self.warn.config(text="⚠ " + "\n⚠ ".join(w) if w else "")

    def save(self):
        species, groups = self.editor.get()
        if not species:
            messagebox.showerror("Animal buttons", "Keep at least one animal button.", parent=self)
            return
        s = self.current()
        s["species"] = species
        s["groups"] = groups
        s["animal_order"] = self.order.get()
        s["common_desc"] = [d.strip() for d in self.common.get().split(",") if d.strip()]
        try:
            s["burst_seconds"] = max(0, int(self.burst.get()))
        except ValueError:
            s["burst_seconds"] = 10
        s["raw_folder"] = self.raw.get().strip() or "Raw"
        s["output_folder"] = self.out.get().strip() or "Output"
        name_keys = ("name_blocks", "separator", "date_format", "time_format", "hilite_word", "animal_order")
        name_changed = any(s.get(k) != self.app.settings.get(k) for k in name_keys)
        renames = {o: n for o, n in self.editor.token_renames.items() if o != n}
        self.destroy()
        self.app.apply_settings(s, name_changed, renames)


# =========================================================================
#  Main application
# =========================================================================
class App:
    def __init__(self, root):
        self.root = root
        self.settings = core.load_settings(SETTINGS_PATH)
        self.mode = tk.StringVar(value="tag")
        self.cur_mode = "tag"
        self.queue = []
        self.qi = 0
        self.camera = None
        self.store = None
        self.undo_stack = []
        self.review_items = []
        self.review_sel = None
        self.xlsx_job = None
        self.xlsx_pending = False

        root.title("Trail Cam Tagger")
        root.geometry("1500x900")
        root.minsize(1100, 700)
        style = ttk.Style()
        style.configure("Big.TButton", font=(FONT, 12, "bold"), padding=7)
        self.build_menu()
        self.build_ui()
        self.tutorial = tutorial.Tutorial(self)
        self.register_help()
        self.bind_keys()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        if MAC:
            root.createcommand("::tk::mac::Quit", self.on_close)  # Cmd+Q closes safely
        root.report_callback_exception = self.on_error
        self.open_store()
        self.last_reconcile = time.time()
        root.after(100, self.start)
        root.after(700, self.reconcile)

    # ----------------------------------------------------------- paths
    @property
    def raw_dir(self):
        return resolve(self.settings["raw_folder"])

    @property
    def out_dir(self):
        return resolve(self.settings["output_folder"])

    def open_store(self):
        try:
            self.store = core.Store(self.out_dir, DATA_PATH)
        except Exception as e:
            messagebox.showerror("Could not read tag data", f"{DATA_PATH}\n\n{e}\n\n"
                                 "A backup copy (.bak) is in the same folder.")
            raise SystemExit(1) from None

    def save_settings(self):
        try:
            core.save_settings(SETTINGS_PATH, self.settings)
        except OSError as e:
            self.status(f"Could not save settings: {e}")

    # -------------------------------------------------------------- UI
    def build_menu(self):
        """File / Tools / Help as real buttons (not a native menu bar) so the tutorial can point at them."""
        bar = self.menubar = tk.Frame(self.root, bd=0)
        bar.pack(fill="x", side="top")
        ttk.Separator(self.root).pack(fill="x", side="top")
        spec = {
            "File": [
                ("Open main trail cam folder", lambda: self.open_path(ROOT),
                 "Opens your Trail Cams folder in File Explorer."),
                ("Open Raw folder", lambda: self.open_path(self.raw_dir),
                 "Opens Raw, where you copy each SD card into its camera's folder."),
                ("Open Output folder", lambda: self.open_path(self.out_dir),
                 "Opens Output, where tagged clips are kept by camera."),
                ("Open spreadsheet", self.open_spreadsheet,
                 "Opens Clip Log.xlsx: every tagged clip, one row per animal, plus an Animals sheet."),
                None,
                ("Exit", self.on_close, "Closes the program. Your tags are always saved."),
            ],
            "Tools": [
                ("Settings…", lambda: SettingsDialog(self),
                 "File name order and format, folders and burst time, animal buttons and groups."),
                None,
                ("Rename a nickname everywhere…", self.tool_rename_nick,
                 "Changes a nickname on every clip and renames the files. Type an existing name to merge two."),
                ("Re-apply file name format to all clips", self.tool_reapply,
                 "Renames every tagged clip to match the current file name settings."),
                ("Check log against files…", self.tool_check,
                 "Finds clips deleted, renamed or added in File Explorer and tidies the log."),
                ("Forget deleted clips…", self.tool_forget,
                 "Removes deleted clips (the grey rows) from the spreadsheet for good."),
                ("Rebuild spreadsheet now", lambda: self.write_xlsx(force_msg=True),
                 "Writes Clip Log.xlsx again right away."),
            ],
            "Help": [
                ("Step-by-step guide", lambda: self.tutorial.start_guided(),
                 "The guided tour from picking a camera to saving your first clip."),
                ("What's this? (click anything)", lambda: self.tutorial.start_whats(),
                 "The mode you're in now: click anything to learn what it does."),
                ("Keyboard shortcuts", self.show_keys, "A list of all the shortcut keys."),
                None,
                ("About Trail Cam Tagger", self.show_about, "Version, license and where to get the source code."),
            ],
        }
        self.menu_btns = {}
        for name, items in spec.items():
            mb = tk.Menubutton(bar, text=name, padx=10, pady=3, relief="flat", activebackground="#d0e4f7",
                               font=(FONT, 10), takefocus=0)
            menu = tk.Menu(mb, tearoff=0)
            for it in items:
                if it is None:
                    menu.add_separator()
                else:
                    label, cmd, info = it
                    menu.add_command(label=label, command=self.menu_action(mb, label, info, cmd))
            mb["menu"] = menu
            mb.pack(side="left")
            self.menu_btns[name] = mb

    def menu_action(self, mb, label, info, cmd, undo=None):
        """Menu item: runs normally, but in What's this? mode explains itself instead."""
        def run():
            tut = getattr(self, "tutorial", None)
            if tut and tut.mode == "whats":
                if undo:
                    undo()
                tut.explain(mb, label.replace("…", ""), info)
            else:
                cmd()
        return run

    def build_ui(self):
        top = ttk.Frame(self.root, padding=6)
        top.pack(fill="x")
        self.mode_bar = ttk.Frame(top)
        self.mode_bar.pack(side="left")
        self.mode_btns = {}
        for text, val in (("Tag new clips", "tag"), ("Review / edit tagged", "review"), ("Animals", "animals")):
            rb = ttk.Radiobutton(self.mode_bar, text=text, value=val, variable=self.mode, style="Toolbutton",
                                 command=self.switch_mode, takefocus=False)
            rb.pack(side="left", padx=2)
            self.mode_btns[val] = rb
        ttk.Separator(top, orient="vertical").pack(side="left", fill="y", padx=10)
        self.tagbar = ttk.Frame(top)
        self.tagbar.pack(side="left", fill="x", expand=True)
        ttk.Label(self.tagbar, text="Camera:").pack(side="left")
        self.cam_var = tk.StringVar()
        self.cam_box = ttk.Combobox(self.tagbar, textvariable=self.cam_var, state="readonly", width=26,
                                    postcommand=self.refresh_cameras, takefocus=False)
        self.cam_box.pack(side="left", padx=4)
        self.cam_box.bind("<<ComboboxSelected>>", lambda e: self.select_camera())
        ttk.Button(self.tagbar, text="+ New camera", takefocus=False, command=self.new_camera).pack(side="left", padx=4)
        ttk.Button(self.tagbar, text="⟳ Rescan", takefocus=False, command=self.rescan).pack(side="left")
        self.tut_auto = tk.BooleanVar(value=self.settings.get("tutorial_auto", True))
        self.tut_btn = ttk.Menubutton(top, text="❓ Tutorial", takefocus=False)
        tmenu = tk.Menu(self.tut_btn, tearoff=0)
        tmenu.add_command(label="Step-by-step guide", command=self.menu_action(
            self.tut_btn, "Step-by-step guide", "Short popups from picking a camera to saving your first clip.",
            lambda: self.tutorial.start_guided()))
        tmenu.add_command(label="What's this?  (click anything to learn what it does)", command=self.menu_action(
            self.tut_btn, "What's this?", "The mode you're in now: click anything to learn what it does.",
            lambda: self.tutorial.start_whats()))
        tmenu.add_separator()
        tmenu.add_checkbutton(label="Show the guide when the program starts", variable=self.tut_auto,
                              command=self.menu_action(
                                  self.tut_btn, "Show the guide when the program starts",
                                  "Ticked: the step-by-step guide opens every time the program starts.",
                                  lambda: self.set_tutorial_auto(self.tut_auto.get()),
                                  undo=lambda: self.tut_auto.set(not self.tut_auto.get())))
        self.tut_btn["menu"] = tmenu
        self.tut_btn.pack(side="right", padx=(8, 0))
        self.progress = ttk.Label(top, text="", font=(FONT, 11, "bold"))
        self.progress.pack(side="right", padx=8)

        self.dup_bar = tk.Frame(self.root, bg="#f6d32d")
        self.dup_lbl = tk.Label(self.dup_bar, bg="#f6d32d", font=(FONT, 10))
        self.dup_lbl.pack(side="left", padx=8, pady=3)
        ttk.Button(self.dup_bar, text="Move duplicate to Raw\\_Duplicates", command=self.remove_duplicate).pack(side="right", padx=8, pady=2)

        self.main = ttk.Frame(self.root)
        self.main.pack(fill="both", expand=True)

        # review sidebar
        self.side = ttk.Frame(self.main, padding=(6, 0, 0, 6), width=470)
        self.side.pack_propagate(False)
        self.f_animal = None
        self.chip = tk.Frame(self.side, bg="#d0e4f7")
        self.chip_lbl = tk.Label(self.chip, bg="#d0e4f7", font=(FONT, 10, "bold"))
        self.chip_lbl.pack(side="left", padx=6, pady=3)
        ttk.Button(self.chip, text="✕ show all", takefocus=False, command=self.clear_animal_filter).pack(side="right", padx=4, pady=2)
        f = ttk.Frame(self.side)
        f.pack(fill="x")
        self.side_filters = f
        self.f_cam = tk.StringVar(value="All cameras")
        self.f_cam_box = ttk.Combobox(f, textvariable=self.f_cam, state="readonly", width=14,
                                      postcommand=lambda: self.f_cam_box.config(values=["All cameras"] + self.store.cameras()))
        self.f_cam_box.grid(row=0, column=0, sticky="we")
        self.f_cam_box.bind("<<ComboboxSelected>>", lambda e: self.refresh_review())
        self.f_hl = tk.BooleanVar()
        ttk.Checkbutton(f, text="★ Hilite only", variable=self.f_hl, command=self.refresh_review).grid(row=0, column=1, padx=6)
        self.f_empty = tk.BooleanVar()
        ttk.Checkbutton(f, text="Show empties", variable=self.f_empty, command=self.refresh_review).grid(row=0, column=2)
        ttk.Label(f, text="Search").grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.f_text = tk.StringVar()
        e = ttk.Entry(f, textvariable=self.f_text)
        e.grid(row=2, column=0, columnspan=3, sticky="we")
        self.f_text.trace_add("write", lambda *a: self.refresh_review())
        ttk.Label(f, text="From (YYYY-MM-DD)").grid(row=3, column=0, sticky="w", pady=(4, 0))
        ttk.Label(f, text="To").grid(row=3, column=1, sticky="w", pady=(4, 0))
        self.f_from, self.f_to = tk.StringVar(), tk.StringVar()
        ttk.Entry(f, textvariable=self.f_from, width=12).grid(row=4, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.f_to, width=12).grid(row=4, column=1, sticky="w")
        for v in (self.f_from, self.f_to):
            v.trace_add("write", lambda *a: self.refresh_review())
        f.columnconfigure(0, weight=1)
        ttk.Label(self.side, text="Search matches anything in the file name: Buck, 10pt, 5x5, NonTyp, a nickname, Hilite…",
                  foreground="gray", wraplength=400).pack(anchor="w", pady=2)
        tv_holder = ttk.Frame(self.side)
        tv_holder.pack(fill="both", expand=True, pady=(4, 0))
        self.tv = ttk.Treeview(tv_holder, columns=("when", "cam", "what"), show="headings", selectmode="browse")
        for col, text, w in (("when", "Date / time", 140), ("cam", "Cam", 60), ("what", "Tags", 240)):
            self.tv.heading(col, text=text)
            self.tv.column(col, width=w, stretch=col == "what")
        self.tv.tag_configure("hl", background=HILITE_BG)
        sb = ttk.Scrollbar(tv_holder, orient="vertical", command=self.tv.yview)
        self.tv.configure(yscrollcommand=sb.set)
        self.tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tv.bind("<<TreeviewSelect>>", lambda e: self.review_open())
        self.review_count = ttk.Label(self.side, text="")
        self.review_count.pack(anchor="w")

        self.panel = TagPanel(self.main, self)
        self.panel.pack(side="right", fill="y")
        self.media = MediaView(self.main, self)
        self.media.pack(side="left", fill="both", expand=True, padx=6)
        self.build_animals_page()

        self.statusbar = ttk.Label(self.root, text="", relief="sunken", padding=(6, 2))
        self.statusbar.pack(fill="x", side="bottom")

    def bind_keys(self):
        def g(fn):
            def h(e):
                if is_text_widget(e.widget):
                    return None
                fn()
                return "break"
            return h
        r = self.root
        r.bind("<space>", g(self.media.toggle_play))
        r.bind("<comma>", g(lambda: self.media.step(-1)))
        r.bind("<period>", g(lambda: self.media.step(1)))
        r.bind("<Left>", g(lambda: self.media.next_photo(-1)))
        r.bind("<Right>", g(lambda: self.media.next_photo(1)))
        for k, fn in (("e", self.mark_empty), ("s", self.skip), ("h", self.toggle_hilite)):
            r.bind(k, g(fn))
            r.bind(k.upper(), g(fn))
        r.bind("<Control-z>", g(self.undo))
        if MAC:
            r.bind("<Command-z>", g(self.undo))
        r.bind("<Return>", lambda e: self.primary_save())
        r.bind("<Escape>", lambda e: r.focus_set())
        r.bind("<F5>", lambda e: self.rescan())
        r.bind("<FocusIn>", lambda e: self.on_focus())

    def on_focus(self):
        """Coming back from File Explorer: pick up new Raw files and deleted/renamed clips."""
        if time.time() - self.last_reconcile < 10:
            return
        self.root.after(300, self.refresh_cameras)
        self.root.after(400, self.reconcile)

    def reconcile(self):
        self.last_reconcile = time.time()
        try:
            deleted, reconnected, restored, cams = core.reconcile(self.store)
        except OSError as e:
            self.status(f"Couldn't check the Output folder: {e}")
            return
        if not (deleted or reconnected or restored):
            return
        if cams:
            self.media.close() if self.mode.get() == "review" else None
            self.report(core.sync_names(self.store, self.settings, cams))
        bits = []
        if deleted:
            bits.append(f"{deleted} deleted")
        if restored:
            bits.append(f"{restored} restored")
        if reconnected:
            bits.append(f"{reconnected} renamed/moved (tags kept)")
        self.status("Noticed changes made in File Explorer: " + ", ".join(bits) + ". Spreadsheet updated.")
        self.schedule_xlsx()
        if self.mode.get() == "animals":
            self.refresh_animals()
        if self.mode.get() == "review":
            if self.review_sel and any(r.get("deleted") for r in self.review_sel):
                self.review_sel = None
                self.media.load([])
                self.panel.clear()
            self.refresh_review()
            if self.review_sel:
                self.reselect(self.review_sel[0]["id"])

    # ---------------------------------------------------------- tutorial
    def set_tutorial_auto(self, on):
        self.settings["tutorial_auto"] = bool(on)
        self.tut_auto.set(bool(on))
        self.save_settings()

    @staticmethod
    def visible_widget(w):
        try:
            return bool(w.winfo_ismapped())
        except tk.TclError:
            return False

    ACTION_HELP = {
        "Save & Next": "Saves the tags, renames the clip, moves it into Output\\<camera> and opens the next one. Shortcut: Enter.",
        "Empty": "Nothing in the clip. It's named …_Empty and moved to Output\\<camera>\\Empty. Shortcut: E.",
        "Skip": "Leaves this clip in Raw for later and shows the next one. Shortcut: S.",
        "Undo": "Moves the clip you just saved back to Raw with its tags filled in, so you can fix it. Ctrl+Z.",
        "Save changes": "Saves your edits to this clip and renames the file to match. Shortcut: Enter.",
        "Mark as Empty": "Changes this clip to Empty and moves it to that camera's Empty folder.",
        "Send back": "Removes the tags and moves the clip back to Raw with its original name.",
    }

    def help_action(self, button, text):
        if getattr(self, "tutorial", None):
            for key, info in self.ACTION_HELP.items():
                if text.startswith(key):
                    self.tutorial.register(button, text.split("  (")[0], info)

    def register_help(self):
        h = self.tutorial.register
        p, m = self.panel, self.media
        h(self.mode_btns["tag"], "Tag new clips", "Go through new clips in Raw one by one and tag them.")
        h(self.mode_btns["review"], "Review / edit tagged",
          "Find any tagged clip (filter by camera, date, Hilite or search) and change its tags. The file is renamed for you.")
        h(self.mode_btns["animals"], "Animals",
          "Every animal you've nicknamed: first/last seen, clips, latest rack. Mark one harvested or dead, or jump to its clips.")
        for name, info in (("File", "Open your folders and Clip Log.xlsx, or exit."),
                           ("Tools", "Settings, rename a nickname everywhere, re-apply file names, check log, "
                                     "forget deleted clips, rebuild spreadsheet."),
                           ("Help", "Step-by-step guide, What's this?, keyboard shortcuts, About (version and license).")):
            h(self.menu_btns[name], f"{name} menu", info + "  (In What's this? mode, Shift+click to open it.)")
        h(self.tut_btn, "❓ Tutorial", "Start the step-by-step guide, or this What's this? mode. "
                                     "You can also choose whether the guide shows at start.")
        h(self.cam_box, "Camera", "Pick which camera's clips to tag. The number shows how many are waiting in Raw. "
                                  "New folders you make in Raw or Output show up here automatically.")
        for w in self.tagbar.winfo_children():
            if isinstance(w, ttk.Button) and "New camera" in str(w.cget("text")):
                h(w, "+ New camera", "Makes a new camera folder in both Raw and Output (e.g. CAM5 or EastRidge).")
            elif isinstance(w, ttk.Button) and "Rescan" in str(w.cget("text")):
                h(w, "⟳ Rescan", "Looks in the Raw folder again, e.g. after copying in more clips or to revisit skipped ones. F5.")
        h(self.progress, "Progress", "Which clip you're on and how many are left for this camera.")
        h(m.canvas, "Viewer", "The clip plays here. Click or Space = pause. Mouse wheel = zoom (for counting points), "
                              "drag = move around, double-click = reset zoom.")
        h(m.vctl, "Video controls", "◀ frame and frame ▶ step one frame (keys , and .). Pause/Play (Space). "
                                    "Drag the bar to scrub; it pauses the video. Speed slows it down for a closer look.")
        h(m.strip, "Burst photos", "Photos taken seconds apart are grouped: tag them once and they all get it. "
                                   "Click a photo to view it, ← → keys to flip.")
        h(m.split_btn, "Split burst here", "If two different visits got grouped, click the first photo of the second "
                                           "visit and press this to separate them.")
        h(m.info, "Clip info", "Type, date and time taken, and the original file name.")
        h(p.btns, "Animal buttons", "Click each animal you see; each click adds a line below. Two bucks = click Buck twice. "
                                    "'+ Add…' makes a new button. Rearrange or group them in Tools → Settings → Animal buttons.")
        h(p.rows_canvas, "In this clip", "One line per animal: Count, Details (spreadsheet only) and ✕ to remove it. "
                                         "Bucks also get Points, Left x Right, NonTyp, Unknown pts and Button buck. "
                                         "Last, Nickname: pick from the list or type. Picking a known buck fills in his rack.")
        h(p.hl_check, "★ Hilite", "Marks a standout clip. 'Hilite' goes in the file name so you can search for it. Shortcut: H.")
        h(p.notes_entry, "Notes", "Anything you want to remember about this clip. Goes in the spreadsheet only.")
        h(p.preview, "New file name", "What the clip will be named. Change the order and format in Tools → Settings → File name.")
        h(self.statusbar, "Status bar", "Shows what just happened (saved, renamed, spreadsheet updated…).")
        h(self.side_filters, "Filters", "Narrow the list: camera, ★ Hilite only, show empties, search (matches anything in "
                                        "the name: Buck, 10pt, a nickname…) and a date range.")
        h(self.tv, "Tagged clips", "Click one to watch it and edit its tags on the right. Hilited clips are yellow.")
        h(self.chip, "Animal filter", "Only this animal's clips are shown. '✕ show all' clears it.")
        h(self.atv, "Nicknamed animals", "Click one to see and edit its status below. Double-click to see its clips. "
                                         "Click a column heading to sort.")
        h(self.a_detail, "Animal details", "Status (Active, Harvested, Found dead, Presumed gone), date, by whom and notes. "
                                           "Save, Show clips, or Rename / merge two nicknames that are the same deer.")
        h(self.a_species_box.master, "Animal filters", "Show one species or status, or search by name or notes.")

    def show_about(self):
        where = core.PROJECT_URL or "the README.md and LICENSE files in your Trail Cams folder"
        messagebox.showinfo("About Trail Cam Tagger", (
            f"Trail Cam Tagger {core.VERSION}\n"
            "Copyright (C) 2026 Trail Cam Tagger contributors\n\n"
            "Free and open source software under the GNU Affero General Public License, "
            "version 3 or later. You may use, share and change it; changed versions must "
            "stay under the same license with their source code available.\n\n"
            "It comes with ABSOLUTELY NO WARRANTY. See the LICENSE file for details.\n\n"
            f"Source code and license: {where}"))

    def show_keys(self):
        messagebox.showinfo("Keyboard shortcuts", (
            "Enter\tSave & next  (or save changes in Review)\n"
            "E\tEmpty\n"
            "S\tSkip for now\n"
            "H\tHilite on/off\n"
            "Ctrl+Z\tUndo last save (clip goes back to Raw)\n"
            "Space\tPlay / pause video  (or click the video)\n"
            ",  .\tStep one frame back / forward\n"
            "← →\tPrevious / next photo in a burst\n"
            "F5\tRescan the Raw folder\n\n"
            "Mouse wheel on the picture = zoom, drag = move, double-click = reset.\n"
            "Shortcut letters don't work while you're typing in a box: press Esc first."))

    def status(self, text):
        self.statusbar.config(text=text)

    def on_error(self, exc, val, tb):
        print(f"\n--- {datetime.now():%Y-%m-%d %H:%M:%S} ---")
        traceback.print_exception(exc, val, tb)
        messagebox.showerror("Something went wrong", f"{val}\n\nDetails were saved to:\n{LOG_PATH}\n"
                             "Send that file along if you need help.")

    def open_path(self, p):
        p = Path(p)
        if not p.exists():
            messagebox.showinfo("Not found", f"{p} doesn't exist yet.")
            return
        try:
            if sys.platform == "win32":
                os.startfile(str(p))  # noqa
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(p)])
            else:
                subprocess.Popen(["xdg-open", str(p)])
        except OSError:
            self.status(str(p))

    # ------------------------------------------------------------ start
    def start(self):
        self.root.after(1200, self.ensure_xlsx)
        if not self.raw_dir.exists() or not core.raw_cameras(self.raw_dir):
            self.first_run()
        self.refresh_cameras()
        last = self.settings.get("last_camera")
        cams = core.raw_cameras(self.raw_dir)
        if cams:
            self.select_camera(last if last in cams else cams[0])
        else:
            self.switch_mode(load=False)
            self.media.message("Add a camera with  + New camera  to get started.")
        if self.settings.get("tutorial_auto", True):
            self.root.after(900, self.tutorial.start_guided)

    def first_run(self):
        msg = (f"Welcome!\n\nYour main trail cam folder is:\n{ROOT}\n\n"
               f"No camera folders were found in {self.raw_dir.name}\\.\n"
               "Create Raw\\CAM1 … CAM4 (and matching Output folders) now?\n\n"
               "You can rename them in File Explorer afterwards (e.g. EastRidge) "
               "or add more with  + New camera.")
        if messagebox.askyesno("Set up folders", msg):
            for i in range(1, 5):
                self.make_camera(f"CAM{i}")

    def make_camera(self, name):
        (self.raw_dir / name).mkdir(parents=True, exist_ok=True)
        (self.out_dir / name / core.EMPTY_DIR).mkdir(parents=True, exist_ok=True)

    def new_camera(self):
        name = simpledialog.askstring("New camera", "Camera name (e.g. CAM5 or EastRidge):", parent=self.root)
        name = core.clean(name or "", " -")
        if not name.strip():
            return
        self.make_camera(name.strip())
        self.refresh_cameras()
        self.select_camera(name.strip())

    # ---------------------------------------------------------- cameras
    def refresh_cameras(self):
        # a camera folder made by hand in either Raw or Output gets its partner folder
        for c in core.raw_cameras(self.out_dir):
            if not (self.raw_dir / c).exists():
                try:
                    (self.raw_dir / c).mkdir(parents=True, exist_ok=True)
                except OSError:
                    pass
        cams = core.raw_cameras(self.raw_dir)
        labels = []
        for c in cams:
            n = len(core.raw_files(self.raw_dir / c))
            labels.append(f"{c}   ({n} to tag)" if n else f"{c}   (done)")
            if not (self.out_dir / c / core.EMPTY_DIR).exists():
                try:
                    (self.out_dir / c / core.EMPTY_DIR).mkdir(parents=True, exist_ok=True)
                except OSError:
                    pass
        self.cam_labels = dict(zip(labels, cams, strict=True))
        self.cam_box.config(values=labels)
        if self.camera in cams:
            self.cam_var.set(labels[cams.index(self.camera)])

    def select_camera(self, cam=None):
        cam = cam or self.cam_labels.get(self.cam_var.get())
        if not cam:
            return
        self.camera = cam
        self.settings["last_camera"] = cam
        self.save_settings()
        self.refresh_cameras()
        self.mode.set("tag")
        self.switch_mode(load=False)
        self.rescan()

    def rescan(self, keep_file=None):
        if not self.camera:
            return
        self.status("Scanning…")
        self.root.update_idletasks()
        self.queue = core.scan_raw(self.raw_dir / self.camera, self.settings["burst_seconds"])
        self.qi = 0
        if keep_file:
            for i, it in enumerate(self.queue):
                if any(f.name == keep_file.name for f in it["files"]):
                    self.qi = i
        self.status(f"{sum(len(i['files']) for i in self.queue)} files in Raw\\{self.camera}")
        self.refresh_cameras()
        if self.mode.get() == "tag":
            self.show_item()

    # ------------------------------------------------------------ modes
    def switch_mode(self, load=True):
        if self.cur_mode == "review" and self.mode.get() != "review":
            if not self.confirm_unsaved():
                self.mode.set("review")
                return
        self.cur_mode = self.mode.get()
        if self.mode.get() == "animals":
            self.media.close()
            for w in (self.tagbar, self.dup_bar, self.side, self.panel, self.media):
                w.pack_forget()
            self.progress.config(text="")
            self.animals_frame.pack(fill="both", expand=True)
            self.reconcile()
            self.refresh_animals()
            return
        self.animals_frame.pack_forget()
        if not self.panel.winfo_manager():
            self.panel.pack(side="right", fill="y")
            self.media.pack(side="left", fill="both", expand=True, padx=6)
        if self.mode.get() == "review":
            self.media.close()
            self.tagbar.pack_forget()
            self.dup_bar.pack_forget()
            self.side.pack(side="left", fill="y", before=self.media)
            self.panel.title.config(text="Edit tags  (click to add animals)")
            self.review_sel = None
            self.reconcile()
            self.refresh_review()
            self.media.load([], "")
            self.media.message("Pick a clip from the list on the left.")
            self.panel.clear()
            self.panel.set_actions([("Save changes  (Enter)", self.review_save, True),
                                    ("Mark as Empty", self.review_empty, False),
                                    ("Send back to Raw (untag)", self.review_send_back, False)])
            self.progress.config(text="")
        else:
            self.side.pack_forget()
            self.tagbar.pack(side="left", fill="x", expand=True)
            self.panel.title.config(text="What's in it?  (click each animal)")
            self.panel.set_actions([("Save & Next  (Enter)", self.save, True),
                                    ("Empty  (E)", self.mark_empty, True),
                                    ("Skip  (S)", self.skip, False),
                                    ("Undo last save  (Ctrl+Z)", self.undo, False)])
            if load:
                self.rescan()

    def has_item(self):
        if self.mode.get() == "tag":
            return self.current() is not None
        if self.mode.get() == "animals":
            return False
        return self.review_sel is not None

    def primary_save(self):
        mode = self.mode.get()
        if mode == "tag":
            self.save()
        elif mode == "review":
            self.review_save()
        else:
            self.save_animal()

    def toggle_hilite(self):
        if self.has_item():
            self.panel.hilite.set(not self.panel.hilite.get())
            self.panel.update_preview()

    # --------------------------------------------------------- tagging
    def current(self):
        return self.queue[self.qi] if 0 <= self.qi < len(self.queue) else None

    def show_item(self, prefill=None):
        self.panel.clear()
        self.dup_bar.pack_forget()
        it = self.current()
        if it is None:
            n = len(self.queue)
            self.progress.config(text="")
            self.media.load([])
            self.media.message(f"Nothing left to tag in {self.camera}." +
                               (f"\n{n} skipped — press ⟳ Rescan to go through them again." if n else "")
                               if self.camera else "Pick a camera.")
            return
        self.progress.config(text=f"{self.camera}:  {self.qi + 1} of {len(self.queue)}")
        t = it["times"][0]
        kind = f"Burst of {len(it['files'])} photos" if len(it["files"]) > 1 else it["kind"].title()
        info = f"{kind}   ·   {t:%a %b %d, %Y   %I:%M:%S %p}   ·   {', '.join(f.name for f in it['files'])}"
        self.media.load(it["files"], info)
        if prefill:
            self.panel.load(prefill)
        self.check_duplicate(it)
        self.panel.update_preview()

    def check_duplicate(self, it):
        idx = self.store.dup_index()
        f, t = it["files"][0], it["times"][0]
        rec = idx.get((self.camera, f.name.upper(), t.isoformat(), f.stat().st_size))
        if rec:
            was = f"  (deleted {rec['deleted']})" if rec.get("deleted") else ""
            self.dup_lbl.config(text=f"⚠ This looks like a duplicate of an already-tagged clip:  {rec['file']}{was}")
            self.dup_bar.pack(fill="x", before=self.main)

    def remove_duplicate(self):
        it = self.current()
        if not it:
            return
        self.media.close()
        dest_dir = self.raw_dir / "_Duplicates"
        dest_dir.mkdir(exist_ok=True)
        for f in it["files"]:
            core.shutil.move(str(f), str(core.unique_path(dest_dir / f.name)))
        del self.queue[self.qi]
        self.refresh_cameras()
        self.show_item()

    def preview_name(self, tags):
        if self.mode.get() == "tag":
            it = self.current()
            if not it:
                return ""
            rec = {"taken": it["times"][0].isoformat(), "camera": self.camera, "original": it["files"][0].name}
            seq = 1 if len(it["files"]) > 1 else None
            more = f"\n(+ {len(it['files']) - 1} more photos, numbered -2, -3…)" if seq else ""
        else:
            if not self.review_sel:
                return ""
            r0 = self.review_sel[0]
            rec = {k: r0[k] for k in ("taken", "camera", "original")}
            seq, more = None, ("\n(numbers like -1, -2 are added automatically)" if len(self.review_sel) > 1 else "")
        rec.update(tags)
        return core.build_name(rec, self.settings, seq) + more

    def harvest_ok(self, tags, taken):
        msgs = core.harvest_warning(self.store, tags, taken)
        if not msgs:
            return True
        return messagebox.askyesno("Check the nickname", "\n".join(msgs) + f", but this clip is from {taken[:10]}."
                                   "\n\nMaybe a look-alike? Save anyway?")

    def current_taken(self):
        """(time of the clip being tagged/edited, record ids to ignore)."""
        if self.mode.get() == "tag":
            it = self.current()
            return (it["times"][0].isoformat(), ()) if it else (None, ())
        if self.review_sel:
            return self.review_sel[0]["taken"], tuple(self.review_ids())
        return None, ()

    def nick_choices(self, token):
        """Nicknames for the dropdown: animals still active first, then harvested/dead ones."""
        active, gone = set(), set()
        for st in core.animal_stats(self.store).values():
            if st["token"] == token:
                (active if st["status"] == "Active" else gone).add(st["nick"])
        active |= set(self.settings["nicknames"].get(token, [])) - gone
        return sorted(active, key=str.lower) + sorted(gone, key=str.lower)

    def remember_nicknames(self, tags):
        for a in tags["animals"]:
            if a.get("nick"):
                lst = self.settings["nicknames"].setdefault(a["token"], [])
                if a["nick"] not in lst:
                    lst.append(a["nick"])
                    lst.sort(key=str.lower)
        self.save_settings()

    def save(self):
        it = self.current()
        if not it:
            return
        if not self.panel.rows:
            messagebox.showinfo("Nothing tagged", "Click the animal(s) first, or press Empty.")
            return
        if not self.harvest_ok(self.panel.tags(), it["times"][0].isoformat()):
            return
        self.commit(self.panel.tags())

    def mark_empty(self):
        if self.mode.get() == "review":
            return
        if self.current():
            self.commit(self.panel.tags(empty=True))

    def commit(self, tags):
        it = self.current()
        self.media.close()
        try:
            ids, errors = core.tag_files(self.store, self.settings, self.camera, it["files"], tags)
        except OSError as e:
            messagebox.showerror("Could not move file", str(e))
            self.rescan()
            return
        self.remember_nicknames(tags)
        self.undo_stack.append(ids)
        del self.queue[self.qi]
        self.report(errors)
        name = self.store.records[ids[0]]["file"]
        self.status(f"Saved → {name}")
        self.schedule_xlsx()
        self.refresh_cameras()
        self.root.focus_set()
        self.show_item()

    def skip(self):
        if self.mode.get() == "tag" and self.current():
            self.qi += 1
            self.show_item()

    def undo(self):
        if self.mode.get() != "tag" or not self.undo_stack:
            return
        ids = [i for i in self.undo_stack.pop() if i in self.store.records]
        if not ids:
            return
        r0 = self.store.records[ids[0]]
        tags = {k: r0.get(k) for k in ("animals", "hilite", "notes")}
        cam = r0["camera"]
        self.media.close()
        moved, errors = core.send_back(self.store, self.settings, self.raw_dir, ids)
        self.report(errors)
        self.schedule_xlsx()
        if cam != self.camera:
            self.camera = cam
        self.rescan(keep_file=moved[0] if moved else None)
        if self.current():
            self.show_item(prefill=None if r0.get("empty") else tags)
        self.status("Undone — the clip is back in Raw with its tags filled in. Fix and save again.")

    def split_burst(self):
        if self.mode.get() == "tag":
            it, i = self.current(), self.media.photo_idx
            if not it or i <= 0:
                return
            tail = {"files": it["files"][i:], "times": it["times"][i:], "kind": "photo"}
            it["files"], it["times"] = it["files"][:i], it["times"][:i]
            self.queue.insert(self.qi + 1, tail)
            self.show_item(prefill=self.panel.tags() if self.panel.rows else None)
            self.status("Burst split. Tag this part; the rest is next.")
        else:
            recs, i = self.review_sel, self.media.photo_idx
            if not recs or i <= 0:
                return
            g = core.new_id()
            for r in recs[i:]:
                r["group"] = g if len(recs) - i > 1 else None
            if i == 1:
                recs[0]["group"] = None
            self.store.save()
            self.refresh_review()
            self.status("Burst split into two separate entries.")

    def report(self, errors):
        if errors:
            messagebox.showwarning("Some files couldn't be renamed",
                                   "\n".join(errors[:15]) + "\n\nIs one of them open in another program? "
                                   "Use Tools → Re-apply file name format to retry.")

    # ----------------------------------------------------------- review
    def review_list(self):
        cam = self.f_cam.get()
        text = self.f_text.get().strip().lower()
        d0, d1 = self.f_from.get().strip(), self.f_to.get().strip()
        out = []
        for item in self.store.items(None if cam == "All cameras" else cam):
            r = item[0]
            if self.f_animal and not any(a["token"] == self.f_animal[0] and core.clean(a.get("nick")) == self.f_animal[1]
                                         for a in r.get("animals", [])):
                continue
            if r.get("empty") and not self.f_empty.get():
                continue
            if self.f_hl.get() and not r.get("hilite"):
                continue
            day = r["taken"][:10]
            if (d0 and day < d0) or (d1 and day > d1):
                continue
            if text:
                hay = " ".join(x["file"] for x in item).lower() + " " + r.get("notes", "").lower() + " " + \
                      " ".join(" ".join(a.get("desc", [])) for a in r.get("animals", [])).lower()
                if not all(w in hay for w in text.split()):
                    continue
            out.append(item)
        return out

    def refresh_review(self):
        if self.mode.get() != "review":
            return
        sel_id = self.review_sel[0]["id"] if self.review_sel else None
        self.review_items = self.review_list()
        self.tv.delete(*self.tv.get_children())
        for i, item in enumerate(self.review_items):
            r = item[0]
            t = datetime.fromisoformat(r["taken"])
            what = "Empty" if r.get("empty") else " ".join(core.animal_part(a) for a in core.sorted_animals(r["animals"], self.settings))
            if len(item) > 1:
                what = f"[{len(item)} photos] " + what
            self.tv.insert("", "end", iid=str(i), values=(f"{t:%Y-%m-%d  %H:%M}", r["camera"], what),
                           tags=("hl",) if r.get("hilite") else ())
            if r["id"] == sel_id:
                self.tv.selection_set(str(i))
                self.tv.see(str(i))
        self.review_count.config(text=f"{len(self.review_items)} shown")

    def review_open(self):
        sel = self.tv.selection()
        if not sel:
            return
        item = self.review_items[int(sel[0])]
        if self.review_sel and [r["id"] for r in item] == [r["id"] for r in self.review_sel]:
            return
        if self.review_dirty():
            old_id = self.review_sel[0]["id"]
            ans = messagebox.askyesnocancel("Unsaved changes", "Save the changes to the clip you were editing?")
            if ans is None or (ans and not self.review_save()):
                self.reselect(old_id)  # stay on the edited clip
                return
            if ans:
                self.reselect(item[0]["id"])  # saved; now open the clip that was clicked
                return
        self.review_sel = item
        r = item[0]
        t = datetime.fromisoformat(r["taken"])
        files = [self.store.abspath(x) for x in item]
        info = f"{t:%a %b %d, %Y   %I:%M:%S %p}   ·   {r['camera']}   ·   was {', '.join(x['original'] for x in item)}"
        if not all(f.exists() for f in files):
            self.media.load([])
            self.media.message("File is missing.\nUse Tools → Check log.")
        else:
            self.media.load(files, info)
        self.panel.load({} if r.get("empty") else r)
        self.panel.hilite.set(bool(r.get("hilite")))
        self.panel.notes.set(r.get("notes", ""))
        self.panel.baseline = self.panel.tags(empty=bool(r.get("empty")))
        self.panel.update_preview()

    def review_dirty(self):
        p = getattr(self, "panel", None)
        if not p or p.baseline is None or not self.review_sel or self.cur_mode != "review":
            return False
        return p.tags(empty=p.baseline["empty"] and not p.rows) != p.baseline

    def confirm_unsaved(self, cancel=True):
        """Before leaving a clip with unsaved edits. Returns False if the user wants to stay."""
        if not self.review_dirty():
            return True
        ask = messagebox.askyesnocancel if cancel else messagebox.askyesno
        ans = ask("Unsaved changes", "Save the changes to the clip you were editing?")
        if ans is None:
            return False
        if ans:
            return bool(self.review_save())
        self.panel.baseline = None
        return True

    def review_ids(self):
        return [r["id"] for r in self.review_sel] if self.review_sel else []

    def review_save(self, empty=False):
        if not self.review_sel:
            return False
        if not empty and not self.panel.rows:
            messagebox.showinfo("Nothing tagged", "Add at least one animal, or use Mark as Empty.")
            return False
        tags = self.panel.tags(empty=empty)
        if not self.harvest_ok(tags, self.review_sel[0]["taken"]):
            return False
        ids = self.review_ids()
        self.media.close()
        errors = core.update_tags(self.store, self.settings, ids, tags)
        self.remember_nicknames(tags)
        self.report(errors)
        self.schedule_xlsx()
        self.status(f"Saved → {self.store.records[ids[0]]['file']}")
        self.review_sel = None
        self.panel.baseline = None
        self.refresh_review()
        self.reselect(ids[0])
        return True

    def reselect(self, rid):
        for i, item in enumerate(self.review_items):
            if any(r["id"] == rid for r in item):
                self.tv.selection_set(str(i))
                self.tv.see(str(i))
                return
        self.media.load([])
        self.panel.clear()

    def review_empty(self):
        self.review_save(empty=True)

    def review_send_back(self):
        if not self.review_sel:
            return
        if not messagebox.askyesno("Send back to Raw", "Remove the tags and move this back to the Raw folder "
                                                       "with its original file name?"):
            return
        self.media.close()
        moved, errors = core.send_back(self.store, self.settings, self.raw_dir, self.review_ids())
        self.report(errors)
        self.schedule_xlsx()
        self.review_sel = None
        self.media.load([])
        self.panel.clear()
        self.refresh_review()
        self.status(f"Moved back to Raw: {', '.join(p.name for p in moved)}")

    # ---------------------------------------------------------- animals
    def build_animals_page(self):
        fr = self.animals_frame = ttk.Frame(self.main, padding=8)
        top = ttk.Frame(fr)
        top.pack(fill="x")
        ttk.Label(top, text="Nicknamed animals", font=(FONT, 13, "bold")).pack(side="left")
        ttk.Label(top, text="   (animals show up here once you give them a nickname while tagging)",
                  foreground="gray").pack(side="left")
        flt = ttk.Frame(fr)
        flt.pack(fill="x", pady=6)
        ttk.Label(flt, text="Species").pack(side="left")
        self.a_species = tk.StringVar(value="All")
        self.a_species_box = ttk.Combobox(flt, textvariable=self.a_species, state="readonly", width=16)
        self.a_species_box.pack(side="left", padx=(4, 14))
        ttk.Label(flt, text="Status").pack(side="left")
        self.a_status = tk.StringVar(value="All")
        ttk.Combobox(flt, textvariable=self.a_status, state="readonly", width=14,
                     values=["All"] + core.STATUSES).pack(side="left", padx=(4, 14))
        ttk.Label(flt, text="Search").pack(side="left")
        self.a_search = tk.StringVar()
        ttk.Entry(flt, textvariable=self.a_search, width=20).pack(side="left", padx=4)
        for v in (self.a_species, self.a_status, self.a_search):
            v.trace_add("write", lambda *a: self.refresh_animals())

        cols = (("species", "Species", 120), ("nick", "Nickname", 140), ("status", "Status", 175),
                ("last", "Last seen", 100), ("first", "First seen", 100), ("clips", "Clips", 60),
                ("cams", "Cameras", 160), ("rack", "Latest rack", 140), ("max", "Most pts", 70))
        holder = ttk.Frame(fr)
        holder.pack(fill="both", expand=True)
        self.atv = ttk.Treeview(holder, columns=[c[0] for c in cols], show="headings", selectmode="browse")
        self.a_sort = ("last", True)
        for c, text, w in cols:
            self.atv.heading(c, text=text, command=lambda c=c: self.sort_animals(c))
            self.atv.column(c, width=w, stretch=c in ("cams", "rack"), anchor="center" if c in ("clips", "max") else "w")
        self.atv.tag_configure("gone", foreground="#77767b", background="#ececec")
        sb = ttk.Scrollbar(holder, orient="vertical", command=self.atv.yview)
        self.atv.configure(yscrollcommand=sb.set)
        self.atv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.atv.bind("<<TreeviewSelect>>", lambda e: self.animal_selected())
        self.atv.bind("<Double-1>", lambda e: self.show_animal_clips())

        d = self.a_detail = ttk.LabelFrame(fr, text="Select an animal", padding=10)
        d.pack(fill="x", pady=(8, 0))
        self.a_stat_var = tk.StringVar(value="Active")
        self.a_date = tk.StringVar()
        self.a_by = tk.StringVar()
        self.a_notes = tk.StringVar()
        ttk.Label(d, text="Status").grid(row=0, column=0, sticky="w")
        ttk.Combobox(d, textvariable=self.a_stat_var, values=core.STATUSES, state="readonly", width=14).grid(row=0, column=1, sticky="w", padx=4)
        ttk.Label(d, text="Date (YYYY-MM-DD)").grid(row=0, column=2, sticky="w", padx=(16, 0))
        ttk.Entry(d, textvariable=self.a_date, width=12).grid(row=0, column=3, sticky="w", padx=4)
        ttk.Button(d, text="Today", takefocus=False,
                   command=lambda: self.a_date.set(datetime.now().strftime("%Y-%m-%d"))).grid(row=0, column=4, sticky="w")
        ttk.Label(d, text="By").grid(row=0, column=5, sticky="w", padx=(16, 0))
        ttk.Entry(d, textvariable=self.a_by, width=18).grid(row=0, column=6, sticky="w", padx=4)
        ttk.Label(d, text="Notes").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(d, textvariable=self.a_notes).grid(row=1, column=1, columnspan=6, sticky="we", padx=4, pady=(8, 0))
        ttk.Label(d, text="e.g. score, weight, where it was found", foreground="gray").grid(row=2, column=1, columnspan=6, sticky="w", padx=4)
        d.columnconfigure(6, weight=1)
        btns = ttk.Frame(d)
        btns.grid(row=0, column=7, rowspan=3, sticky="ne", padx=(16, 0))
        ttk.Button(btns, text="Save  (Enter)", style="Big.TButton", takefocus=False, command=self.save_animal).pack(fill="x")
        ttk.Button(btns, text="Show clips ▶", takefocus=False, command=self.show_animal_clips).pack(fill="x", pady=3)
        ttk.Button(btns, text="Rename / merge…", takefocus=False, command=self.rename_animal).pack(fill="x")
        self.a_rows = {}
        self.a_sel = None

    def sort_animals(self, col):
        key, desc = self.a_sort
        self.a_sort = (col, not desc if key == col else col in ("last", "first", "clips", "max"))
        self.refresh_animals()

    def refresh_animals(self):
        if self.mode.get() != "animals":
            return
        stats = core.animal_stats(self.store)
        self.a_species_box.config(values=["All"] + sorted({s["token"] for s in stats.values()}, key=str.lower))
        sp, stt, q = self.a_species.get(), self.a_status.get(), self.a_search.get().strip().lower()
        rows = []
        for key, st in stats.items():
            if sp != "All" and st["token"] != sp:
                continue
            if stt != "All" and st["status"] != stt:
                continue
            if q and q not in f"{st['nick']} {st['token']} {st['notes']} {st['by']}".lower():
                continue
            clips = str(st["clips"]) + (f" ({st['deleted']} del)" if st["deleted"] else "")
            status = st["status"] + (f" {st['date']}" if st["date"] and st["status"] != "Active" else "")
            vals = {"species": st["token"], "nick": st["nick"], "status": status, "last": (st.get("last") or "")[:10],
                    "first": st["first"][:10], "clips": clips, "cams": ", ".join(sorted(st["cameras"])),
                    "rack": st["rack"], "max": st["max_pts"] or ""}
            sortv = {"clips": st["clips"], "max": st["max_pts"]}.get(self.a_sort[0], str(vals[self.a_sort[0]]).lower())
            rows.append((sortv, key, vals, st["status"] != "Active"))
        rows.sort(key=lambda r: r[0], reverse=self.a_sort[1])
        self.atv.delete(*self.atv.get_children())
        self.a_rows = {}
        for _, key, vals, gone in rows:
            self.atv.insert("", "end", iid=key, values=[vals[c] for c in self.atv["columns"]],
                            tags=("gone",) if gone else ())
            self.a_rows[key] = stats[key]
        if self.a_sel in self.a_rows:
            self.atv.selection_set(self.a_sel)
            self.atv.see(self.a_sel)

    def animal_selected(self):
        sel = self.atv.selection()
        if not sel:
            return
        self.a_sel = sel[0]
        st = self.a_rows[self.a_sel]
        self.a_detail.config(text=f"{st['nick']}  ({st['token']})")
        self.a_stat_var.set(st["status"])
        self.a_date.set(st["date"])
        self.a_by.set(st["by"])
        self.a_notes.set(st["notes"])

    def save_animal(self):
        if not self.a_sel or self.a_sel not in self.a_rows:
            return
        date = self.a_date.get().strip()
        if date:
            try:
                date = datetime.strptime(date, "%Y-%m-%d").strftime("%Y-%m-%d")
            except ValueError:
                messagebox.showerror("Date", "Please enter the date as YYYY-MM-DD, e.g. 2026-11-23.")
                return
        status = self.a_stat_var.get()
        if status != "Active" and not date:
            date = datetime.now().strftime("%Y-%m-%d")
        prof = {"status": status, "date": date, "by": self.a_by.get().strip(), "notes": self.a_notes.get().strip()}
        if status == "Active" and not any([prof["date"], prof["by"], prof["notes"]]):
            self.store.animals.pop(self.a_sel, None)
        else:
            self.store.animals[self.a_sel] = prof
        self.store.save()
        self.schedule_xlsx()
        self.status(f"Saved {self.a_rows[self.a_sel]['nick']}: {status}")
        self.refresh_animals()
        self.animal_selected()

    def show_animal_clips(self):
        if not self.a_sel or self.a_sel not in self.a_rows:
            return
        st = self.a_rows[self.a_sel]
        self.f_animal = (st["token"], st["nick"])
        self.f_cam.set("All cameras")
        self.f_text.set("")
        self.f_from.set("")
        self.f_to.set("")
        self.f_hl.set(False)
        self.chip_lbl.config(text=f"Showing: {st['nick']} ({st['token']})")
        self.chip.pack(fill="x", before=self.side_filters, pady=(0, 6))
        self.mode.set("review")
        self.switch_mode()
        if self.review_items:
            self.tv.selection_set("0")

    def clear_animal_filter(self):
        self.f_animal = None
        self.chip.pack_forget()
        self.refresh_review()

    def rename_animal(self):
        if not self.a_sel or self.a_sel not in self.a_rows:
            return
        st = self.a_rows[self.a_sel]
        new = simpledialog.askstring("Rename / merge", f"New nickname for {st['nick']} ({st['token']}):\n\n"
                                     "Tip: type another animal's nickname to merge the two (same deer).",
                                     parent=self.root)
        new = core.clean(new or "")
        if not new or new == st["nick"]:
            return
        self.reconcile()
        n, errors = core.rename_nickname(self.store, self.settings, st["nick"], new, st["token"])
        self.save_settings()
        self.report(errors)
        self.schedule_xlsx()
        self.a_sel = core.animal_key(st["token"], new)
        self.refresh_animals()
        self.animal_selected()
        self.status(f"{st['nick']} is now {new} ({n} tags).")

    # ----------------------------------------------------------- tools
    def tool_rename_nick(self):
        old = simpledialog.askstring("Rename nickname", "Current nickname:", parent=self.root)
        if not old:
            return
        new = simpledialog.askstring("Rename nickname", f"Change '{old}' to:", parent=self.root)
        if not new:
            return
        self.media.close()
        self.reconcile()
        n, errors = core.rename_nickname(self.store, self.settings, old, new)
        self.save_settings()
        self.report(errors)
        self.schedule_xlsx()
        messagebox.showinfo("Done", f"{n} animal tags now use '{core.clean(new)}'.")
        self.after_bulk()

    def tool_reapply(self):
        self.media.close()
        self.reconcile()
        errors = core.sync_names(self.store, self.settings)
        self.report(errors)
        self.schedule_xlsx()
        self.status(f"File names updated for {len(self.store.records)} clips.")
        self.after_bulk()

    def after_bulk(self):
        if self.mode.get() == "animals":
            self.refresh_animals()
        elif self.mode.get() == "review":
            self.review_sel = None
            self.refresh_review()
        else:
            self.show_item()

    def tool_forget(self):
        n = sum(1 for r in self.store.records.values() if r.get("deleted"))
        if not n:
            messagebox.showinfo("Forget deleted clips", "There are no deleted clips in the log.")
            return
        if messagebox.askyesno("Forget deleted clips",
                               f"{n} clips were deleted in File Explorer but are still listed (greyed out) in "
                               "the spreadsheet as history.\n\nRemove them from the spreadsheet for good?"):
            core.forget_deleted(self.store)
            self.schedule_xlsx()
            self.status(f"Removed {n} deleted clips from the log.")

    def tool_check(self):
        self.reconcile()
        missing, untracked = core.check_log(self.store)
        if not missing and not untracked:
            messagebox.showinfo("Check log", f"All good. {len(self.store.records)} clips, every file accounted for.")
            return
        if missing and messagebox.askyesno(
                "Missing files", f"{len(missing)} tagged clips have no file anymore (deleted or renamed "
                                 "outside this program), e.g.:\n\n" + "\n".join(r["file"] for r in missing[:8]) +
                                 "\n\nRemove them from the log?"):
            for r in missing:
                del self.store.records[r["id"]]
            self.store.save()
        if untracked and messagebox.askyesno(
                "Untracked files", f"{len(untracked)} photo/video files in Output aren't in the log, e.g.:\n\n" +
                                   "\n".join(str(p.relative_to(self.out_dir)) for p in untracked[:8]) +
                                   "\n\nMove them to Raw\\<camera> so you can tag them?"):
            self.media.close()
            for p in untracked:
                cam = p.relative_to(self.out_dir).parts[0] if len(p.relative_to(self.out_dir).parts) > 1 else "_Unknown"
                dest = core.unique_path(self.raw_dir / cam / p.name)
                dest.parent.mkdir(parents=True, exist_ok=True)
                core.shutil.move(str(p), str(dest))
            self.refresh_cameras()
        self.schedule_xlsx()
        self.after_bulk()

    # ----------------------------------------------------------- excel
    def schedule_xlsx(self):
        self.xlsx_pending = True
        if self.xlsx_job:
            self.root.after_cancel(self.xlsx_job)
        self.xlsx_job = self.root.after(2500, self.write_xlsx)

    def write_xlsx(self, force_msg=False):
        self.xlsx_job = None
        try:
            core.export_xlsx(self.store, XLSX_PATH, self.settings)
            self.xlsx_pending = False
            if force_msg:
                self.status(f"Spreadsheet updated: {XLSX_PATH}")
            return True
        except PermissionError:
            self.status(f"⚠ {core.XLSX_NAME} is open in Excel — it will update after you close it and save again "
                        "(or use Tools → Rebuild spreadsheet).")
        except Exception as e:
            print(f"\n--- {datetime.now():%Y-%m-%d %H:%M:%S}  spreadsheet error ---")
            traceback.print_exc()
            self.status(f"⚠ Spreadsheet not updated: {e}")
            if not getattr(self, "xlsx_error_shown", False):
                self.xlsx_error_shown = True
                messagebox.showwarning("Spreadsheet problem",
                                       f"Couldn't write {XLSX_PATH}\n\n{e}\n\nYour tags are safe. "
                                       f"Details were saved to:\n{LOG_PATH}")
        return False

    def ensure_xlsx(self):
        if not XLSX_PATH.exists():
            self.write_xlsx(force_msg=True)

    def open_spreadsheet(self):
        if not XLSX_PATH.exists() or self.xlsx_pending:
            self.write_xlsx()
        self.open_path(XLSX_PATH)

    # -------------------------------------------------------- settings
    def apply_settings(self, s, name_changed, token_renames=None):
        old_out = self.out_dir
        self.settings = s
        self.save_settings()
        if self.out_dir != old_out:
            self.open_store()
        self.panel.build_buttons()
        for old, new in (token_renames or {}).items():
            n = core.token_in_use(self.store, old)
            if n and messagebox.askyesno(
                    "Update tagged clips?", f"{n} tags already use '{old}' in their file names.\n\n"
                                            f"Change them to '{new}' and rename those files?"):
                self.media.close()
                self.report(core.rename_token(self.store, self.settings, old, new))
                self.save_settings()
                self.schedule_xlsx()
        if name_changed and self.store.records and messagebox.askyesno(
                "Rename existing clips?", f"Rename the {len(self.store.records)} clips you've already tagged "
                                          "to the new file name format?"):
            self.tool_reapply()
        self.refresh_cameras()
        if self.mode.get() == "tag":
            self.rescan()
        else:
            self.refresh_review()

    def on_close(self):
        if not self.confirm_unsaved():
            return
        self.tutorial.stop()
        self.media.close()
        if self.xlsx_pending and not self.write_xlsx():
            if not messagebox.askyesno("Spreadsheet not updated",
                                       f"{core.XLSX_NAME} is open in Excel, so it couldn't be updated.\n"
                                       "Your tags are safe; it will update next time.\n\nClose anyway?"):
                return
        self.save_settings()
        self.root.destroy()


def main():
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
