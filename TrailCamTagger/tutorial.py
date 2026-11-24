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
Trail Cam Tagger - tutorials.

  Step-by-step guide : popups that walk through tagging a first clip.
  What's this?       : click any part of the window to see what it does.
"""

import tkinter as tk

FONT = "Segoe UI"
BG = "#fff8d6"
EDGE = "#c48a00"
RING = "#ff7a00"
BTN = dict(relief="flat", bd=0, padx=10, pady=3, cursor="hand2", font=(FONT, 9))


class Tutorial:
    def __init__(self, app):
        self.app = app
        self.root = app.root
        self.mode = None          # None, "guided" or "whats"
        self.step = 0
        self.bubble = None
        self.ring = []
        self.help = {}            # widget path -> (title, text)
        self.redraw = None        # function that redraws the current popup
        self.banner = None
        self.tagged = []
        self.root.bind("<Configure>", self.on_configure, add="+")
        self.root.bind_class("WhatsThis", "<ButtonPress-1>", self.whats_click)
        self.root.bind_class("WhatsThis", "<ButtonRelease-1>", self.whats_release)
        self.root.bind_class("WhatsThis", "<B1-Motion>", lambda e: None if self.passthrough else "break")
        for ev in ("<Double-Button-1>", "<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.root.bind_class("WhatsThis", ev, lambda e: None if e.state & 0x0001 else "break")
        self.root.bind_class("WhatsThis", "<ButtonPress-3>", lambda e: self.whats_click(e, force_open=True))
        self.root.bind_class("WhatsThis", "<ButtonRelease-3>", self.whats_release)
        if self.root.tk.call("tk", "windowingsystem") == "aqua":  # Mac: right-click is button 2 / Ctrl+click
            self.root.bind_class("WhatsThis", "<ButtonPress-2>", lambda e: self.whats_click(e, force_open=True))
            self.root.bind_class("WhatsThis", "<ButtonRelease-2>", self.whats_release)
            self.root.bind_class("WhatsThis", "<Control-ButtonPress-1>", lambda e: self.whats_click(e, force_open=True))
        self.pending_open = None   # menu/dropdown to open when the click is released
        self.passthrough = False   # Shift+click on anything else: let it act normally
        self.root.bind_class("WhatsThis", "<KeyPress>", self.whats_key)
        self.root.bind_class("WhatsThis", "<<ComboboxSelected>>", self.whats_combo_selected)
        self.combo_restore = None

    # ================================================================ help registry
    def register(self, widget, title, text):
        self.help[str(widget)] = (title, text)

    def lookup(self, widget):
        w = widget
        while w is not None:
            if str(w) in self.help:
                return w, self.help[str(w)]
            w = getattr(w, "master", None)
        return None, None

    # ===================================================================== drawing
    def clear(self):
        if self.bubble is not None:
            self.bubble.destroy()
            self.bubble = None
        for r in self.ring:
            r.destroy()
        self.ring = []

    def visible(self, w):
        try:
            return w is not None and w.winfo_exists() and w.winfo_ismapped() and w.winfo_width() > 1
        except tk.TclError:
            return False

    def outline(self, w):
        """Orange box around a widget, made of four thin borderless windows."""
        x, y, wd, ht = w.winfo_rootx(), w.winfo_rooty(), w.winfo_width(), w.winfo_height()
        t = 3
        for gx, gy, gw, gh in ((x - t, y - t, wd + 2 * t, t), (x - t, y + ht, wd + 2 * t, t),
                               (x - t, y, t, ht), (x + wd, y, t, ht)):
            r = tk.Toplevel(self.root, bg=RING)
            r.overrideredirect(True)
            r.attributes("-topmost", True)
            r.geometry(f"{max(gw, 1)}x{max(gh, 1)}+{gx}+{gy}")
            self.ring.append(r)

    def show(self, target, title, text, buttons, footer=""):
        """Popup near `target` (or centred). buttons: list of (label, command, primary?)."""
        self.clear()
        self.root.update_idletasks()
        b = self.bubble = tk.Toplevel(self.root, bg=EDGE)
        b.overrideredirect(True)
        b.attributes("-topmost", True)
        inner = tk.Frame(b, bg=BG, padx=14, pady=10)
        inner.pack(padx=2, pady=2)
        tk.Label(inner, text=title, bg=BG, font=(FONT, 11, "bold"), anchor="w", justify="left").pack(fill="x")
        tk.Label(inner, text=text, bg=BG, font=(FONT, 10), wraplength=340, justify="left",
                 anchor="w").pack(fill="x", pady=(4, 8))
        row = tk.Frame(inner, bg=BG)
        row.pack(fill="x")
        if footer:
            tk.Label(row, text=footer, bg=BG, fg="#8a7a4a", font=(FONT, 9)).pack(side="left")
        for label, cmd, primary in reversed(buttons):
            tk.Button(row, text=label, command=cmd, bg="#3584e4" if primary else "#e9dfb8",
                      fg="white" if primary else "black", activebackground="#1a5fb4" if primary else "#ddd2a6",
                      **BTN).pack(side="right", padx=(4, 0))
        b.update_idletasks()
        bw, bh = b.winfo_reqwidth(), b.winfo_reqheight()
        rx, ry = self.root.winfo_rootx(), self.root.winfo_rooty()
        rw, rh = self.root.winfo_width(), self.root.winfo_height()
        if self.visible(target):
            self.outline(target)
            x, y = target.winfo_rootx(), target.winfo_rooty()
            w, h = target.winfo_width(), target.winfo_height()
            if y + h + 12 + bh <= ry + rh:          # below
                px, py = x, y + h + 12
            elif y - 12 - bh >= ry:                 # above
                px, py = x, y - 12 - bh
            elif x - 12 - bw >= rx:                 # left
                px, py = x - 12 - bw, y
            else:                                    # big target: inside, centred
                px, py = x + (w - bw) // 2, y + (h - bh) // 2
        else:
            px, py = rx + (rw - bw) // 2, ry + (rh - bh) // 3
        px = min(max(px, rx + 8), rx + rw - bw - 8)
        py = min(max(py, ry + 8), ry + rh - bh - 8)
        b.geometry(f"+{int(px)}+{int(py)}")
        b.lift()

    def on_configure(self, e):
        if e.widget is self.root and self.redraw and self.bubble is not None:
            self.root.after_idle(self.redraw)

    def stop(self):
        self.clear()
        self.redraw = None
        if self.mode == "whats":
            self.untag_all()
            if self.banner is not None:
                self.banner.destroy()
                self.banner = None
        self.mode = None

    # ================================================================ guided tour
    def steps(self):
        a, p, m = self.app, self.app.panel, self.app.media
        return [
            (None, "Welcome to Trail Cam Tagger!",
             "This quick tour takes you from opening the program to saving your first tagged clip. "
             "Click Next to go through it."),
            (lambda: a.cam_box, "Pick a camera",
             "Copy each SD card into its camera folder in Raw (Raw\\CAM1, Raw\\CAM2…). "
             "Then pick that camera here. The number shows how many clips are waiting."),
            (lambda: m.canvas, "Watch the clip",
             "The first clip plays here. Click it or press Space to pause. "
             "Scroll to zoom in (great for counting points), drag to move, double-click to reset."),
            (lambda: m.vctl if a.visible_widget(m.vctl) else m.strip, "Scrub and step",
             "◀ frame and frame ▶ step one frame at a time. Drag the bar to move through the video. "
             "Photos taken seconds apart show together as a burst."),
            (lambda: p.btns, "Click what you see",
             "Click each animal in the clip. Two bucks? Click Buck twice. "
             "'+ Add…' makes a new button."),
            (lambda: p.rows_canvas, "Fill in the details",
             "Each animal gets a line: Count, Details and ✕ to remove it. Bucks also get Points, "
             "Left x Right, NonTyp, Unknown pts and Button buck. Then Nickname: pick or type."),
            (lambda: p.hl_check, "Hilite and notes",
             "★ Hilite (H) marks a great clip so it's easy to find later. Notes go in the spreadsheet only."),
            (lambda: p.preview, "Check the new name",
             "This is the file name your clip will get: date, time, animals, camera."),
            (lambda: p.actions, "Save!",
             "Save & Next (Enter) renames the clip, moves it to Output and opens the next one. "
             "Nothing in it? Empty (E). Not sure? Skip (S). Made a mistake? Undo (Ctrl+Z)."),
            (lambda: a.mode_bar, "Review and Animals",
             "Review / edit tagged: find any clip and change its tags. "
             "Animals: your nicknamed deer, mark one harvested, jump to all its clips."),
            (lambda: a.menu_btns["File"], "File menu",
             "Open your Trail Cams, Raw and Output folders, and Clip Log.xlsx (the spreadsheet)."),
            (lambda: a.menu_btns["Tools"], "Tools menu",
             "Settings: file name order and format, animal buttons and groups. "
             "Also rename a nickname everywhere, check the log and rebuild the spreadsheet."),
            (lambda: a.menu_btns["Help"], "Help menu",
             "The step-by-step guide, What's this?, a list of keyboard shortcuts, and About (version and license)."),
            (lambda: a.tut_btn, "❓ Tutorial",
             "Brings this guide back any time, or turn on What's this? and click any button to learn what it does."),
            (None, "You're ready!",
             "Tag away. Everything is tracked in Clip Log.xlsx in your Trail Cams folder. "
             "You can delete old clips in File Explorer any time and the program keeps up."),
        ]

    def start_guided(self):
        self.stop()
        if self.app.mode.get() != "tag":
            self.app.mode.set("tag")
            self.app.switch_mode()
        self.mode = "guided"
        self.step = 0
        self.redraw = self.show_step
        self.root.after(150, self.show_step)

    def show_step(self):
        if self.mode != "guided":
            return
        steps = self.steps()
        self.step = max(0, min(self.step, len(steps) - 1))
        getter, title, text = steps[self.step]
        target = getter() if getter else None
        last = self.step == len(steps) - 1
        buttons = []
        if self.step > 0:
            buttons.append(("◀ Back", self.back, False))
        buttons.append(("Finish" if last else "Next ▶", self.finish if last else self.next, True))
        buttons.append(("Close", self.stop, False))
        buttons.append(("Don't show again", self.dont_show, False))
        self.show(target, title, text, buttons, footer=f"{self.step + 1} of {len(steps)}")

    def next(self):
        self.step += 1
        self.show_step()

    def back(self):
        self.step -= 1
        self.show_step()

    def finish(self):
        self.app.set_tutorial_auto(False)  # seen it all: don't pop up at start any more
        self.stop()

    def dont_show(self):
        """Confirmation popup pointing at the Tutorial button."""
        was_mode = self.mode
        self.clear()
        self.redraw = None

        def confirm():
            self.app.set_tutorial_auto(False)
            self.mode = was_mode
            self.stop()

        def undo():
            self.mode = was_mode
            if was_mode == "guided":
                self.redraw = self.show_step
                self.show_step()
            else:
                self.whats_intro()

        self.show(self.app.tut_btn, "OK, no more tutorial",
                  "It won't pop up again. To turn it back on, just click ❓ Tutorial right here.",
                  [("Keep tutorial", undo, False), ("Got it", confirm, True)])

    # ================================================================ what's this?
    def start_whats(self):
        self.stop()
        self.mode = "whats"
        a = self.app
        self.banner = tk.Frame(self.root, bg=RING)
        tk.Label(self.banner, text="What's this?  Click anything to see what it does.   "
                                   "Shift+click = really click it (open menus and lists, switch pages).   (Esc to quit)",
                 bg=RING, fg="white", font=(FONT, 10, "bold")).pack(side="left", padx=10, pady=4)
        tk.Button(self.banner, text="Quit What's this?", command=self.stop, bg="white", **BTN).pack(side="right", padx=8, pady=3)
        self.banner.pack(fill="x", before=a.main)
        self.tag_all()
        self.whats_intro()

    def whats_intro(self):
        self.redraw = self.whats_intro
        self.show(None, "What's this? mode",
                  "Click any part of the window and a note explains it.\n\n"
                  "Hold Shift to really click something: open a menu or list (picking an item explains it, "
                  "nothing changes), or switch to the Review or Animals page to learn it too.",
                  [("Start clicking", self.clear_keep, True), ("Quit", self.stop, False)])

    def clear_keep(self):
        self.clear()
        self.redraw = None

    def tag_all(self):
        """Put our bindtag first on every widget so clicks show help instead of acting."""
        self.tagged = []

        def walk(w):
            if w is self.banner:
                return
            tags = w.bindtags()
            if "WhatsThis" not in tags:
                w.bindtags(("WhatsThis",) + tags)
                self.tagged.append(w)
            for c in w.winfo_children():
                if isinstance(c, (tk.Toplevel, tk.Menu)):
                    continue  # menus opened with Shift must keep working
                walk(c)
        walk(self.root)

    def untag_all(self):
        for w in self.tagged:
            try:
                w.bindtags(tuple(t for t in w.bindtags() if t != "WhatsThis"))
            except tk.TclError:
                pass
        self.tagged = []

    def whats_click(self, e, force_open=False):
        if self.mode != "whats":
            return None
        w = e.widget if isinstance(e.widget, tk.Misc) else None
        self.pending_open, self.passthrough = None, False
        shift = bool(e.state & 0x0001)
        if (shift or force_open) and self.is_menu(w):
            self.pending_open = w      # opened on release: on Windows, opening on press gets cancelled
            self.clear_keep()
            return "break"
        if shift and not force_open:  # Shift+click anything else = really click it
            self.passthrough = True
            self.clear_keep()
            return None
        target, info = self.lookup(w)
        if not info:
            target, info = w, ("This area", "Nothing special here. Try a button, a box or a list.")
        self.redraw = lambda: self.show(target, info[0], info[1], self.whats_buttons())
        self.redraw()
        return "break"

    @staticmethod
    def is_menu(w):
        try:
            cls = w.winfo_class()
            return (cls in ("Menubutton", "TMenubutton") and bool(str(w.cget("menu")))) or cls == "TCombobox"
        except (tk.TclError, AttributeError):
            return False

    def whats_release(self, e):
        if self.mode != "whats":
            return None
        if self.pending_open is not None:
            w, self.pending_open = self.pending_open, None
            self.root.after(30, lambda: self.open_menu(w))
            return "break"
        if self.passthrough:
            self.passthrough = False
            self.root.after(300, self.retag)  # a page switch etc. may show new widgets
            return None
        return "break"

    def retag(self):
        if self.mode == "whats":
            self.tag_all()

    def open_menu(self, w):
        """Shift+click / right-click: open a menu or dropdown ourselves (works the same on every system).
        Picking an item is then explained instead of done. Returns True if something was opened."""
        if w is None:
            return False
        cls = w.winfo_class()
        try:
            if cls in ("Menubutton", "TMenubutton") and w.cget("menu"):
                self.clear_keep()
                menu = w.nametowidget(str(w.cget("menu")))
                x, y = w.winfo_rootx(), w.winfo_rooty() + w.winfo_height()
                self.popup(menu, x, y)
                return True
            if cls == "TCombobox":
                self.clear_keep()
                self.combo_restore = (w, w.get())
                w.focus_set()
                self.root.tk.call("ttk::combobox::Post", str(w))
                return True
        except tk.TclError:
            return False
        return False

    def popup(self, menu, x, y):
        try:
            menu.tk_popup(x, y)
        finally:
            try:
                menu.grab_release()
            except tk.TclError:
                pass

    def explain(self, target, title, text):
        """Explain a menu item / option picked while in What's this? mode."""
        self.redraw = lambda: self.show(target, title, text, self.whats_buttons())
        self.root.after(50, self.redraw)

    def whats_combo_selected(self, e):
        if self.mode != "whats":
            return None
        w = e.widget
        if self.combo_restore and self.combo_restore[0] is w:
            picked = w.get()
            w.set(self.combo_restore[1])  # put it back: nothing changes in this mode
            self.combo_restore = None
            _, info = self.lookup(w)
            title, text = info or ("Dropdown", "")
            self.explain(w, f"{title}: {picked}", text + "\n\n(Not changed: you're in What's this? mode.)")
        return "break"

    def whats_buttons(self):
        return [("OK", self.clear_keep, True), ("Quit What's this?", self.stop, False)]

    def whats_key(self, e):
        if e.keysym == "Escape":
            self.stop()
        return "break"
