# Changelog

All notable changes are listed here. Versions follow [Semantic Versioning](https://semver.org/):
MAJOR = breaking change (renamed/removed node or input), MINOR = new node or backward-compatible feature, PATCH = bug fix.

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
