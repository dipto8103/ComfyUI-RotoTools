import importlib
import os
import sys

import pytest


@pytest.fixture
def batch(nodes_mod):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return importlib.import_module("batch")


@pytest.fixture
def tree(tmp_path):
    for rel in ["A/clip1.mp4", "A/clip10.mp4", "A/clip2.mov", "B/deep/x.mkv", "B/notes.txt", "C/.hidden.mp4",
                ".git/v.mp4", "top.mp4"]:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
    return tmp_path


def test_scan_finds_sorts_naturally(batch, tree):
    root, vids = batch.scan_videos(str(tree))
    rel = [os.path.relpath(v, root).replace(os.sep, "/") for v in vids]
    assert rel == ["A/clip1.mp4", "A/clip2.mov", "A/clip10.mp4", "B/deep/x.mkv", "top.mp4"]
    assert not any("hidden" in r or ".git" in r or r.endswith(".txt") for r in rel)


def test_scan_not_recursive(batch, tree):
    root, vids = batch.scan_videos(str(tree), recursive=False)
    assert [os.path.basename(v) for v in vids] == ["top.mp4"]


def test_scan_missing_folder(batch, tmp_path):
    with pytest.raises(FileNotFoundError):
        batch.scan_videos(str(tmp_path / "nope"))


def test_zip_name(batch, tree):
    root = str(tree)
    assert batch.zip_name_for(root, os.path.join(root, "B", "deep", "x.mkv"), True) == "B__deep__x"
    assert batch.zip_name_for(root, os.path.join(root, "B", "deep", "x.mkv"), False) == "x"
    assert batch.zip_name_for(root, os.path.join(root, "top.mp4"), True) == "top"


def run(batch, monkeypatch, tree, **kw):
    monkeypatch.setattr(batch, "_make_video", lambda p: ("VIDEO", p))
    class B:  # stand-in for ExecutionBlocker
        def __init__(self, v): self.v = v
    monkeypatch.setattr(batch, "_blocker", lambda: B)
    args = dict(batch_folder=str(tree), index=0, use_subfolder_in_name=True, skip_if_zip_exists=True,
                zips_folder="", extensions=batch.DEFAULT_EXTS, recursive=True)
    args.update(kw)
    return batch.LoadVideoBatchFolders().load(**args), B


def test_load_each_index(batch, monkeypatch, tree):
    _, vids = batch.scan_videos(str(tree))
    for i, v in enumerate(vids):
        (video, name, path, idx, total), _ = run(batch, monkeypatch, tree, index=i)
        assert video == ("VIDEO", v) and path == v and idx == i and total == len(vids)


def test_index_past_end_is_blocked_not_error(batch, monkeypatch, tree):
    out, B = run(batch, monkeypatch, tree, index=99)
    assert all(isinstance(o, B) for o in out)


def test_skip_if_zip_exists(batch, monkeypatch, tree, tmp_path):
    zips = tmp_path / "zips"
    zips.mkdir()
    _, vids = batch.scan_videos(str(tree))
    root = str(tree)
    name = batch.zip_name_for(root, vids[0], True)
    (zips / (name + ".zip")).write_bytes(b"z")
    out, B = run(batch, monkeypatch, tree, index=0, zips_folder=str(zips))
    assert all(isinstance(o, B) for o in out)
    out, B = run(batch, monkeypatch, tree, index=1, zips_folder=str(zips))
    assert not isinstance(out[0], B)
    out, B = run(batch, monkeypatch, tree, index=0, zips_folder=str(zips), skip_if_zip_exists=False)
    assert not isinstance(out[0], B)


def test_empty_folder_errors(batch, monkeypatch, tmp_path):
    with pytest.raises(ValueError):
        run(batch, monkeypatch, tmp_path)


def test_saver_zip_name_override(nodes_mod, make_frames, tmp_path):
    from helpers import FakeVideo
    node = nodes_mod.SaveImageSequenceTGA()
    node.save(images=make_frames(1), output_folder=str(tmp_path), filename_prefix="frame", start_number=0, digits=5,
              rle_compression=True, overwrite=False, preview_frames=0, save_as_zip=True,
              source_video=FakeVideo("/x/clip.mp4"), zip_name="A__clip")
    assert os.listdir(tmp_path) == ["A__clip.zip"]
