# Changelog

This file documents the change history for RemoteINDIPAD.

## [v0.9.1]

### Added

- Added a "Start on launch" setting for the Receiver, enabled by default and saved with the GUI settings.
- Added an Xbox One gamepad profile with detailed action mappings.

### Changed

- Centralized the application version in the `VERSION` file and use it for the Sender, Receiver, package, and PyInstaller builds.
- Updated the Sender and Receiver window titles to include "RemoteINDIPAD".
- Improved Receiver window layout and button behavior.

### Bug Fixes

- Fixed unstable joystick detection in the Sender by waiting for the joystick count to stabilize, with a configurable maximum wait.

### Documentation

- Added documentation for gamepad profiles and settings.
- Documented configuration file locations for Windows and Linux, and clarified the Receiver's "Start on launch" setting.

## [v0.9.1-beta.1]

### Added

- Added IPv4 and IPv6 receiver listen-address selection, including local-address discovery and unavailable-state handling for addresses that cannot be bound.
- Added receiver connection-state reporting and Start / Stop controls. Stopping the receiver also stops active mount and rotator movement.
- Added sender gamepad rescanning and connection-state handling for controllers connected or disconnected while the application is running.
- Added a single-command wheel build that produces separate Sender and Receiver wheels. The Sender wheel includes `gamepad_profiles.json`; the Receiver wheel contains only receiver modules.

### Changed

- Replaced the `pygame-ce` dependency with `pygame`.
- Updated PyInstaller builds to include only the Sender and `gamepad_profiles.json` on Windows, and only the Receiver on Linux.
- Updated the package version to `0.9.1b1`.

### Documentation

- Updated the README files with IPv4/IPv6 listen-address behavior, receiver Start / Stop operation, sender gamepad scanning, platform-specific wheel contents, and build instructions.
- Updated the development policy and pygame license filename for the dependency change.

## [v0.9.0-beta.8]

### Added

- Added INDIPAD JSON protocol documentation and a JSON schema definition (`docs/protocol.md`, `docs/protocol.schema.json`).
- Added the GNU Lesser General Public License version 2.1 to the project.

### Changed

- Migrated D-Bus integration from `dbus-next` to `QtDBus`, removing the `dbus-next` dependency and its license file.
- Replaced the `pygame` dependency with `pygame-ce`.
- Added a placeholder type for missing PySide6 classes so that using GUI features without PySide6 installed raises a clear error instead of behaving like a bare `object`.
- Removed deprecated per-instance `Joystick.init()` calls in the sender (pygame 2.4.0+ deprecation).
- Removed `FOCUS_STOP` and `SKYMAP_MOVE` from the action names list for clarity.
- Renamed `pygame-LGPL-2.1.txt` to `pygame-ce-LGPL-2.1.txt`.
- Updated `build-pyinstaller.yml` (Ubuntu runner version, target/job description clarity).
- Fixed the gamepad profiles configuration path used in `test_default_mapping_uses_gamepad_profile_value`.
- Updated the package version to `0.9.0b8`.

### Documentation

- Updated the README files to clarify wheel file installation/usage instructions and the QtDBus migration.
- Updated `docs/DEVELOPMENT_POLICY.md` for the QtDBus migration and LGPL-2.1 license.

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
