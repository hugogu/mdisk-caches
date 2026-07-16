"""Tests for mount.py."""
import os

from mdisk_caches.mount import (
    create_ramdisk,
    remove_ramdisk,
    is_mounted,
    get_disk_usage,
    _humanize,
)
from mdisk_caches.detect import get_os


def test_is_mounted():
    os_name = get_os()
    if os_name == "linux":
        # /tmp is typically tmpfs on Linux
        assert is_mounted("/tmp") is True
    elif os_name == "macos":
        # / is always mounted
        assert is_mounted("/") is True


def test_create_ramdisk_dry_run():
    result = create_ramdisk("/tmp/test-ramdisk", 1024 * 1024, dry_run=True)
    assert "[DRY-RUN]" in result


def test_remove_ramdisk_dry_run():
    result = remove_ramdisk("/tmp/test-ramdisk", dry_run=True)
    assert "[DRY-RUN]" in result


def test_humanize():
    assert _humanize(1024) == "1.0 KB"
    assert _humanize(1024 ** 2) == "1.0 MB"
    assert _humanize(1024 ** 3) == "1.0 GB"


def test_get_disk_usage_existing():
    """Test disk usage on an existing mount."""
    usage = get_disk_usage("/tmp")
    assert isinstance(usage, dict)
    if usage:  # may fail in some environments
        assert "total" in usage
        assert "used" in usage
        assert "free" in usage


def test_integration_tmpfs():
    """Integration test: actually create and remove a tmpfs."""
    if os.geteuid() != 0:
        print("SKIP integration_tmpfs: requires root")
        return
    if get_os() != "linux":
        print("SKIP integration_tmpfs: only on Linux")
        return
    mount_point = "/tmp/mdisk-test-ramdisk"
    try:
        result = create_ramdisk(mount_point, 1024 * 1024, dry_run=False)
        assert is_mounted(mount_point)
        usage = get_disk_usage(mount_point)
        assert usage["total"] >= 1024 * 1024
    finally:
        if is_mounted(mount_point):
            remove_ramdisk(mount_point, dry_run=False)
        assert not is_mounted(mount_point)
