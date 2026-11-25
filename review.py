# ComfyUI-RotoTools - Roto Review (A/B), a preview-only review player for roto work.
#
# Based on ComfyUI-KM-VideoReview (videoreview/nodes.py) by Kasun Malinda:
#   https://github.com/KasunMalinda/ComfyUI-KM-VideoReview
#   MIT License, Copyright (c) 2026 Kasun Malinda (full text in LICENSE-KM-VideoReview)
# Everything of the original node is kept; RotoTools adds on top:
#   * an RGBA B input (the roto) is kept with its alpha (colour frame + a small PNG matte; no WebP, whose encoder
#     crashed ComfyUI on long batches), so the player can show it over any background colour or as the alpha matte
#   * a history of every shot reviewed in this ComfyUI session (lightest preview by default; the oldest are only
#     dropped when the drive runs low)
#   * the alpha matte (white on black) downloaded on request at full resolution - nothing is saved to the output
#     folder (the TGA zip is the full-quality master)
import os
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED

import numpy as np
from PIL import Image

import folder_paths

try:
    from comfy.utils import ProgressBar
except Exception:  # pragma: no cover - ComfyUI always ships this
    ProgressBar = None


class RotoReview:
    """RV-style A/B review player.

    Writes preview frames to ComfyUI's temp directory and hands the file
    references to the frontend widget via the `ui` dict. Pure review sink:
    no graph outputs.
    """

    CATEGORY = "image/video"
    FUNCTION = "review"
    RETURN_TYPES = ()
    OUTPUT_NODE = True
    DESCRIPTION = ("A/B review player (wipe, side by side, difference, flip) for roto work: A = original, "
                   "B = RGBA roto, shown over any background or as the alpha matte. Keeps a history of the "
                   "shots of this session and downloads the alpha matte at full resolution on request. "
                   "Preview only: nothing is "
                   "saved to the output folder.")

    # Make the node discoverable under the terms people actually search for.
    SEARCH_ALIASES = [
        "video compare", "compare video", "video comparison", "compare",
        "a/b compare", "ab compare", "wipe", "video wipe", "difference",
        "side by side", "video review", "review", "player", "rv",
        "roto review", "roto compare", "alpha compare", "matte review",
    ]

    # Dropdown label -> internal encoder key. Labels carry the quality tier so
    # the fidelity/speed trade-off is obvious in the UI.
    # RotoTools: no WebP (its encoder crashed ComfyUI on long batches). Values saved in older workflows still work:
    # see LEGACY_FORMATS.
    PREVIEW_FORMATS = {
        "jpeg (low quality)": "jpeg",
        "png (best quality)": "png",
    }
    LEGACY_FORMATS = {
        "webp (mid quality)": "jpeg",
        "webp lossless (best quality)": "png",
    }
    DEFAULT_PREVIEW_FORMAT = "jpeg (low quality)"
    MAX_WORKERS = 4   # RotoTools: the preview must not load the whole CPU during a batch

    # Playback resolution = scale factor applied to the source when generating
    # preview frames. < 1 downscales (faster/lighter).
    PLAYBACK_RES = {
        "0.25": 0.25,
        "0.5": 0.5,
        "1:1": 1.0,
    }
    # RotoTools: the lightest preview by default (only for looking; the zip is the full-quality master and the
    # alpha matte download is made from full-resolution alpha frames, whatever the preview settings).
    DEFAULT_PLAYBACK_RES = "0.25"
    DEFAULT_QUALITY = 50

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images_a": ("IMAGE", {"tooltip": "A: the original clip."}),
            },
            "optional": {
                "images_b": ("IMAGE", {"tooltip": "B: the roto. RGBA frames keep their alpha, so the player can "
                                                  "show them over a background colour or as the alpha matte."}),
                # Names with spaces are display labels; they arrive via **kwargs.
                "Base fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 120.0, "step": 1.0,
                                       "tooltip": "Base playback rate of the review player (the live rate can be changed in the player)."}),
                "preview_format": (list(cls.PREVIEW_FORMATS.keys()),
                                   {"default": cls.DEFAULT_PREVIEW_FORMAT,
                                    "tooltip": "How preview frames are encoded for the browser. jpeg is light and fast to load; png is pixel-exact but about 5x bigger (keep jpeg for long batches)."}),
                "quality": ("INT", {"default": cls.DEFAULT_QUALITY, "min": 1, "max": 100,
                                    "tooltip": "Encode quality for jpeg. Ignored for png (always lossless)."}),
                "Playback resolution": (list(cls.PLAYBACK_RES.keys()),
                                        {"default": cls.DEFAULT_PLAYBACK_RES,
                                         "tooltip": "Scale the preview frames relative to the source. Lower = faster load and less memory."}),
                "name": ("STRING", {"forceInput": True,
                                    "tooltip": "Shot name for the history and the download (connect shot_label from "
                                               "Load Video Batch: 'ep93 / shot6', unique even for same-named shots)."}),
                # RotoTools: never read; the wire only makes this node wait until the zip is on disk
                "after_save": ("STRING", {"forceInput": True,
                                          "tooltip": "Connect saved_path of Save Image Sequence (TGA): the preview is "
                                                     "then made AFTER the zip is saved, so a problem with the preview "
                                                     "can never cost a finished shot."}),
            },
        }

    @classmethod
    def VALIDATE_INPUTS(cls, preview_format=None):
        # taking preview_format here makes ComfyUI accept values of older workflows that left the list
        # (LEGACY_FORMATS); anything unknown falls back to jpeg
        return True

    # RotoTools: a preview must never stop a batch. Problems making it (disk full, no memory, no new thread ...) are
    # reported and the run goes on without a preview.
    def review(self, images_a, images_b=None, **kwargs):
        try:
            return self._review(images_a, images_b, **kwargs)
        except (OSError, MemoryError, RuntimeError) as e:
            print("[RotoReview] no preview for this shot (the batch goes on): %s: %s" % (type(e).__name__, e))
            return {"ui": {"a_frames": [], "b_frames": []}}

    def _review(self, images_a, images_b=None, preview_format=None,
                quality=DEFAULT_QUALITY, name=None, after_save=None, **kwargs):
        fps = float(kwargs.get("Base fps", 24.0))
        fmt = {**self.LEGACY_FORMATS, **self.PREVIEW_FORMATS}.get(preview_format, "jpeg")
        scale = self.PLAYBACK_RES.get(kwargs.get("Playback resolution", self.DEFAULT_PLAYBACK_RES), 1.0)
        # Fresh id per execution so re-runs never overwrite files the browser
        # may still be fetching from a previous run.
        run_id = "".join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=6))
        # RotoTools: an RGBA B keeps its alpha as a separate small PNG matte next to its colour frame.
        b_alpha = images_b is not None and int(images_b.shape[-1]) == 4
        # Node execution progress bar (the green bar on the node, like VHS).
        total = int(images_a.shape[0]) + (int(images_b.shape[0]) if images_b is not None else 0)
        pbar = ProgressBar(total) if ProgressBar else None
        # Color transform + encode are CPU-bound numpy/C code that releases the
        # GIL, so a thread pool gives a near-linear speedup.
        workers = min(self.MAX_WORKERS, (os.cpu_count() or 4))
        with ThreadPoolExecutor(max_workers=workers) as ex:
            a_frames = self._save_batch(images_a, f"vr_{run_id}_a", fmt,
                                        quality, scale, ex, workers, pbar)
            b_frames, b_masks = [], []
            if images_b is not None:
                b_frames = self._save_batch(images_b, f"vr_{run_id}_b", fmt,
                                            quality, scale, ex, workers, pbar, b_masks if b_alpha else None)
            # RotoTools: the alpha at full resolution, lossless (grey PNG, small: mattes are mostly flat),
            # so the matte download is exact whatever the preview settings are
            m_frames = self._save_alpha(images_b, f"vr_{run_id}_m", ex) if b_alpha else []

        def prev_dim(images):
            w, h = int(images.shape[2]), int(images.shape[1])
            return [max(1, round(w * scale)), max(1, round(h * scale))]

        # Deliberately NOT using the "images" key: that would trigger the
        # frontend's default preview overlay on top of our player widget.
        ui = {
            "a_frames": a_frames,
            "b_frames": b_frames,
            "fps": [fps],
            "a_size": [[int(images_a.shape[2]), int(images_a.shape[1])]],
            "b_size": [[int(images_b.shape[2]), int(images_b.shape[1])]] if images_b is not None else [],
            # Actual encoded preview resolution (source x playback scale).
            "a_prev": [prev_dim(images_a)],
            "b_prev": [prev_dim(images_b)] if images_b is not None else [],
            # RotoTools additions
            "run_id": [run_id],
            # shown in the history as is (e.g. "ep93 / shot6" from Load Video Batch's shot_label) ...
            "name": [" ".join(str(name).split()) if name and str(name).strip() else "shot_" + run_id],
            # ... and file-safe for the download name ("ep93_shot6")
            "file": [_clean_name(re.sub(r"\s*[\\/]+\s*", "_", str(name or "").strip())) or "shot_" + run_id],
            "b_alpha": [bool(b_alpha)],
            "b_masks": b_masks,
            "m_frames": m_frames,
        }
        remember_run(ui)
        return {"ui": ui}

    # RotoTools
    def _save_alpha(self, images, prefix, ex):
        folder = folder_paths.get_temp_directory()
        os.makedirs(folder, exist_ok=True)

        def save(arr, path):
            Image.fromarray((np.clip(arr, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8), "L").save(
                path, format="PNG", compress_level=1)

        results, futures = [], []
        for i in range(int(images.shape[0])):
            arr = images[i].cpu().numpy()[..., 3].astype(np.float32, copy=False)
            file = f"{prefix}_{i:05}_.png"
            results.append({"filename": file, "subfolder": "", "type": "temp"})
            futures.append(ex.submit(save, arr, os.path.join(folder, file)))
        for f in futures:
            f.result()
        return results

    def _save_batch(self, images, prefix, fmt, quality, scale, ex, workers, pbar=None, masks=None):
        output_dir = folder_paths.get_temp_directory()
        full_folder, filename, counter, subfolder, _ = folder_paths.get_save_image_path(
            prefix, output_dir, images.shape[2], images.shape[1]
        )
        ext = "png" if fmt == "png" else "jpg"
        if fmt == "png":
            save_kwargs = dict(format="PNG", compress_level=1)
        else:
            save_kwargs = dict(format="JPEG", quality=quality)

        def encode_frame(arr, path):
            # Runs on a worker thread: uint8 conversion -> PIL -> save.
            img = Image.fromarray((np.clip(arr, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8))
            size = img.size
            if scale != 1.0:
                size = (max(1, round(size[0] * scale)), max(1, round(size[1] * scale)))
            if masks is not None:
                img = split_alpha(img, size, os.path.splitext(path)[0] + "m.png")
            elif fmt == "jpeg" and img.mode != "RGB":
                img = img.convert("RGB")
            if img.size != size:
                img = img.resize(size, Image.LANCZOS)
            img.save(path, **save_kwargs)

        # RotoTools: RGBA -> colour frame (returned) + matte (white with the alpha, PNG)
        def split_alpha(img, size, mask_path):
            small = img.resize(size, Image.LANCZOS) if img.size != size else img
            alpha = small.getchannel("A")
            Image.merge("LA", (Image.new("L", size, 255), alpha)).save(mask_path, format="PNG")
            if small is img:
                return img.convert("RGB")
            # edge colours exactly as in the scaled roto; where nothing is visible the plain frame, so the
            # jpeg has no hard black border that would bleed into soft edges
            plate = img.convert("RGB").resize(size, Image.LANCZOS)
            plate.paste(small.convert("RGB"), (0, 0), alpha.point(lambda v: 255 if v else 0))
            return plate

        n = int(images.shape[0])
        results = [None] * n
        # Bound in-flight encodes so peak memory stays at a couple of frames per
        # worker rather than the whole batch.
        max_outstanding = max(2, workers * 2)
        pending = set()

        def tick(futures):
            for d in futures:
                d.result()  # surface any encode error
                if pbar is not None:
                    pbar.update(1)

        for i in range(n):
            # Tensor -> numpy stays on the main thread: .cpu() touches the CUDA
            # context, which must not be hit from worker threads. Keep float so
            # HDR values survive into the color transform.
            arr = images[i].cpu().numpy().astype(np.float32, copy=False)
            file = f"{filename}_{counter + i:05}_.{ext}"
            path = os.path.join(full_folder, file)
            results[i] = {"filename": file, "subfolder": subfolder, "type": "temp"}
            if masks is not None:
                masks.append({"filename": os.path.splitext(file)[0] + "m.png", "subfolder": subfolder, "type": "temp"})
            pending.add(ex.submit(encode_frame, arr, path))
            if len(pending) >= max_outstanding:
                done, pending = wait(pending, return_when=FIRST_COMPLETED)
                tick(done)
        tick(pending)
        return results


NODE_CLASS_MAPPINGS = {"RotoReview": RotoReview}
NODE_DISPLAY_NAME_MAPPINGS = {"RotoReview": "Roto Review (A/B)"}


# ---------------------------------------------------------------- RotoTools: history
# Every run of this ComfyUI session, newest last. The previews are small (lowest settings by default), so all of
# them are kept; only if the drive of the temp folder gets low (MIN_FREE_GB) are the oldest runs dropped.
MIN_FREE_GB = 10
_HISTORY = []


def _clean_name(name):
    if not name:
        return None
    name = "".join(c if (c.isalnum() or c in " ._-()[]") else "_" for c in str(name)).strip(" .")
    return name or None


def _frame_path(f):
    return os.path.join(folder_paths.get_temp_directory(), f.get("subfolder") or "", f["filename"])


def _free_gb():
    import shutil
    try:
        return shutil.disk_usage(folder_paths.get_temp_directory()).free / 1024 ** 3
    except OSError:
        return float("inf")


def _forget(run):
    ui = run["ui"]
    for f in ui["a_frames"] + ui["b_frames"] + ui.get("b_masks", []) + ui.get("m_frames", []):
        try:
            os.remove(_frame_path(f))
        except OSError:
            pass


def remember_run(ui):
    _HISTORY.append({"ui": ui, "time": time.time()})
    while len(_HISTORY) > 1 and _free_gb() < MIN_FREE_GB:
        old = _HISTORY.pop(0)
        _forget(old)
        print("[RotoReview] drive low on space (< %d GB free): dropped the oldest review, %s"
              % (MIN_FREE_GB, old["ui"]["name"][0]))


def history():
    """Newest first; only runs whose frames are still on disk (the temp folder is emptied on restart)."""
    out = []
    for h in reversed(_HISTORY):
        if h["ui"]["a_frames"] and os.path.exists(_frame_path(h["ui"]["a_frames"][0])):
            out.append(dict(h["ui"], time=[h["time"]]))
    return out


def find_run(run_id):
    for h in _HISTORY:
        if h["ui"]["run_id"][0] == run_id:
            return h["ui"]
    return None


# ---------------------------------------------------------------- RotoTools: download
# The alpha matte (white = subject on black) at full resolution, made from the lossless full-resolution
# alpha frames when asked, into temp\rototools_review_dl (old ones are cleaned up), and sent to the browser.
def make_download(run_id, kind="alpha"):
    """Write the alpha matte video to temp and return (path, download file name)."""
    ui = find_run(run_id)
    if ui is None:
        raise KeyError("this shot is no longer in the review history")
    if kind != "alpha":
        raise ValueError("unknown download: %s (only the alpha matte is offered)" % kind)
    if not ui.get("m_frames"):
        raise ValueError("this run has no roto with alpha (images_b must be RGBA)")
    import av   # ComfyUI ships PyAV; imported here so the checks above work without it
    from fractions import Fraction
    folder = os.path.join(folder_paths.get_temp_directory(), "rototools_review_dl")
    os.makedirs(folder, exist_ok=True)
    for f in os.listdir(folder):   # downloads already sent; keep the folder small
        p = os.path.join(folder, f)
        try:
            if time.time() - os.path.getmtime(p) > 600:
                os.remove(p)
        except OSError:
            pass
    name = "%s_alpha.mp4" % (ui.get("file") or ui["name"])[0]
    path = os.path.join(folder, "%s_%s" % (run_id, name))
    first = Image.open(_frame_path(ui["m_frames"][0]))
    w, h = first.size
    w, h = w - w % 2, h - h % 2     # yuv420p needs even sizes (a grey matte loses nothing to 4:2:0)
    with av.open(path, "w") as c:
        s = c.add_stream("libx264", rate=Fraction(ui["fps"][0] or 24).limit_denominator(1001))
        s.pix_fmt = "yuv420p"
        s.width, s.height = w, h
        s.options = {"crf": "4", "preset": "medium"}   # visually lossless, still plays everywhere
        for f in ui["m_frames"]:
            im = Image.open(_frame_path(f)).convert("RGB")
            if im.size != (w, h):
                im = im.crop((0, 0, w, h))
            for p in s.encode(av.VideoFrame.from_ndarray(np.asarray(im), format="rgb24")):
                c.mux(p)
        for p in s.encode():
            c.mux(p)
    return path, name


def _register_routes():
    try:
        import asyncio
        from aiohttp import web
        from server import PromptServer
        routes = PromptServer.instance.routes
    except Exception:
        return  # not inside ComfyUI (tests)

    @routes.get("/rototools/review/history")
    async def _history(request):
        return web.json_response({"runs": history()})

    @routes.get("/rototools/review/download")
    async def _download(request):
        q = request.rel_url.query
        try:
            path, name = await asyncio.get_running_loop().run_in_executor(
                None, make_download, q.get("run", ""), q.get("kind", "alpha"))
        except (KeyError, ValueError) as e:
            return web.Response(status=404, text=str(e))
        except Exception as e:
            print("[RotoReview] download failed:", e)
            return web.Response(status=500, text="download failed: %s" % e)
        print("[RotoReview] download ready: %s" % name)
        return web.FileResponse(path, headers={"Content-Disposition": 'attachment; filename="%s"' % name})


_register_routes()
