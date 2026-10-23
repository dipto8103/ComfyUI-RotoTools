# Changelog

All notable changes are listed here. Versions follow [Semantic Versioning](https://semver.org/):
MAJOR = breaking change (renamed/removed node or input), MINOR = new node or backward-compatible feature, PATCH = bug fix.

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
