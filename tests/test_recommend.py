"""Tests for recommend.py."""
from mdisk_caches.detect import SystemInfo
from mdisk_caches.recommend import recommend


def test_recommend():
    info = SystemInfo()
    rec = recommend(info)
    assert rec["size_bytes"] > 0
    assert rec["mount_point"] in ("/mnt/ramdisk", "/Volumes/RAMDisk")
    assert isinstance(rec["tools"], list)
    assert rec["tmpdir"] is True
    assert rec["docker_buildkit_hint"] is True


def test_recommend_size_reasonable():
    """Recommended size should be reasonable (1-16GB)."""
    info = SystemInfo()
    rec = recommend(info)
    size_gb = rec["size_bytes"] / (1024 ** 3)
    assert 1 <= size_gb <= 16
