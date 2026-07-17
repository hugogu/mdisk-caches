# mdisk-caches

CLI tool to set up and manage RAM disk / tmpfs caches on macOS and Ubuntu, with auto-detection, recommendations, and third-party tool redirection (Maven, Gradle, npm, pnpm, pip, cargo, TMPDIR, Docker BuildKit).

## Overview

`mdisk-caches` helps you:

1. **Detect** your system's RAM, existing cache directories, and current mount status
2. **Recommend** an optimal RAM disk size based on your available memory and cache usage
3. **Create** a RAM disk (tmpfs on Linux, APFS RAM disk on macOS)
4. **Configure** your build tools to redirect their caches to the RAM disk
5. **Report** current status and configuration

All operations support `--dry-run` so you can preview changes before applying them.

## Installation

```bash
# Clone the repo
git clone https://github.com/hugogu/mdisk-caches.git
cd mdisk-caches

# Install (no external dependencies — stdlib only)
pip install -e .

# Or run directly without installing
PYTHONPATH=src python -m mdisk_caches
```

## Requirements

- Python 3.9+
- Linux (tmpfs) or macOS (hdiutil + diskutil)
- `sudo` for creating / removing mounts (on Linux)

## Usage

### Detect system info

```bash
mdisk-caches detect
mdisk-caches detect --format json
```

Shows OS, RAM, detected cache directories, and current tmpfs mounts.

### Show recommendations

```bash
mdisk-caches recommend
mdisk-caches recommend --format json
```

Recommends a RAM disk size (typically 30–50% of total RAM, capped at 16 GB), mount point, and tools to configure.

### Create RAM disk

```bash
# Preview (dry run)
mdisk-caches create --dry-run

# Create with default size and mount point
mdisk-caches create --yes

# Custom size and mount point
mdisk-caches create --size 8G --mount /mnt/my-ramdisk --yes
```

### Configure tools

```bash
# Preview all tool configurations (including the planned migration)
mdisk-caches configure --all --dry-run

# Apply all configurations (with migration of existing cache data)
mdisk-caches configure --all --yes

# Configure a single tool
mdisk-caches configure --tool maven --yes

# Skip moving existing data (only redirect the path)
mdisk-caches configure --all --yes --no-migrate
```

### Migrate existing cache data

If you already ran `configure` with `--no-migrate` (or migrated manually) and want to move the data later without touching tool configs again:

```bash
# Preview migration for all tools
mdisk-caches migrate --dry-run

# Migrate all tools
mdisk-caches migrate --yes

# Migrate a single tool
mdisk-caches migrate --tool maven --yes
```

Supported tools:

| Tool | Configuration Method |
|------|---------------------|
| Maven | `~/.m2/settings.xml` (`localRepository`) |
| Gradle | `GRADLE_USER_HOME` env var (in shell rc) |
| npm | `npm config set cache` |
| pnpm | `pnpm config set store-dir` |
| pip | `PIP_CACHE_DIR` env var (in shell rc) |
| cargo | `CARGO_HOME` env var (in shell rc) |
| TMPDIR | `TMPDIR` env var (in shell rc) |
| Docker | Prints BuildKit `--mount=type=cache` hints |

After `configure` points a tool at the new tmpfs location, by default
`mdisk-caches` also **migrates the existing cache data** from the
tool's old on-disk location to the new one and removes the now-empty
old directory. The migration is:

- **Per-tool scoped**: each tool's known old cache path is moved to
  its new tmpfs path. For example, `~/.m2/repository` → `<mount>/maven-repo`.
- **Cross-filesystem safe**: uses `shutil.move`, which copies + deletes
  when crossing the disk→tmpfs boundary.
- **Idempotent**: re-running is a no-op if the old directory is already gone
  or already a symlink to the new location.
- **Safe by default**: a non-empty old directory (e.g. with a hidden
  file) is **kept** with a warning instead of being force-deleted.
- **Opt-out**: pass `--no-migrate` to skip the data move entirely.
- **Dry-run aware**: `configure --dry-run` reports exactly what would
  be moved (with file count) without touching anything.

Tools without an on-disk cache to migrate (`tmpdir`, `docker_buildkit`)
are no-ops for the migration step.

### Check status

```bash
mdisk-caches status
mdisk-caches status --mount /mnt/ramdisk
```

### Full report

```bash
mdisk-caches report
```

### Remove RAM disk

```bash
# Preview
mdisk-caches cleanup --dry-run

# Remove
mdisk-caches cleanup --yes
```

## Architecture

```
mdisk_caches/
├── cli.py        # argparse CLI entry point
├── detect.py     # System detection (OS, RAM, caches, mounts)
├── recommend.py  # Recommendation engine
├── mount.py      # tmpfs / RAM disk creation and removal
├── configure.py  # Third-party tool configuration
└── report.py     # Plain-text report generation
```

All modules use the Python standard library only — no external dependencies.

## Platform Notes

### Linux (Ubuntu)

- Uses `mount -t tmpfs` for RAM disk creation
- Requires `sudo` for mount/umount operations
- `/tmp` is typically already tmpfs on Ubuntu

### macOS

- Uses `hdiutil attach -nomount ram://` + `diskutil erasevolume APFS` for RAM disk creation
- No `sudo` needed for creation (but requires admin for some operations)
- Recommended format: **APFS** (macOS 12+)
- Can set up LaunchAgent for automatic creation at login

## Safety

- **Default to dry-run**: All `create` and `configure` commands support `--dry-run` to preview changes
- **Confirmation prompts**: Commands that modify the system ask for confirmation unless `--yes` is provided
- **Backups**: `configure` commands back up existing config files (e.g., `settings.xml.backup`) before modification
- **Optional migration**: After redirecting, optionally move existing on-disk cache data to the new tmpfs location and remove the now-empty old directory. Pass ``--no-migrate`` to skip.

## Testing

```bash
# Run the test suite (no pytest required — stdlib only)
python3 run_tests.py
```

41 tests covering:
- System detection (OS, RAM, cache sizes)
- Recommendation logic
- Mount operations (dry-run and actual tmpfs integration)
- Tool configuration (file and env var modifications)
- CLI smoke tests

Integration test for tmpfs requires root and is skipped otherwise.

## License

MIT — see [LICENSE](LICENSE).

## Contributing

Issues and PRs welcome at [github.com/hugogu/mdisk-caches](https://github.com/hugogu/mdisk-caches).
