"""Report generation using plain text (stdlib only)."""
from typing import Any

from mdisk_caches.detect import SystemInfo, humanize_bytes
from mdisk_caches.recommend import recommend
from mdisk_caches.mount import get_ramdisk_info, get_disk_usage


def generate_report(system_info: SystemInfo) -> str:
    """Generate a full report and print it."""
    rec = recommend(system_info)
    mount_status = get_ramdisk_info(rec["mount_point"])

    print("=" * 60)
    print("SYSTEM INFO")
    print("=" * 60)
    print(f"  OS:              {system_info.os_name}")
    print(f"  Total RAM:       {humanize_bytes(system_info.ram['total'])}")
    print(f"  Available RAM:   {humanize_bytes(system_info.ram['available'])}")
    print()

    print("=" * 60)
    print("DETECTED CACHES")
    print("=" * 60)
    if system_info.caches:
        print(f"  {'Tool':<10} {'Path':<50} {'Size':<10}")
        print("  " + "-" * 68)
        for tool, info in system_info.caches.items():
            print(f"  {tool:<10} {info['path']:<50} {humanize_bytes(info['size']):<10}")
    else:
        print("  No caches detected.")
    print()

    print("=" * 60)
    print("RECOMMENDATIONS")
    print("=" * 60)
    print(f"  RAM Disk Size:   {rec['size_human']}")
    print(f"  Mount Point:     {rec['mount_point']}")
    print(f"  Tools:           {', '.join(rec['tools'])}")
    print(f"  TMPDIR:          {'Yes' if rec['tmpdir'] else 'No'}")
    print(f"  Docker BuildKit: {'Yes' if rec['docker_buildkit_hint'] else 'No'}")
    print()

    print("=" * 60)
    print("RAM DISK STATUS")
    print("=" * 60)
    if mount_status:
        print(f"  Status: MOUNTED")
        if mount_status.get("df"):
            print(f"  {mount_status['df']}")
    else:
        print(f"  Status: NOT MOUNTED")
    print()

    return ""
