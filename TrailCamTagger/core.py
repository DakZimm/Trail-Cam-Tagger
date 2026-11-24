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
Trail Cam Tagger - core logic (no user interface in this file).

The tag data file (Output/_tagger_data.json) is the master record of every
clip. File names are always generated from it, so names can be rebuilt at any
time (new name format, nickname changes, back-to-back numbering).
"""

import copy
import json
import os
import re
import shutil
import time
import uuid
from datetime import datetime
from pathlib import Path

PHOTO_EXT = {".jpg", ".jpeg", ".png"}
VIDEO_EXT = {".avi", ".mp4", ".mov", ".mkv", ".wmv", ".m4v"}
MEDIA_EXT = PHOTO_EXT | VIDEO_EXT

VERSION = "1.0.0"
PROJECT_URL = ""  # set to the GitHub page, e.g. "https://github.com/<you>/trail-cam-tagger"

DATA_NAME = "tagger_data.json"
XLSX_NAME = "Clip Log.xlsx"
EMPTY_DIR = "Empty"
TEMP_PREFIX = ".~tag_"

# (label shown in settings, strftime format, keeps files in date/time order)
DATE_FORMATS = [
    ("2026-11-20   (YYYY-MM-DD)", "%Y-%m-%d", True),
    ("20261120   (YYYYMMDD)", "%Y%m%d", True),
    ("2026_11_20", "%Y_%m_%d", True),
    ("2026.11.20", "%Y.%m.%d", True),
    ("26-11-20   (YY-MM-DD)", "%y-%m-%d", True),
    ("11-20-2026   (month first: breaks date order!)", "%m-%d-%Y", False),
]
TIME_FORMATS = [
    ("0614   (24-hour HHMM)", "%H%M", True),
    ("061422   (with seconds)", "%H%M%S", True),
    ("06.14", "%H.%M", True),
    ("06h14", "%Hh%M", True),
    ("0614AM   (12-hour: breaks time order!)", "%I%M%p", False),
]
SEPARATORS = [("_  underscore", "_"), ("-  dash", "-"), ("   space", " ")]

BLOCKS = {
    "date": "Date",
    "time": "Time",
    "hilite": "Hilite",
    "animals": "Animals",
    "camera": "Camera",
    "original": "Original #",
}

COMMON_DESC = ["Fighting", "Chasing", "Scraping", "Rubbing", "Feeding",
               "Injured", "Mange", "Piebald", "Collared"]


def _sp(group, label, token, points=False, desc=()):
    return {"group": group, "label": label, "token": token, "points": points, "desc": list(desc)}


DEFAULT_SPECIES = [
    _sp("Deer", "Buck", "Buck", True, ["Drop tine", "Kicker", "Broken", "Sticker", "Velvet", "Shed"]),
    _sp("Deer", "Doe", "Doe", False, ["With fawn"]),
    _sp("Deer", "Fawn", "Fawn", False, ["Spotted"]),
    _sp("Deer", "Deer ?", "Deer"),
    _sp("Turkey", "Tom", "Turkey-Tom", False, ["Strutting", "Gobbling"]),
    _sp("Turkey", "Jake", "Turkey-Jake", False, ["Strutting", "Gobbling"]),
    _sp("Turkey", "Hen", "Turkey-Hen", False, ["With poults"]),
    _sp("Turkey", "Turkey ?", "Turkey"),
    _sp("Pheasant", "Rooster", "Pheasant-Rooster"),
    _sp("Pheasant", "Hen", "Pheasant-Hen"),
    _sp("Pheasant", "Pheasant ?", "Pheasant"),
] + [_sp("", n, n) for n in ["Raccoon", "Coyote", "Fox", "Bobcat", "Opossum", "Skunk",
                             "Squirrel", "Rabbit", "Groundhog", "Bird", "Cat", "Dog",
                             "Person", "Vehicle"]]

DEFAULT_SETTINGS = {
    "raw_folder": "Raw",
    "output_folder": "Output",
    "name_blocks": ["date", "time", "hilite", "animals", "camera"],
    "separator": "_",
    "date_format": "%Y-%m-%d",
    "time_format": "%H%M",
    "hilite_word": "Hilite",
    "burst_seconds": 10,
    "species": DEFAULT_SPECIES,
    "common_desc": COMMON_DESC,
    "nicknames": {},
    "last_camera": "",
    "groups": ["Deer", "Turkey", "Pheasant"],   # order of the button rows ("Other" is always last)
    "tutorial_auto": True,                      # show the step-by-step guide at start
    "animal_order": "bucks_first",              # or "buttons": file names follow the button order
}


# --------------------------------------------------------------------- utils
def clean(text, keep=""):
    """Letters and digits only (plus any characters in `keep`)."""
    return re.sub(r"[^A-Za-z0-9" + re.escape(keep) + "]", "", str(text or ""))


def unique_path(path):
    path = Path(path)
    if not path.exists():
        return path
    n = 2
    while True:
        p = path.with_name(f"{path.stem} ({n}){path.suffix}")
        if not p.exists():
            return p
        n += 1


def retry(fn, *args):
    """Windows briefly locks files (Explorer thumbnails, antivirus, NAS). Try again for ~2 s."""
    for attempt in range(9):
        try:
            return fn(*args)
        except PermissionError:
            if attempt == 8:
                raise
            time.sleep(0.25)


def move(src, dest):
    return retry(shutil.move, str(src), str(dest))


def new_id():
    return uuid.uuid4().hex[:12]


def is_photo(path):
    return Path(path).suffix.lower() in PHOTO_EXT


def taken_time(path):
    """Photos: date stored inside the photo (EXIF). Videos/fallback: Date modified."""
    path = Path(path)
    if is_photo(path):
        try:
            from PIL import Image
            with Image.open(path) as im:
                exif = im.getexif()
                val = exif.get_ifd(0x8769).get(36867) or exif.get(306)
            if val:
                return datetime.strptime(str(val).strip()[:19], "%Y:%m:%d %H:%M:%S")
        except Exception:
            pass
    return datetime.fromtimestamp(path.stat().st_mtime).replace(microsecond=0)


def format_ok(settings):
    """Return a list of warnings about name formats that break date/time order."""
    warn = []
    blocks = settings["name_blocks"]
    if "date" not in blocks:
        warn.append("No Date block: files won't sort by date.")
    elif blocks[0] != "date":
        warn.append("Date is not first: Explorer won't sort files by date.")
    if "time" not in blocks:
        warn.append("No Time block: files from the same day won't be in time order.")
    elif "date" in blocks and blocks.index("time") != blocks.index("date") + 1:
        warn.append("Time doesn't come right after Date: same-day files may sort out of order.")
    for _label, fmt, ok in DATE_FORMATS:
        if fmt == settings["date_format"] and not ok:
            warn.append("Month-first date format breaks date order.")
    for _label, fmt, ok in TIME_FORMATS:
        if fmt == settings["time_format"] and not ok:
            warn.append("12-hour time breaks time order (1 PM sorts before 6 AM).")
    return warn


# ------------------------------------------------------------------- naming
def animal_part(a):
    parts = [clean(a["token"], "-")]
    if a.get("button"):
        parts.append("Button")
    elif a.get("unk_pts"):
        parts.append("UnkPts")
    elif a.get("total"):
        parts.append(f"{int(a['total']):02d}pt")
    if a.get("left") is not None and a.get("right") is not None:
        parts.append(f"{int(a['left'])}x{int(a['right'])}")
    if a.get("nontyp"):
        parts.append("NonTyp")
    nick = clean(a.get("nick"))
    if nick:
        parts.append(nick)
    if int(a.get("count") or 1) > 1:
        parts.append(f"x{int(a['count'])}")
    return "-".join(parts)


def group_order(settings):
    """Button rows in order. "" (Other) is not included; it always comes last."""
    groups = [g for g in settings.get("groups", []) if g]
    for sp in settings["species"]:
        if sp["group"] and sp["group"] not in groups:
            groups.append(sp["group"])
    return groups


def button_order(settings):
    """Every animal button in on-screen order: each group in turn, then Other."""
    groups = group_order(settings)
    out = []
    for g in groups + [""]:
        out += [sp for sp in settings["species"] if sp["group"] == g]
    return out


def sorted_animals(animals, settings=None):
    """Order of animals in a file name.
    Default: bucks (anything with antler points) first, then in the order clicked.
    Setting "buttons": the order of the animal buttons."""
    if settings and settings.get("animal_order") == "buttons":
        rank = {sp["token"]: i for i, sp in enumerate(button_order(settings))}
        return sorted(animals, key=lambda a: rank.get(a["token"], len(rank)))
    return sorted(animals, key=lambda a: 0 if a.get("points") else 1)


def build_name(rec, settings, seq=None):
    t = datetime.fromisoformat(rec["taken"])
    sep = settings["separator"]
    parts = []
    for b in settings["name_blocks"]:
        if b == "date":
            v = t.strftime(settings["date_format"])
        elif b == "time":
            v = t.strftime(settings["time_format"])
        elif b == "hilite":
            v = clean(settings["hilite_word"]) if rec.get("hilite") else ""
        elif b == "animals":
            v = "Empty" if rec.get("empty") else sep.join(animal_part(a) for a in sorted_animals(rec["animals"], settings))
        elif b == "camera":
            v = clean(rec["camera"])
        elif b == "original":
            v = clean(Path(rec["original"]).stem)
        else:
            v = ""
        if v:
            parts.append((b, v))
    if not parts:
        parts = [("x", "clip")]
    if seq:
        # number goes right after the time (or date, or the last block)
        idx = len(parts) - 1
        for want in ("time", "date"):
            hits = [i for i, (b, _) in enumerate(parts) if b == want]
            if hits:
                idx = hits[0]
                break
        b, v = parts[idx]
        parts[idx] = (b, f"{v}-{seq}")
    return sep.join(v for _, v in parts) + Path(rec["original"]).suffix.lower()


def seq_key(rec, settings):
    """Clips from the same camera in the same (displayed) minute get -1, -2, -3."""
    t = datetime.fromisoformat(rec["taken"])
    return (rec["camera"], t.strftime(settings["date_format"] + "|" + settings["time_format"]))


# -------------------------------------------------------------------- store
class Store:
    """Master record of tagged clips. File paths inside are relative to the Output folder."""

    def __init__(self, output_dir, data_path):
        self.output = Path(output_dir)
        self.path = Path(data_path)
        self.records = {}
        self.animals = {}  # nicknamed animal profiles: "Buck|Droptine" -> {status, date, by, notes}
        self._backed_up = False
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.records = data.get("clips", {})
            self.animals = data.get("animals", {})

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists() and not self._backed_up:
            shutil.copy2(self.path, self.path.with_suffix(".json.bak"))
            self._backed_up = True
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"version": 1, "clips": self.records, "animals": self.animals}, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)

    def abspath(self, rec):
        return self.output / rec["file"]

    def items(self, camera=None):
        """Group records into items (bursts together), newest first."""
        groups = {}
        for r in self.records.values():
            if r.get("deleted") or (camera and r["camera"] != camera):
                continue
            groups.setdefault(r.get("group") or r["id"], []).append(r)
        items = [sorted(g, key=lambda r: (r["taken"], r["original"])) for g in groups.values()]
        items.sort(key=lambda g: g[0]["taken"], reverse=True)
        return items

    def cameras(self):
        return sorted({r["camera"] for r in self.records.values() if not r.get("deleted")}, key=str.lower)

    def dup_index(self):
        return {(r["camera"], r["original"].upper(), r["taken"], r.get("size")): r
                for r in self.records.values()}


def sync_names(store, settings, cameras=None):
    """Rename files so they match their tags. Returns list of error strings."""
    errors = []
    recs = [r for r in store.records.values() if cameras is None or r["camera"] in cameras]
    # back-to-back numbering
    groups = {}
    for r in recs:
        groups.setdefault(seq_key(r, settings), []).append(r)
    desired = {}
    for g in groups.values():
        g.sort(key=lambda r: (r["taken"], r["original"], r["id"]))
        for i, r in enumerate(g):
            seq = i + 1 if len(g) > 1 else None
            sub = Path(r["camera"])
            if r.get("empty"):
                sub = sub / EMPTY_DIR
            desired[r["id"]] = (sub / build_name(r, settings, seq)).as_posix()
    # make full names unique (in case blocks were chosen that allow duplicates)
    seen = {}
    for rid in sorted(desired, key=lambda i: desired[i]):
        d = desired[rid]
        if d.lower() in seen:
            p = Path(d)
            n = 2
            while (p.parent / f"{p.stem}-{n}{p.suffix}").as_posix().lower() in seen:
                n += 1
            d = (p.parent / f"{p.stem}-{n}{p.suffix}").as_posix()
            desired[rid] = d
        seen[d.lower()] = rid

    todo = [r for r in recs if r["file"] != desired[r["id"]] and store.abspath(r).exists()]
    # phase 1: move to temporary names (avoids clashes when names swap)
    staged = []
    for r in todo:
        src = store.abspath(r)
        tmp = src.with_name(f"{TEMP_PREFIX}{r['id']}{src.suffix}")
        try:
            retry(os.replace, src, tmp)
            staged.append((r, tmp))
        except OSError as e:
            errors.append(f"{r['file']}: {e}")
    # phase 2: final names
    for r, tmp in staged:
        dest = store.output / desired[r["id"]]
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():  # a file we don't track is in the way
                dest = unique_path(dest)
            move(tmp, dest)
            r["file"] = dest.relative_to(store.output).as_posix()
        except OSError as e:
            errors.append(f"{r['file']}: {e}")
            try:
                retry(os.replace, tmp, store.abspath(r))
            except OSError:
                r["file"] = tmp.relative_to(store.output).as_posix()
    store.save()
    return errors


def tag_files(store, settings, camera, files, tags):
    """Move raw files into Output and record their tags. Returns new record ids."""
    group = new_id() if len(files) > 1 else None
    ids = []
    out_dir = store.output / camera
    for f in files:
        f = Path(f)
        rid = new_id()
        rec = {
            "id": rid,
            "camera": camera,
            "taken": taken_time(f).isoformat(),
            "kind": "photo" if is_photo(f) else "video",
            "original": f.name,
            "size": f.stat().st_size,
            "group": group,
            "tagged_at": datetime.now().replace(microsecond=0).isoformat(),
        }
        rec.update(copy.deepcopy(tags))
        out_dir.mkdir(parents=True, exist_ok=True)
        tmp = out_dir / f"{TEMP_PREFIX}{rid}{f.suffix.lower()}"
        move(f, tmp)
        rec["file"] = tmp.relative_to(store.output).as_posix()
        store.records[rid] = rec
        ids.append(rid)
    store.save()
    return ids, sync_names(store, settings, [camera])


def update_tags(store, settings, ids, tags):
    for rid in ids:
        store.records[rid].update(copy.deepcopy(tags))
        store.records[rid]["edited_at"] = datetime.now().replace(microsecond=0).isoformat()
    cams = {store.records[i]["camera"] for i in ids}
    return sync_names(store, settings, cams)


def send_back(store, settings, raw_dir, ids):
    """Untag: move files back to Raw/<camera>/ with their original names."""
    moved, errors = [], []
    cams = set()
    for rid in ids:
        r = store.records[rid]
        src = store.abspath(r)
        dest = unique_path(Path(raw_dir) / r["camera"] / r["original"])
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if src.exists():
                move(src, dest)
                moved.append(dest)
            del store.records[rid]
            cams.add(r["camera"])
        except OSError as e:
            errors.append(f"{r['file']}: {e}")
    errors += sync_names(store, settings, cams)
    return moved, errors


def rename_token(store, settings, old, new):
    """An animal's file-name word changed (e.g. Groundhog -> Woodchuck): update tagged clips."""
    hit = set()
    for r in store.records.values():
        for a in r.get("animals", []):
            if a["token"] == old:
                a["token"] = new
                hit.add(r["camera"])
    for key in list(store.animals):
        tok, nick = key.split("|", 1)
        if tok == old:
            store.animals[animal_key(new, nick)] = store.animals.pop(key)
    if old in settings["nicknames"]:
        settings["nicknames"].setdefault(new, [])
        settings["nicknames"][new] = sorted(set(settings["nicknames"][new]) | set(settings["nicknames"].pop(old)),
                                            key=str.lower)
    store.save()
    return sync_names(store, settings, hit) if hit else []


def token_in_use(store, token):
    return sum(1 for r in store.records.values() for a in r.get("animals", []) if a["token"] == token)


def rename_nickname(store, settings, old, new, token=None):
    old_c, new_c = clean(old).lower(), clean(new)
    hit = set()
    for r in store.records.values():
        for a in r.get("animals", []):
            if clean(a.get("nick")).lower() == old_c and (token is None or a["token"] == token):
                a["nick"] = new_c
                hit.add(r["camera"])
    errors = sync_names(store, settings, hit) if hit else []
    for key in list(store.animals):
        tok, nick = key.split("|", 1)
        if nick.lower() == old_c and (token is None or tok == token) and new_c:
            prof = store.animals.pop(key)
            new_key = animal_key(tok, new_c)
            if not any(store.animals.get(new_key, {}).values()):  # merging: keep existing status if set
                store.animals[new_key] = prof
    store.save()
    for tok, names in settings["nicknames"].items():
        if token is None or tok == token:
            names[:] = sorted({new_c if n.lower() == old_c else n for n in names} - {""}, key=str.lower)
    return sum(1 for r in store.records.values() for a in r.get("animals", [])
               if clean(a.get("nick")) == new_c and new_c), errors


# ------------------------------------------------------------------ animals
STATUSES = ["Active", "Harvested", "Found dead", "Presumed gone"]


def animal_key(token, nick):
    return f"{token}|{nick}"


def rack_text(a):
    if a.get("button"):
        return "Button"
    if a.get("unk_pts"):
        return "Unknown"
    if not a.get("total"):
        return ""
    t = f"{int(a['total'])}pt"
    if a.get("left") is not None and a.get("right") is not None:
        t += f" {a['left']}x{a['right']}"
    if a.get("nontyp"):
        t += " NonTyp"
    return t


def animal_stats(store):
    """Summary of every nicknamed animal, from all clips (deleted ones count as history)."""
    out = {}
    for r in sorted(store.records.values(), key=lambda r: r["taken"]):
        seen_here = set()
        for a in r.get("animals", []):
            nick = clean(a.get("nick"))
            if not nick:
                continue
            key = animal_key(a["token"], nick)
            st = out.setdefault(key, {"token": a["token"], "nick": nick, "first": r["taken"], "clips": 0,
                                      "deleted": 0, "cameras": set(), "rack": "", "max_pts": 0,
                                      "points": bool(a.get("points"))})
            st["last"] = r["taken"]
            st["cameras"].add(r["camera"])
            if key not in seen_here and not (r.get("group") and r["group"] in st.setdefault("_groups", set())):
                st["clips"] += 1
                st["deleted"] += 1 if r.get("deleted") else 0
                if r.get("group"):
                    st["_groups"].add(r["group"])
            seen_here.add(key)
            if a.get("button") and not st["rack"]:
                st["rack"] = "Button"  # until a real rack is recorded
            if a.get("total") and not a.get("unk_pts") and not a.get("button"):
                st["rack"] = rack_text(a)
                st["max_pts"] = max(st["max_pts"], int(a["total"]))
    for key in store.animals:  # profiles whose clips were all forgotten
        if key not in out:
            tok, nick = key.split("|", 1)
            out[key] = {"token": tok, "nick": nick, "first": "", "last": "", "clips": 0, "deleted": 0,
                        "cameras": set(), "rack": "", "max_pts": 0, "points": False}
    for key, st in out.items():
        st.pop("_groups", None)
        prof = store.animals.get(key, {})
        st["status"] = prof.get("status") or "Active"
        st.update({k: prof.get(k, "") for k in ("date", "by", "notes")})
    return out


def known_rack(store, token, nick, taken, exclude_ids=()):
    """Rack of a nicknamed animal from its clip closest in date to `taken` (ISO time).
    Returns (fields, date) or None. Clips with unknown points are skipped."""
    nick = clean(nick).lower()
    if not nick:
        return None
    t0 = datetime.fromisoformat(taken)
    best = None
    for r in store.records.values():
        if r["id"] in exclude_ids:
            continue
        for a in r.get("animals", []):
            if a["token"] != token or clean(a.get("nick")).lower() != nick:
                continue
            if not (a.get("total") or a.get("button")) or a.get("unk_pts"):
                continue
            gap = abs((datetime.fromisoformat(r["taken"]) - t0).total_seconds())
            if best is None or gap < best[0]:
                best = (gap, a, r["taken"][:10])
    if not best:
        return None
    a = best[1]
    fields = {k: a.get(k) for k in ("total", "left", "right", "nontyp", "button")}
    return fields, best[2]


def harvest_warning(store, tags, taken):
    """Warn when a clip is tagged with an animal already marked harvested/dead before that date."""
    msgs = []
    for a in tags.get("animals", []):
        prof = store.animals.get(animal_key(a["token"], clean(a.get("nick"))), {})
        if prof.get("status") in ("Harvested", "Found dead") and prof.get("date") and taken[:10] > prof["date"]:
            msgs.append(f"{a.get('nick')} was marked {prof['status'].lower()} on {prof['date']}")
    return msgs


def check_log(store):
    """Find tracked clips whose file is missing, and media files nobody tracks."""
    live = [r for r in store.records.values() if not r.get("deleted")]
    missing = [r for r in live if not store.abspath(r).exists()]
    tracked = {store.abspath(r).resolve() for r in live}
    untracked = [p for p in output_media(store.output) if p.resolve() not in tracked]
    return missing, untracked


def output_media(output):
    out = []
    for dirpath, _dirnames, filenames in os.walk(output):
        for n in filenames:
            if Path(n).suffix.lower() in MEDIA_EXT:
                out.append(Path(dirpath) / n)
    return out


def reconcile(store):
    """Catch up with changes made in File Explorer.

    - file deleted          -> record marked deleted (kept for history)
    - file restored          -> record un-deleted
    - file renamed / moved   -> record follows it (matched by camera, size and time taken)
    Returns (deleted, reconnected, restored, cameras_reconnected).
    """
    deleted = reconnected = restored = 0
    cams = set()  # cameras whose file names need fixing
    missing = []
    for r in store.records.values():
        exists = store.abspath(r).exists()
        if r.get("deleted") and exists:
            r.pop("deleted")
            restored += 1
        elif not r.get("deleted") and not exists:
            missing.append(r)
    def norm(p):  # fast on network drives
        return os.path.normcase(os.path.abspath(p))

    missing_ids = {r["id"] for r in missing}
    tracked = {norm(store.abspath(r)) for r in store.records.values()
               if not r.get("deleted") and r["id"] not in missing_ids}
    untracked = [p for p in output_media(store.output)
                 if not p.name.startswith(TEMP_PREFIX) and norm(p) not in tracked]
    lost = missing + [r for r in store.records.values() if r.get("deleted")]
    if untracked and lost:
        # match renamed/moved files by camera folder + size + type + time taken
        cand = {}
        for p in untracked:
            rel = p.relative_to(store.output).parts
            try:
                key = (rel[0] if len(rel) > 1 else "", p.stat().st_size, p.suffix.lower(),
                       taken_time(p).isoformat())
            except OSError:
                continue
            cand.setdefault(key, []).append(p)
        need = {}
        for r in lost:
            key = (r["camera"], r.get("size"), Path(r["original"]).suffix.lower(), r["taken"])
            need.setdefault(key, []).append(r)
        for key, recs in need.items():
            found = cand.get(key, [])
            if len(recs) == 1 and len(found) == 1:
                r = recs[0]
                r["file"] = found[0].relative_to(store.output).as_posix()
                if r.get("deleted"):
                    r.pop("deleted")
                    restored += 1
                else:
                    reconnected += 1
                    missing.remove(r)
                cams.add(r["camera"])
    today = datetime.now().strftime("%Y-%m-%d")
    for r in missing:
        r["deleted"] = today
        deleted += 1
    if deleted or reconnected or restored:
        store.save()
    return deleted, reconnected, restored, cams


def forget_deleted(store):
    gone = [rid for rid, r in store.records.items() if r.get("deleted")]
    for rid in gone:
        del store.records[rid]
    if gone:
        store.save()
    return len(gone)


# ---------------------------------------------------------------------- raw
def raw_cameras(raw_dir):
    raw_dir = Path(raw_dir)
    if not raw_dir.is_dir():
        return []
    return sorted([p.name for p in raw_dir.iterdir() if p.is_dir() and not p.name.startswith(("_", "."))],
                  key=str.lower)


def raw_files(cam_dir):
    cam_dir = Path(cam_dir)
    if not cam_dir.is_dir():
        return []
    return [p for p in cam_dir.iterdir() if p.is_file() and p.suffix.lower() in MEDIA_EXT
            and not p.name.startswith(".")]


def scan_raw(cam_dir, burst_seconds):
    """Return items in time order. An item is one video, one photo, or a photo burst."""
    entries = sorted(((taken_time(p), p) for p in raw_files(cam_dir)), key=lambda e: (e[0], e[1].name))
    items = []
    for t, p in entries:
        last = items[-1] if items else None
        if (last and is_photo(p) and last["kind"] == "photo"
                and (t - last["times"][-1]).total_seconds() <= burst_seconds):
            last["files"].append(p)
            last["times"].append(t)
        else:
            items.append({"files": [p], "times": [t], "kind": "photo" if is_photo(p) else "video"})
    return items


# -------------------------------------------------------------------- excel
XLSX_COLS = [("Date", 11), ("Time", 9), ("Camera", 10), ("Type", 7), ("Hilite", 7), ("Animal", 17),
             ("Count", 7), ("Total Pts", 9), ("Left", 6), ("Right", 6), ("NonTyp", 8), ("Details", 24),
             ("Nickname", 14), ("Animal Status", 13), ("Notes", 30), ("File", 60), ("Original File", 15), ("Burst", 8),
             ("Tagged", 17), ("Deleted", 11)]


def export_xlsx(store, path, settings=None):
    """Write the spreadsheet. Raises PermissionError if it's open in Excel."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    path = Path(path)
    wb = Workbook()
    ws = wb.active
    ws.title = "Clips"
    ws.append([c for c, _ in XLSX_COLS])
    for i, (_, w) in enumerate(XLSX_COLS, 1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = w
        ws.cell(1, i).font = Font(bold=True, color="FFFFFF")
        ws.cell(1, i).fill = PatternFill("solid", fgColor="2F5233")
    file_col = [c for c, _ in XLSX_COLS].index("File") + 1
    hl_fill = PatternFill("solid", fgColor="FFF2CC")
    stats = animal_stats(store)

    def status_of(a):
        nick = clean(a.get("nick"))
        return stats.get(animal_key(a["token"], nick), {}).get("status", "") if nick else ""
    recs = sorted(store.records.values(), key=lambda r: (r["taken"], r["camera"], r["file"]))
    for r in recs:
        t = datetime.fromisoformat(r["taken"])
        base = [t.date(), t.strftime("%H:%M:%S"), r["camera"], r["kind"].title(), "Yes" if r.get("hilite") else ""]
        tail = [r.get("notes", ""), r["file"], r["original"], "Yes" if r.get("group") else "",
                r.get("edited_at") or r.get("tagged_at", ""), r.get("deleted", "")]
        animals = sorted_animals(r.get("animals", []), settings) if not r.get("empty") else []
        rows = [[a["token"], int(a.get("count") or 1), "Button" if a.get("button") else "Unknown" if a.get("unk_pts") else (a.get("total") or None), a.get("left"), a.get("right"),
                 "Yes" if a.get("nontyp") else "", ", ".join(a.get("desc", [])), a.get("nick", ""),
                 status_of(a)]
                for a in animals] or [["Empty", 0, None, None, None, "", "", "", ""]]
        for row in rows:
            ws.append(base + row + tail)
            n = ws.max_row
            ws.cell(n, 1).number_format = "yyyy-mm-dd"
            c = ws.cell(n, file_col)
            if r.get("deleted"):
                for i in range(1, len(XLSX_COLS) + 1):
                    ws.cell(n, i).font = Font(color="999999", italic=True)
                continue
            c.hyperlink = os.path.relpath(store.abspath(r), path.parent).replace(os.sep, "/")
            c.font = Font(color="0563C1", underline="single")
            if r.get("hilite"):
                for i in range(1, len(XLSX_COLS) + 1):
                    ws.cell(n, i).fill = hl_fill
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    # ---- Animals sheet
    wa = wb.create_sheet("Animals")
    cols = [("Species", 14), ("Nickname", 16), ("Status", 13), ("Status Date", 12), ("By", 14), ("Notes", 36),
            ("First Seen", 12), ("Last Seen", 12), ("Clips", 7), ("Cameras", 20), ("Latest Rack", 16),
            ("Most Pts", 9)]
    wa.append([c for c, _ in cols])
    for i, (_, w) in enumerate(cols, 1):
        wa.column_dimensions[wa.cell(1, i).column_letter].width = w
        wa.cell(1, i).font = Font(bold=True, color="FFFFFF")
        wa.cell(1, i).fill = PatternFill("solid", fgColor="2F5233")
    gone_fill = PatternFill("solid", fgColor="E7E6E6")
    for st in sorted(stats.values(), key=lambda x: (x["token"], x["nick"].lower())):
        wa.append([st["token"], st["nick"], st["status"], st["date"], st["by"], st["notes"],
                   st["first"][:10], (st.get("last") or "")[:10], st["clips"], ", ".join(sorted(st["cameras"])),
                   st["rack"], st["max_pts"] or None])
        if st["status"] != "Active":
            for i in range(1, len(cols) + 1):
                wa.cell(wa.max_row, i).fill = gone_fill
    wa.freeze_panes = "A2"
    wa.auto_filter.ref = wa.dimensions
    tmp = path.with_name("~tmp_" + path.name)
    wb.save(tmp)
    try:
        os.replace(tmp, path)
    except PermissionError:
        tmp.unlink(missing_ok=True)
        raise


# ----------------------------------------------------------------- settings
def load_settings(path):
    s = copy.deepcopy(DEFAULT_SETTINGS)
    try:
        s.update(json.loads(Path(path).read_text(encoding="utf-8")))
    except Exception:
        pass
    return s


def save_settings(path, settings):
    Path(path).write_text(json.dumps(settings, indent=2), encoding="utf-8")
