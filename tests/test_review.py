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
    return FakeTensor(arr)


def test_roto_b_keeps_alpha_and_ui(review):
    out = review.RotoReview().review(frames(), frames(c=4), preview_format="jpeg (low quality)",
                                     name="ep93/shot5", **{"Base fps": 25.0})
    ui = out["ui"]
    assert ui["b_alpha"] == [True] and ui["name"] == ["ep93_shot5"] and len(ui["run_id"][0]) == 6
    assert ui["a_frames"][0]["filename"].endswith(".jpg") and ui["b_frames"][0]["filename"].endswith(".webp")
    b0 = Image.open(review._frame_path(ui["b_frames"][0]))
    assert b0.mode == "RGBA" and b0.getpixel((0, 0))[3] == 0 and b0.getpixel((24, 16))[3] == 255
    assert ui["fps"] == [25.0] and ui["a_size"] == [[48, 32]]
    assert review.history()[0]["run_id"] == ui["run_id"]


def test_plain_b_and_single_stream_unchanged(review):
    ui = review.RotoReview().review(frames(), frames(), preview_format="webp (mid quality)")["ui"]
    assert ui["b_alpha"] == [False] and ui["b_frames"][0]["filename"].endswith(".webp")
    ui = review.RotoReview().review(frames())["ui"]
    assert ui["b_frames"] == [] and ui["b_size"] == []


def test_history_keeps_the_last_runs_and_deletes_older_frames(review, monkeypatch):
    monkeypatch.setattr(review, "HISTORY_SIZE", 2)
    uis = [review.RotoReview().review(frames(1), frames(1, c=4), name="s%d" % i)["ui"] for i in range(3)]
    assert [h["name"][0] for h in review.history()] == ["s2", "s1"]
    assert not os.path.exists(review._frame_path(uis[0]["a_frames"][0]))
    assert os.path.exists(review._frame_path(uis[2]["b_frames"][0]))
    assert review.find_run(uis[0]["run_id"][0]) is None


@pytest.mark.parametrize("kind,ext", [("roto_alpha", "mov"), ("alpha", "mp4")])
def test_downloads(review, kind, ext):
    av = pytest.importorskip("av")
    ui = review.RotoReview().review(frames(5), frames(5, c=4), name="shot5", **{"Base fps": 25.0})["ui"]
    path, name = review.make_download(ui["run_id"][0], kind)
    assert name == "shot5_%s.%s" % (kind, ext)
    with av.open(path) as c:
        s = c.streams.video[0]
        got = [f for f in c.decode(s)]
        assert len(got) == 5 and (got[0].width, got[0].height) == (48, 32)
        if kind == "roto_alpha":   # ProRes 4444 with a real alpha channel
            assert s.codec_context.name == "prores" and "a" in s.codec_context.pix_fmt
            a = got[0].to_ndarray(format="rgba")[..., 3]
            assert a[2, 2] < 10 and a[16, 24] > 245                  # transparent background, opaque subject
        else:                      # matte: white subject on black
            px = got[0].to_ndarray(format="rgb24")
            assert px[2, 2].max() < 40 and px[16, 24].min() > 215


def test_download_errors(review):
    with pytest.raises(KeyError):
        review.make_download("nope", "roto_alpha")
    ui = review.RotoReview().review(frames(1))["ui"]
    with pytest.raises(ValueError):
        review.make_download(ui["run_id"][0], "roto_alpha")   # no B
    with pytest.raises(ValueError):
        review.make_download(ui["run_id"][0], "roto")         # no longer offered
