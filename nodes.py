"""
ComfyUI-RotoTools - nodes.

1. Save Image Sequence (TGA, RGBA)
   * writes every frame of the IMAGE batch as a numbered .tga (frame_00000.tga ...)
   * keeps the 4th channel as a real alpha channel when the batch is RGBA
     (feed it from "Join Image with Alpha"); 3-channel batches are saved as RGB
   * optional RLE compression (lossless, much smaller files for mattes)
   * save_as_zip (default ON): ONE <name>.zip in the typed folder holding all the
     TGA frames, no loose files. OFF: loose .tga files in the folder.
   * optional source_video input: the zip is named after the video file
   * never overwrites an earlier run unless asked (_v2, _v3 ...)
   * shows a few transparent preview frames on the node

2. Spec Readout (size / frames / fps)
   * shows width x height | frames | fps | seconds on the node while the workflow
     runs, an optional padding check (multiple of 32, frames = 8n+1) and an optional
     MATCH / MISMATCH check against another image batch.
"""
import io
import os
import random
import zipfile

import numpy as np
from PIL import Image

import folder_paths


def _clean_name(name):
    """Make a string safe to use as a file name (no extension); None if nothing is left."""
    if not name:
        return None
    name = "".join(c if (c.isalnum() or c in " ._-()[]") else "_" for c in str(name)).strip(" .")
    return name or None


def _video_stem(video):
    """File name (without extension) of the clip a VIDEO input was loaded from, or None."""
    if video is None:
        return None
    try:
        src = video.get_stream_source()
    except Exception:
        return None
    if not isinstance(src, (str, os.PathLike)):
        return None
    return _clean_name(os.path.splitext(os.path.basename(str(src)))[0])


class SaveImageSequenceTGA:
    def __init__(self):
        self.output_dir = folder_paths.get_output_directory()
        self.type = "output"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE", {"tooltip": "RGB or RGBA frames. 4 channels = real alpha in the TGA."}),
                "output_folder": ("STRING", {
                    "default": "",
                    "tooltip": "Folder to save into, typed by you, e.g. D:\\renders\\roto_zips . "
                               "Created if missing. In zip mode every zip is saved in this one folder. "
                               "Empty = ComfyUI output folder / roto_tga.",
                }),
                "filename_prefix": ("STRING", {
                    "default": "frame",
                    "tooltip": "File name before the frame number, e.g. shot01 -> shot01_00000.tga. "
                               "Also the zip name when no source_video is connected.",
                }),
                "start_number": ("INT", {"default": 0, "min": 0, "max": 99999999,
                                         "tooltip": "Number of the first frame in the file names."}),
                "digits": ("INT", {"default": 5, "min": 1, "max": 9,
                                   "tooltip": "Zero padding of the frame number."}),
                "rle_compression": ("BOOLEAN", {"default": True,
                                                "tooltip": "Lossless RLE. Smaller files, every app reads it."}),
                "overwrite": ("BOOLEAN", {"default": False,
                                          "tooltip": "Off: a new _v2/_v3 name is used if the zip (or the .tga "
                                                     "files) already exist."}),
                "preview_frames": ("INT", {"default": 3, "min": 0, "max": 12,
                                           "tooltip": "How many evenly spaced frames to show on this node "
                                                      "(transparent PNG preview). 0 = no preview. Files are not affected."}),
                "save_as_zip": ("BOOLEAN", {"default": True,
                                            "tooltip": "On: ONE .zip file holding all the TGA frames (no loose files). "
                                                       "Off: loose .tga files in the folder. The zip is named "
                                                       "<name of the video file>.zip when source_video is connected, "
                                                       "else <filename_prefix>.zip (_v2, _v3 if it already exists)."}),
            },
            "optional": {
                "source_video": ("VIDEO", {"tooltip": "Connect the Load Video node here. The zip is then named after "
                                                      "the video file (clip.mp4 -> clip.zip). Not connected: the "
                                                      "filename_prefix is used as the zip name."}),
                "zip_name": ("STRING", {"forceInput": True, "tooltip": "Optional: exact zip name (no extension), e.g. from "
                                                                         "Load Video Batch (Folders). Wins over source_video."}),
            },
        }

    RETURN_TYPES = ()
    FUNCTION = "save"
    OUTPUT_NODE = True
    CATEGORY = "image/save"
    DESCRIPTION = ("Saves the batch as a numbered TGA image sequence (with alpha if the batch is RGBA), "
                   "as one zip or as loose files.")

    def _target_dir(self, output_folder, overwrite):
        output_folder = (output_folder or "").strip().strip('"')
        if output_folder:
            base_dir = os.path.abspath(os.path.expandvars(os.path.expanduser(output_folder)))
        else:
            base_dir = os.path.join(os.path.abspath(self.output_dir), "roto_tga")
        folder = base_dir
        if not overwrite:
            n = 1
            while os.path.isdir(folder) and any(f.lower().endswith(".tga") for f in os.listdir(folder)):
                n += 1
                folder = "%s_v%d" % (base_dir, n)
        os.makedirs(folder, exist_ok=True)
        return folder

    def _zip_target(self, output_folder, zip_base, overwrite):
        """Folder is the typed folder itself; the zip is <zip_base>.zip (_v2, _v3 ... if it exists)."""
        output_folder = (output_folder or "").strip().strip('"')
        if output_folder:
            folder = os.path.abspath(os.path.expandvars(os.path.expanduser(output_folder)))
        else:
            folder = os.path.join(os.path.abspath(self.output_dir), "roto_tga")
        os.makedirs(folder, exist_ok=True)
        base = (zip_base or "frame").strip() or "frame"
        path = os.path.join(folder, base + ".zip")
        n = 1
        while not overwrite and os.path.exists(path):
            n += 1
            path = os.path.join(folder, "%s_v%d.zip" % (base, n))
        return folder, path

    def save(self, images, output_folder, filename_prefix, start_number, digits, rle_compression, overwrite,
             preview_frames=3, save_as_zip=True, source_video=None, zip_name=None):
        base = (filename_prefix or "frame").strip() or "frame"
        results = []
        zf = None
        zip_path = None
        part_path = None
        if save_as_zip:
            zip_base = _clean_name(zip_name) or _video_stem(source_video) or base
            folder, zip_path = self._zip_target(output_folder, zip_base, overwrite)
            part_path = zip_path + ".part"   # written under a temp name, renamed when complete
            zf = zipfile.ZipFile(part_path, "w", zipfile.ZIP_DEFLATED, compresslevel=3)
        else:
            folder = self._target_dir(output_folder, overwrite)
        try:
            for i, img in enumerate(images):
                arr = np.clip(255.0 * img.cpu().numpy(), 0, 255).astype(np.uint8)
                if arr.shape[-1] == 4:
                    pil = Image.fromarray(arr, "RGBA")
                else:
                    pil = Image.fromarray(arr[..., :3], "RGB")
                name = "%s_%0*d.tga" % (base, digits, start_number + i)
                if zf is not None:
                    buf = io.BytesIO()
                    pil.save(buf, format="TGA", compression="tga_rle" if rle_compression else None)
                    zf.writestr(name, buf.getvalue())
                else:
                    pil.save(os.path.join(folder, name), format="TGA",
                             compression="tga_rle" if rle_compression else None)
                results.append(name)
        except Exception:
            if zf is not None:
                zf.close()
                try:
                    os.remove(part_path)
                except OSError:
                    pass
            raise
        if zf is not None:
            zf.close()
            try:
                os.replace(part_path, zip_path)
            except PermissionError:
                # the old zip is open in another program (Explorer, 7-Zip ...): keep it, save under a new name
                stem = zip_path[:-4]
                k = 2
                while os.path.exists("%s_v%d.zip" % (stem, k)):
                    k += 1
                zip_path = "%s_v%d.zip" % (stem, k)
                os.replace(part_path, zip_path)
                print("[SaveImageSequenceTGA] target zip was locked, saved as", zip_path)
            print("[SaveImageSequenceTGA] wrote %d TGA frames into ONE zip: %s (%.1f MB)" % (
                len(results), zip_path, os.path.getsize(zip_path) / 1048576.0))
        else:
            print("[SaveImageSequenceTGA] wrote %d frames to %s" % (len(results), folder))
        return {"ui": {"images": self._previews(images, preview_frames, start_number)}}

    @staticmethod
    def _previews(images, preview_frames, start_number):
        ui_images = []
        total = len(images)
        if preview_frames > 0 and total > 0:
            tmp = folder_paths.get_temp_directory()
            os.makedirs(tmp, exist_ok=True)
            tag = "".join(random.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(6))
            n_prev = min(preview_frames, total)
            idxs = sorted(set(int(round(k * (total - 1) / max(n_prev - 1, 1))) for k in range(n_prev)))
            for k in idxs:
                arr = np.clip(255.0 * images[k].cpu().numpy(), 0, 255).astype(np.uint8)
                pil = Image.fromarray(arr, "RGBA") if arr.shape[-1] == 4 else Image.fromarray(arr[..., :3], "RGB")
                # keep the browser preview light: max 1024 px on the long side
                pil.thumbnail((1024, 1024))
                fname = "roto_tga_preview_%s_%05d.png" % (tag, start_number + k)
                pil.save(os.path.join(tmp, fname), format="PNG")
                ui_images.append({"filename": fname, "subfolder": "", "type": "temp"})
        return ui_images


class SpecReadout:
    """Stage monitor: shows W x H | frames | fps (and optional checks) on the node itself while the workflow runs."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE", {"tooltip": "The frames to measure."}),
                "check_padding": ("BOOLEAN", {"default": False,
                                              "tooltip": "Also check: width/height multiple of 32 and frames = 8n+1."}),
            },
            "optional": {
                "fps": ("FLOAT", {"forceInput": True, "tooltip": "Optional: shows fps and duration."}),
                "compare_to": ("IMAGE", {"tooltip": "Optional: shows MATCH / MISMATCH against these frames "
                                                    "(for example the original clip)."}),
            },
            "hidden": {"unique_id": "UNIQUE_ID"},
        }

    RETURN_TYPES = ()
    FUNCTION = "show"
    OUTPUT_NODE = True
    CATEGORY = "image/monitor"
    DESCRIPTION = "Shows the size, frame count and fps of the frames passing through this point of the workflow."

    @staticmethod
    def _text(images, check_padding, fps=None, compare_to=None):
        n, h, w = int(images.shape[0]), int(images.shape[1]), int(images.shape[2])
        line1 = "%d x %d   |   %d frames" % (w, h, n)
        if fps:
            line1 += "   |   %g fps   |   %.2f s" % (float(fps), n / float(fps))
        lines = [line1]
        if check_padding:
            lines.append("W %s32   H %s32   frames %s8n+1" % (
                "OK x" if w % 32 == 0 else "NOT x", "OK x" if h % 32 == 0 else "NOT x",
                "OK = " if n % 8 == 1 else "NOT = "))
        if compare_to is not None:
            cn, ch, cw = int(compare_to.shape[0]), int(compare_to.shape[1]), int(compare_to.shape[2])
            if (cn, ch, cw) == (n, h, w):
                lines.append("MATCHES the original clip (OK)")
            else:
                lines.append("MISMATCH! original is %d x %d | %d frames" % (cw, ch, cn))
        return "\n".join(lines)

    def show(self, images, check_padding, fps=None, compare_to=None, unique_id=None):
        text = self._text(images, check_padding, fps, compare_to)
        print("[SpecReadout] " + text.replace("\n", "  //  "))
        try:
            from server import PromptServer
            if unique_id is not None:
                PromptServer.instance.send_progress_text(text, unique_id)
        except Exception as e:  # monitoring must never break a run
            print("[SpecReadout] could not send text to the UI:", e)
        return {"ui": {"text": [text]}}


NODE_CLASS_MAPPINGS = {"SaveImageSequenceTGA": SaveImageSequenceTGA, "SpecReadout": SpecReadout}
NODE_DISPLAY_NAME_MAPPINGS = {"SaveImageSequenceTGA": "Save Image Sequence (TGA, RGBA)",
                              "SpecReadout": "Spec Readout (size / frames / fps)"}
