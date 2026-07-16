"""Recommendation engine: suggest RAM disk size, mount point, tools."""
from typing import Any, Dict, List

from mdisk_caches.detect import SystemInfo, humanize_bytes


def recommend(system_info: SystemInfo) -> Dict[str, Any]:
    """Return recommendations based on system info."""
    os_name = system_info.os_name
    ram = system_info.ram
    caches = system_info.caches

    total_gb = ram["total"] / (1024 ** 3)
    available_gb = ram["available"] / (1024 ** 3)

    # Heuristic: 30-50% of total RAM, max 16GB
    suggested_gb = max(1, min(16, round(total_gb * 0.4)))
    # Also consider if available is tight
    if suggested_gb > available_gb * 0.5:
        suggested_gb = max(1, round(available_gb * 0.3))

    mount_point = _default_mount_point(os_name)

    tools_to_configure = list(caches.keys())

    return {
        "size_bytes": int(suggested_gb * 1024 ** 3),
        "size_human": f"{suggested_gb} GB",
        "mount_point": mount_point,
        "tools": tools_to_configure,
        "tmpdir": True,  # always suggest TMPDIR
        "docker_buildkit_hint": True,
        "rationale": {
            "total_ram": f"{total_gb:.1f} GB",
            "available_ram": f"{available_gb:.1f} GB",
            "existing_cache_size": _sum_cache_sizes(caches),
            "suggested_size_gb": suggested_gb,
        },
    }


def _default_mount_point(os_name: str) -> str:
    if os_name == "macos":
        return "/Volumes/RAMDisk"
    return "/mnt/ramdisk"


def _sum_cache_sizes(caches: Dict[str, Dict[str, Any]]) -> str:
    total = sum(c.get("size", 0) for c in caches.values())
    return humanize_bytes(total)
