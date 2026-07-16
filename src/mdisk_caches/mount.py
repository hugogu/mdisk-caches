"""Mount operations: create and remove RAM disk / tmpfs."""
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from mdisk_caches.detect import get_os, get_current_mounts


def is_mounted(mount_point: str) -> bool:
    """Check if mount point is currently mounted."""
    return mount_point in get_current_mounts()


def get_ramdisk_info(mount_point: str) -> Optional[Dict[str, Any]]:
    """Get filesystem info for a mount point."""
    mounts = get_current_mounts()
    if mount_point in mounts:
        info = mounts[mount_point].copy()
        # Try to get size info from df
        try:
            result = subprocess.run(
                ["df", "-h", mount_point],
                capture_output=True,
                text=True,
                check=True,
            )
            info["df"] = result.stdout.strip()
        except subprocess.CalledProcessError:
            info["df"] = None
        return info
    return None


def create_ramdisk(mount_point: str, size_bytes: int, dry_run: bool = False) -> str:
    """Create RAM disk. Returns mount point. On dry_run, only prints commands."""
    os_name = get_os()
    if os_name == "linux":
        return _create_tmpfs(mount_point, size_bytes, dry_run)
    return _create_ramdisk_macos(mount_point, size_bytes, dry_run)


def _create_tmpfs(mount_point: str, size_bytes: int, dry_run: bool) -> str:
    """Create a tmpfs mount on Linux."""
    size_str = f"{size_bytes}"
    if size_bytes >= 1024 ** 3:
        size_str = f"{size_bytes // (1024 ** 3)}G"
    elif size_bytes >= 1024 ** 2:
        size_str = f"{size_bytes // (1024 ** 2)}M"

    if is_mounted(mount_point):
        return f"Mount point {mount_point} already mounted"

    mount_cmd = [
        "sudo", "mount", "-t", "tmpfs", "-o",
        f"size={size_str},noatime,nosuid",
        "tmpfs", mount_point,
    ]

    if dry_run:
        return f"[DRY-RUN] Would run: {' '.join(mount_cmd)}"

    # Create mount point if needed
    Path(mount_point).mkdir(parents=True, exist_ok=True)
    subprocess.run(mount_cmd, check=True)
    return f"Mounted tmpfs at {mount_point} (size={size_str})"


def _create_ramdisk_macos(mount_point: str, size_bytes: int, dry_run: bool) -> str:
    """Create a RAM disk on macOS using hdiutil + diskutil."""
    sectors = size_bytes // 512
    attach_cmd = ["hdiutil", "attach", "-nomount", f"ram://{sectors}"]
    name = Path(mount_point).name or "RAMDisk"
    format_cmd = [
        "diskutil", "erasevolume", "APFS", name, "DEVICE_PLACEHOLDER",
    ]

    if dry_run:
        return (
            f"[DRY-RUN] Would run: {' '.join(attach_cmd)}\n"
            f"[DRY-RUN] Then: diskutil erasevolume APFS {name} <device>"
        )

    result = subprocess.run(attach_cmd, capture_output=True, text=True, check=True)
    device = result.stdout.strip().splitlines()[0].strip()
    format_cmd[-1] = device
    subprocess.run(format_cmd, check=True)
    return f"Created RAM disk {name} at {device} ({mount_point})"


def remove_ramdisk(mount_point: str, dry_run: bool = False) -> str:
    """Remove / unmount the RAM disk."""
    os_name = get_os()
    if os_name == "linux":
        cmd = ["sudo", "umount", mount_point]
    else:
        # macOS: find device and detach
        cmd = ["diskutil", "eject", mount_point]

    if dry_run:
        return f"[DRY-RUN] Would run: {' '.join(cmd)}"

    if not is_mounted(mount_point):
        return f"Mount point {mount_point} is not mounted"

    subprocess.run(cmd, check=True)
    return f"Unmounted {mount_point}"


def get_disk_usage(mount_point: str) -> Dict[str, Any]:
    """Return disk usage for a mount point."""
    try:
        total, used, free = shutil.disk_usage(mount_point)
        return {
            "total": total,
            "used": used,
            "free": free,
            "total_human": _humanize(total),
            "used_human": _humanize(used),
            "free_human": _humanize(free),
        }
    except OSError:
        return {}


def _humanize(value: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(value) < 1024.0:
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} PB"
