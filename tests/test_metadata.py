"""Guards the Comfy Registry rules so a bad pyproject.toml is caught before publishing."""
import os
import re

import pytest

tomllib = pytest.importorskip("tomllib")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def meta():
    with open(os.path.join(ROOT, "pyproject.toml"), "rb") as f:
        return tomllib.load(f)


def test_name_follows_registry_rules(meta):
    name = meta["project"]["name"]
    assert len(name) < 100
    assert re.fullmatch(r"[A-Za-z][A-Za-z0-9._-]*", name)
    assert not re.search(r"[._-]{2,}", name)
    assert "comfyui" not in name.lower()


def test_version_is_semver(meta):
    assert re.fullmatch(r"\d+\.\d+\.\d+", meta["project"]["version"])


def test_license_is_a_file_or_text_table(meta):
    lic = meta["project"]["license"]
    assert isinstance(lic, dict) and ("file" in lic or "text" in lic)
    if "file" in lic:
        assert os.path.exists(os.path.join(ROOT, lic["file"]))


def test_registry_table_and_repo_url(meta):
    assert meta["tool"]["comfy"]["PublisherId"]
    assert meta["project"]["urls"]["Repository"].startswith("https://github.com/")


def test_changelog_mentions_current_version(meta):
    with open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8") as f:
        assert "[%s]" % meta["project"]["version"] in f.read()
