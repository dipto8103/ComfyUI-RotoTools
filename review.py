# ComfyUI-RotoTools - Roto Review (A/B), a preview-only review player for roto work.
#
# Based on ComfyUI-KM-VideoReview (videoreview/nodes.py) by Kasun Malinda:
#   https://github.com/KasunMalinda/ComfyUI-KM-VideoReview
#   MIT License, Copyright (c) 2026 Kasun Malinda (full text in LICENSE-KM-VideoReview)
# Everything of the original node is kept; RotoTools adds on top:
#   * an RGBA B input (the roto) is kept with its alpha (WebP), so the player can show it over any
#     background colour or as the alpha matte
#   * a history of the shots reviewed in this ComfyUI session (the last HISTORY_SIZE), older frames deleted
#   * downloads made on request (mp4 / ProRes 4444 .mov with alpha) - nothing is saved to the output folder
import os
import random
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
                   "shots of this session and downloads mp4 / ProRes on request. Preview only: nothing is "
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
    PREVIEW_FORMATS = {
        "jpeg (low quality)": "jpeg",
        "webp (mid quality)": "webp",
        "webp lossless (best quality)": "webp_lossless",
    }
    DEFAULT_PREVIEW_FORMAT = "jpeg (low quality)"

    # Playback resolution = scale factor applied to the source when generating
    # preview frames. < 1 downscales (faster/lighter).
    PLAYBACK_RES = {
        "0.25": 0.25,
        "0.5": 0.5,
        "1:1": 1.0,
    }
    DEFAULT_PLAYBACK_RES = "1:1"

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
                                    "tooltip": "How preview frames are encoded for the browser. jpeg is fastest to load; webp lossless is pixel-exact but slowest. An RGBA B is always webp (jpeg has no alpha)."}),
                "quality": ("INT", {"default": 90, "min": 1, "max": 100,
                                    "tooltip": "Encode quality for jpeg / webp. Ignored for webp lossless."}),
                "Playback resolution": (list(cls.PLAYBACK_RES.keys()),
                                        {"default": cls.DEFAULT_PLAYBACK_RES,
                                         "tooltip": "Scale the preview frames relative to the source. Lower = faster load and less memory."}),
                "name": ("STRING", {"forceInput": True,
                                    "tooltip": "Shot name for the history strip and downloads (e.g. zip_name from Load Video Batch)."}),
            },
        }

    def review(self, images_a, images_b=None, preview_format=None,
               quality=90, name=None, **kwargs):
        fps = float(kwargs.get("Base fps", 24.0))
        fmt = self.PREVIEW_FORMATS.get(preview_format, "jpeg")
        scale = self.PLAYBACK_RES.get(kwargs.get("Playback resolution", "1:1"), 1.0)
        # Fresh id per execution so re-runs never overwrite files the browser
        # may still be fetching from a previous run.
        run_id = "".join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=6))
        # RotoTools: an RGBA B keeps its alpha (webp; jpeg cannot hold alpha).
        b_alpha = images_b is not None and int(images_b.shape[-1]) == 4
        b_fmt = ("webp_lossless" if fmt == "webp_lossless" else "webp") if b_alpha else fmt
        # Node execution progress bar (the green bar on the node, like VHS).
        total = int(images_a.shape[0]) + (int(images_b.shape[0]) if images_b is not None else 0)
        pbar = ProgressBar(total) if ProgressBar else None
        # Color transform + encode are CPU-bound numpy/C code that releases the
        # GIL, so a thread pool gives a near-linear speedup.
        workers = min(12, (os.cpu_count() or 4))
        with ThreadPoolExecutor(max_workers=workers) as ex:
            a_frames = self._save_batch(images_a, f"vr_{run_id}_a", fmt,
                                        quality, scale, ex, workers, pbar)
            b_frames = []
            if images_b is not None:
                b_frames = self._save_batch(images_b, f"vr_{run_id}_b", b_fmt,
                                            quality, scale, ex, workers, pbar)

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
            "name": [_clean_name(name) or "shot_" + run_id],
            "b_alpha": [bool(b_alpha)],
        }
        remember_run(ui)
        return {"ui": ui}

    def _save_batch(self, images, prefix, fmt, quality, scale, ex, workers, pbar=None):
        output_dir = folder_paths.get_temp_directory()
        full_folder, filename, counter, subfolder, _ = folder_paths.get_save_image_path(
            prefix, output_dir, images.shape[2], images.shape[1]
        )
        ext = "webp" if fmt.startswith("webp") else "jpg"
        if fmt == "webp_lossless":
            save_kwargs = dict(format="WEBP", lossless=True, method=2)
        elif fmt == "webp":
            save_kwargs = dict(format="WEBP", quality=quality)
        else:
            save_kwargs = dict(format="JPEG", quality=quality)

        def encode_frame(arr, path):
            # Runs on a worker thread: uint8 conversion -> PIL -> save.
            img = Image.fromarray((np.clip(arr, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8))
            if fmt == "jpeg" and img.mode != "RGB":
                img = img.convert("RGB")
            if scale != 1.0:
                w, h = img.size
                img = img.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
            img.save(path, **save_kwargs)

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
            pending.add(ex.submit(encode_frame, arr, path))
            if len(pending) >= max_outstanding:
                done, pending = wait(pending, return_when=FIRST_COMPLETED)
                tick(done)
        tick(pending)
        return results


NODE_CLASS_MAPPINGS = {"RotoReview": RotoReview}
NODE_DISPLAY_NAME_MAPPINGS = {"RotoReview": "Roto Review (A/B)"}


# ---------------------------------------------------------------- RotoTools: history
# The runs of this ComfyUI session, newest last. Only the last HISTORY_SIZE keep their preview frames;
# older ones are deleted from the temp folder so a 300-shot batch does not fill the disk.
HISTORY_SIZE = 40
_HISTORY = []


def _clean_name(name):
    if not name:
        return None
    name = "".join(c if (c.isalnum() or c in " ._-()[]") else "_" for c in str(name)).strip(" .")
    return name or None


def _frame_path(f):
    return os.path.join(folder_paths.get_temp_directory(), f.get("subfolder") or "", f["filename"])


def remember_run(ui):
    _HISTORY.append({"ui": ui, "time": time.time()})
    while len(_HISTORY) > HISTORY_SIZE:
        old = _HISTORY.pop(0)
        for f in old["ui"]["a_frames"] + old["ui"]["b_frames"]:
            try:
                os.remove(_frame_path(f))
            except OSError:
                pass


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


# ---------------------------------------------------------------- RotoTools: downloads
# Made only when asked, into temp\rototools_review_dl (old ones are cleaned up), and sent to the browser.
DOWNLOADS = {
    "roto": ("mp4", "roto over the background colour"),
    "alpha": ("mp4", "alpha matte (white = subject)"),
    "side": ("mp4", "original | roto, side by side"),
    "original": ("mp4", "original (A)"),
    "roto_alpha": ("mov", "roto with alpha, ProRes 4444"),
}


def _hex_rgb(bg):
    bg = (bg or "ff0000").lstrip("#")
    try:
        return tuple(int(bg[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return (255, 0, 0)


def _frames(ui, key):
    out = []
    for f in ui[key]:
        im = Image.open(_frame_path(f))
        im.load()
        out.append(im)
    return out


def _over(im, rgb):
    im = im.convert("RGBA")
    base = Image.new("RGBA", im.size, rgb + (255,))
    return Image.alpha_composite(base, im).convert("RGB")


def _matte(im):
    a = im.convert("RGBA").getchannel("A")
    return Image.merge("RGB", (a, a, a))


def make_download(run_id, kind, bg="ff0000"):
    """Write the requested video to temp and return (path, download file name)."""
    import av
    ui = find_run(run_id)
    if ui is None:
        raise KeyError("this shot is no longer in the review history")
    if kind not in DOWNLOADS:
        raise ValueError("unknown download: %s" % kind)
    ext = DOWNLOADS[kind][0]
    if kind != "original" and not ui["b_frames"]:
        raise ValueError("this run has no B (roto) frames")
    rgb = _hex_rgb(bg)
    if kind == "original":
        frames = [im.convert("RGB") for im in _frames(ui, "a_frames")]
    elif kind == "roto":
        frames = [_over(im, rgb) for im in _frames(ui, "b_frames")]
    elif kind == "alpha":
        frames = [_matte(im) for im in _frames(ui, "b_frames")]
    elif kind == "roto_alpha":
        frames = [im.convert("RGBA") for im in _frames(ui, "b_frames")]
    else:  # side by side, both at the height of A
        a_frames, b_frames = _frames(ui, "a_frames"), _frames(ui, "b_frames")
        frames = []
        for a, b in zip(a_frames, b_frames):
            a = a.convert("RGB")
            b = _over(b, rgb).resize((max(1, round(b.width * a.height / b.height)), a.height))
            pair = Image.new("RGB", (a.width + b.width, a.height))
            pair.paste(a, (0, 0))
            pair.paste(b, (a.width, 0))
            frames.append(pair)
    if not frames:
        raise ValueError("no frames")
    folder = os.path.join(folder_paths.get_temp_directory(), "rototools_review_dl")
    os.makedirs(folder, exist_ok=True)
    for f in os.listdir(folder):   # downloads already sent; keep the folder small
        p = os.path.join(folder, f)
        try:
            if time.time() - os.path.getmtime(p) > 600:
                os.remove(p)
        except OSError:
            pass
    name = "%s_%s.%s" % (ui["name"][0], kind, ext)
    path = os.path.join(folder, "%s_%s" % (run_id, name))
    w, h = frames[0].size
    fps = ui["fps"][0] or 24
    from fractions import Fraction
    with av.open(path, "w") as c:
        if ext == "mov":
            s = c.add_stream("prores_ks", rate=Fraction(fps).limit_denominator(1001))
            s.options = {"profile": "4"}   # 4444, keeps the alpha
            s.pix_fmt = "yuva444p10le"
            s.width, s.height = w, h
            pix = "rgba"
        else:
            w, h = w - w % 2, h - h % 2     # yuv420p needs even sizes
            s = c.add_stream("libx264", rate=Fraction(fps).limit_denominator(1001))
            s.pix_fmt = "yuv420p"
            s.width, s.height = w, h
            s.options = {"crf": "16", "preset": "fast"}
            pix = "rgb24"
        for im in frames:
            if im.size != (w, h):
                im = im.crop((0, 0, w, h))
            frame = av.VideoFrame.from_ndarray(np.asarray(im), format=pix)
            for p in s.encode(frame):
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
        return web.json_response({"runs": history(), "size": HISTORY_SIZE})

    @routes.get("/rototools/review/download")
    async def _download(request):
        q = request.rel_url.query
        try:
            path, name = await asyncio.get_running_loop().run_in_executor(
                None, make_download, q.get("run", ""), q.get("kind", "roto"), q.get("bg", "ff0000"))
        except (KeyError, ValueError) as e:
            return web.Response(status=404, text=str(e))
        except Exception as e:
            print("[RotoReview] download failed:", e)
            return web.Response(status=500, text="download failed: %s" % e)
        print("[RotoReview] download ready: %s" % name)
        return web.FileResponse(path, headers={"Content-Disposition": 'attachment; filename="%s"' % name})


_register_routes()
