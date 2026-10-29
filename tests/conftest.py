import os
import sys
import types

import numpy as np
import pytest

from helpers import FakeTensor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="session")
def nodes_mod(tmp_path_factory):
    """Import nodes.py with a stub `folder_paths` (ComfyUI is not needed to test)."""
    base = tmp_path_factory.mktemp("comfy")
    fp = types.ModuleType("folder_paths")
    fp.get_output_directory = lambda: str(base / "output")
    fp.get_temp_directory = lambda: str(base / "temp")

    def get_save_image_path(prefix, output_dir, w=0, h=0):   # like ComfyUI's, without the counter search
        os.makedirs(output_dir, exist_ok=True)
        return output_dir, prefix, 0, "", prefix
    fp.get_save_image_path = get_save_image_path
    sys.modules["folder_paths"] = fp
    sys.path.insert(0, ROOT)
    import importlib
    return importlib.import_module("nodes")


@pytest.fixture
def make_frames():
    def _make(n=4, h=32, w=48, c=4):
        arr = np.zeros((n, h, w, c), dtype=np.float32)
        for i in range(n):
            arr[i, ..., 0] = i / max(n - 1, 1)
            arr[i, ..., 1] = 0.5
            arr[i, ..., 2] = 0.25
            if c == 4:
                arr[i, ..., 3] = 0.0
                arr[i, 8:24, 8:24, 3] = 1.0   # opaque square on a transparent background
        return FakeTensor(arr)
    return _make
