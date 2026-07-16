"""System detection: OS, RAM, cache sizes, current mounts."""
import os
import platform
import subprocess
from pathlib import Path
from typing import Any, Dict


class SystemInfo:
    """Container for system detection results."""

    def __init__(self) -> None:
        self.os_name = get_os()
        self.ram = get_ram_info()
        self.caches = get_cache_sizes()
        self.mounts = get_current_mounts()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "os": self.os_name,
            "ram": self.ram,
            "caches": self.caches,
            "mounts": self.mounts,
        }


def get_os() -> str:
    """Return 'macos' or 'linux'."""
    system = platform.system().lower()
    if system == "darwin":
        return "macos"
    elif system == "linux":
        return "linux"
    raise OSError(f"Unsupported OS: {platform.system()}")


def get_ram_info() -> Dict[str, int]:
    """Return RAM info in bytes: total, available, free."""
    os_name = get_os()
    if os_name == "linux":
        return _get_ram_linux()
    return _get_ram_macos()


def _get_ram_linux() -> Dict[str, int]:
    """Parse /proc/meminfo."""
    meminfo: Dict[str, int] = {}
    with open("/proc/meminfo") as f:
        for line in f:
            parts = line.split()
            if len(parts) >= 2:
                key = parts[0].strip(":")
                meminfo[key] = int(parts[1]) * 1024
    return {
        "total": meminfo.get("MemTotal", 0),
        "available": meminfo.get("MemAvailable", 0),
        "free": meminfo.get("MemFree", 0),
    }


def _get_ram_macos() -> Dict[str, int]:
    """Use sysctl and vm_stat."""
    result = subprocess.run(
        ["sysctl", "-n", "hw.memsize"],
        capture_output=True,
        text=True,
        check=True,
    )
    total = int(result.stdout.strip())
    vm = subprocess.run(
        ["vm_stat"], capture_output=True, text=True, check=True
    )
    pages_free = 0
    for line in vm.stdout.splitlines():
        if "Pages free" in line:
            pages_free = int(line.split(":")[1].strip().strip("."))
            break
    page_size = 4096
    available = pages_free * page_size
    return {"total": total, "available": available, "free": available}


def get_cache_sizes() -> Dict[str, Dict[str, Any]]:
    """Detect cache directories and their sizes."""
    caches: Dict[str, Dict[str, Any]] = {}
    cache_paths = [
        ("maven", Path.home() / ".m2" / "repository"),
        ("gradle", Path.home() / ".gradle"),
        ("npm", Path.home() / ".npm"),
        ("pnpm", Path.home() / ".pnpm-store"),
        ("pip", Path.home() / ".cache" / "pip"),
        ("cargo", Path.home() / ".cargo"),
    ]
    for name, path in cache_paths:
        if path.exists():
            caches[name] = {
                "path": str(path),
                "size": get_dir_size(path),
            }
    return caches


def get_dir_size(path: Path) -> int:
    """Recursive directory size in bytes."""
    total = 0
    if path.is_file():
        return path.stat().st_size
    for entry in os.scandir(path):
        if entry.is_file():
            total += entry.stat().st_size
        elif entry.is_dir():
            total += get_dir_size(Path(entry.path))
    return total


def get_current_mounts() -> Dict[str, Dict[str, Any]]:
    """Return current mount points relevant to RAM disks."""
    mounts: Dict[str, Dict[str, Any]] = {}
    os_name = get_os()
    if os_name == "linux":
        with open("/proc/mounts") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 3 and parts[2] == "tmpfs":
                    mounts[parts[1]] = {
                        "device": parts[0],
                        "type": "tmpfs",
                        "options": parts[3] if len(parts) > 3 else "",
                    }
    elif os_name == "macos":
        result = subprocess.run(
            ["mount"], capture_output=True, text=True, check=True
        )
        for line in result.stdout.splitlines():
            if "hfs" in line or "apfs" in line:
                parts = line.split()
                if len(parts) >= 3 and "RAMDisk" in parts[2]:
                    mounts[parts[2]] = {
                        "device": parts[0],
                        "type": parts[4] if len(parts) > 4 else "",
                        "options": "",
                    }
    return mounts


def humanize_bytes(value: int) -> str:
    """Convert bytes to human readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(value) < 1024.0:
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} PB"
