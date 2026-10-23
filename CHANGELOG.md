# Changelog

All notable changes are listed here. Versions follow [Semantic Versioning](https://semver.org/):
MAJOR = breaking change (renamed/removed node or input), MINOR = new node or backward-compatible feature, PATCH = bug fix.

## [0.1.0] - 2026-10-23
### Added
- **Save Image Sequence (TGA, RGBA)**: RGBA TGA frames, saved as one zip (default) or loose files; zip named after the source video or an exact `zip_name`; no overwrite (`_v2`, `_v3`); locked-zip fallback.
- **Spec Readout (size / frames / fps)**: on-node size / frames / fps display with padding and match checks.
- **Load Video Batch (Folders)**: loads one video per run from a folder of folders, with an `n / total` readout and skip-if-zip-exists resume.
