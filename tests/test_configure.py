"""Tests for configure.py."""
import os
import tempfile
from pathlib import Path

from mdisk_caches.configure import (
    configure_maven,
    configure_gradle,
    configure_npm,
    configure_pip,
    configure_tmpdir,
    configure_docker_buildkit,
    _add_or_replace_in_shell_rc,
    _get_shell_rc,
)


def test_configure_maven_dry_run():
    result = configure_maven("/tmp/ramdisk", dry_run=True)
    assert "[DRY-RUN]" in result


def test_configure_maven_actual():
    """Test actual Maven settings.xml creation."""
    with tempfile.TemporaryDirectory() as tmp:
        fake_home = Path(tmp) / "home"
        fake_home.mkdir()
        original_home = Path.home
        Path.home = lambda: fake_home
        try:
            mount = "/tmp/ramdisk"
            result = configure_maven(mount, dry_run=False)
            assert "Created" in result or "Updated" in result
            settings_file = fake_home / ".m2" / "settings.xml"
            assert settings_file.exists()
            content = settings_file.read_text()
            assert "/tmp/ramdisk/maven-repo" in content
        finally:
            Path.home = original_home


def test_configure_gradle_dry_run():
    result = configure_gradle("/tmp/ramdisk", dry_run=True)
    assert "[DRY-RUN]" in result


def test_configure_npm_dry_run():
    result = configure_npm("/tmp/ramdisk", dry_run=True)
    assert "[DRY-RUN]" in result


def test_configure_pip_dry_run():
    result = configure_pip("/tmp/ramdisk", dry_run=True)
    assert "[DRY-RUN]" in result


def test_configure_tmpdir_dry_run():
    result = configure_tmpdir("/tmp/ramdisk", dry_run=True)
    assert "[DRY-RUN]" in result


def test_configure_docker_buildkit():
    result = configure_docker_buildkit("/tmp/ramdisk", dry_run=False)
    assert "BuildKit" in result
    assert "--mount=type=cache" in result


def test_add_or_replace_in_shell_rc():
    """Test shell rc modification with a temp file."""
    with tempfile.TemporaryDirectory() as tmp:
        fake_rc = Path(tmp) / ".bashrc"
        original_get_shell_rc = _get_shell_rc

        def fake_get_shell_rc():
            return fake_rc

        import mdisk_caches.configure as configure_module
        configure_module._get_shell_rc = fake_get_shell_rc
        try:
            result = _add_or_replace_in_shell_rc("TEST_VAR", 'export TEST_VAR="value1"\n')
            assert "added" in result
            content = fake_rc.read_text()
            assert 'export TEST_VAR="value1"' in content

            result = _add_or_replace_in_shell_rc("TEST_VAR", 'export TEST_VAR="value2"\n')
            assert "replaced" in result
            content = fake_rc.read_text()
            assert 'export TEST_VAR="value2"' in content
            assert 'export TEST_VAR="value1"' not in content
        finally:
            configure_module._get_shell_rc = original_get_shell_rc


def test_get_shell_rc_fallback():
    """Test shell rc detection."""
    original_shell = os.environ.get("SHELL")
    os.environ["SHELL"] = "/bin/bash"
    original_home = Path.home
    with tempfile.TemporaryDirectory() as tmp:
        Path.home = lambda: Path(tmp)
        try:
            rc = _get_shell_rc()
            assert rc.name == ".bashrc"
        finally:
            Path.home = original_home
            if original_shell is not None:
                os.environ["SHELL"] = original_shell
            elif "SHELL" in os.environ:
                del os.environ["SHELL"]



# ---------------------------------------------------------------------------
# Migration tests
# ---------------------------------------------------------------------------

import shutil as _shutil
from mdisk_caches.configure import migrate_directory, OLD_PATHS


def _write(p, content="x"):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


def test_migrate_directory_no_old_data(tmp_path, monkeypatch):
    """No source directory => 'nothing to migrate'."""
    monkeypatch.setenv("HOME", str(tmp_path))
    src = tmp_path / "old"          # does not exist
    dst = tmp_path / "new"
    result = migrate_directory(src, dst)
    assert "nothing to migrate" in result
    assert not dst.exists()


def test_migrate_directory_dry_run_reports(tmp_path, monkeypatch):
    """Dry-run must NOT move data, only report the planned move."""
    monkeypatch.setenv("HOME", str(tmp_path))
    src = tmp_path / "old"
    dst = tmp_path / "new"
    _write(src / "a.bin", "AAA")
    _write(src / "b.bin", "BBB")
    result = migrate_directory(src, dst, dry_run=True)
    assert "[DRY-RUN]" in result
    assert "2 entries" in result
    # Old data untouched
    assert (src / "a.bin").read_text() == "AAA"
    assert (src / "b.bin").read_text() == "BBB"
    assert not dst.exists()


def test_migrate_directory_moves_and_cleans(tmp_path, monkeypatch):
    """When src has data and is emptyable, src is removed after move."""
    monkeypatch.setenv("HOME", str(tmp_path))
    src = tmp_path / "old"
    dst = tmp_path / "new"
    _write(src / "a.bin", "AAA")
    _write(src / "sub" / "b.bin", "BBB")
    result = migrate_directory(src, dst)
    assert "migrated 2 entries" in result
    assert "removed empty" in result
    assert (dst / "a.bin").read_text() == "AAA"
    assert (dst / "sub" / "b.bin").read_text() == "BBB"
    assert not src.exists()


def test_migrate_directory_keeps_nonempty_old(tmp_path, monkeypatch):
    """Hidden files in src keep the old directory around (no data loss)."""
    monkeypatch.setenv("HOME", str(tmp_path))
    src = tmp_path / "old"
    dst = tmp_path / "new"
    _write(src / "a.bin", "AAA")
    _write(src / ".hidden", "do-not-move")
    result = migrate_directory(src, dst)
    assert "migrated 1 entries" in result
    assert "not empty" in result
    assert (dst / "a.bin").read_text() == "AAA"
    # src retained because .hidden is still there
    assert src.exists()
    assert (src / ".hidden").read_text() == "do-not-move"


def test_migrate_directory_idempotent_same_path(tmp_path, monkeypatch):
    """If src resolves to dst (e.g. user symlinked it), no-op."""
    monkeypatch.setenv("HOME", str(tmp_path))
    real = tmp_path / "real"
    real.mkdir()
    _write(real / "x", "X")
    # src is a symlink that points to real
    src = tmp_path / "link"
    src.symlink_to(real)
    # dst == real
    result = migrate_directory(src, real)
    assert "same path" in result
    # The symlink should still be there
    assert src.is_symlink()


def test_migrate_directory_removes_dangling_symlink(tmp_path, monkeypatch):
    """A symlink already pointing at dst can be safely removed."""
    monkeypatch.setenv("HOME", str(tmp_path))
    src = tmp_path / "link"
    dst = tmp_path / "dst"
    dst.mkdir()
    src.symlink_to(dst)
    result = migrate_directory(src, dst)
    assert "removed symlink" in result
    assert not src.exists()
    assert dst.exists()


def test_configure_maven_migrates_old_repo(tmp_path, monkeypatch):
    """End-to-end: configure_maven moves ~/.m2/repository to <mount>/maven-repo."""
    monkeypatch.setenv("HOME", str(tmp_path))
    old_repo = tmp_path / ".m2" / "repository"
    _write(old_repo / "com" / "foo" / "bar.jar", "fakejar")
    # Point maven settings at our mock HOME; configure_maven uses
    # Path.home() via monkeypatch.
    from mdisk_caches import configure as cfg
    out = cfg.configure_maven(str(tmp_path / "mnt"), dry_run=True)
    assert "localRepository" in out
    # Dry-run must NOT move data
    assert (old_repo / "com" / "foo" / "bar.jar").exists()
    # Now run for real
    out = cfg.configure_maven(str(tmp_path / "mnt"))
    new_repo = tmp_path / "mnt" / "maven-repo"
    assert (new_repo / "com" / "foo" / "bar.jar").read_text() == "fakejar"
    assert not old_repo.exists()
    # settings.xml exists, points at new repo
    s = (tmp_path / ".m2" / "settings.xml").read_text()
    assert str(new_repo) in s


def test_old_paths_known_tools():
    """The migration source-of-truth table covers every migratable tool."""
    # tmpdir + docker_buildkit intentionally do NOT migrate.
    expected_migratable = {"maven", "gradle", "npm", "pnpm", "pip", "cargo"}
    assert set(OLD_PATHS.keys()) == expected_migratable
