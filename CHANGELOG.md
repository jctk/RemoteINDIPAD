# Changelog

This file documents the change history for RemoteINDIPAD.

## [v0.9.0-beta.6]

### Added

- Added a pip-installable wheel package with sender and receiver commands and platform-specific dependencies.
- Added per-user configuration storage for installed packages. Packaged gamepad profiles are refreshed once per package version, while user edits are preserved on subsequent launches of that version.
- Added GitHub Actions workflows to build PyInstaller archives for Windows x64, Linux x64, and Linux aarch64, and to publish wheel files to GitHub Releases. Wheel publishing can also be started manually with a selected release tag.

### Changed

- Renamed the PyInstaller build script to `build-pyinstaller.py` and updated the workflow references.
- Updated the package version to `0.9.0b6`.

### Documentation

- Updated the README files with executable, wheel, and GitHub repository distribution options and their installation and launch instructions.

## [v0.9.0-beta.3]

### Added

- Added GUI controls for sender heartbeat/request logs and receiver heartbeat/request/action/D-BUS logs.
- Added configurable console word wrapping, with horizontal scrolling when wrapping is disabled.
- Marked error messages with `[ERROR]` and displayed them in red in the GUI consoles.

### Changed

- Standardized console log timestamps and message formatting.
- Made the sender and receiver launch through their GUIs; removed the command-line/headless launch paths.

### Documentation

- Documented abstract actions table.

## [v0.9.0-beta]

### Added

- Initial Release
