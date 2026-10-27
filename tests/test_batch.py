import importlib
import os
import sys

import pytest


@pytest.fixture
def batch(nodes_mod):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return importlib.import_module("batch")


def make(base, rels):
    for rel in rels:
        p = base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
    return base


@pytest.fixture(autouse=True)
def fresh_attempts(batch):
    batch.reset_attempts()   # the failed-video memory is per ComfyUI session; each test starts clean
    yield


@pytest.fixture
def tree(tmp_path):
    return make(tmp_path / "ep93", ["A/clip1.mp4", "A/clip10.mp4", "A/clip2.mov", "B/deep/x.mkv", "B/notes.txt",
                                    "C/.hidden.mp4", ".git/v.mp4", "top.mp4"])


@pytest.fixture
def eps(tmp_path):
    """Two episodes with the same shot folder names, plus a second folder that is also called ep93."""
    make(tmp_path / "x" / "ep93", ["shot1/shot1.mp4", "shot2/shot2.mp4", "shot10/shot10.mp4", "shot2/extra.mov"])
    make(tmp_path / "x" / "ep94", ["shot1/shot1.mp4", "shot2/shot2.mp4"])
    make(tmp_path / "y" / "ep93", ["shot1/shot1.mp4"])
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


def test_split_folders(batch, tmp_path):
    a, b = str(tmp_path / "a"), str(tmp_path / "b")
    assert batch.split_folders(' "%s" , %s\n%s,,%s ' % (a, b, a, a + os.sep)) == [a, b]
    assert batch.split_folders("  ") == []


def test_split_folders_copy_as_path(batch, tmp_path):
    a, b, c = (str(tmp_path / n) for n in ("ep 93", "ep94", "ep95"))
    want = [a, b, c]
    assert batch.split_folders('"%s"\r\n"%s"\r\n"%s"' % (a, b, c)) == want    # Explorer's Copy as path
    assert batch.split_folders('"%s""%s""%s"' % (a, b, c)) == want          # same, line breaks squashed
    assert batch.split_folders('"%s" "%s", %s' % (a, b, c)) == want


def test_merge_folders(batch, tmp_path):
    a, b, c = (str(tmp_path / n) for n in ("a", "b", "c"))
    assert batch.merge_folders("%s, %s" % (a, b), [c, a]) == "\n".join([a, b, c])
    assert batch.merge_folders("", [a]) == a


def test_parse_picker_output(batch, tmp_path):
    (tmp_path / "x").mkdir()
    out = '%s\r\n"%s"\n%s\n\n' % (tmp_path / "x", tmp_path / "x", tmp_path / "gone")
    assert batch.parse_picker_output(out) == [str(tmp_path / "x")] * 2


def test_picker_command_exists_on_windows(batch, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    import shutil
    monkeypatch.setattr(shutil, "which", lambda n: "C:\\ps.exe" if n == "powershell" else None)
    cmd = batch.picker_command("D:\\x")
    assert cmd[0] == "C:\\ps.exe" and cmd[cmd.index("-File") + 1].endswith("pick_folders.ps1")
    assert cmd[-2:] == ["-Start", "D:\\x"] and os.path.exists(batch._PICKER_PS1)


def test_scan_batch_groups_names_and_order(batch, eps):
    text = ", ".join(str(eps / p) for p in ["x/ep93", "x/ep94", "y/ep93"])
    groups, items, errors = batch.scan_batch(text)
    assert errors == []
    assert [g["label"] for g in groups] == ["ep93", "ep94", "ep93 (y)"]
    assert groups[2]["root"] == str(eps / "y" / "ep93")
    assert [g["count"] for g in groups] == [4, 2, 1]
    got = [(groups[i["group"]]["label"], i["name"]) for i in items]
    assert got == [("ep93", "shot1"), ("ep93", "extra"), ("ep93", "shot2"), ("ep93", "shot10"),
                   ("ep94", "shot1"), ("ep94", "shot2"), ("ep93 (y)", "shot1")]


def labels(batch, eps, out, *rels):
    groups, _, _ = batch.scan_batch(", ".join(str(eps / r) for r in rels), output_folder=str(out))
    return [g["label"] for g in groups]


def claim(batch, eps, out, rel, label):
    batch.claim_folder(str(out / label), str(eps / rel))


def test_output_folder_names_stay_with_their_input_folder(batch, eps, tmp_path):
    out = tmp_path / "out"
    assert labels(batch, eps, out, "x/ep93", "y/ep93") == ["ep93", "ep93 (y)"]
    claim(batch, eps, out, "x/ep93", "ep93")
    claim(batch, eps, out, "y/ep93", "ep93 (y)")
    assert labels(batch, eps, out, "y/ep93") == ["ep93 (y)"]               # alone: still its own folder
    assert labels(batch, eps, out, "y/ep93", "x/ep93") == ["ep93 (y)", "ep93"]   # order does not matter
    assert labels(batch, eps, out, "x/ep93") == ["ep93"]


def test_first_folder_to_run_keeps_the_plain_name(batch, eps, tmp_path):
    out = tmp_path / "out"
    claim(batch, eps, out, "y/ep93", "ep93")                                # y ran first, on its own
    assert labels(batch, eps, out, "x/ep93") == ["ep93 (x)"]                # never writes into y's folder
    assert labels(batch, eps, out, "x/ep93", "y/ep93") == ["ep93 (x)", "ep93"]


def test_folder_made_before_the_record_is_taken_over(batch, eps, tmp_path):
    out = tmp_path / "out"
    (out / "ep93").mkdir(parents=True)                                      # 0.2.0 output, no record
    assert labels(batch, eps, out, "x/ep93") == ["ep93"]


def test_same_folder_name_and_same_parent_name(batch, tmp_path):
    make(tmp_path / "a" / "show" / "ep1", ["s1/s1.mp4"])
    make(tmp_path / "b" / "show" / "ep1", ["s1/s1.mp4"])
    make(tmp_path / "c" / "ep1", ["s1/s1.mp4"])
    text = ", ".join(str(tmp_path / p) for p in ["c/ep1", "a/show/ep1", "b/show/ep1"])
    groups, _, _ = batch.scan_batch(text, output_folder=str(tmp_path / "out"))
    assert [g["label"] for g in groups] == ["ep1", "ep1 (show)", "ep1 (show) 2"]


def test_load_records_the_input_folder(batch, monkeypatch, eps, tmp_path):
    out = tmp_path / "out"
    text = "%s, %s" % (eps / "x" / "ep93", eps / "y" / "ep93")
    run(batch, monkeypatch, text, index=4, output_folder=str(out), skip_if_zip_exists=False)   # y\ep93\shot1
    with open(out / "ep93 (y)" / batch.SOURCE_MARK, encoding="utf-8") as f:
        assert f.read().strip() == str(eps / "y" / "ep93")
    run(batch, monkeypatch, str(eps / "y" / "ep93"), index=0, output_folder=str(out), skip_if_zip_exists=False)
    assert sorted(os.listdir(out)) == ["ep93 (y)"]                          # alone: same folder, no new one


@pytest.fixture
def loose(tmp_path):
    """Single videos, two of them with the same name in different places."""
    return make(tmp_path / "loose", ["misc/clip_a.mp4", "misc/clip_b.mov", "other/clip_a.mp4", "misc/notes.txt"])


def test_single_files_mixed_with_folders(batch, eps, loose, tmp_path):
    out = tmp_path / "out"
    text = "\n".join(str(p) for p in [loose / "misc" / "clip_a.mp4", eps / "x" / "ep93",
                                      loose / "other" / "clip_a.mp4", loose / "misc" / "clip_b.mov"])
    groups, items, errors = batch.scan_batch(text, output_folder=str(out))
    assert errors == []
    assert [(g["kind"], g["label"], g["count"]) for g in groups] == [("files", "", 3), ("folder", "ep93", 4)]
    assert [i["name"] for i in items[:3]] == ["clip_a", "clip_a (other)", "clip_b"]
    assert batch.zip_folder_for(str(out), "") == str(out)


def test_single_file_errors(batch, loose):
    with pytest.raises(FileNotFoundError):
        batch.scan_batch(str(loose / "misc" / "notes.txt"))
    _, items, errors = batch.scan_batch("%s, %s" % (loose / "misc" / "notes.txt", loose / "misc" / "gone.mp4"),
                                        strict=False)
    assert items == [] and "Not a video" in errors[0] and "gone.mp4" in errors[1]


def test_single_video_names_stay_with_their_video(batch, loose, tmp_path):
    out = tmp_path / "out"
    a, a2 = str(loose / "misc" / "clip_a.mp4"), str(loose / "other" / "clip_a.mp4")
    assert batch.assign_single_names([a, a2], str(out)) == ["clip_a", "clip_a (other)"]
    batch.claim_single(str(out), "clip_a", a)
    batch.claim_single(str(out), "clip_a (other)", a2)
    assert batch.assign_single_names([a2], str(out)) == ["clip_a (other)"]   # alone: same zip name
    assert batch.assign_single_names([a2, a], str(out)) == ["clip_a (other)", "clip_a"]
    batch.claim_single(str(out), "clip_a", a)                               # rewriting the record works
    assert batch._singles_record(str(out))["clip_a (other)"] == a2


def test_load_single_video_saves_into_output_folder(batch, nodes_mod, make_frames, monkeypatch, eps, loose, tmp_path):
    from helpers import FakeVideo
    out = tmp_path / "out"
    text = "%s\n%s" % (loose / "misc" / "clip_a.mp4", eps / "x" / "ep94")
    for i in (0, 1):
        (video, name, path, idx, total, zfolder), _ = run(batch, monkeypatch, text, index=i, output_folder=str(out))
        nodes_mod.SaveImageSequenceTGA().save(
            images=make_frames(1), output_folder=zfolder, filename_prefix="frame", start_number=0, digits=5,
            rle_compression=True, overwrite=False, preview_frames=0, save_as_zip=True,
            source_video=FakeVideo(path), zip_name=name)
    assert sorted(os.listdir(out)) == [batch.SINGLES_MARK, "clip_a.zip", "ep94"]
    out_, B = run(batch, monkeypatch, text, output_folder=str(out))   # resume: the next video without a zip
    assert out_[1] == "shot2" and out_[5] == str(out / "ep94")
    rep = batch.scan_report(text, batch.DEFAULT_EXTS, True, str(out))
    assert rep["groups"][0]["out"] == str(out) and rep["items"][0]["done"] and rep["items"][0]["key"]


def test_place_drop(batch, tmp_path):
    drops = tmp_path / "drops"
    def upload(content, name="clip.mp4"):
        tmp = tmp_path / ("up_%d.part" % len(os.listdir(tmp_path)))
        tmp.write_bytes(content)
        return batch.place_drop(str(tmp), name, str(drops))
    first = upload(b"AAA")
    assert first == str(drops / "clip.mp4")
    assert upload(b"AAA") == first                                   # same video again: same copy
    assert upload(b"BBB") == str(drops / "2" / "clip.mp4")           # same name, other video
    assert upload(b"BBB") == str(drops / "2" / "clip.mp4")
    assert not [f for f in os.listdir(tmp_path) if f.endswith(".part")]


def test_same_video_name_in_one_folder_gets_suffix(batch, tmp_path):
    make(tmp_path / "ep1", ["shot1/take.mp4", "shot2/take.mp4", "shot3/TAKE.mov"])
    _, items, _ = batch.scan_batch(str(tmp_path / "ep1"))
    assert [i["name"] for i in items] == ["take", "take_2", "TAKE_3"]


def test_scan_batch_missing_folder(batch, eps):
    text = "%s, %s" % (eps / "x" / "ep93", eps / "nope")
    with pytest.raises(FileNotFoundError):
        batch.scan_batch(text)
    groups, items, errors = batch.scan_batch(text, strict=False)
    assert len(groups) == 1 and len(items) == 4 and "nope" in errors[0]


def test_zip_folder_for(batch, tmp_path, nodes_mod):
    assert batch.zip_folder_for(str(tmp_path), "ep93") == os.path.join(str(tmp_path), "ep93")
    import folder_paths
    assert batch.zip_folder_for("", "ep93") == os.path.join(os.path.abspath(folder_paths.get_output_directory()),
                                                           "roto_tga", "ep93")


def run(batch, monkeypatch, folders, **kw):
    monkeypatch.setattr(batch, "_make_video", lambda p: ("VIDEO", p))
    class B:  # stand-in for ExecutionBlocker
        def __init__(self, v): self.v = v
    monkeypatch.setattr(batch, "_blocker", lambda: B)
    args = dict(batch_folder=str(folders), index=0, skip_if_zip_exists=True, output_folder="",
                extensions=batch.DEFAULT_EXTS, recursive=True)
    args.update(kw)
    out = batch.LoadVideoBatchFolders().load(**args)
    assert len(out["ui"]["rototools_index"]) == 1
    if not args["skip_if_zip_exists"]:
        assert out["ui"]["rototools_index"] == [args["index"]]
    assert len(out["ui"]["rototools_status"]) == 1 and "\n" not in out["ui"]["rototools_status"][0]
    return out["result"], B


def test_load_each_index(batch, monkeypatch, eps, tmp_path):
    text = "%s, %s" % (eps / "x" / "ep93", eps / "x" / "ep94")
    groups, items, _ = batch.scan_batch(text)
    out_root = tmp_path / "out"
    for i, it in enumerate(items):
        (video, name, path, idx, total, zfolder), _ = run(batch, monkeypatch, text, index=i, output_folder=str(out_root),
                                                          skip_if_zip_exists=False)
        assert video == ("VIDEO", it["path"]) and path == it["path"] and idx == i and total == len(items)
        assert name == it["name"]
        assert zfolder == str(out_root / groups[it["group"]]["label"])


def test_index_past_end_is_blocked_not_error(batch, monkeypatch, tree):
    out, B = run(batch, monkeypatch, tree, index=99, skip_if_zip_exists=False)
    assert len(out) == 6 and all(isinstance(o, B) for o in out)


def test_skip_if_zip_exists_per_folder(batch, monkeypatch, eps, tmp_path):
    text = "%s, %s" % (eps / "x" / "ep93", eps / "x" / "ep94")
    out_root = tmp_path / "out"
    (out_root / "ep93").mkdir(parents=True)
    (out_root / "ep93" / "shot1.zip").write_bytes(b"z")
    out, B = run(batch, monkeypatch, text, output_folder=str(out_root))   # ep93 shot1 done: the next one
    assert out[1] == "extra" and out[3] == 1
    out, B = run(batch, monkeypatch, text, index=4, output_folder=str(out_root), skip_if_zip_exists=False)
    assert out[1] == "shot1" and out[5] == str(out_root / "ep94")             # same name, other episode
    out, B = run(batch, monkeypatch, text, index=0, output_folder=str(out_root), skip_if_zip_exists=False)
    assert out[1] == "shot1" and out[5] == str(out_root / "ep93")             # index mode redoes a done one


def test_empty_folder_errors(batch, monkeypatch, tmp_path):
    with pytest.raises(ValueError, match="No videos"):
        run(batch, monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="list is empty"):
        run(batch, monkeypatch, "  \n ")


def test_scan_report_and_allowed_paths(batch, eps, tmp_path):
    text = "%s, %s, %s" % (eps / "x" / "ep93", eps / "y" / "ep93", eps / "missing")
    out_root = tmp_path / "out"
    (out_root / "ep93 (y)").mkdir(parents=True)
    (out_root / "ep93 (y)" / "shot1.zip").write_bytes(b"z")
    rep = batch.scan_report(text, batch.DEFAULT_EXTS, True, str(out_root))
    assert rep["total"] == 5 and len(rep["errors"]) == 1
    assert [g["out"] for g in rep["groups"]] == [str(out_root / "ep93"), str(out_root / "ep93 (y)")]
    assert [i["done"] for i in rep["items"]] == [False, False, False, False, True]
    assert batch._allowed(rep["items"][0]["path"])
    assert not batch._allowed(str(eps / "x" / "ep94" / "shot1" / "shot1.mp4"))   # never scanned
    assert not batch._allowed(__file__)


def test_saver_writes_into_episode_folder(batch, nodes_mod, make_frames, monkeypatch, eps, tmp_path):
    from helpers import FakeVideo
    text = "%s, %s" % (eps / "x" / "ep93", eps / "x" / "ep94")
    out_root = tmp_path / "out"
    for i in (0, 4):   # ep93/shot1 and ep94/shot1: same video name, different episodes
        (video, name, path, idx, total, zfolder), _ = run(batch, monkeypatch, text, index=i, output_folder=str(out_root),
                                                          skip_if_zip_exists=False)
        nodes_mod.SaveImageSequenceTGA().save(
            images=make_frames(1), output_folder=zfolder, filename_prefix="frame", start_number=0, digits=5,
            rle_compression=True, overwrite=False, preview_frames=0, save_as_zip=True,
            source_video=FakeVideo(path), zip_name=name)
    assert sorted(os.listdir(out_root)) == ["ep93", "ep94"]
    for ep in ("ep93", "ep94"):
        assert sorted(os.listdir(out_root / ep)) == [batch.SOURCE_MARK, "shot1.zip"]


def zip_for(out, ep, name):
    (out / ep).mkdir(parents=True, exist_ok=True)
    (out / ep / (name + ".zip")).write_bytes(b"z")


def test_next_without_zip_ignores_index_and_skips_done_and_excluded(batch, monkeypatch, eps, tmp_path):
    out = tmp_path / "out"
    text = "%s\n%s" % (eps / "x" / "ep93", eps / "x" / "ep94")
    picked = []
    for _ in range(3):   # index far ahead of the work (a queue that ran ahead: the "84 skipped" case)
        res, B = run(batch, monkeypatch, text, index=250, output_folder=str(out))
        picked.append(res[1])
        zip_for(out, "ep93", res[1])
    assert picked == ["shot1", "extra", "shot2"]
    excluded = "\n".join(str(p) for p in [eps / "x" / "ep93" / "shot10" / "shot10.mp4",
                                          eps / "x" / "ep94" / "shot1" / "shot1.mp4"])
    res, B = run(batch, monkeypatch, text, output_folder=str(out), excluded=excluded)
    assert res[1] == "shot2" and res[5] == str(out / "ep94")                # shot10 and ep94/shot1 left out
    zip_for(out, "ep94", "shot2")
    res, B = run(batch, monkeypatch, text, output_folder=str(out), excluded=excluded)
    assert all(isinstance(o, B) for o in res)                                # nothing left: blocked, no error


def test_failed_video_is_retried_once_then_passed_over(batch, monkeypatch, eps, tmp_path, capsys):
    out = tmp_path / "out"
    text = str(eps / "x" / "ep94")
    names = [run(batch, monkeypatch, text, output_folder=str(out))[0][1] for _ in range(3)]
    assert names == ["shot1", "shot1", "shot2"]                              # still no zip after 2 tries: passed over
    assert "failed twice" in capsys.readouterr().out
    zip_for(out, "ep94", "shot2")
    res, B = run(batch, monkeypatch, text, output_folder=str(out))
    assert all(isinstance(o, B) for o in res)                                # only the broken one is left
    batch.reset_attempts()                                                   # Clear / ComfyUI restart
    assert run(batch, monkeypatch, text, output_folder=str(out))[0][1] == "shot1"


def test_excluded_keys(batch, tmp_path):
    a = str(tmp_path / "A" / "x.mp4")
    assert batch.excluded_keys("%s\n\n  %s  \n" % (a, a.upper())) == {os.path.normcase(a)}
    assert batch.excluded_keys("") == set()
