# Changelog

All notable changes are listed here. Versions follow [Semantic Versioning](https://semver.org/):
MAJOR = breaking change (renamed/removed node or input), MINOR = new node or backward-compatible feature, PATCH = bug fix.

## [0.4.0] - 2026-10-29
### Added
- **Roto Review (A/B)** (`image/video`): a preview-only review player for roto work, based on [ComfyUI-KM-VideoReview](https://github.com/KasunMalinda/ComfyUI-KM-VideoReview) by Kasun Malinda (MIT; notice kept in the copied files and in `LICENSE-KM-VideoReview`). All of the original player is kept (wipe H/V, side by side, difference, A/B flip, frame-accurate transport, loop/bounce, fullscreen, exposure/gamma, info). Added on top:
  - an **RGBA B** (the roto) keeps its alpha: show it over a background (red, green, blue, black, white, grey, checkerboard), as the **alpha matte**, or as is
  - a **history strip** of the shots reviewed in this session (last 40; older preview frames are deleted from temp); click one to review it again
  - **⤓ Download** made on request: roto on background, alpha matte, original | roto side by side, original (mp4) or roto with alpha (ProRes 4444 .mov), saved by the browser; nothing goes to ComfyUI's output folder
  - optional `name` input (e.g. `zip_name`) for the history and download names

## [0.3.6] - 2026-10-29
### Changed
- **Load Video Batch (Folders)** preview: the ✕ that leaves a shot out is a large round button in the middle of the tile (on hover), easier to hit.
- The **Refresh** button is gone; the preview re-reads the folders by itself when the list changes, after every run, and when you come back to the ComfyUI tab (e.g. after adding shots in Explorer). Only **Clear** is left.
- The "… to do: set Run batch count to …" line wraps onto a second line instead of being cut off.

## [0.3.5] - 2026-10-27
### Changed
- **Load Video Batch (Folders)**: each preview tile shows the shot name with its **duration and frame count** (`55 · 2.96 s · 74 frames`) instead of the list number and the name (which looked doubled when shots are named by number). The list number is in the tile's tooltip. Read from the video header only, once the tile is on screen.

## [0.3.4] - 2026-10-27
### Changed
- **Load Video Batch (Folders)**: with `skip_if_zip_exists` on (the default), every run now takes **the next video that has no zip yet**, whatever `index` says. Cancelled queues, restarts or a queue that ran ahead can no longer skip videos (a 372-video batch had skipped 84). A video whose run left no zip is tried once more; after a second try it is passed over (until ComfyUI restarts or Clear), so one broken video cannot use up the queue. Every decision is logged as `[LoadVideoBatchFolders] …` in ComfyUI's console. `index` is only used with `skip_if_zip_exists` off (to redo a video).
### Added
- ✕ on every preview tile leaves that video out of the batch (greyed, **↺ undo** puts it back), saved with the workflow. The bar counts what is left to do.
- Browser console lines `[RotoTools] …` for drops, scans, Clear and runs.
### Fixed
- After **Clear**, dropping a video that was in the earlier list did nothing (the preview still remembered the old list) until the page was reloaded.
- **Clear** now empties everything: the list, the left-out videos, the "Last run" line, `index` and the failed-video memory.
- The preview asks for its scan with a POST, so very long lists always fit.

## [0.3.3] - 2026-10-23
### Fixed
- **Load Video Batch (Folders)**: `index` now goes back to 0 when the list of folders / videos changes, and when it is past the last video. Before, it kept counting from the previous batch, so a new list ran as "index 9 is past the last video" and nothing was processed. Works with both "control after generate" and "control before generate".
- An empty list now says "The batch list is empty: add folders or drop videos …" instead of "No videos … found under (no folder)".

## [0.3.2] - 2026-10-23
### Fixed
- **Load Video Batch (Folders)**: the "n / total" run status is now one slim line in the preview ("Last run: …") instead of ComfyUI's large progress-text box under the node.

## [0.3.1] - 2026-10-23
### Added
- **Load Video Batch (Folders)**: single videos. Drop videos onto the node (they are copied into `ComfyUI\input\rototools_drops`, like the normal Load Video does) or list video files in `batch_folder`, mixed freely with folders. Their zips go straight into the save folder (`SAVE FOLDER\clip.zip`); same-named videos from different places get their folder added (`clip (misc)`), and each zip name stays with its video from run to run (hidden `.rototools_singles.json`). ✕ on a single video's tile removes it.

## [0.3.0] - 2026-10-23
### Added
- **Load Video Batch (Folders)**: **+ Add folders…** button on the preview opens the system folder dialog (several folders at once, can be opened again to add folders from other drives); **✕ remove** per folder and **Clear**.
- `batch_folder` is now a multi-line box (one folder per line) and accepts Explorer's *Copy as path* lists.
### Changed
- Another input folder with the same name now gets its location added (`y\ep93` -> `ep93 (y)`) instead of `ep93_2`. Each output folder records its input folder (hidden `.rototools_source` file), so a folder keeps the same output folder from run to run and never writes into another folder's.

## [0.2.0] - 2026-10-23
### Added
- **Load Video Batch (Folders)**: several folders at once (comma separated); a preview grid of every detected video on the node (hover = play, click = full view, resizable tiles, done marks); new `zip_folder` output.
### Changed (Load Video Batch only; the node was new in 0.1.0)
- Each input folder gets its own output folder named after it (`output\ep93\shot5.zip`; a repeated name becomes `ep93_2`), and zips are named after the video file only.
- `zips_folder` is now `output_folder` (the parent of those folders); `use_subfolder_in_name` was removed.
  Workflows saved with the 0.1.0 batch node need this node re-added.

## [0.1.0] - 2026-10-23
### Added
- **Save Image Sequence (TGA, RGBA)**: RGBA TGA frames, saved as one zip (default) or loose files; zip named after the source video or an exact `zip_name`; no overwrite (`_v2`, `_v3`); locked-zip fallback.
- **Spec Readout (size / frames / fps)**: on-node size / frames / fps display with padding and match checks.
- **Load Video Batch (Folders)**: loads one video per run from a folder of folders, with an `n / total` readout and skip-if-zip-exists resume.
