"""
ComfyUI-RotoTools - Load Video Batch (Folders).

Point it at one or more folders (comma separated, e.g. x\\ep93, x\\ep94); it finds every video in their
sub-folders, sorts them, and hands ONE video per run to the rest of the workflow.  Set the index widget to
"increment" and Run's batch count to the number of videos: ComfyUI queues them one after another.

Each input folder gets its own output folder named after it (output\\ep93, output\\ep94; another folder
with the same name gets its location added: y\\ep93 -> ep93 (y), and keeps that name from run to run),
and every zip is named after its video file (shot5.mp4 -> shot5.zip),
so the same shot names in different episodes never clash.

The node also shows a preview grid of every detected video (hover = play, click = full view), served by
the small /rototools/batch/* routes at the bottom of this file.
"""
import asyncio
import hashlib
import os
import re

import folder_paths

DEFAULT_EXTS = "mp4,mov,mkv,avi,webm,m4v"


def _natural_key(text):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", text)]


def _clean(name):
    name = "".join(c if (c.isalnum() or c in " ._-()[]") else "_" for c in str(name)).strip(" .")
    return name or "video"


def _abs(path):
    return os.path.normpath(os.path.abspath(os.path.expandvars(os.path.expanduser((path or "").strip().strip('"')))))


def split_folders(text):
    """'x\\ep93, x\\ep94' (or one per line, or Explorer's "Copy as path" list, even with the line breaks
    squashed: "x\\ep93""x\\ep94") -> list of absolute paths, duplicates dropped, order kept."""
    out, seen = [], set()
    for quoted, plain in re.findall(r'"([^"]*)"|([^",\r\n]+)', text or ""):
        part = (quoted or plain).strip()
        if not part:
            continue
        p = _abs(part)
        if os.path.normcase(p) not in seen:
            seen.add(os.path.normcase(p))
            out.append(p)
    return out


def scan_videos(root, extensions=DEFAULT_EXTS, recursive=True):
    """Sorted list of absolute video paths under root (natural sort, so clip2 comes before clip10)."""
    root = _abs(root)
    if not os.path.isdir(root):
        raise FileNotFoundError("Batch folder not found: %s" % root)
    exts = {"." + e.strip().lower().lstrip(".") for e in (extensions or DEFAULT_EXTS).split(",") if e.strip()}
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted((d for d in dirnames if not d.startswith(".")), key=_natural_key)
        for f in filenames:
            if os.path.splitext(f)[1].lower() in exts and not f.startswith("."):
                found.append(os.path.join(dirpath, f))
        if not recursive:
            break
    rel = lambda p: os.path.relpath(p, root)
    found.sort(key=lambda p: [_natural_key(part) for part in rel(p).split(os.sep)])
    return root, found


def _unique(name, used):
    """name, name_2, name_3 ... (case-insensitive, Windows file names do not care about case)."""
    cand, n = name, 1
    while cand.lower() in used:
        n += 1
        cand = "%s_%d" % (name, n)
    used.add(cand.lower())
    return cand


# Each output folder remembers which input folder it belongs to, so a name never moves to another folder:
# x\ep93 -> output\ep93 and y\ep93 -> output\ep93 (y), whether they are run together or on their own.
SOURCE_MARK = ".rototools_source"


def _owner(folder):
    """normcase'd input folder recorded in an output folder; '' = folder exists but has no record; None = no folder."""
    try:
        with open(os.path.join(folder, SOURCE_MARK), encoding="utf-8") as f:
            return os.path.normcase(f.readline().strip())
    except OSError:
        return "" if os.path.isdir(folder) else None


def claim_folder(folder, root):
    """Create the output folder and record its input folder (hidden file, best effort)."""
    os.makedirs(folder, exist_ok=True)
    mark = os.path.join(folder, SOURCE_MARK)
    if _owner(folder) == os.path.normcase(root):
        return
    try:
        with open(mark, "w", encoding="utf-8") as f:
            f.write(root + "\n")
        if os.name == "nt":
            import ctypes
            ctypes.windll.kernel32.SetFileAttributesW(mark, 0x2)  # FILE_ATTRIBUTE_HIDDEN
    except OSError as e:
        print("[LoadVideoBatchFolders] could not write %s: %s" % (mark, e))


def _label_candidates(root, base=None):
    """ep93, ep93 (y), ep93 (y) 2, ep93 (y) 3 ...  (y = the folder that holds ep93).
    base overrides the first part (a video's file name without extension)."""
    base = base or _clean(os.path.basename(root) or root.replace(":", ""))
    parent = os.path.dirname(root)
    where = _clean(os.path.basename(parent) or parent.replace(":", "").strip("\\/")) if parent != root else "root"
    yield base
    yield "%s (%s)" % (base, where)
    for n in range(2, 1000):
        yield "%s (%s) %d" % (base, where, n)


# Single videos (dropped on the node or listed as files) are saved straight into the output folder:
# output\clip.zip. A record there keeps each zip name with its video, like SOURCE_MARK does for folders.
SINGLES_MARK = ".rototools_singles.json"


def _singles_record(base):
    import json
    try:
        with open(os.path.join(base, SINGLES_MARK), encoding="utf-8") as f:
            return {k.lower(): v for k, v in json.load(f).items()}
    except (OSError, ValueError):
        return {}


def claim_single(base, name, path):
    """Record that <base>\\<name>.zip belongs to this video (hidden file, best effort)."""
    import json
    os.makedirs(base, exist_ok=True)
    rec = _singles_record(base)
    if os.path.normcase(rec.get(name.lower(), "")) == os.path.normcase(path):
        return
    rec[name.lower()] = path
    mark = os.path.join(base, SINGLES_MARK)
    try:
        if os.name == "nt" and os.path.exists(mark):
            import ctypes
            ctypes.windll.kernel32.SetFileAttributesW(mark, 0x80)  # hidden files cannot be opened for writing
        with open(mark, "w", encoding="utf-8") as f:
            json.dump(rec, f, indent=1, ensure_ascii=False)
        if os.name == "nt":
            import ctypes
            ctypes.windll.kernel32.SetFileAttributesW(mark, 0x2)  # FILE_ATTRIBUTE_HIDDEN
    except OSError as e:
        print("[LoadVideoBatchFolders] could not write %s: %s" % (mark, e))


def assign_single_names(paths, output_folder=""):
    """Zip name for each single video: clip, clip (misc), clip (misc) 2 ... (misc = the folder it sits in).
    Same rules as assign_labels: a recorded name is reused, a name recorded for another video is never taken."""
    base = zip_folder_for(output_folder, "")
    rec = {k: os.path.normcase(v) for k, v in _singles_record(base).items()}
    used, names = set(), []
    for p in paths:
        key = os.path.normcase(p)
        owners = {}
        for i, c in enumerate(_label_candidates(p, _clean(os.path.splitext(os.path.basename(p))[0]))):
            if c.lower() in used:
                continue
            o = rec.get(c.lower())
            owners[c] = o if o is not None else ("" if os.path.exists(os.path.join(base, c + ".zip")) else None)
            if owners[c] is None and i >= 1:
                break
        mine = [c for c, o in owners.items() if o == key]
        free = [c for c, o in owners.items() if o in (None, "")]
        name = (mine or free)[0]
        used.add(name.lower())
        names.append(name)
    return names


def assign_labels(roots, output_folder=""):
    """Output folder name for each input folder.

    The plain name (ep93) goes to the first input folder that may use it; another folder with the same name
    gets its location added (ep93 (y)). A name already recorded for a folder (SOURCE_MARK) is always reused,
    and a name recorded for a different folder is never taken, so the same input folder keeps its output
    folder from run to run. Output folders made before this record existed are taken as they are.
    """
    used, labels = set(), []
    for root in roots:
        key = os.path.normcase(root)
        cands = list(_label_candidates(root))
        owners = {}
        for i, c in enumerate(cands):
            if c.lower() in used:
                continue
            owners[c] = _owner(zip_folder_for(output_folder, c))
            if owners[c] is None and i >= 1:
                break   # ep93 (y) 2, 3 ... are made in order, so none after a missing one exists
        mine = [c for c, o in owners.items() if o == key]
        free = [c for c, o in owners.items() if o in (None, "")]
        label = (mine or free)[0]
        used.add(label.lower())
        labels.append(label)
    return labels


def scan_batch(folders_text, extensions=DEFAULT_EXTS, recursive=True, strict=True, output_folder=""):
    """Every video in every listed folder and every listed video file, in order.

    Returns (groups, items, errors):
      groups: [{"kind": "folder", "label": output folder name (see assign_labels), "root": abs path, "count": n}
               or {"kind": "files", "label": "" (= the output folder itself), "root": "", "count": n}]
              All single videos form one "files" group, placed where the first of them is listed.
      items:  [{"path", "rel", "group" (index into groups), "name" (zip name, unique inside its group)}]
    strict=True raises on a missing folder or file; False collects the message in errors instead.
    """
    exts = {"." + e.strip().lower().lstrip(".") for e in (extensions or DEFAULT_EXTS).split(",") if e.strip()}
    groups, items, errors = [], [], []
    found, singles = [], []   # found: (root, vids) per folder, or None where the single videos go
    for entry in split_folders(folders_text):
        try:
            if os.path.isfile(entry):
                if os.path.splitext(entry)[1].lower() not in exts:
                    raise FileNotFoundError("Not a video (%s): %s" % (extensions, entry))
                if not singles:
                    found.append(None)
                singles.append(entry)
            else:
                found.append(scan_videos(entry, extensions, recursive))
        except FileNotFoundError as e:
            if strict:
                raise
            errors.append(str(e))
    labels = iter(assign_labels([f[0] for f in found if f], output_folder))
    for f in found:
        g = len(groups)
        if f is None:
            groups.append({"kind": "files", "label": "", "root": "", "count": len(singles)})
            for p, name in zip(singles, assign_single_names(singles, output_folder)):
                items.append({"path": p, "rel": os.path.basename(p), "group": g, "name": name})
            continue
        root, vids = f
        groups.append({"kind": "folder", "label": next(labels), "root": root, "count": len(vids)})
        names = set()
        for p in vids:
            items.append({"path": p, "rel": os.path.relpath(p, root), "group": g,
                          "name": _unique(_clean(os.path.splitext(os.path.basename(p))[0]), names)})
    return groups, items, errors


def zip_folder_for(output_folder, label):
    """<output_folder>\\<label> (label "" = the output folder itself);
    empty output_folder = ComfyUI output\\roto_tga (the saver's default)."""
    base = (output_folder or "").strip().strip('"')
    base = _abs(base) if base else os.path.join(os.path.abspath(folder_paths.get_output_directory()), "roto_tga")
    return os.path.join(base, label) if label else base


def _make_video(path):
    try:
        from comfy_api.latest import InputImpl
        return InputImpl.VideoFromFile(path)
    except Exception:
        from comfy_api.input_impl import VideoFromFile
        return VideoFromFile(path)


def _blocker():
    try:
        from comfy_execution.graph_utils import ExecutionBlocker
        return ExecutionBlocker
    except Exception:
        return None


class LoadVideoBatchFolders:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "batch_folder": ("STRING", {"default": "", "multiline": True,
                                            "tooltip": "Folders and/or single video files, one per line or comma "
                                                       "separated (x\\ep93, x\\ep94, D:\\clips\\a.mp4). Use 'Add folders' "
                                                       "on the preview, drop videos onto the node, or paste Explorer's "
                                                       "Copy as path (Ctrl+Shift+C). Every video inside the folders and "
                                                       "their sub-folders is found automatically."}),
                "index": ("INT", {"default": 0, "min": 0, "max": 999999, "control_after_generate": "increment",
                                  "tooltip": "Only used when skip_if_zip_exists is off: which video to load (0 = first). "
                                             "With skip_if_zip_exists on (default), every run simply takes the next video "
                                             "that has no zip yet."}),
                "skip_if_zip_exists": ("BOOLEAN", {"default": True,
                                                   "tooltip": "On (default): every run takes the next video that has no zip "
                                                              "yet; done and excluded videos are passed over. "
                                                              "Off: the video at 'index' is processed even if its zip exists."}),
                "output_folder": ("STRING", {"default": "", "tooltip": "Where everything is saved. A folder named after each "
                                                                       "input folder is made inside it (output\\ep93\\shot5.zip). "
                                                                       "Connect zip_folder to the TGA saver's output_folder."}),
                "extensions": ("STRING", {"default": DEFAULT_EXTS, "tooltip": "Comma separated video extensions."}),
                "recursive": ("BOOLEAN", {"default": True, "tooltip": "Look inside sub-folders of sub-folders too."}),
            },
            "optional": {
                # filled by the preview's x / undo buttons and saved with the workflow; hidden on the node
                "excluded": ("STRING", {"default": "", "tooltip": "Videos left out of the batch, one path per line."}),
            },
            "hidden": {"unique_id": "UNIQUE_ID"},
        }

    RETURN_TYPES = ("VIDEO", "STRING", "STRING", "INT", "INT", "STRING")
    RETURN_NAMES = ("video", "zip_name", "video_path", "index", "total", "zip_folder")
    OUTPUT_TOOLTIPS = ("The video for this run.", "Video file name without extension (shot5).",
                       "Full path of the video.", "Index of this video (0 = first).", "Number of videos found.",
                       "Output folder for this video's input folder (output\\ep93). Connect to the saver's output_folder.")
    FUNCTION = "load"
    CATEGORY = "image/video"
    DESCRIPTION = "Loads one video per run from one or more folders of folders, for queueing hundreds of clips in one go."

    @classmethod
    def IS_CHANGED(cls, **kw):
        return float("nan")   # which video comes next depends on the zips on disk, so always run

    def load(self, batch_folder, index, skip_if_zip_exists, output_folder, extensions, recursive, excluded="",
             unique_id=None):
        groups, items, _ = scan_batch(batch_folder, extensions, recursive, output_folder=output_folder)
        _remember(items)
        total = len(items)
        if total == 0:
            if not split_folders(batch_folder):
                raise ValueError("The batch list is empty: add folders or drop videos onto the Load Video Batch node.")
            raise ValueError("No videos (%s) found under %s" % (extensions, ", ".join(split_folders(batch_folder))))
        blocker = _blocker()
        out_of = excluded_keys(excluded)

        # the status goes to the node's preview bar (ui message), not ComfyUI's large progress-text box
        def skip(msg, k=index):
            log(msg)
            if blocker is None:
                raise RuntimeError(msg)
            b = blocker(None)
            return {"ui": {"rototools_index": [k], "rototools_status": [msg]}, "result": (b, b, b, b, b, b)}

        if skip_if_zip_exists:
            k, counts = next_without_zip(groups, items, output_folder, out_of)
            if k is None:
                return skip("nothing left to do: all %d videos are done or left out (%s)" % (total, counts["text"]),
                            total)
        else:   # index mode: the video at `index`, even if its zip exists (to redo it)
            k, counts = index, None
            if k >= total:
                return skip("index %d is past the last video (%d videos). Nothing to do." % (k, total))
            if os.path.normcase(items[k]["path"]) in out_of:
                return skip("%d/%d is excluded: %s" % (k + 1, total, items[k]["rel"]))
        index = k
        it = items[index]
        group = groups[it["group"]]
        label = group["label"]
        zfolder = zip_folder_for(output_folder, label)
        if group["kind"] == "folder":
            claim_folder(zfolder, group["root"])          # this name now belongs to this input folder
        else:
            claim_single(zfolder, it["name"], it["path"])  # and this zip name to this video
        where = label or "single video"
        msg = "%d / %d   %s \\ %s" % (index + 1, total, where, it["rel"])
        log("run: %s   (%s)" % (msg, "next without a zip: " + counts["text"] if counts else "index mode"))
        return {"ui": {"rototools_index": [index], "rototools_status": [msg]},
                "result": (_make_video(it["path"]), it["name"], it["path"], index, total, zfolder)}


# ---------------------------------------------------------------- picking the next video
# Each run takes the first video that has no zip yet. A video that was started but still has no zip when the
# next run comes (that run failed or was cancelled) is tried once more; after a second try it is passed over
# until ComfyUI restarts or the list is cleared, so one broken video cannot use up the whole queue.
_STARTS = {}          # normcase'd path -> times this video was started in this session
_SKIP_LOGGED = set()  # broken videos already reported in the log


def log(msg):
    print("[LoadVideoBatchFolders] " + msg)


def excluded_keys(text):
    return {os.path.normcase(_abs(line)) for line in (text or "").splitlines() if line.strip()}


def reset_attempts():
    _STARTS.clear()
    _SKIP_LOGGED.clear()


def next_without_zip(groups, items, output_folder, out_of=()):
    """(index of the next video to process or None, counts). Records that the chosen video was started."""
    done = excl = broken = left = 0
    pick = None
    folders = {}
    for k, it in enumerate(items):
        key = os.path.normcase(it["path"])
        if key in out_of:
            excl += 1
            continue
        g = it["group"]
        if g not in folders:
            folders[g] = zip_folder_for(output_folder, groups[g]["label"])
        if os.path.exists(os.path.join(folders[g], it["name"] + ".zip")):
            done += 1
            _STARTS.pop(key, None)
            continue
        if _STARTS.get(key, 0) >= 2:
            broken += 1
            if key not in _SKIP_LOGGED:
                _SKIP_LOGGED.add(key)
                log("%s failed twice (still no zip): passing over it. It is tried again after a ComfyUI restart "
                    "or Clear on the node." % it["path"])
            continue
        left += 1
        if pick is None:
            pick = k
    text = "%d left, %d done, %d excluded%s" % (left, done, excl, ", %d failed twice" % broken if broken else "")
    if pick is not None:
        key = os.path.normcase(items[pick]["path"])
        if _STARTS.get(key):
            log("retrying %s: the previous run of it left no zip (failed or cancelled)" % items[pick]["path"])
        _STARTS[key] = _STARTS.get(key, 0) + 1
    return pick, {"done": done, "excluded": excl, "broken": broken, "left": left, "text": text}



NODE_CLASS_MAPPINGS = {"LoadVideoBatchFolders": LoadVideoBatchFolders}
NODE_DISPLAY_NAME_MAPPINGS = {"LoadVideoBatchFolders": "Load Video Batch (Folders)"}


# ---------------------------------------------------------------- preview grid backend
# Only files found by a scan can be served, so these routes cannot be used to read anything else on disk.
_ALLOWED = set()
_THUMB_LOCK = None


def _remember(items):
    _ALLOWED.update(os.path.normcase(it["path"]) for it in items)


def _allowed(path):
    return bool(path) and os.path.normcase(_abs(path)) in _ALLOWED and os.path.isfile(path)


def scan_report(folders_text, extensions, recursive, output_folder):
    """JSON for the preview grid: groups (with full path and output folder), items with a done flag."""
    groups, items, errors = scan_batch(folders_text, extensions, recursive, strict=False, output_folder=output_folder)
    _remember(items)
    for g in groups:
        g["out"] = zip_folder_for(output_folder, g["label"])
    rows = []
    for i, it in enumerate(items):
        out = groups[it["group"]]["out"]
        rows.append({"i": i, "group": it["group"], "rel": it["rel"], "name": it["name"], "path": it["path"],
                     "key": os.path.normcase(it["path"]),
                     "done": os.path.exists(os.path.join(out, it["name"] + ".zip"))})
    folders = [{"path": p, "key": os.path.normcase(p)} for p in split_folders(folders_text)]
    for g in groups:
        g["key"] = os.path.normcase(g["root"])
    return {"total": len(rows), "groups": groups, "items": rows, "errors": errors, "folders": folders}


def merge_folders(current, added):
    """The batch_folder text after adding folders: one per line, nothing listed twice."""
    return "\n".join(split_folders("\n".join([current or ""] + ['"%s"' % a for a in added])))


# ---------------------------------------------------------------- dropped videos
# A browser never tells a page where a dropped file lives, so dropped videos are uploaded (copied) into
# ComfyUI's input folder, like the normal Load Video does, and listed by their copy's path.
DROPS_SUBFOLDER = "rototools_drops"


def _same_file(a, b):
    if os.path.getsize(a) != os.path.getsize(b):
        return False
    with open(a, "rb") as fa, open(b, "rb") as fb:
        while True:
            x, y = fa.read(1 << 20), fb.read(1 << 20)
            if x != y:
                return False
            if not x:
                return True


def place_drop(tmp, filename, drops_dir):
    """Move an uploaded temp file to drops_dir\\<filename>, keeping the file name (it becomes the zip name).
    The same video dropped again reuses its copy; a different video with the same name goes to
    drops_dir\\2\\<filename>, 3\\ ... Returns the final path."""
    n = 1
    while True:
        folder = drops_dir if n == 1 else os.path.join(drops_dir, str(n))
        dest = os.path.join(folder, filename)
        if not os.path.exists(dest):
            os.makedirs(folder, exist_ok=True)
            os.replace(tmp, dest)
            return dest
        if _same_file(tmp, dest):
            os.remove(tmp)
            return dest
        n += 1


# ---------------------------------------------------------------- native folder picker
# Opens the system's own folder dialog on the machine running ComfyUI (several folders at once).
_PICKER_PS1 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pick_folders.ps1")


def picker_command(start=""):
    """argv for the folder dialog of this OS, or None if there is none."""
    import shutil
    import sys
    if sys.platform == "win32":
        ps = shutil.which("powershell") or shutil.which("pwsh")
        if ps:
            return [ps, "-NoProfile", "-NonInteractive", "-STA", "-ExecutionPolicy", "Bypass",
                    "-File", _PICKER_PS1, "-Start", start or ""]
    elif sys.platform == "darwin":
        return ["osascript", "-e", 'set fs to choose folder with prompt "Add video folders" with multiple selections allowed',
                "-e", 'set out to ""', "-e", "repeat with f in fs", "-e", "set out to out & POSIX path of f & linefeed",
                "-e", "end repeat", "-e", "return out"]
    for tool, args in (("zenity", ["--file-selection", "--directory", "--multiple", "--separator=\n",
                                   "--title=Add video folders"] + (["--filename=" + start + os.sep] if start else [])),
                       ("kdialog", ["--multiple", "--separate-output", "--getexistingdirectory", start or "~"])):
        exe = shutil.which(tool)
        if exe:
            return [exe] + args
    return None


def parse_picker_output(text):
    """Folder paths printed by the dialog, one per line; only folders that exist."""
    out = []
    for line in (text or "").splitlines():
        p = line.strip().strip('"')
        if p and os.path.isdir(p):
            out.append(os.path.normpath(p.rstrip("/\\") or p))
    return out


_INFO = {}   # (path, mtime, size) -> video_info result


def video_info(path):
    """{"frames", "seconds", "fps", "exact"} of a video, read from its header only (fast, no decoding).
    exact is False when the file has no frame count and frames is worked out from duration x fps."""
    st = os.stat(path)
    key = (path, st.st_mtime, st.st_size)
    if key in _INFO:
        return _INFO[key]
    import av
    with av.open(path) as c:
        s = c.streams.video[0]
        fps = float(s.average_rate or s.guessed_rate or 0)
        if s.duration and s.time_base:
            seconds = float(s.duration * s.time_base)
        else:
            seconds = float(c.duration or 0) / 1000000.0   # container duration is in microseconds
        frames, exact = int(s.frames or 0), True
        if frames <= 0 and fps and seconds:
            frames, exact = int(round(seconds * fps)), False
    info = {"frames": frames, "seconds": round(seconds, 2), "fps": round(fps, 3), "exact": exact}
    _INFO[key] = info
    return info


def make_thumb(path, size=320):
    """JPEG bytes of the first frame (cached in ComfyUI's temp folder)."""
    st = os.stat(path)
    key = hashlib.sha1(("%s|%s|%s|%s" % (path, st.st_mtime, st.st_size, size)).encode("utf-8")).hexdigest()
    cache = os.path.join(folder_paths.get_temp_directory(), "rototools_thumbs")
    out = os.path.join(cache, key + ".jpg")
    if os.path.exists(out):
        with open(out, "rb") as f:
            return f.read()
    import io
    import av
    with av.open(path) as c:
        frame = next(c.decode(video=0))
        img = frame.to_image()
    img.thumbnail((size, size))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=82)
    os.makedirs(cache, exist_ok=True)
    with open(out, "wb") as f:
        f.write(buf.getvalue())
    return buf.getvalue()


def _register_routes():
    try:
        from aiohttp import web
        from server import PromptServer
        routes = PromptServer.instance.routes
    except Exception:
        return  # not inside ComfyUI (tests)

    @routes.get("/rototools/batch/scan")
    @routes.post("/rototools/batch/scan")   # POST: the list goes in the body, so any number of videos fits
    async def _scan(request):
        q = dict(request.rel_url.query)
        if request.method == "POST":
            try:
                q.update(await request.json())
            except Exception:
                pass
        rep = await asyncio.get_running_loop().run_in_executor(
            None, scan_report, q.get("folders", ""), q.get("extensions") or DEFAULT_EXTS,
            str(q.get("recursive", "1")).lower() not in ("0", "false"), q.get("output_folder", ""))
        return web.json_response(rep)

    @routes.post("/rototools/batch/reset")
    async def _reset(request):
        reset_attempts()
        log("list cleared: failed-video memory reset")
        return web.json_response({"ok": True})

    @routes.get("/rototools/batch/thumb")
    async def _thumb(request):
        global _THUMB_LOCK
        path = request.rel_url.query.get("path", "")
        if not _allowed(path):
            return web.Response(status=404)
        if _THUMB_LOCK is None:
            _THUMB_LOCK = asyncio.Semaphore(4)  # a 400-shot grid must not start 400 decoders at once
        async with _THUMB_LOCK:
            try:
                data = await asyncio.get_running_loop().run_in_executor(None, make_thumb, path)
            except Exception as e:
                print("[LoadVideoBatchFolders] no thumbnail for %s: %s" % (path, e))
                return web.Response(status=415)
        return web.Response(body=data, content_type="image/jpeg", headers={"Cache-Control": "max-age=3600"})

    @routes.post("/rototools/batch/upload")
    async def _upload(request):
        reader = await request.multipart()
        field = await reader.next()
        while field is not None and field.name != "file":
            field = await reader.next()
        if field is None or not field.filename:
            return web.json_response({"error": "no file"}, status=400)
        filename = os.path.basename(field.filename.replace("\\", "/"))
        exts = {"." + e for e in DEFAULT_EXTS.split(",")}
        if os.path.splitext(filename)[1].lower() not in exts or filename.startswith("."):
            return web.json_response({"error": "Not a video (%s): %s" % (DEFAULT_EXTS, filename)}, status=415)
        drops = os.path.join(folder_paths.get_input_directory(), DROPS_SUBFOLDER)
        os.makedirs(drops, exist_ok=True)
        tmp = os.path.join(drops, ".upload_%s.part" % os.urandom(6).hex())
        try:
            with open(tmp, "wb") as f:
                while True:
                    chunk = await field.read_chunk(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
            path = await asyncio.get_running_loop().run_in_executor(None, place_drop, tmp, filename, drops)
        except Exception as e:
            if os.path.exists(tmp):
                os.remove(tmp)
            return web.json_response({"error": "Upload failed: %s" % e}, status=500)
        return web.json_response({"path": path})

    picking = asyncio.Lock()

    @routes.post("/rototools/batch/pick")
    async def _pick(request):
        try:
            body = await request.json()
        except Exception:
            body = {}
        if picking.locked():
            return web.json_response({"error": "A folder dialog is already open on the ComfyUI computer."}, status=409)
        start = body.get("start") or ""
        cmd = picker_command(os.path.dirname(start.rstrip("/\\")) if start else "")  # open next to the last folder
        if not cmd:
            return web.json_response({"error": "No folder dialog available on this system; type or paste the paths."},
                                     status=501)
        async with picking:
            try:
                proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE,
                                                            stderr=asyncio.subprocess.PIPE)
                out, err = await proc.communicate()
            except Exception as e:
                return web.json_response({"error": "Folder dialog failed: %s" % e}, status=500)
        picked = parse_picker_output(out.decode("utf-8", "replace"))
        if proc.returncode not in (0, 1) and not picked:   # 1 = cancelled for zenity/osascript
            msg = err.decode("utf-8", "replace").strip()[-400:]
            print("[LoadVideoBatchFolders] folder dialog error:", msg)
            return web.json_response({"error": "Folder dialog failed: " + (msg or "exit %s" % proc.returncode)},
                                     status=500)
        return web.json_response({"picked": picked, "text": merge_folders(body.get("current", ""), picked)})

    @routes.get("/rototools/batch/info")
    async def _info(request):
        global _THUMB_LOCK
        path = request.rel_url.query.get("path", "")
        if not _allowed(path):
            return web.Response(status=404)
        if _THUMB_LOCK is None:
            _THUMB_LOCK = asyncio.Semaphore(4)
        async with _THUMB_LOCK:
            try:
                info = await asyncio.get_running_loop().run_in_executor(None, video_info, path)
            except Exception as e:
                log("no frame count for %s: %s" % (path, e))
                return web.json_response({"error": str(e)}, status=415)
        return web.json_response(info, headers={"Cache-Control": "max-age=3600"})

    @routes.get("/rototools/batch/video")
    async def _video(request):
        path = request.rel_url.query.get("path", "")
        if not _allowed(path):
            return web.Response(status=404)
        return web.FileResponse(path)


_register_routes()
