"""Tests for detect.py."""
import tempfile
from pathlib import Path

from mdisk_caches.detect import get_os, get_ram_info, get_dir_size, humanize_bytes, get_cache_sizes


def test_get_os():
    os_name = get_os()
    assert os_name in ("linux", "macos")


def test_get_ram_info():
    ram = get_ram_info()
    assert isinstance(ram, dict)
    assert ram["total"] > 0
    assert ram["available"] >= 0
    assert ram["free"] >= 0


def test_humanize_bytes():
    assert humanize_bytes(0) == "0.0 B"
    assert humanize_bytes(512) == "512.0 B"
    assert humanize_bytes(1024) == "1.0 KB"
    assert humanize_bytes(1024 ** 2) == "1.0 MB"
    assert humanize_bytes(1024 ** 3) == "1.0 GB"


def test_get_dir_size():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world")
        assert get_dir_size(tmp_path) == 11

        nested = tmp_path / "nested" / "deep"
        nested.mkdir(parents=True)
        (nested / "file.txt").write_text("12345")
        assert get_dir_size(tmp_path) == 16


def test_get_cache_sizes():
    caches = get_cache_sizes()
    assert isinstance(caches, dict)
    for tool, info in caches.items():
        assert "path" in info
        assert "size" in info
        assert isinstance(info["size"], int)
