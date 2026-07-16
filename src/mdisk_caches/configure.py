"""Configure third-party tools to use RAM disk."""
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from mdisk_caches.detect import get_os

SUPPORTED_TOOLS = [
    "maven", "gradle", "npm", "pnpm", "pip", "cargo",
    "tmpdir", "docker_buildkit",
]


def configure_all(mount_point: str, dry_run: bool = False) -> Dict[str, str]:
    """Configure all supported tools. Returns dict of tool -> result message."""
    results = {}
    for tool in SUPPORTED_TOOLS:
        func = globals().get(f"configure_{tool}")
        if func:
            results[tool] = func(mount_point, dry_run)
    return results


def configure_maven(mount_point: str, dry_run: bool = False) -> str:
    """Configure Maven localRepository to use RAM disk."""
    m2_dir = Path.home() / ".m2"
    new_repo = Path(mount_point) / "maven-repo"
    settings_file = m2_dir / "settings.xml"
    if dry_run:
        return f"[DRY-RUN] Would set Maven localRepository to {new_repo}"
    m2_dir.mkdir(parents=True, exist_ok=True)
    new_repo.mkdir(parents=True, exist_ok=True)
    if not settings_file.exists():
        settings_file.write_text(
            "\u003csettings\u003e\n"
            f'  \u003clocalRepository\u003e{new_repo}\u003c/localRepository\u003e\n'
            "\u003c/settings\u003e\n"
        )
        return f"Created {settings_file} with localRepository={new_repo}"
    backup = _backup_file(settings_file)
    content = settings_file.read_text()
    if "\u003clocalRepository\u003e" in content:
        content = re.sub(
            r"\u003clocalRepository\u003e.*?\u003c/localRepository\u003e",
            f"\u003clocalRepository\u003e{new_repo}\u003c/localRepository\u003e",
            content,
            count=1,
        )
    else:
        content = content.replace(
            "\u003c/settings\u003e",
            f"  \u003clocalRepository\u003e{new_repo}\u003c/localRepository\u003e\n\u003c/settings\u003e",
        )
    settings_file.write_text(content)
    return f"Updated Maven localRepository to {new_repo} (backup: {backup})"


def configure_gradle(mount_point: str, dry_run: bool = False) -> str:
    """Configure Gradle user home to use RAM disk."""
    new_home = Path(mount_point) / "gradle"
    if dry_run:
        return f"[DRY-RUN] Would set GRADLE_USER_HOME={new_home}"
    new_home.mkdir(parents=True, exist_ok=True)
    env_line = f'export GRADLE_USER_HOME="{new_home}"\n'
    result = _add_or_replace_in_shell_rc("GRADLE_USER_HOME", env_line)
    return f"Set GRADLE_USER_HOME={new_home} ({result})"


def configure_npm(mount_point: str, dry_run: bool = False) -> str:
    """Configure npm cache to use RAM disk."""
    new_cache = Path(mount_point) / "npm"
    if dry_run:
        return f"[DRY-RUN] Would run: npm config set cache {new_cache} --global"
    new_cache.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            ["npm", "config", "set", "cache", str(new_cache), "--global"],
            check=True, capture_output=True, text=True,
        )
        return f"Set npm cache to {new_cache}"
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        return f"npm command failed ({e}); manually set: npm config set cache {new_cache}"


def configure_pnpm(mount_point: str, dry_run: bool = False) -> str:
    """Configure pnpm store to use RAM disk."""
    new_store = Path(mount_point) / "pnpm"
    if dry_run:
        return f"[DRY-RUN] Would run: pnpm config set store-dir {new_store}"
    new_store.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            ["pnpm", "config", "set", "store-dir", str(new_store)],
            check=True, capture_output=True, text=True,
        )
        return f"Set pnpm store-dir to {new_store}"
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        return f"pnpm command failed ({e}); manually set: pnpm config set store-dir {new_store}"


def configure_pip(mount_point: str, dry_run: bool = False) -> str:
    """Configure pip cache to use RAM disk."""
    new_cache = Path(mount_point) / "pip"
    if dry_run:
        return f"[DRY-RUN] Would set PIP_CACHE_DIR={new_cache}"
    new_cache.mkdir(parents=True, exist_ok=True)
    env_line = f'export PIP_CACHE_DIR="{new_cache}"\n'
    result = _add_or_replace_in_shell_rc("PIP_CACHE_DIR", env_line)
    return f"Set PIP_CACHE_DIR={new_cache} ({result})"


def configure_cargo(mount_point: str, dry_run: bool = False) -> str:
    """Configure cargo home to use RAM disk."""
    new_home = Path(mount_point) / "cargo"
    if dry_run:
        return f"[DRY-RUN] Would set CARGO_HOME={new_home}"
    new_home.mkdir(parents=True, exist_ok=True)
    env_line = f'export CARGO_HOME="{new_home}"\n'
    result = _add_or_replace_in_shell_rc("CARGO_HOME", env_line)
    return f"Set CARGO_HOME={new_home} ({result})"


def configure_tmpdir(mount_point: str, dry_run: bool = False) -> str:
    """Configure TMPDIR to use RAM disk."""
    new_tmp = Path(mount_point) / "tmp"
    if dry_run:
        return f"[DRY-RUN] Would set TMPDIR={new_tmp}"
    new_tmp.mkdir(parents=True, exist_ok=True)
    env_line = f'export TMPDIR="{new_tmp}"\n'
    result = _add_or_replace_in_shell_rc("TMPDIR", env_line)
    return f"Set TMPDIR={new_tmp} ({result})"


def configure_docker_buildkit(mount_point: str, dry_run: bool = False) -> str:
    """Print Docker BuildKit cache mount hints."""
    return (
        "Docker BuildKit cache mount hints:\n"
        "  # In your Dockerfile:\n"
        "  RUN --mount=type=cache,target=/root/.m2 \\n"
        "      mvn package\n"
        "  RUN --mount=type=cache,target=/root/.npm \\n"
        "      npm ci\n"
        "  # Enable BuildKit: export DOCKER_BUILDKIT=1"
    )


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
