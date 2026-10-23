import io
import os
import zipfile

import pytest
from PIL import Image

from helpers import FakeVideo


def run_save(mod, frames, folder, **kw):
    node = mod.SaveImageSequenceTGA()
    args = dict(images=frames, output_folder=str(folder), filename_prefix="frame", start_number=0, digits=5,
                rle_compression=True, overwrite=False, preview_frames=0, save_as_zip=True)
    args.update(kw)
    return node.save(**args)


def zips(folder):
    return sorted(f for f in os.listdir(folder) if f.endswith(".zip"))


# ---------- video stem ----------
def test_video_stem_from_path(nodes_mod):
    assert nodes_mod._video_stem(FakeVideo("C:/clips/roto_04_curly.mp4")) == "roto_04_curly"


def test_video_stem_sanitises(nodes_mod):
    assert nodes_mod._video_stem(FakeVideo("/x/we:ird*name?.mp4")) == "we_ird_name_"


@pytest.mark.parametrize("src", [None, io.BytesIO(b"x"), RuntimeError("boom")])
def test_video_stem_none_cases(nodes_mod, src):
    video = None if src is None else FakeVideo(src)
    assert nodes_mod._video_stem(video) is None


# ---------- zip saving ----------
def test_zip_contains_all_frames_rgba(nodes_mod, make_frames, tmp_path):
    run_save(nodes_mod, make_frames(4), tmp_path)
    assert zips(tmp_path) == ["frame.zip"]
    assert not [f for f in os.listdir(tmp_path) if f.endswith(".part") or f.endswith(".tga")]
    with zipfile.ZipFile(tmp_path / "frame.zip") as zf:
        names = zf.namelist()
        assert names == ["frame_%05d.tga" % i for i in range(4)]
        img = Image.open(io.BytesIO(zf.read(names[1])))
        assert img.mode == "RGBA" and img.size == (48, 32)
        assert img.getpixel((0, 0))[3] == 0 and img.getpixel((12, 12))[3] == 255


def test_zip_named_after_video(nodes_mod, make_frames, tmp_path):
    run_save(nodes_mod, make_frames(2), tmp_path, source_video=FakeVideo("/clips/shot_07.mov"))
    assert zips(tmp_path) == ["shot_07.zip"]


def test_second_run_gets_v2_and_overwrite_replaces(nodes_mod, make_frames, tmp_path):
    run_save(nodes_mod, make_frames(2), tmp_path)
    run_save(nodes_mod, make_frames(2), tmp_path)
    assert zips(tmp_path) == ["frame.zip", "frame_v2.zip"]
    run_save(nodes_mod, make_frames(3), tmp_path, overwrite=True)
    assert zips(tmp_path) == ["frame.zip", "frame_v2.zip"]
    with zipfile.ZipFile(tmp_path / "frame.zip") as zf:
        assert len(zf.namelist()) == 3


def test_creates_missing_folder(nodes_mod, make_frames, tmp_path):
    target = tmp_path / "a" / "b"
    run_save(nodes_mod, make_frames(1), target)
    assert zips(target) == ["frame.zip"]


def test_rgb_batch_saved_as_rgb(nodes_mod, make_frames, tmp_path):
    run_save(nodes_mod, make_frames(1, c=3), tmp_path)
    with zipfile.ZipFile(tmp_path / "frame.zip") as zf:
        assert Image.open(io.BytesIO(zf.read(zf.namelist()[0]))).mode == "RGB"


def test_loose_files_mode(nodes_mod, make_frames, tmp_path):
    run_save(nodes_mod, make_frames(3), tmp_path / "out", save_as_zip=False)
    assert sorted(os.listdir(tmp_path / "out")) == ["frame_00000.tga", "frame_00001.tga", "frame_00002.tga"]


def test_loose_files_mode_does_not_overwrite(nodes_mod, make_frames, tmp_path):
    run_save(nodes_mod, make_frames(1), tmp_path / "out", save_as_zip=False)
    run_save(nodes_mod, make_frames(1), tmp_path / "out", save_as_zip=False)
    assert os.path.isdir(tmp_path / "out_v2")


def test_start_number_and_digits(nodes_mod, make_frames, tmp_path):
    run_save(nodes_mod, make_frames(2), tmp_path, start_number=10, digits=3)
    with zipfile.ZipFile(tmp_path / "frame.zip") as zf:
        assert zf.namelist() == ["frame_010.tga", "frame_011.tga"]


def test_failed_run_leaves_no_part_file(nodes_mod, make_frames, tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("disk full")
    monkeypatch.setattr(Image.Image, "save", boom)
    with pytest.raises(RuntimeError):
        run_save(nodes_mod, make_frames(2), tmp_path)
    assert os.listdir(tmp_path) == []


def test_preview_frames_written_to_temp(nodes_mod, make_frames, tmp_path):
    res = run_save(nodes_mod, make_frames(5), tmp_path, preview_frames=3)
    assert len(res["ui"]["images"]) == 3
    assert all(i["type"] == "temp" for i in res["ui"]["images"])


# ---------- spec readout ----------
def test_readout_basic(nodes_mod, make_frames):
    t = nodes_mod.SpecReadout._text(make_frames(9, 64, 96), False, fps=24.0)
    assert t.startswith("96 x 64   |   9 frames   |   24 fps")
    assert "0.38 s" in t


def test_readout_padding_check(nodes_mod, make_frames):
    ok = nodes_mod.SpecReadout._text(make_frames(9, 64, 96), True)
    bad = nodes_mod.SpecReadout._text(make_frames(10, 65, 96), True)
    assert "W OK x32" in ok and "H OK x32" in ok and "frames OK = 8n+1" in ok
    assert "H NOT x32" in bad and "frames NOT = 8n+1" in bad


def test_readout_compare(nodes_mod, make_frames):
    a, b = make_frames(9, 64, 96), make_frames(9, 64, 96)
    assert "MATCHES" in nodes_mod.SpecReadout._text(a, False, compare_to=b)
    assert "MISMATCH" in nodes_mod.SpecReadout._text(a, False, compare_to=make_frames(9, 64, 128))


def test_mappings(nodes_mod):
    assert set(nodes_mod.NODE_CLASS_MAPPINGS) == set(nodes_mod.NODE_DISPLAY_NAME_MAPPINGS)
