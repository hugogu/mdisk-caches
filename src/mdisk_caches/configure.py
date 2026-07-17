"""Configure third-party tools to use RAM disk.

After pointing each tool at the new tmpfs location, we also offer a
migration step that moves existing data from the tool's old cache
location to the new one. This is opt-out via ``--no-migrate`` and is
skipped automatically in dry-run mode unless ``--dry-run-migrate`` is
given.
"""
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from mdisk_caches.detect import get_os

SUPPORTED_TOOLS = [
    "maven", "gradle", "npm", "pnpm", "pip", "cargo",
    "tmpdir", "docker_buildkit",
]

# Each tool's "old → new" cache path. Keep these in one place so the
# README, the configure_* implementations, and the test suite can share
# a single source of truth.
OLD_PATHS: Dict[str, Callable[[], Path]] = {
    "maven": lambda: Path.home() / ".m2" / "repository",
    "gradle": lambda: Path.home() / ".gradle",
    "npm": lambda: Path.home() / ".npm",
    "pnpm": lambda: Path.home() / ".pnpm-store",
    "pip": lambda: Path.home() / ".cache" / "pip",
    "cargo": lambda: Path.home() / ".cargo",
    # tmpdir has no per-user cache to migrate; docker_buildkit has no
    # on-disk cache; both are config-only.
}


def _get_new_path(tool: str, mount_point: str) -> Path:
    """Return the RAM disk cache path for a tool.

    This mirrors the paths chosen by the configure_* implementations so
    restore/migrate can reason about them from a single table.
    """
    return {
        "maven": Path(mount_point) / "maven-repo",
        "gradle": Path(mount_point) / "gradle",
        "npm": Path(mount_point) / "npm",
        "pnpm": Path(mount_point) / "pnpm",
        "pip": Path(mount_point) / "pip",
        "cargo": Path(mount_point) / "cargo",
        "tmpdir": Path(mount_point) / "tmp",
    }[tool]


def configure_all(
    mount_point: str,
    dry_run: bool = False,
    migrate: bool = True,
) -> Dict[str, str]:
    """Configure all supported tools.

    ``migrate`` controls whether existing data is also moved to the
    new location (default True). It is automatically suppressed in
    dry-run mode unless callers explicitly want the migration report.
    """
    results = {}
    for tool in SUPPORTED_TOOLS:
        func = globals().get(f"configure_{tool}")
        if func:
            results[tool] = func(mount_point, dry_run, migrate=migrate)
    return results


def restore_all(
    mount_point: str,
    dry_run: bool = False,
    migrate: bool = True,
) -> Dict[str, str]:
    """Restore all supported tools to their original cache locations.

    ``migrate`` controls whether existing data on the RAM disk is moved
    back to the tool's original on-disk location before the disk is
    released (default True).
    """
    results = {}
    for tool in SUPPORTED_TOOLS:
        func = globals().get(f"restore_{tool}")
        if func:
            results[tool] = func(mount_point, dry_run, migrate=migrate)
    return results


# ---------------------------------------------------------------------------
# Migration helper
# ---------------------------------------------------------------------------


def migrate_directory(
    src: Path,
    dst: Path,
    dry_run: bool = False,
) -> str:
    """Move the contents of ``src`` to ``dst`` and remove ``src`` if empty.

    Behaviour:
      - If ``src`` does not exist: "no old data, nothing to do".
      - If ``src`` is a symlink to ``dst``: remove the symlink, no copy.
      - If ``src`` resolves to the same path as ``dst`` (e.g. user already
        redirected earlier): no-op.
      - Otherwise: ``shutil.move`` every entry; ``shutil.move`` falls back
        to copy+delete when crossing filesystems, which is exactly what
        we need when the destination is tmpfs and the source is on disk.
        Existing files in ``dst`` with the same name are overwritten.
      - After moving, ``src.rmdir()`` succeeds only when nothing is left
        behind. If hidden files / sub-mounts remain, the old directory
        is kept and a warning is reported so the user can clean up by
        hand.

    Returns a short human-readable status string suitable for printing
    or returning from a ``configure_*`` function.
    """
    if not src.exists() and not src.is_symlink():
        return f"no old data at {src} (nothing to migrate)"
    if src.is_symlink() and src.resolve() == dst.resolve():
        if dry_run:
            return f"[DRY-RUN] would remove symlink {src} -> {dst}"
        src.unlink()
        return f"removed symlink {src} (already pointed at {dst})"
    if src.exists() and src.resolve() == dst.resolve():
        return f"{src} and {dst} are the same path; nothing to migrate"
    if not src.is_dir():
        return f"{src} is not a directory; skipping migration"

    if dry_run:
        entries = list(src.iterdir())
        if not entries:
            return f"[DRY-RUN] would remove empty {src}"
        sample = ", ".join(e.name for e in entries[:3])
        more = f" (+{len(entries) - 3} more)" if len(entries) > 3 else ""
        return f"[DRY-RUN] would move {len(entries)} entries from {src} to {dst} (e.g. {sample}{more}), then rmdir {src}"

    dst.mkdir(parents=True, exist_ok=True)
    moved, failed = 0, []
    for entry in src.iterdir():
        # Skip dotfiles / dot-dirs. Cache directories are full of
        # ``.cache/``, ``.DS_Store`` etc. that don't belong on tmpfs.
        if entry.name.startswith("."):
            continue
        # Preserve the relative path so nested cache structures
        # (e.g. ``repository/com/foo/bar.jar``) land at the matching
        # nested path under ``dst`` instead of being flattened to the
        # leaf name. ``shutil.move`` will create parent dirs as part
        # of the move on the same FS, but on cross-FS it copies into
        # a non-existent target directory and fails — so we
        # pre-create the parent path explicitly.
        rel = entry.relative_to(src)
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            # ``shutil.move`` uses os.rename() on the same FS and
            # copy+delete across FS boundaries. tmpfs is almost
            # always a different FS from disk, so the cross-FS path
            # is what runs in practice. Existing files in dst are
            # overwritten by the copy step.
            shutil.move(str(entry), str(target))
            moved += 1
        except OSError as exc:
            failed.append(f"{rel}: {exc}")

    cleanup_msg = ""
    try:
        src.rmdir()
        cleanup_msg = f", removed empty {src}"
    except OSError:
        leftover = list(src.iterdir())
        if leftover:
            names = ", ".join(e.name for e in leftover[:3])
            cleanup_msg = (
                f", {src} not empty (kept for manual cleanup; "
                f"sample leftover: {names})"
            )
        else:
            cleanup_msg = f", {src} kept (permission issue)"

    if failed:
        return (
            f"migrated {moved} entries to {dst}{cleanup_msg}; "
            f"failed: {'; '.join(failed)}"
        )
    return f"migrated {moved} entries to {dst}{cleanup_msg}"


# ---------------------------------------------------------------------------
# Per-tool configure_*
# ---------------------------------------------------------------------------


def configure_maven(
    mount_point: str, dry_run: bool = False, migrate: bool = True
) -> str:
    """Configure Maven localRepository to use RAM disk."""
    m2_dir = Path.home() / ".m2"
    new_repo = Path(mount_point) / "maven-repo"
    settings_file = m2_dir / "settings.xml"
    if dry_run:
        msg = f"[DRY-RUN] Would set Maven localRepository to {new_repo}"
        if migrate:
            msg += f"; {migrate_directory(OLD_PATHS['maven'](), new_repo, dry_run=True)}"
        return msg
    m2_dir.mkdir(parents=True, exist_ok=True)
    new_repo.mkdir(parents=True, exist_ok=True)
    if not settings_file.exists():
        settings_file.write_text(
            "<settings>\n"
            f"  <localRepository>{new_repo}</localRepository>\n"
            "</settings>\n"
        )
        configure_msg = f"Created {settings_file} with localRepository={new_repo}"
    else:
        backup = _backup_file(settings_file)
        content = settings_file.read_text()
        if "<localRepository>" in content:
            content = re.sub(
                r"<localRepository>.*?</localRepository>",
                f"<localRepository>{new_repo}</localRepository>",
                content,
                count=1,
            )
        else:
            content = content.replace(
                "</settings>",
                f"  <localRepository>{new_repo}</localRepository>\n</settings>",
            )
        settings_file.write_text(content)
        configure_msg = f"Updated Maven localRepository to {new_repo} (backup: {backup})"

    if migrate:
        configure_msg += f"; {migrate_directory(OLD_PATHS['maven'](), new_repo)}"
    return configure_msg


def configure_gradle(
    mount_point: str, dry_run: bool = False, migrate: bool = True
) -> str:
    """Configure Gradle user home to use RAM disk."""
    new_home = Path(mount_point) / "gradle"
    if dry_run:
        msg = f"[DRY-RUN] Would set GRADLE_USER_HOME={new_home}"
        if migrate:
            msg += f"; {migrate_directory(OLD_PATHS['gradle'](), new_home, dry_run=True)}"
        return msg
    new_home.mkdir(parents=True, exist_ok=True)
    env_line = f'export GRADLE_USER_HOME="{new_home}"\n'
    configure_msg = f"Set GRADLE_USER_HOME={new_home} ({_add_or_replace_in_shell_rc('GRADLE_USER_HOME', env_line)})"
    if migrate:
        configure_msg += f"; {migrate_directory(OLD_PATHS['gradle'](), new_home)}"
    return configure_msg


def configure_npm(
    mount_point: str, dry_run: bool = False, migrate: bool = True
) -> str:
    """Configure npm cache to use RAM disk."""
    new_cache = Path(mount_point) / "npm"
    if dry_run:
        msg = f"[DRY-RUN] Would run: npm config set cache {new_cache} --global"
        if migrate:
            # npm's official cache is ~/.npm/_cacache; surface that path
            # in the dry-run report so the user can see what would move.
            old_npm_cache = Path.home() / ".npm" / "_cacache"
            msg += f"; {migrate_directory(old_npm_cache, new_cache, dry_run=True)}"
        return msg
    new_cache.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            ["npm", "config", "set", "cache", str(new_cache), "--global"],
            check=True, capture_output=True, text=True,
        )
        configure_msg = f"Set npm cache to {new_cache}"
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        return f"npm command failed ({e}); manually set: npm config set cache {new_cache}"
    if migrate:
        # npm's actual cache directory is ~/.npm/_cacache (not the whole
        # ~/.npm). The rest of ~/.npm (config etc.) stays put.
        old_npm_cache = Path.home() / ".npm" / "_cacache"
        configure_msg += f"; {migrate_directory(old_npm_cache, new_cache)}"
    return configure_msg


def configure_pnpm(
    mount_point: str, dry_run: bool = False, migrate: bool = True
) -> str:
    """Configure pnpm store to use RAM disk."""
    new_store = Path(mount_point) / "pnpm"
    if dry_run:
        msg = f"[DRY-RUN] Would run: pnpm config set store-dir {new_store}"
        if migrate:
            msg += f"; {migrate_directory(OLD_PATHS['pnpm'](), new_store, dry_run=True)}"
        return msg
    new_store.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            ["pnpm", "config", "set", "store-dir", str(new_store)],
            check=True, capture_output=True, text=True,
        )
        configure_msg = f"Set pnpm store-dir to {new_store}"
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        return f"pnpm command failed ({e}); manually set: pnpm config set store-dir {new_store}"
    if migrate:
        configure_msg += f"; {migrate_directory(OLD_PATHS['pnpm'](), new_store)}"
    return configure_msg


def configure_pip(
    mount_point: str, dry_run: bool = False, migrate: bool = True
) -> str:
    """Configure pip cache to use RAM disk."""
    new_cache = Path(mount_point) / "pip"
    if dry_run:
        msg = f"[DRY-RUN] Would set PIP_CACHE_DIR={new_cache}"
        if migrate:
            msg += f"; {migrate_directory(OLD_PATHS['pip'](), new_cache, dry_run=True)}"
        return msg
    new_cache.mkdir(parents=True, exist_ok=True)
    env_line = f'export PIP_CACHE_DIR="{new_cache}"\n'
    configure_msg = f"Set PIP_CACHE_DIR={new_cache} ({_add_or_replace_in_shell_rc('PIP_CACHE_DIR', env_line)})"
    if migrate:
        configure_msg += f"; {migrate_directory(OLD_PATHS['pip'](), new_cache)}"
    return configure_msg


def configure_cargo(
    mount_point: str, dry_run: bool = False, migrate: bool = True
) -> str:
    """Configure cargo home to use RAM disk."""
    new_home = Path(mount_point) / "cargo"
    if dry_run:
        msg = f"[DRY-RUN] Would set CARGO_HOME={new_home}"
        if migrate:
            msg += f"; {migrate_directory(OLD_PATHS['cargo'](), new_home, dry_run=True)}"
        return msg
    new_home.mkdir(parents=True, exist_ok=True)
    env_line = f'export CARGO_HOME="{new_home}"\n'
    configure_msg = f"Set CARGO_HOME={new_home} ({_add_or_replace_in_shell_rc('CARGO_HOME', env_line)})"
    if migrate:
        configure_msg += f"; {migrate_directory(OLD_PATHS['cargo'](), new_home)}"
    return configure_msg


def configure_tmpdir(
    mount_point: str, dry_run: bool = False, migrate: bool = True
) -> str:
    """Configure TMPDIR to use RAM disk.

    ``migrate`` is accepted for API symmetry with the other configure_*
    functions but is intentionally a no-op for TMPDIR: copying ``/tmp``
    is unsafe (system-managed, may contain live sockets / held file
    descriptors) and most distributions already mount ``/tmp`` on tmpfs.
    """
    new_tmp = Path(mount_point) / "tmp"
    if dry_run:
        return f"[DRY-RUN] Would set TMPDIR={new_tmp} (no migration; /tmp is system-managed)"
    new_tmp.mkdir(parents=True, exist_ok=True)
    env_line = f'export TMPDIR="{new_tmp}"\n'
    return (
        f"Set TMPDIR={new_tmp} "
        f"({_add_or_replace_in_shell_rc('TMPDIR', env_line)})"
    )


def configure_docker_buildkit(
    mount_point: str, dry_run: bool = False, migrate: bool = True
) -> str:
    """Print Docker BuildKit cache mount hints."""
    # No migration: BuildKit cache lives in the build-time mount, not
    # in a persistent on-disk path. ``migrate`` is accepted for API
    # symmetry but is intentionally a no-op here.
    return (
        "Docker BuildKit cache mount hints:\n"
        "  # In your Dockerfile:\n"
        "  RUN --mount=type=cache,target=/root/.m2 \\\n"
        "      mvn package\n"
        "  RUN --mount=type=cache,target=/root/.npm \\\n"
        "      npm ci\n"
        "  # Enable BuildKit: export DOCKER_BUILDKIT=1"
    )


def restore_maven(
    mount_point: str, dry_run: bool = False, migrate: bool = True
) -> str:
    """Restore Maven localRepository to its default location."""
    m2_dir = Path.home() / ".m2"
    new_repo = _get_new_path("maven", mount_point)
    old_repo = OLD_PATHS["maven"]()
    settings_file = m2_dir / "settings.xml"
    backup_file = settings_file.with_suffix(settings_file.suffix + ".backup")

    if dry_run:
        msg = "[DRY-RUN] Would restore Maven localRepository to default"
        if migrate:
            msg += f"; {migrate_directory(new_repo, old_repo, dry_run=True)}"
        return msg

    if backup_file.exists():
        shutil.copy2(backup_file, settings_file)
        restore_msg = f"Restored {settings_file} from backup"
    elif settings_file.exists():
        content = settings_file.read_text()
        pattern = re.compile(
            r"^\s*<localRepository>(.*?)</localRepository>\n?",
            re.MULTILINE,
        )
        match = pattern.search(content)
        if match and str(mount_point) in match.group(1):
            content = pattern.sub("", content, count=1)
            content = re.sub(r"\n{3,}", "\n\n", content)
            settings_file.write_text(content)
            restore_msg = f"Removed RAM disk localRepository from {settings_file}"
        else:
            restore_msg = f"No RAM disk localRepository found in {settings_file}"
    else:
        restore_msg = f"No {settings_file} to restore"

    if migrate:
        restore_msg += f"; {migrate_directory(new_repo, old_repo)}"
    return restore_msg


def restore_gradle(
    mount_point: str, dry_run: bool = False, migrate: bool = True
) -> str:
    """Restore Gradle user home to its default location."""
    new_home = _get_new_path("gradle", mount_point)
    old_home = OLD_PATHS["gradle"]()
    if dry_run:
        msg = "[DRY-RUN] Would unset GRADLE_USER_HOME"
        if migrate:
            msg += f"; {migrate_directory(new_home, old_home, dry_run=True)}"
        return msg
    restore_msg = f"Removed GRADLE_USER_HOME ({_remove_from_shell_rc('GRADLE_USER_HOME')})"
    if migrate:
        restore_msg += f"; {migrate_directory(new_home, old_home)}"
    return restore_msg


def restore_npm(
    mount_point: str, dry_run: bool = False, migrate: bool = True
) -> str:
    """Restore npm cache to its default location."""
    new_cache = _get_new_path("npm", mount_point)
    old_cache = Path.home() / ".npm" / "_cacache"
    if dry_run:
        msg = "[DRY-RUN] Would run: npm config delete cache --global"
        if migrate:
            msg += f"; {migrate_directory(new_cache, old_cache, dry_run=True)}"
        return msg
    try:
        subprocess.run(
            ["npm", "config", "delete", "cache", "--global"],
            check=True, capture_output=True, text=True,
        )
        restore_msg = "Deleted npm cache config"
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        restore_msg = (
            f"npm command failed ({e}); "
            f"manually run: npm config delete cache --global"
        )
    if migrate:
        restore_msg += f"; {migrate_directory(new_cache, old_cache)}"
    return restore_msg


def restore_pnpm(
    mount_point: str, dry_run: bool = False, migrate: bool = True
) -> str:
    """Restore pnpm store to its default location."""
    new_store = _get_new_path("pnpm", mount_point)
    old_store = OLD_PATHS["pnpm"]()
    if dry_run:
        msg = "[DRY-RUN] Would run: pnpm config delete store-dir"
        if migrate:
            msg += f"; {migrate_directory(new_store, old_store, dry_run=True)}"
        return msg
    try:
        subprocess.run(
            ["pnpm", "config", "delete", "store-dir"],
            check=True, capture_output=True, text=True,
        )
        restore_msg = "Deleted pnpm store-dir config"
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        restore_msg = (
            f"pnpm command failed ({e}); "
            f"manually run: pnpm config delete store-dir"
        )
    if migrate:
        restore_msg += f"; {migrate_directory(new_store, old_store)}"
    return restore_msg


def restore_pip(
    mount_point: str, dry_run: bool = False, migrate: bool = True
) -> str:
    """Restore pip cache to its default location."""
    new_cache = _get_new_path("pip", mount_point)
    old_cache = OLD_PATHS["pip"]()
    if dry_run:
        msg = "[DRY-RUN] Would unset PIP_CACHE_DIR"
        if migrate:
            msg += f"; {migrate_directory(new_cache, old_cache, dry_run=True)}"
        return msg
    restore_msg = f"Removed PIP_CACHE_DIR ({_remove_from_shell_rc('PIP_CACHE_DIR')})"
    if migrate:
        restore_msg += f"; {migrate_directory(new_cache, old_cache)}"
    return restore_msg


def restore_cargo(
    mount_point: str, dry_run: bool = False, migrate: bool = True
) -> str:
    """Restore cargo home to its default location."""
    new_home = _get_new_path("cargo", mount_point)
    old_home = OLD_PATHS["cargo"]()
    if dry_run:
        msg = "[DRY-RUN] Would unset CARGO_HOME"
        if migrate:
            msg += f"; {migrate_directory(new_home, old_home, dry_run=True)}"
        return msg
    restore_msg = f"Removed CARGO_HOME ({_remove_from_shell_rc('CARGO_HOME')})"
    if migrate:
        restore_msg += f"; {migrate_directory(new_home, old_home)}"
    return restore_msg


def restore_tmpdir(
    mount_point: str, dry_run: bool = False, migrate: bool = True
) -> str:
    """Restore TMPDIR to its default value.

    ``migrate`` is accepted for API symmetry but is intentionally a no-op
    for TMPDIR: ``/tmp`` is system-managed and should not be copied back.
    """
    if dry_run:
        return "[DRY-RUN] Would unset TMPDIR (no migration; /tmp is system-managed)"
    return f"Removed TMPDIR ({_remove_from_shell_rc('TMPDIR')})"


def restore_docker_buildkit(
    mount_point: str, dry_run: bool = False, migrate: bool = True
) -> str:
    """Docker BuildKit has no persistent config to restore."""
    return "Docker BuildKit has no persistent config to restore"


# ---------------------------------------------------------------------------
# Shell-rc helpers (unchanged)
# ---------------------------------------------------------------------------


def _backup_file(path: Path) -> str:
    """Create a .backup copy next to the file."""
    backup = path.with_suffix(path.suffix + ".backup")
    shutil.copy2(path, backup)
    return str(backup)


def _add_or_replace_in_shell_rc(var_name: str, env_line: str) -> str:
    """Add or replace env var in shell rc. Returns status string."""
    shell_rc = _get_shell_rc()
    if not shell_rc:
        return "no shell rc found"
    if not shell_rc.exists():
        shell_rc.write_text("")
    content = shell_rc.read_text()
    pattern = re.compile(rf'^export\s+{re.escape(var_name)}=.*$', re.MULTILINE)
    if pattern.search(content):
        content = pattern.sub(env_line.rstrip('\n'), content)
        shell_rc.write_text(content)
        return f"replaced in {shell_rc}"
    with open(shell_rc, "a") as f:
        f.write(f"\n# mdisk-caches: {var_name}\n")
        f.write(env_line)
    return f"added to {shell_rc}"


def _remove_from_shell_rc(var_name: str) -> str:
    """Remove an mdisk-caches env var from shell rc.

    Removes both the ``# mdisk-caches: VAR_NAME`` comment and the
    ``export VAR_NAME=...`` line. Returns a status string.
    """
    shell_rc = _get_shell_rc()
    if not shell_rc or not shell_rc.exists():
        return "no shell rc found"

    lines = shell_rc.read_text().splitlines()
    new_lines = []
    removed = False
    comment_marker = f"# mdisk-caches: {var_name}"
    export_prefix = f"export {var_name}="
    for line in lines:
        stripped = line.strip()
        if stripped == comment_marker or stripped.startswith(export_prefix):
            removed = True
            continue
        new_lines.append(line)
    if not removed:
        return f"{var_name} not found in {shell_rc}"

    while new_lines and new_lines[-1].strip() == "":
        new_lines.pop()
    shell_rc.write_text("\n".join(new_lines) + "\n")
    return f"Removed {var_name} from {shell_rc}"


def _get_shell_rc() -> Optional[Path]:
    """Detect shell rc file."""
    shell = os.environ.get("SHELL", "")
    if "zsh" in shell:
        return Path.home() / ".zshrc"
    if "bash" in shell:
        return Path.home() / ".bashrc"
    for rc in [".zshrc", ".bashrc", ".bash_profile", ".profile"]:
        p = Path.home() / rc
        if p.exists():
            return p
    return Path.home() / ".bashrc"
