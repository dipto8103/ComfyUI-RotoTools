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
Built for hundreds of clips in one go. Type or paste **one or more folders, comma separated** (`x\ep93, x\ep94`); every video in their sub-folders is found automatically (natural sort, so `shot2` comes before `shot10`) and **one video per run** is sent on as a `VIDEO`.

```
batch_folder  = x\ep93, x\ep94          output_folder = D:\rotos
x\ep93\shot1\shot1.mp4   ->  D:\rotos\ep93\shot1.zip
x\ep94\shot1\shot1.mp4   ->  D:\rotos\ep94\shot1.zip
y\ep93\shot1\shot1.mp4   ->  D:\rotos\ep93_2\shot1.zip   (second folder named ep93)
```

1. Replace *Load Video* with this node and connect `video` where Load Video went.
2. Connect `zip_name` to the saver's `zip_name` input and `zip_folder` to the saver's `output_folder`.
   Each input folder gets its own folder inside `output_folder`, named after it; zips are named after the video file. Two input folders with the same name become `ep93`, `ep93_2` (the preview shows the full path of each). Two videos with the same name inside one folder become `take`, `take_2`.
3. Leave `index` on **increment** and set Run's **batch count** to the number of videos (shown on the preview bar; the node shows `n / total` while it runs). ComfyUI queues them one after another.
4. **Resume**: with `skip_if_zip_exists` on, any video whose zip is already in its folder is skipped quickly, so re-queueing after a crash or a stop only does the missing ones.

**Preview grid**: the node shows a thumbnail of every detected video, grouped per input folder (with its full path and output folder). Hover a tile to play it, click it for a full view in the node (✕ to go back to the grid). Resize the node or use the slider to change the tile size. ✓ = zip already exists; the yellow frame is the video of the last run. Videos the browser cannot play (some .mov/.mkv/.avi codecs) still get a thumbnail.

Outputs: `video`, `zip_name`, `video_path`, `index`, `total`, `zip_folder`.

## Install

**Comfy Registry / ComfyUI-Manager** (once published): search for `RotoTools` in ComfyUI-Manager, or run `comfy node install rototools`.

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

## Versions

[Semantic Versioning](https://semver.org/). See [CHANGELOG.md](CHANGELOG.md); maintainers see [RELEASING.md](RELEASING.md).

## License

MIT, see [LICENSE](LICENSE).
