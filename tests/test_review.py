import importlib
import os
import sys

import numpy as np
import pytest
from PIL import Image

from helpers import FakeTensor


@pytest.fixture
def review(nodes_mod):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    mod = importlib.import_module("review")
    mod._HISTORY.clear()
    return mod


def frames(n=3, h=32, w=48, c=3):
    arr = np.zeros((n, h, w, c), dtype=np.float32)
    arr[..., 0] = 0.8
    if c == 4:
        arr[..., 3] = 0.0
        arr[:, 8:24, 12:36, 3] = 1.0   # opaque subject in the middle
        arr[:, 8:24, 36, 3] = 0.5      # a soft edge
    return FakeTensor(arr)


def test_roto_b_keeps_alpha_and_ui(review):
    out = review.RotoReview().review(frames(), frames(c=4), preview_format="jpeg (low quality)",
                                     name="ep93/shot5", **{"Base fps": 25.0, "Playback resolution": "1:1"})
    ui = out["ui"]
    assert ui["b_alpha"] == [True] and ui["name"] == ["ep93/shot5"] and ui["file"] == ["ep93_shot5"]
    assert len(ui["run_id"][0]) == 6
    assert ui["a_frames"][0]["filename"].endswith(".jpg") and ui["b_frames"][0]["filename"].endswith(".jpg")
    b0 = Image.open(review._frame_path(ui["b_frames"][0]))
    m0 = Image.open(review._frame_path(ui["b_masks"][0]))
    assert b0.mode == "RGB" and len(ui["b_masks"]) == len(ui["b_frames"]) == 3
    assert m0.mode == "LA" and m0.size == b0.size
    assert [m0.getpixel(p) for p in ((0, 0), (24, 16), (36, 16))] == [(255, 0), (255, 255), (255, 128)]
    assert ui["fps"] == [25.0] and ui["a_size"] == [[48, 32]]
    assert review.history()[0]["run_id"] == ui["run_id"]


def test_lightest_preview_by_default_but_full_resolution_alpha(review):
    inputs = review.RotoReview.INPUT_TYPES()["optional"]
    assert inputs["Playback resolution"][1]["default"] == "0.25"
    assert inputs["preview_format"][1]["default"] == "jpeg (low quality)"
    assert inputs["quality"][1]["default"] == 50
    ui = review.RotoReview().review(frames(2, 64, 96), frames(2, 64, 96, c=4))["ui"]   # node defaults
    assert Image.open(review._frame_path(ui["a_frames"][0])).size == (24, 16)          # preview: 1/4
    m0 = Image.open(review._frame_path(ui["m_frames"][0]))
    assert m0.mode == "L" and m0.size == (96, 64)                                       # alpha: full size
    assert len(ui["m_frames"]) == 2


def test_no_preview_ever_uses_the_webp_encoder(review, monkeypatch):
    # its native encoder crashed ComfyUI (access violation) on long batches
    real = Image.Image.save
    used = []
    monkeypatch.setattr(Image.Image, "save", lambda self, fp, format=None, **k: (used.append(format),
                                                                                 real(self, fp, format=format, **k))[1])
    review.RotoReview().review(frames(4, 64, 96), frames(4, 64, 96, c=4))
    review.RotoReview().review(frames(4, 64, 96), frames(4, 64, 96, c=4), preview_format="jpeg (low quality)",
                               **{"Playback resolution": "1:1"})
    assert set(used) == {"JPEG", "PNG"} and len(used) == 2 * 4 * 4
    # the choices of today, the ones of older workflows and nonsense
    for fmt in list(review.RotoReview.INPUT_TYPES()["optional"]["preview_format"][0]) + [
            "webp (mid quality)", "webp lossless (best quality)", "whatever", None]:
        review.RotoReview().review(frames(2), frames(2, c=4), preview_format=fmt)
        review.RotoReview().review(frames(2), frames(2), preview_format=fmt)
    assert set(used) == {"JPEG", "PNG"}


def test_formats_of_older_workflows_still_run(review):
    R = review.RotoReview
    assert list(R.INPUT_TYPES()["optional"]["preview_format"][0]) == ["jpeg (low quality)", "png (best quality)"]
    ext = lambda f: R().review(frames(1), frames(1, c=4), preview_format=f)["ui"]["b_frames"][0]["filename"][-4:]
    assert ext("webp (mid quality)") == ".jpg" and ext("webp lossless (best quality)") == ".png"
    import inspect       # ComfyUI skips the list check of inputs that VALIDATE_INPUTS takes
    assert "preview_format" in inspect.signature(R.VALIDATE_INPUTS).parameters
    assert R.VALIDATE_INPUTS("webp (mid quality)") is True


def test_after_save_is_only_a_wire(review):
    assert review.RotoReview.INPUT_TYPES()["optional"]["after_save"][0] == "STRING"
    ui = review.RotoReview().review(frames(1), frames(1, c=4), after_save="X:/out/shot1.zip", name="s")["ui"]
    assert ui["name"] == ["s"] and len(ui["a_frames"]) == 1


def test_scaled_roto_keeps_its_edge_colours(review):
    # a red subject on a blue background that the matte hides: no blue in the visible part, no black border
    arr = np.zeros((1, 64, 96, 4), dtype=np.float32)
    arr[..., 2] = 1.0
    arr[:, 16:48, 22:70] = (1.0, 0.0, 0.0, 1.0)
    ui = review.RotoReview().review(FakeTensor(arr[..., :3]), FakeTensor(arr), preview_format="png (best quality)")["ui"]
    rgb = np.asarray(Image.open(review._frame_path(ui["b_frames"][0])).convert("RGB")).astype(int)
    a = np.asarray(Image.open(review._frame_path(ui["b_masks"][0])))[..., 1].astype(int)
    solid = a > 40
    assert solid.sum() > 50 and rgb[solid][:, 0].min() > 200 and rgb[solid][:, 2].max() < 60
    assert (rgb[a == 0][:, 2] > 200).mean() > 0.9        # hidden part: the plate, not black


@pytest.mark.parametrize("err", [OSError(28, "No space left on device"), MemoryError(), RuntimeError("can't start new thread")])
def test_preview_problems_do_not_stop_the_batch(review, monkeypatch, capsys, err):
    def full(*a, **k):
        raise err
    monkeypatch.setattr(Image.Image, "save", full)
    out = review.RotoReview().review(frames(2), frames(2, c=4), name="s1")
    assert out["ui"]["a_frames"] == [] and review.history() == []
    assert "the batch goes on" in capsys.readouterr().out


def test_plain_b_and_single_stream_unchanged(review):
    ui = review.RotoReview().review(frames(), frames(), preview_format="png (best quality)")["ui"]
    assert ui["b_alpha"] == [False] and ui["b_frames"][0]["filename"].endswith(".png") and ui["m_frames"] == []
    assert ui["b_masks"] == []
    ui = review.RotoReview().review(frames())["ui"]
    assert ui["b_frames"] == [] and ui["b_size"] == [] and ui["m_frames"] == []


def test_history_keeps_every_shot(review):
    uis = [review.RotoReview().review(frames(1), frames(1, c=4), name="s%d" % i)["ui"] for i in range(60)]
    assert len(review.history()) == 60 and review.history()[0]["name"] == ["s59"]
    assert os.path.exists(review._frame_path(uis[0]["m_frames"][0]))


def test_history_drops_the_oldest_only_when_the_drive_is_low(review, monkeypatch):
    uis = [review.RotoReview().review(frames(1), frames(1, c=4), name="s%d" % i)["ui"] for i in range(3)]
    monkeypatch.setattr(review, "_free_gb", lambda: 5.0)                  # below MIN_FREE_GB
    review.RotoReview().review(frames(1), frames(1, c=4), name="s3")
    assert [h["name"][0] for h in review.history()] == ["s3"]            # the newest is always kept
    for ui in uis:
        assert not os.path.exists(review._frame_path(ui["a_frames"][0]))
        assert not os.path.exists(review._frame_path(ui["m_frames"][0]))
        assert not os.path.exists(review._frame_path(ui["b_masks"][0]))


def test_alpha_matte_download_is_full_resolution_and_exact(review):
    av = pytest.importorskip("av")
    ui = review.RotoReview().review(frames(5, 64, 96), frames(5, 64, 96, c=4), name="shot5",
                                    **{"Base fps": 25.0, "Playback resolution": "0.25"})["ui"]
    path, name = review.make_download(ui["run_id"][0])
    assert name == "shot5_alpha.mp4"
    with av.open(path) as c:
        got = list(c.decode(video=0))
        assert len(got) == 5 and (got[0].width, got[0].height) == (96, 64)      # full size, not the 1/4 preview
        y = got[0].to_ndarray(format="rgb24")[..., 0].astype(int)
        assert y[50, 80] < 25 and y[16, 24] > 230                               # black background, white subject
        assert 100 < y[16, 36] < 155                                            # the soft edge stays grey


def test_labels_from_load_video_batch(review):
    pytest.importorskip("av")
    names = ["folderA / shot6", "folderB / shot6", "folderA (c) / shot6", "single / shot6 (misc)"]
    uis = [review.RotoReview().review(frames(1), frames(1, c=4), name=n)["ui"] for n in names]
    assert [u["name"][0] for u in uis] == names                       # history shows them as they are
    files = [review.make_download(u["run_id"][0])[1] for u in uis]
    assert files == ["folderA_shot6_alpha.mp4", "folderB_shot6_alpha.mp4", "folderA (c)_shot6_alpha.mp4",
                     "single_shot6 (misc)_alpha.mp4"]                 # all different


def test_download_errors(review):
    with pytest.raises(KeyError):
        review.make_download("nope")
    ui = review.RotoReview().review(frames(1), frames(1))["ui"]
    with pytest.raises(ValueError):
        review.make_download(ui["run_id"][0])            # B has no alpha
    ui = review.RotoReview().review(frames(1), frames(1, c=4))["ui"]
    with pytest.raises(ValueError):
        review.make_download(ui["run_id"][0], "roto_alpha")   # only the matte is offered
