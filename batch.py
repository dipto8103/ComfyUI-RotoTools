"""
ComfyUI-RotoTools - Load Video Batch (Folders).

Point it at a parent folder; it finds every video in the sub-folders (recursively), sorts them,
and hands ONE video per run to the rest of the workflow.  Set the index widget to
"increment" and Run's batch count to the number of videos: ComfyUI queues them one after another.
"""
import os
import re

import folder_paths  # noqa: F401  (kept so the module only loads inside ComfyUI)

DEFAULT_EXTS = "mp4,mov,mkv,avi,webm,m4v"


def _natural_key(text):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", text)]


def _clean(name):
    name = "".join(c if (c.isalnum() or c in " ._-()[]") else "_" for c in str(name)).strip(" .")
    return name or "video"


def scan_videos(root, extensions=DEFAULT_EXTS, recursive=True):
    """Sorted list of absolute video paths under root (natural sort, so clip2 comes before clip10)."""
    root = os.path.abspath(os.path.expandvars(os.path.expanduser((root or "").strip().strip('"'))))
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


def zip_name_for(root, path, use_subfolder):
    """'sub__clip' when the video sits in a sub-folder (and use_subfolder is on), else 'clip'."""
    rel = os.path.relpath(path, root)
    parts = rel.split(os.sep)
    stem = os.path.splitext(parts[-1])[0]
    if use_subfolder and len(parts) > 1:
        return _clean("__".join(parts[:-1] + [stem]))
    return _clean(stem)


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
                "batch_folder": ("STRING", {"default": "", "tooltip": "Parent folder. Every video inside it and its "
                                                                      "sub-folders is found automatically. Type or paste the path."}),
                "index": ("INT", {"default": 0, "min": 0, "max": 999999, "control_after_generate": "increment",
                                  "tooltip": "Which video to load (0 = first). Leave this on 'increment' and set Run's "
                                             "batch count to the number of videos: they are queued one after another."}),
                "use_subfolder_in_name": ("BOOLEAN", {"default": True,
                                                      "tooltip": "zip_name becomes subfolder__clip, so same-named clips in "
                                                                 "different folders never clash."}),
                "skip_if_zip_exists": ("BOOLEAN", {"default": True,
                                                   "tooltip": "Resume support: if <zip_name>.zip is already in zips_folder, "
                                                              "this video is skipped (the rest of the workflow does not run)."}),
                "zips_folder": ("STRING", {"default": "", "tooltip": "The folder your zips are saved in (same as the TGA "
                                                                     "saver's output_folder). Used only for the skip check."}),
                "extensions": ("STRING", {"default": DEFAULT_EXTS, "tooltip": "Comma separated video extensions."}),
                "recursive": ("BOOLEAN", {"default": True, "tooltip": "Look inside sub-folders of sub-folders too."}),
            },
            "hidden": {"unique_id": "UNIQUE_ID"},
        }

    RETURN_TYPES = ("VIDEO", "STRING", "STRING", "INT", "INT")
    RETURN_NAMES = ("video", "zip_name", "video_path", "index", "total")
    FUNCTION = "load"
    CATEGORY = "image/video"
    DESCRIPTION = "Loads one video per run from a folder of folders, for queueing hundreds of clips in one go."

    @classmethod
    def IS_CHANGED(cls, batch_folder, index, **kw):
        try:
            root, vids = scan_videos(batch_folder, kw.get("extensions", DEFAULT_EXTS), kw.get("recursive", True))
            p = vids[index] if index < len(vids) else ""
            return "%s|%d|%s|%s" % (len(vids), index, p, os.path.getmtime(p) if p else "")
        except Exception:
            return float("nan")

    def load(self, batch_folder, index, use_subfolder_in_name, skip_if_zip_exists, zips_folder, extensions,
             recursive, unique_id=None):
        root, vids = scan_videos(batch_folder, extensions, recursive)
        total = len(vids)
        if total == 0:
            raise ValueError("No videos (%s) found under %s" % (extensions, root))
        blocker = _blocker()

        def skip(msg):
            print("[LoadVideoBatchFolders] " + msg)
            self._say(msg, unique_id)
            if blocker is None:
                raise RuntimeError(msg)
            b = blocker(None)
            return (b, b, b, b, b)

        if index >= total:
            return skip("index %d is past the last video (%d videos). Nothing to do." % (index, total))
        path = vids[index]
        name = zip_name_for(root, path, use_subfolder_in_name)
        zf = (zips_folder or "").strip().strip('"')
        if skip_if_zip_exists and zf:
            zpath = os.path.join(os.path.abspath(os.path.expandvars(os.path.expanduser(zf))), name + ".zip")
            if os.path.exists(zpath):
                return skip("%d/%d SKIPPED (zip already exists): %s" % (index + 1, total, name))
        msg = "%d / %d   %s" % (index + 1, total, os.path.relpath(path, root))
        print("[LoadVideoBatchFolders] " + msg)
        self._say(msg, unique_id)
        return (_make_video(path), name, path, index, total)

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
