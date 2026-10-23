import numpy as np


class FakeTensor:
    """Minimal stand-in for a torch tensor: supports indexing, iteration, shape, cpu().numpy()."""

    def __init__(self, arr):
        self.arr = np.asarray(arr, dtype=np.float32)

    @property
    def shape(self):
        return self.arr.shape

    def __len__(self):
        return self.arr.shape[0]

    def __iter__(self):
        return (FakeTensor(a) for a in self.arr)

    def __getitem__(self, i):
        return FakeTensor(self.arr[i])

    def cpu(self):
        return self

    def numpy(self):
        return self.arr


class FakeVideo:
    def __init__(self, src):
        self.src = src

    def get_stream_source(self):
        if isinstance(self.src, Exception):
            raise self.src
        return self.src
