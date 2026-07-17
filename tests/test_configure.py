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
    _remove_from_shell_rc,
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
#
# These tests follow the project pattern of `with
# tempfile.TemporaryDirectory() as tmp:` and `Path.home = lambda: fake_home`
# instead of pytest fixtures (run_tests.py is a stdlib-only runner).

from mdisk_caches.configure import migrate_directory, OLD_PATHS


def _write(p, content="x"):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


def _in_tmp(tmp, fn):
    """Run ``fn(Path(tmp))`` with Path.home() redirected to a fake HOME."""
    fake_home = Path(tmp) / "home"
    fake_home.mkdir()
    original_home = Path.home
    Path.home = lambda: fake_home
    try:
        return fn(fake_home)
    finally:
        Path.home = original_home


def test_migrate_directory_no_old_data():
    """No source directory => 'nothing to migrate'."""
    with tempfile.TemporaryDirectory() as tmp:
        def run(fake_home):
            src = fake_home / "old"  # does not exist
            dst = fake_home / "new"
            result = migrate_directory(src, dst)
            assert "nothing to migrate" in result
            assert not dst.exists()
        _in_tmp(tmp, run)


def test_migrate_directory_dry_run_reports():
    """Dry-run must NOT move data, only report the planned move."""
    with tempfile.TemporaryDirectory() as tmp:
        def run(fake_home):
            src = fake_home / "old"
            dst = fake_home / "new"
            _write(src / "a.bin", "AAA")
            _write(src / "b.bin", "BBB")
            result = migrate_directory(src, dst, dry_run=True)
            assert "[DRY-RUN]" in result
            assert "2 entries" in result
            # Old data untouched
            assert (src / "a.bin").read_text() == "AAA"
            assert (src / "b.bin").read_text() == "BBB"
            assert not dst.exists()
        _in_tmp(tmp, run)


def test_migrate_directory_moves_and_cleans():
    """When src has data and is emptyable, src is removed after move."""
    with tempfile.TemporaryDirectory() as tmp:
        def run(fake_home):
            src = fake_home / "old"
            dst = fake_home / "new"
            _write(src / "a.bin", "AAA")
            _write(src / "sub" / "b.bin", "BBB")
            result = migrate_directory(src, dst)
            assert "migrated 2 entries" in result
            assert "removed empty" in result
            assert (dst / "a.bin").read_text() == "AAA"
            assert (dst / "sub" / "b.bin").read_text() == "BBB"
            assert not src.exists()
        _in_tmp(tmp, run)


def test_migrate_directory_keeps_nonempty_old():
    """Hidden files in src keep the old directory around (no data loss)."""
    with tempfile.TemporaryDirectory() as tmp:
        def run(fake_home):
            src = fake_home / "old"
            dst = fake_home / "new"
            _write(src / "a.bin", "AAA")
            _write(src / ".hidden", "do-not-move")
            result = migrate_directory(src, dst)
            assert "migrated 1 entries" in result
            assert "not empty" in result
            assert (dst / "a.bin").read_text() == "AAA"
            # src retained because .hidden is still there
            assert src.exists()
            assert (src / ".hidden").read_text() == "do-not-move"
        _in_tmp(tmp, run)


def test_migrate_directory_existing_symlink_is_removed():
    """A symlink already pointing at dst means the user pre-redirected;
    remove the symlink instead of copying data (which would be a no-op
    double-move)."""
    with tempfile.TemporaryDirectory() as tmp:
        def run(fake_home):
            real = fake_home / "real"
            real.mkdir()
            _write(real / "x", "X")
            # src is a symlink that points to real (= dst)
            src = fake_home / "link"
            src.symlink_to(real)
            result = migrate_directory(src, real)
            assert "removed symlink" in result
            assert not src.exists()
            # The data at dst is untouched
            assert (real / "x").read_text() == "X"
        _in_tmp(tmp, run)


def test_migrate_directory_removes_dangling_symlink():
    """A symlink already pointing at dst can be safely removed."""
    with tempfile.TemporaryDirectory() as tmp:
        def run(fake_home):
            src = fake_home / "link"
            dst = fake_home / "dst"
            dst.mkdir()
            src.symlink_to(dst)
            result = migrate_directory(src, dst)
            assert "removed symlink" in result
            assert not src.exists()
            assert dst.exists()
        _in_tmp(tmp, run)


def test_configure_maven_migrates_old_repo():
    """End-to-end: configure_maven moves ~/.m2/repository to <mount>/maven-repo."""
    with tempfile.TemporaryDirectory() as tmp:
        def run(fake_home):
            old_repo = fake_home / ".m2" / "repository"
            _write(old_repo / "com" / "foo" / "bar.jar", "fakejar")
            mnt = fake_home / "mnt"
            out = configure_maven(str(mnt), dry_run=True)
            assert "localRepository" in out
            # Dry-run must NOT move data
            assert (old_repo / "com" / "foo" / "bar.jar").exists()
            # Now run for real
            out = configure_maven(str(mnt))
            new_repo = mnt / "maven-repo"
            assert (new_repo / "com" / "foo" / "bar.jar").read_text() == "fakejar"
            assert not old_repo.exists()
            # settings.xml exists, points at new repo
            s = (fake_home / ".m2" / "settings.xml").read_text()
            assert str(new_repo) in s
        _in_tmp(tmp, run)


def test_old_paths_known_tools():
    """The migration source-of-truth table covers every migratable tool."""
    # tmpdir + docker_buildkit intentionally do NOT migrate.
    expected_migratable = {"maven", "gradle", "npm", "pnpm", "pip", "cargo"}
    assert set(OLD_PATHS.keys()) == expected_migratable


# ---------------------------------------------------------------------------
# Restore tests
# ---------------------------------------------------------------------------

from mdisk_caches.configure import (
    restore_all,
    restore_maven,
    restore_gradle,
    restore_npm,
    restore_pnpm,
    restore_pip,
    restore_cargo,
    restore_tmpdir,
    restore_docker_buildkit,
    SUPPORTED_TOOLS,
)


def test_restore_maven_dry_run():
    result = restore_maven("/tmp/ramdisk", dry_run=True)
    assert "[DRY-RUN]" in result


def test_restore_maven_from_backup():
    """If a backup exists, restore uses it."""
    with tempfile.TemporaryDirectory() as tmp:
        def run(fake_home):
            m2_dir = fake_home / ".m2"
            m2_dir.mkdir()
            backup = m2_dir / "settings.xml.backup"
            backup.write_text("<settings><localRepository>/old/repo</localRepository></settings>")
            result = restore_maven("/tmp/ramdisk")
            assert "Restored" in result
            restored = (m2_dir / "settings.xml").read_text()
            assert "/old/repo" in restored
        _in_tmp(tmp, run)


def test_restore_maven_removes_ramdisk_repo():
    """Without a backup, restore removes the RAM disk localRepository line."""
    with tempfile.TemporaryDirectory() as tmp:
        def run(fake_home):
            m2_dir = fake_home / ".m2"
            m2_dir.mkdir()
            settings = m2_dir / "settings.xml"
            settings.write_text(
                "<settings>\n"
                "  <localRepository>/tmp/ramdisk/maven-repo</localRepository>\n"
                "</settings>\n"
            )
            result = restore_maven("/tmp/ramdisk")
            assert "Removed RAM disk localRepository" in result
            content = settings.read_text()
            assert "maven-repo" not in content
        _in_tmp(tmp, run)


def test_restore_maven_migrates_data_back():
    """End-to-end: restore_maven moves data back to ~/.m2/repository."""
    with tempfile.TemporaryDirectory() as tmp:
        def run(fake_home):
            m2_dir = fake_home / ".m2"
            m2_dir.mkdir()
            old_repo = m2_dir / "repository"
            mnt = fake_home / "mnt"
            new_repo = mnt / "maven-repo"
            _write(new_repo / "com" / "foo" / "bar.jar", "fakejar")
            settings = m2_dir / "settings.xml"
            settings.write_text(
                "<settings>\n"
                "  <localRepository>/tmp/ramdisk/maven-repo</localRepository>\n"
                "</settings>\n"
            )
            result = restore_maven(str(mnt))
            assert (old_repo / "com" / "foo" / "bar.jar").read_text() == "fakejar"
            assert "Migrated" in result or "migrated" in result
        _in_tmp(tmp, run)


def test_restore_gradle_dry_run():
    result = restore_gradle("/tmp/ramdisk", dry_run=True)
    assert "[DRY-RUN]" in result


def test_restore_gradle_removes_env():
    """restore_gradle removes GRADLE_USER_HOME from shell rc."""
    with tempfile.TemporaryDirectory() as tmp:
        fake_rc = Path(tmp) / ".bashrc"
        original_get_shell_rc = _get_shell_rc

        def fake_get_shell_rc():
            return fake_rc

        import mdisk_caches.configure as configure_module
        configure_module._get_shell_rc = fake_get_shell_rc
        try:
            _add_or_replace_in_shell_rc(
                "GRADLE_USER_HOME", 'export GRADLE_USER_HOME="/tmp/ramdisk/gradle"\n'
            )
            result = restore_gradle("/tmp/ramdisk")
            assert "Removed GRADLE_USER_HOME" in result
            content = fake_rc.read_text()
            assert "GRADLE_USER_HOME" not in content
        finally:
            configure_module._get_shell_rc = original_get_shell_rc


def test_restore_npm_dry_run():
    result = restore_npm("/tmp/ramdisk", dry_run=True)
    assert "[DRY-RUN]" in result


def test_restore_pnpm_dry_run():
    result = restore_pnpm("/tmp/ramdisk", dry_run=True)
    assert "[DRY-RUN]" in result


def test_restore_pip_dry_run():
    result = restore_pip("/tmp/ramdisk", dry_run=True)
    assert "[DRY-RUN]" in result


def test_restore_cargo_dry_run():
    result = restore_cargo("/tmp/ramdisk", dry_run=True)
    assert "[DRY-RUN]" in result


def test_restore_tmpdir():
    result = restore_tmpdir("/tmp/ramdisk", dry_run=True)
    assert "[DRY-RUN]" in result


def test_restore_docker_buildkit():
    result = restore_docker_buildkit("/tmp/ramdisk", dry_run=False)
    assert "no persistent config" in result


def test_restore_all_dry_run():
    results = restore_all("/tmp/ramdisk", dry_run=True)
    for tool in SUPPORTED_TOOLS:
        assert tool in results
        assert "[DRY-RUN]" in results[tool] or "no persistent config" in results[tool]


def test_remove_from_shell_rc():
    """_remove_from_shell_rc removes both comment and export lines."""
    with tempfile.TemporaryDirectory() as tmp:
        fake_rc = Path(tmp) / ".bashrc"
        original_get_shell_rc = _get_shell_rc

        def fake_get_shell_rc():
            return fake_rc

        import mdisk_caches.configure as configure_module
        configure_module._get_shell_rc = fake_get_shell_rc
        try:
            _add_or_replace_in_shell_rc("TEST_VAR", 'export TEST_VAR="value"\n')
            result = _remove_from_shell_rc("TEST_VAR")
            assert "Removed" in result
            content = fake_rc.read_text()
            assert "TEST_VAR" not in content
        finally:
            configure_module._get_shell_rc = original_get_shell_rc


def test_remove_from_shell_rc_not_found():
    """_remove_from_shell_rc reports when a var is not present."""
    with tempfile.TemporaryDirectory() as tmp:
        fake_rc = Path(tmp) / ".bashrc"
        original_get_shell_rc = _get_shell_rc

        def fake_get_shell_rc():
            return fake_rc

        import mdisk_caches.configure as configure_module
        configure_module._get_shell_rc = fake_get_shell_rc
        try:
            fake_rc.write_text("# existing\n")
            result = _remove_from_shell_rc("MISSING_VAR")
            assert "not found" in result
        finally:
            configure_module._get_shell_rc = original_get_shell_rc
