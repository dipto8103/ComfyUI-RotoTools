"""
ComfyUI-RotoTools - Load Video Batch (Folders).

Point it at one or more folders (comma separated, e.g. x\\ep93, x\\ep94); it finds every video in their
sub-folders, sorts them, and hands ONE video per run to the rest of the workflow.  Set the index widget to
"increment" and Run's batch count to the number of videos: ComfyUI queues them one after another.

Each input folder gets its own output folder named after it (output\\ep93, output\\ep94; a second folder
with the same name becomes ep93_2), and every zip is named after its video file (shot5.mp4 -> shot5.zip),
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
    """'x\\ep93, x\\ep94' (or one per line) -> list of absolute paths, duplicates dropped, order kept."""
    out, seen = [], set()
    for part in re.split(r"[,\n]", text or ""):
        part = part.strip().strip('"').strip()
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


def scan_batch(folders_text, extensions=DEFAULT_EXTS, recursive=True, strict=True):
    """Every video in every listed folder, in order.

    Returns (groups, items, errors):
      groups: [{"label": "ep93", "root": abs path, "count": n}]   label = folder name, ep93_2 if repeated
      items:  [{"path", "rel", "group" (index into groups), "name" (zip name, unique inside its group)}]
    strict=True raises on a missing folder; False collects the message in errors instead.
    """
    groups, items, errors, labels = [], [], [], set()
    for root in split_folders(folders_text):
        try:
            root, vids = scan_videos(root, extensions, recursive)
        except FileNotFoundError as e:
            if strict:
                raise
            errors.append(str(e))
            continue
        g = len(groups)
        groups.append({"label": _unique(_clean(os.path.basename(root) or root.replace(":", "")), labels),
                       "root": root, "count": len(vids)})
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
                "batch_folder": ("STRING", {"default": "", "tooltip": "One or more folders, comma separated "
                                                                      "(x\\ep93, x\\ep94). Every video inside them and their "
                                                                      "sub-folders is found automatically."}),
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
        groups, items, _ = scan_batch(batch_folder, extensions, recursive)
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
    groups, items, errors = scan_batch(folders_text, extensions, recursive, strict=False)
    _remember(items)
    for g in groups:
        g["out"] = zip_folder_for(output_folder, g["label"])
    rows = []
    for i, it in enumerate(items):
        out = groups[it["group"]]["out"]
        rows.append({"i": i, "group": it["group"], "rel": it["rel"], "name": it["name"], "path": it["path"],
                     "done": os.path.exists(os.path.join(out, it["name"] + ".zip"))})
    return {"total": len(rows), "groups": groups, "items": rows, "errors": errors}


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

    @routes.get("/rototools/batch/video")
    async def _video(request):
        path = request.rel_url.query.get("path", "")
        if not _allowed(path):
            return web.Response(status=404)
        return web.FileResponse(path)


_register_routes()
