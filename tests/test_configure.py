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
