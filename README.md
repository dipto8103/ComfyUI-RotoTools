# ComfyUI-RotoTools

Small, focused nodes for **roto / alpha-matte workflows** in ComfyUI (built around LTX alpha-gen, but they work with any `IMAGE` batch).

## Nodes

### Save Image Sequence (TGA, RGBA)  — `image/save`
Saves an `IMAGE` batch as numbered **TGA** frames, keeping a real **alpha channel** when the batch is RGBA (feed it from *Join Image with Alpha*).

- **One zip instead of thousands of loose files** (`save_as_zip`, on by default).
- **Zip named after the source video**: connect the *Load Video* node to `source_video` and `clip.mp4` becomes `clip.zip`. Without it, `filename_prefix` is used.
- **One folder for every zip**: type or paste `output_folder` once; every run drops its zip there.
- Never overwrites an earlier result unless you turn `overwrite` on (`_v2`, `_v3` ...). If the old zip is open in Explorer / 7-Zip, the new one is saved under a new name instead of failing.
- Zip is written to `*.zip.part` and renamed when complete, so a crash never leaves a half-written zip that looks finished.
- Lossless RLE compression option, start number, zero padding, and a transparent preview of a few frames on the node.
- Optional `zip_name` input: an exact zip name from another node (wins over `source_video`).
- Turn `save_as_zip` off to get loose `.tga` files.

### Spec Readout (size / frames / fps)  — `image/monitor`
Drop it at any stage of a workflow to see `W x H | frames | fps | seconds` printed on the node itself while the graph runs.
Optional padding check (width/height multiple of 32, frames = 8n+1) and an optional `compare_to` input that shows **MATCHES** / **MISMATCH** against another batch (for example the original clip).

### Load Video Batch (Folders)  — `image/video`
Built for hundreds of clips in one go. Type or paste a **parent folder**; every video in its sub-folders is found automatically (natural sort, so `clip2` comes before `clip10`) and **one video per run** is sent on as a `VIDEO`.

1. Replace *Load Video* with this node and connect `video` where Load Video went.
2. Connect its `zip_name` output to the saver's `zip_name` input (zips are named `subfolder__clip`, so same-named clips in different folders never clash).
3. Leave `index` on **increment** and set Run's **batch count** to the number of videos (the node shows `n / total` while it runs). ComfyUI queues them one after another.
4. **Resume**: put the zips folder in `zips_folder`. Any video whose zip already exists is skipped quickly, so re-queueing after a crash or a stop only does the missing ones.

Outputs: `video`, `zip_name`, `video_path`, `index`, `total`.

## Install

**ComfyUI-Manager / Registry** (once published): search for `ComfyUI-RotoTools`.

**Manual:**
```
cd ComfyUI/custom_nodes
git clone https://github.com/dipto8103/ComfyUI-RotoTools
```
Restart ComfyUI. No extra dependencies (uses Pillow and NumPy, which ComfyUI already ships).

## Notes on alpha

TGA stores straight (non-premultiplied) alpha. Make sure the alpha you feed into *Join Image with Alpha* has the direction your matte uses (ComfyUI's node treats its input as an inverted mask, so pass an inverted mask if your matte is white = subject).

## Development

```
pip install -r requirements-dev.txt
pytest
```
The tests stub `folder_paths`, so ComfyUI itself is not needed.

## License

MIT, see [LICENSE](LICENSE).
