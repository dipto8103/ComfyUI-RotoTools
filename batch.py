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


def _label_candidates(root):
    """ep93, ep93 (y), ep93 (y) 2, ep93 (y) 3 ...  (y = the folder that holds ep93)."""
    base = _clean(os.path.basename(root) or root.replace(":", ""))
    parent = os.path.dirname(root)
    where = _clean(os.path.basename(parent) or parent.replace(":", "").strip("\\/")) if parent != root else "root"
    yield base
    yield "%s (%s)" % (base, where)
    for n in range(2, 1000):
        yield "%s (%s) %d" % (base, where, n)


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
    """Every video in every listed folder, in order.

    Returns (groups, items, errors):
      groups: [{"label": output folder name (see assign_labels), "root": abs path, "count": n}]
      items:  [{"path", "rel", "group" (index into groups), "name" (zip name, unique inside its group)}]
    strict=True raises on a missing folder; False collects the message in errors instead.
    """
    groups, items, errors = [], [], []
    found = []
    for root in split_folders(folders_text):
        try:
            found.append(scan_videos(root, extensions, recursive))
        except FileNotFoundError as e:
            if strict:
                raise
            errors.append(str(e))
    for (root, vids), label in zip(found, assign_labels([r for r, _ in found], output_folder)):
        g = len(groups)
        groups.append({"label": label, "root": root, "count": len(vids)})
        names = set()
        for p in vids:
            items.append({"path": p, "rel": os.path.relpath(p, root), "group": g,
                          "name": _unique(_clean(os.path.splitext(os.path.basename(p))[0]), names)})
    return groups, items, errors


def zip_folder_for(output_folder, label):
    """<output_folder>\\<label>; empty output_folder = ComfyUI output\\roto_tga\\<label> (the saver's default)."""
    base = (output_folder or "").strip().strip('"')
    base = _abs(base) if base else os.path.join(os.path.abspath(folder_paths.get_output_directory()), "roto_tga")
    return os.path.join(base, label)


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
                                            "tooltip": "One or more folders, one per line or comma separated "
                                                       "(x\\ep93, x\\ep94). Use 'Add folders' on the preview to pick them, "
                                                       "or paste Explorer's Copy as path (Ctrl+Shift+C). Every video inside "
                                                       "them and their sub-folders is found automatically."}),
                "index": ("INT", {"default": 0, "min": 0, "max": 999999, "control_after_generate": "increment",
                                  "tooltip": "Which video to load (0 = first). Leave this on 'increment' and set Run's "
                                             "batch count to the number of videos: they are queued one after another."}),
                "skip_if_zip_exists": ("BOOLEAN", {"default": True,
                                                   "tooltip": "Resume support: if the video's zip is already in its output "
                                                              "folder, this video is skipped (the rest of the workflow does not run)."}),
                "output_folder": ("STRING", {"default": "", "tooltip": "Where everything is saved. A folder named after each "
                                                                       "input folder is made inside it (output\\ep93\\shot5.zip). "
                                                                       "Connect zip_folder to the TGA saver's output_folder."}),
                "extensions": ("STRING", {"default": DEFAULT_EXTS, "tooltip": "Comma separated video extensions."}),
                "recursive": ("BOOLEAN", {"default": True, "tooltip": "Look inside sub-folders of sub-folders too."}),
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
    def IS_CHANGED(cls, batch_folder, index, **kw):
        try:
            _, items, _ = scan_batch(batch_folder, kw.get("extensions", DEFAULT_EXTS), kw.get("recursive", True))
            p = items[index]["path"] if index < len(items) else ""
            return "%s|%d|%s|%s|%s" % (len(items), index, p, os.path.getmtime(p) if p else "", kw.get("output_folder"))
        except Exception:
            return float("nan")

    def load(self, batch_folder, index, skip_if_zip_exists, output_folder, extensions, recursive, unique_id=None):
        groups, items, _ = scan_batch(batch_folder, extensions, recursive, output_folder=output_folder)
        _remember(items)
        total = len(items)
        if total == 0:
            raise ValueError("No videos (%s) found under %s" % (extensions, ", ".join(split_folders(batch_folder)) or "(no folder)"))
        blocker = _blocker()

        def skip(msg):
            print("[LoadVideoBatchFolders] " + msg)
            self._say(msg, unique_id)
            if blocker is None:
                raise RuntimeError(msg)
            b = blocker(None)
            return {"ui": {"rototools_index": [index]}, "result": (b, b, b, b, b, b)}

        if index >= total:
            return skip("index %d is past the last video (%d videos). Nothing to do." % (index, total))
        it = items[index]
        label = groups[it["group"]]["label"]
        zfolder = zip_folder_for(output_folder, label)
        claim_folder(zfolder, groups[it["group"]]["root"])   # this name now belongs to this input folder
        if skip_if_zip_exists and os.path.exists(os.path.join(zfolder, it["name"] + ".zip")):
            return skip("%d/%d SKIPPED (zip already exists): %s\\%s" % (index + 1, total, label, it["name"]))
        msg = "%d / %d   %s \\ %s" % (index + 1, total, label, it["rel"])
        print("[LoadVideoBatchFolders] " + msg)
        self._say(msg, unique_id)
        return {"ui": {"rototools_index": [index]},
                "result": (_make_video(it["path"]), it["name"], it["path"], index, total, zfolder)}

    @staticmethod
    def _say(text, unique_id):
        try:
            from server import PromptServer
            if unique_id is not None:
                PromptServer.instance.send_progress_text(text, unique_id)
        except Exception:
            pass


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
                     "done": os.path.exists(os.path.join(out, it["name"] + ".zip"))})
    folders = [{"path": p, "key": os.path.normcase(p)} for p in split_folders(folders_text)]
    for g in groups:
        g["key"] = os.path.normcase(g["root"])
    return {"total": len(rows), "groups": groups, "items": rows, "errors": errors, "folders": folders}


def merge_folders(current, added):
    """The batch_folder text after adding folders: one per line, nothing listed twice."""
    return "\n".join(split_folders("\n".join([current or ""] + ['"%s"' % a for a in added])))


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
    async def _scan(request):
        q = request.rel_url.query
        rep = await asyncio.get_running_loop().run_in_executor(
            None, scan_report, q.get("folders", ""), q.get("extensions", DEFAULT_EXTS),
            q.get("recursive", "1") not in ("0", "false"), q.get("output_folder", ""))
        return web.json_response(rep)

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

    @routes.get("/rototools/batch/video")
    async def _video(request):
        path = request.rel_url.query.get("path", "")
        if not _allowed(path):
            return web.Response(status=404)
        return web.FileResponse(path)


_register_routes()
