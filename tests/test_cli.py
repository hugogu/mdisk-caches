"""Tests for CLI using subprocess."""
import subprocess
import sys
import os


def run_cmd(args):
    """Run CLI command and return (exit_code, stdout, stderr)."""
    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.join(os.path.dirname(__file__), "..", "src")
    result = subprocess.run(
        [sys.executable, "-m", "mdisk_caches"] + args,
        capture_output=True,
        text=True,
        env=env,
    )
    return result.returncode, result.stdout, result.stderr


def test_detect():
    code, out, err = run_cmd(["detect"])
    assert code == 0, f"exit code {code}: {err}"
    assert "OS" in out or "os" in out.lower(), f"unexpected output: {out}"


def test_detect_json():
    code, out, err = run_cmd(["detect", "--format", "json"])
    assert code == 0, f"exit code {code}: {err}"
    assert "total" in out, f"unexpected output: {out}"


def test_recommend():
    code, out, err = run_cmd(["recommend"])
    assert code == 0, f"exit code {code}: {err}"
    assert "RAM Disk Size" in out, f"unexpected output: {out}"


def test_recommend_json():
    code, out, err = run_cmd(["recommend", "--format", "json"])
    assert code == 0, f"exit code {code}: {err}"
    assert "size_bytes" in out, f"unexpected output: {out}"


def test_create_dry_run():
    code, out, err = run_cmd(["create", "--dry-run"])
    assert code == 0, f"exit code {code}: {err}"
    assert "[DRY-RUN]" in out or "DRY-RUN" in out, f"unexpected output: {out}"


def test_configure_dry_run():
    code, out, err = run_cmd(["configure", "--all", "--dry-run"])
    assert code == 0, f"exit code {code}: {err}"
    assert "DRY-RUN" in out or "dry-run" in out.lower(), f"unexpected output: {out}"


def test_migrate_dry_run():
    code, out, err = run_cmd(["migrate", "--dry-run"])
    assert code == 0, f"exit code {code}: {err}"
    assert "DRY-RUN" in out or "dry-run" in out.lower(), f"unexpected output: {out}"


def test_status():
    code, out, err = run_cmd(["status"])
    assert code == 0, f"exit code {code}: {err}"


def test_report():
    code, out, err = run_cmd(["report"])
    assert code == 0, f"exit code {code}: {err}"
    assert "SYSTEM INFO" in out, f"unexpected output: {out}"


def test_cleanup_dry_run():
    code, out, err = run_cmd(["cleanup", "--dry-run"])
    assert code == 0, f"exit code {code}: {err}"


def test_version():
    code, out, err = run_cmd(["--version"])
    assert code == 0, f"exit code {code}: {err}"
    assert "0.1.0" in out, f"unexpected output: {out}"


def test_help():
    code, out, err = run_cmd(["--help"])
    assert code == 0, f"exit code {code}: {err}"
    assert "mdisk-caches" in out, f"unexpected output: {out}"
