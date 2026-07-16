"""CLI entry point using argparse (stdlib only)."""
import argparse
import json
import sys
from pathlib import Path

from mdisk_caches import __version__
from mdisk_caches.detect import SystemInfo, humanize_bytes
from mdisk_caches.recommend import recommend
from mdisk_caches.mount import (
    create_ramdisk,
    remove_ramdisk,
    is_mounted,
    get_disk_usage,
)
from mdisk_caches.configure import configure_all, SUPPORTED_TOOLS
from mdisk_caches.report import generate_report


def cmd_detect(args):
    """Show system detection results."""
    info = SystemInfo()
    if args.format == "json":
        print(json.dumps(info.to_dict(), indent=2))
    else:
        print(f"{'OS':<15} {info.os_name}")
        print(f"{'Total RAM':<15} {humanize_bytes(info.ram['total'])}")
        print(f"{'Available RAM':<15} {humanize_bytes(info.ram['available'])}")
        print()
        if info.caches:
            print("Detected Caches:")
            print(f"{'Tool':<10} {'Path':<50} {'Size':<10}")
            print("-" * 70)
            for tool, data in info.caches.items():
                print(f"{tool:<10} {data['path']:<50} {humanize_bytes(data['size']):<10}")


def cmd_recommend(args):
    """Show recommendations for RAM disk size and tool configs."""
    info = SystemInfo()
    rec = recommend(info)
    if args.format == "json":
        print(json.dumps(rec, indent=2))
    else:
        print(f"{'RAM Disk Size':<20} {rec['size_human']}")
        print(f"{'Mount Point':<20} {rec['mount_point']}")
        print(f"{'Tools':<20} {', '.join(rec['tools'])}")
        print(f"{'TMPDIR':<20} {'Yes' if rec['tmpdir'] else 'No'}")
        print(f"{'Docker BuildKit':<20} {'Yes' if rec['docker_buildkit_hint'] else 'No'}")


def cmd_create(args):
    """Create RAM disk / tmpfs."""
    info = SystemInfo()
    rec = recommend(info)
    mount_point = args.mount or rec["mount_point"]

    if args.size:
        size_bytes = _parse_size(args.size)
    else:
        size_bytes = rec["size_bytes"]

    if is_mounted(mount_point):
        print(f"⚠ Mount point {mount_point} is already mounted.")
        return

    if not args.dry_run and not args.yes:
        msg = f"Create RAM disk at {mount_point} with size {humanize_bytes(size_bytes)}? [y/N] "
        if input(msg).lower() != "y":
            print("Aborted.")
            return

    result = create_ramdisk(mount_point, size_bytes, dry_run=args.dry_run)
    print(result)


def cmd_configure(args):
    """Configure tools to use RAM disk."""
    info = SystemInfo()
    rec = recommend(info)
    mount_point = args.mount or rec["mount_point"]

    if not args.all and not args.tool:
        print("Error: specify --tool or --all")
        sys.exit(1)

    tools = [args.tool] if args.tool else SUPPORTED_TOOLS

    if not args.dry_run and not args.yes:
        msg = f"Configure {', '.join(tools)} to use {mount_point}? [y/N] "
        if input(msg).lower() != "y":
            print("Aborted.")
            return

    results = configure_all(mount_point, dry_run=args.dry_run)
    for t in tools:
        print(f"{t:15} {results.get(t, 'not supported')}")


def cmd_cleanup(args):
    """Remove RAM disk and clean up."""
    info = SystemInfo()
    rec = recommend(info)
    mount_point = args.mount or rec["mount_point"]

    if not is_mounted(mount_point):
        print(f"⚠ Mount point {mount_point} is not mounted.")
        return

    if not args.dry_run and not args.yes:
        if input(f"Remove RAM disk at {mount_point}? [y/N] ").lower() != "y":
            print("Aborted.")
            return

    result = remove_ramdisk(mount_point, dry_run=args.dry_run)
    print(result)


def cmd_status(args):
    """Show current RAM disk status."""
    info = SystemInfo()
    rec = recommend(info)
    mount_point = args.mount or rec["mount_point"]

    if is_mounted(mount_point):
        print(f"✓ Mounted at {mount_point}")
        usage = get_disk_usage(mount_point)
        if usage:
            print(f"  Total: {usage['total_human']}")
            print(f"  Used:  {usage['used_human']}")
            print(f"  Free:  {usage['free_human']}")
    else:
        print(f"✗ Not mounted at {mount_point}")


def cmd_report(args):
    """Generate full report."""
    info = SystemInfo()
    generate_report(info)


def _parse_size(size_str: str) -> int:
    """Parse size string like '4G', '1M', '16K' into bytes."""
    size_str = size_str.upper().strip()
    multipliers = {
        "K": 1024,
        "M": 1024 ** 2,
        "G": 1024 ** 3,
        "T": 1024 ** 4,
    }
    for suffix, multiplier in multipliers.items():
        if size_str.endswith(suffix):
            return int(float(size_str[:-1]) * multiplier)
    return int(size_str)


def main():
    parser = argparse.ArgumentParser(
        prog="mdisk-caches",
        description="Manage RAM disk / tmpfs caches for build tools.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # detect
    p_detect = subparsers.add_parser("detect", help="Show system information")
    p_detect.add_argument(
        "--format", choices=["table", "json"], default="table"
    )
    p_detect.set_defaults(func=cmd_detect)

    # recommend
    p_recommend = subparsers.add_parser(
        "recommend", help="Show recommendations"
    )
    p_recommend.add_argument(
        "--format", choices=["table", "json"], default="table"
    )
    p_recommend.set_defaults(func=cmd_recommend)

    # create
    p_create = subparsers.add_parser("create", help="Create RAM disk / tmpfs")
    p_create.add_argument("--mount", "-m", default=None, help="Mount point")
    p_create.add_argument("--size", "-s", default=None, help="Size (e.g., 4G, 1M)")
    p_create.add_argument("--dry-run", action="store_true", help="Show what would be done")
    p_create.add_argument("--yes", "-y", action="store_true", help="Skip confirmation")
    p_create.set_defaults(func=cmd_create)

    # configure
    p_configure = subparsers.add_parser(
        "configure", help="Configure tools to use RAM disk"
    )
    p_configure.add_argument("--mount", "-m", default=None, help="Mount point")
    p_configure.add_argument("--tool", "-t", default=None, help="Tool to configure")
    p_configure.add_argument("--all", action="store_true", help="Configure all tools")
    p_configure.add_argument("--dry-run", action="store_true", help="Show what would be done")
    p_configure.add_argument("--yes", "-y", action="store_true", help="Skip confirmation")
    p_configure.set_defaults(func=cmd_configure)

    # status
    p_status = subparsers.add_parser("status", help="Show current RAM disk status")
    p_status.add_argument("--mount", "-m", default=None, help="Mount point")
    p_status.set_defaults(func=cmd_status)

    # report
    p_report = subparsers.add_parser("report", help="Generate full report")
    p_report.set_defaults(func=cmd_report)

    # cleanup
    p_cleanup = subparsers.add_parser("cleanup", help="Remove RAM disk")
    p_cleanup.add_argument("--mount", "-m", default=None, help="Mount point")
    p_cleanup.add_argument("--dry-run", action="store_true", help="Show what would be done")
    p_cleanup.add_argument("--yes", "-y", action="store_true", help="Skip confirmation")
    p_cleanup.set_defaults(func=cmd_cleanup)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    args.func(args)
