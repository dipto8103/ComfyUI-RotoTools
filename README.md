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
Built for hundreds of clips in one go. Give it **one or more folders**; every video in their sub-folders is found automatically (natural sort, so `shot2` comes before `shot10`) and **one video per run** is sent on as a `VIDEO`.

```
batch_folder  = x\ep93, x\ep94          output_folder = D:\rotos
x\ep93\shot1\shot1.mp4   ->  D:\rotos\ep93\shot1.zip
x\ep94\shot1\shot1.mp4   ->  D:\rotos\ep94\shot1.zip
y\ep93\shot1\shot1.mp4   ->  D:\rotos\ep93 (y)\shot1.zip   (another folder named ep93)
```

**Adding folders** (any mix of drives):
- **+ Add folders…** on the preview opens the normal Windows folder dialog (macOS / Linux: the system one). Ctrl / Shift click to pick several. Open it again to add more from another drive; folders already in the list are not added twice.
- **✕ remove** on a folder's header takes it out of the batch; **Clear** empties the list (nothing is deleted on disk).
- Or type / paste into `batch_folder`: one folder per line or comma separated. Explorer's *Copy as path* (select the folders, Ctrl+Shift+C) can be pasted as is.
- The dialog opens on the computer running ComfyUI. Dragging folders onto the node is not possible: browsers never give a web page the full path of a dropped folder.

**Single videos** (no folder needed), mixed freely with folders:
- **Drop video files onto the node.** Like the normal *Load Video*, each dropped video is copied once into `ComfyUI\input\rototools_drops` and that copy is used. The same video dropped again reuses its copy.
- Or list video files in `batch_folder` like folders (no copy is made).
- Their zips go **straight into the save folder**: `SAVE FOLDER\clip_a.zip`. Two videos with the same name from different places become `clip_a` and `clip_a (misc)` (misc = the folder the second one sits in), and each keeps its zip name from run to run.
- The big ✕ in the middle of a single video's tile (hover) takes it out of the batch; **✕ remove all** on the *Single videos* header removes them all.

```
batch_folder  = D:\clips\clip_a.mp4          output_folder = D:\rotos
                x\ep93
D:\clips\clip_a.mp4      ->  D:\rotos\clip_a.zip
x\ep93\shot1\shot1.mp4   ->  D:\rotos\ep93\shot1.zip
```

1. Replace *Load Video* with this node and connect `video` where Load Video went.
2. Connect `zip_name` to the saver's `zip_name` input and `zip_folder` to the saver's `output_folder`.
   Each input folder gets its own folder inside `output_folder`, named after it; zips are named after the video file. Another input folder with the same name gets its location added: `y\ep93` becomes `ep93 (y)`. Each output folder remembers its input folder (a hidden `.rototools_source` file), so a folder keeps the same output folder from run to run, whether it is batched with the other ep93 or on its own. The preview shows the full path of each. Two videos with the same name inside one folder become `take`, `take_2`.
3. Set Run's **batch count** to the number "to do" on the preview bar (more is fine: extra runs are skipped in a moment). With `skip_if_zip_exists` on (default), **every run takes the next video that has no zip yet**, so a cancelled queue, a crash or a restart never skips videos: just press Run again. A slim "Last run: n / total …" line shows where the batch is.
4. A video whose run left no zip (failed or cancelled) is tried once more; after a second try it is passed over until ComfyUI restarts or you press Clear, so one broken video cannot use up the queue. Every decision is printed as `[LoadVideoBatchFolders] …` in ComfyUI's console.
5. **Leave shots out**: the big ✕ in the middle of a tile (hover) greys it out and it is not queued; **↺ undo** puts it back. This is saved with the workflow. **Clear** empties the node completely (list, left-out shots, last-run line).
6. `index` only matters with `skip_if_zip_exists` off: then the video at `index` is processed even if its zip exists (to redo one).

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
