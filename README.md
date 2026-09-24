# RemoteINDIPAD

[日本語 README](README.ja.md)

A tool that transmits input from a gamepad connected to Windows over a LAN to KStars / Ekos / INDI on Linux, such as StellarMate OS or Ubuntu, allowing you to operate equipment including focusers, filter wheels, rotators, and the KStars SkyMap.

## Overview

- The project consists of two programs: a sender and a receiver.
- Sender (Windows): Captures gamepad input, converts it into abstract operations, and sends them over the network.
- Receiver (Linux): Converts the received abstract operations into D-BUS control commands for KStars / Ekos / INDI to operate the equipment.

> ⚠️ This program has been developed almost entirely with GitHub Copilot.
> Implementations in ways the developer did not anticipate, redundant code, and bugs may remain.

![Diagram](images/diagram.png)

## Tested Devices

### GAMEPAD

- Microsoft Xbox Wireless Controller
- ELECOM JC-U3712T
- 8BitDo Zero 2

### INDI Devices

- Juwei 17
- GEMINI EAF
- ZWO CAA
- ToupTek AWF-L

## Controllable KStars / Ekos / INDI Features

### KStars

- SkyMap: Zoom in, zoom out, and rotate the field of view

### INDI

- MOUNT: Slew, increase or decrease speed, and stop slewing
- FOCUSER: Focus in, focus out, and increase or decrease the step count
- Rotator: Rotate and stop rotation
- Filter wheel: Change the filter slot

## Distribution

- Two distribution formats are available.
- One is the executable format, and the other is the script format.
- Use either one of them.

## Executable Format

- The executable format consists of files created with PyInstaller from the script-format files described below, allowing them to be run as single files.
- No additional files are required. (This has not been thoroughly verified.)
- Builds are available for Windows x64 and Linux aarch64.
- The Linux aarch64 build is intended for Raspberry Pi devices running StellarMate OS and similar systems.

### Download

Download `RemoteINDIPAD-windows-x64.zip` for Windows and `RemoteINDIPAD-linux-aarch64.tar.gz` for StellarMate OS from [Releases](https://github.com/jctk/RemoteINDIPAD/releases).

### Installation

1. On Windows, extract `RemoteINDIPAD-windows-x64.zip`, and place `remote_indipad_sender.exe` and `gamepad_profiles.json` in the same folder of your choice.
2. On StellarMate OS, extract `RemoteINDIPAD-linux-aarch64.tar.gz`, and place `remote_indipad_receiver` in a folder of your choice.

### Usage

1. Start KStars on StellarMate OS and start the Ekos Profile. If you are using a mount, unpark it first.
1. Start `remote_indipad_receiver` on StellarMate OS.
1. The devices from the started Ekos Profile are listed in the Mount / Focuser / Filter Wheel / Rotator dropdown lists. If multiple devices of the same type are connected, select one manually from the appropriate dropdown list.
1. Connect the GAMEPAD to the Windows PC.
1. Start `remote_indipad_sender.exe` on Windows.
1. Select the GAMEPAD to use in `[Controller]`, then click `[Edit Mapping]` to open the INDIPAD Mapping Editor. Map the DPAD / Buttons / Axes to KStars / INDI operations. When mapping is complete, close the INDIPAD Mapping Editor with `[Close]`.
1. Enter the IP address of StellarMate OS in `[Host]`, then click `[Connect]` to connect to `remote_indipad_receiver` on StellarMate OS. Once connected, both consoles log the connection.
1. Operate the equipment with the GAMEPAD.

> ⚠️ Start with conservative movements and verify operation first. In particular, abnormal behavior of a mount or rotator may damage the equipment. Make sure you can stop the equipment at any time.

## Script Format

The script format is the development environment for RemoteINDIPAD.

### Requirements

- Sender (Windows)
  - Windows 11
  - Python 3.10 or later
  - `pygame` (for obtaining gamepad input)
  - `pyside6` (GUI)
- Receiver (Linux)
  - A Linux environment such as StellarMate OS 2.x or Ubuntu
  - Python 3.x
  - `pyside6` (GUI)
  - `dbus-next` (D-BUS integration with KStars / Ekos / INDI)

### Installation

### Sender (Windows)

```powershell
cd ~
mkdir Projects
cd Projects
git clone https://github.com/jctk/RemoteINDIPAD.git
cd RemoteINDIPAD

python -m venv .venv
.venv\Scripts\activate
pip install pygame pyside6
```

### Receiver (Linux)

```bash
cd ~
mkdir Projects
cd Projects
git clone https://github.com/jctk/RemoteINDIPAD.git
cd RemoteINDIPAD

python -m venv .venv
source .venv/bin/activate
pip install pyside6 dbus-next
```

## Starting the Programs

- Start each script with Python.
- For usage instructions other than how to start the programs, see [Usage](#usage).

### Windows

```powershell
python remote_indipad_sender.py
```

### StellarMate OS

```bash
python remote_indipad_receiver.py
```

## License

Copyrighted works in this project, including the RemoteINDIPAD source code, configuration files, and documentation (excluding third-party libraries), may be used, modified, and redistributed under the terms of the MIT License.

Third-party libraries and related components included in the distributions are subject to their respective license terms. Check the licenses and copyright notices for each library before using, modifying, or redistributing them.

The main dependency libraries currently identified are as follows:

- `pygame`: GNU LGPL 2.1
- `PySide6` / Qt for Python: LGPL 3.0, GPL, or a commercial license
- `dbus-next`: MIT License
- `PyInstaller`: GPL 2.0 or later, with a special exception permitting distribution of applications created with PyInstaller
- Python standard library: Python Software Foundation License

The license texts that have been checked are stored in the [license](license/) folder. For dependencies not listed here, including components used internally by PySide6, Qt, and pygame, check the license terms applicable to the versions and distribution formats you actually use.

In particular, when distributing an executable that uses PySide6, comply with the LGPL terms, retain the Qt / PySide6 license notices, and do not unjustifiably prevent users from replacing the relevant libraries. Executables created with PyInstaller are also subject to the terms of every bundled dependency, in addition to PyInstaller's own exception.