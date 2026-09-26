"""Build remote_indipad_receiver.py and remote_indipad_sender.py with PyInstaller.

The output directory varies by whether the build environment is Windows x64,
Linux x64, or Linux aarch64. Both scripts are built as one-file applications
with the console hidden. If one build fails, the other build continues.
"""

import hashlib
import argparse
import platform
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
BUILD_DIR = ROOT_DIR / "build"

# Scripts to build.
SCRIPTS = ["remote_indipad_receiver.py", "remote_indipad_sender.py"]

# Additional data files placed alongside the executables, by script.
EXTRA_DATA_FILES = {
    "remote_indipad_sender.py": ["gamepad_profiles.json"],
}
ICON_DATA_FILE = "resources/icon.png"

# Output directory, icon, and distribution archive settings by environment.
PLATFORM_SETTINGS = {
    "windows-x64": {
        "release_dir": "windows-x64",
        "icon": str(ROOT_DIR / "resources" / "icon.ico"),
        "exe_suffix": ".exe",
        "archive_name": "RemoteINDIPAD-windows-x64",
        "archive_format": "zip",
    },
    "linux-aarch64": {
        "release_dir": "linux-aarch64",
        "icon": str(ROOT_DIR / "resources" / "icon.icns"),
        "exe_suffix": "",
        "archive_name": "RemoteINDIPAD-linux-aarch64",
        "archive_format": "tar.gz",
    },
    "linux-x64": {
        "release_dir": "linux-x64",
        "icon": str(ROOT_DIR / "resources" / "icon.icns"),
        "exe_suffix": "",
        "archive_name": "RemoteINDIPAD-linux-x64",
        "archive_format": "tar.gz",
    },
}


def create_argument_parser() -> argparse.ArgumentParser:
    """Create the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Build the RemoteINDIPAD receiver and sender as standalone "
            "PyInstaller applications."
        ),
        epilog=(
            "The build platform is detected automatically. The executables and "
            "gamepad_profiles.json are saved under release/<platform>/, where "
            "<platform> is windows-x64, linux-x64, or linux-aarch64. The "
            "distribution archive and its SHA256 checksum are saved in the "
            "same directory. Windows builds produce a ZIP archive; Linux "
            "builds produce a tar.gz archive. PyInstaller must be installed in "
            "the Python environment used to run this script. If one script "
            "fails to build, the other script continues, but no archive is "
            "created and the command exits with status 1."
        ),
    )
    return parser


def detect_platform_key() -> str:
    """Determine the PLATFORM_SETTINGS key from the build environment."""
    system = platform.system()
    machine = platform.machine().lower()

    if system == "Windows" and machine in ("amd64", "x86_64"):
        return "windows-x64"
    if system == "Linux" and machine in ("amd64", "x86_64"):
        return "linux-x64"
    if system == "Linux" and machine in ("aarch64", "arm64"):
        return "linux-aarch64"

    raise RuntimeError(f"Unsupported build environment: system={system}, machine={machine}")


def clear_previous_cache(script_name: str) -> None:
    """Remove the previous build cache (build/ and *.spec)."""
    script_stem = Path(script_name).stem

    script_build_dir = BUILD_DIR / script_stem
    if script_build_dir.exists():
        shutil.rmtree(script_build_dir)

    spec_file = ROOT_DIR / f"{script_stem}.spec"
    if spec_file.exists():
        spec_file.unlink()


def run_pyinstaller(script_name: str, release_dir: str, icon: str | None) -> bool:
    """Run PyInstaller and return True on success or False on failure."""
    output_dir = ROOT_DIR / "release" / release_dir

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(ROOT_DIR / script_name),
        "--onefile",
        "--noconsole",
        "--distpath",
        str(output_dir),
        "--workpath",
        str(BUILD_DIR / Path(script_name).stem),
        "--specpath",
        str(ROOT_DIR),
        "--noconfirm",
        "--add-data",
        f"{ROOT_DIR / ICON_DATA_FILE}{';' if platform.system() == 'Windows' else ':'}resources",
    ]

    if icon:
        command += ["--icon", icon]

    print(f"=== Running PyInstaller: {script_name} -> {output_dir} ===")
    result = subprocess.run(command, cwd=ROOT_DIR)
    return result.returncode == 0


def copy_extra_data_files(script_name: str, release_dir: str) -> None:
    """Copy additional data files required at runtime to the release directory.

    Existing files are overwritten.
    """
    output_dir = ROOT_DIR / "release" / release_dir

    for filename in EXTRA_DATA_FILES.get(script_name, []):
        src = ROOT_DIR / filename
        dst = output_dir / filename

        if not src.exists():
            print(f"Warning: skipped copying {filename} because it was not found.", file=sys.stderr)
            continue

        shutil.copy2(src, dst)
        print(f"Copied {filename}: {dst}")


def create_release_archive(
    release_dir: str,
    exe_suffix: str,
    archive_name: str,
    archive_format: str,
) -> bool:
    """Archive the executables and additional data files, then save the SHA256 hash."""
    output_dir = ROOT_DIR / "release" / release_dir

    files_to_archive = []
    for script_name in SCRIPTS:
        exe_path = output_dir / f"{Path(script_name).stem}{exe_suffix}"
        if not exe_path.exists():
            print(f"Error: executable not found: {exe_path}", file=sys.stderr)
            return False
        files_to_archive.append(exe_path)

    extra_filenames = {filename for filenames in EXTRA_DATA_FILES.values() for filename in filenames}
    for filename in sorted(extra_filenames):
        data_path = output_dir / filename
        if data_path.exists():
            files_to_archive.append(data_path)

    archive_path = output_dir / f"{archive_name}.{archive_format}"
    hash_path = output_dir / f"{archive_path.name}.sha256"

    if archive_format == "zip":
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for file_path in files_to_archive:
                archive.write(file_path, arcname=file_path.name)
    elif archive_format == "tar.gz":
        with tarfile.open(archive_path, "w:gz") as archive:
            for file_path in files_to_archive:
                archive.add(file_path, arcname=file_path.name)
    else:
        print(f"Error: unsupported archive format: {archive_format}", file=sys.stderr)
        return False

    sha256 = hashlib.sha256()
    with open(archive_path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            sha256.update(chunk)

    hash_path.write_text(f"{sha256.hexdigest()}  {archive_path.name}\n", encoding="utf-8")

    print(f"Created {archive_path.name}: {archive_path}")
    print(f"Saved SHA256 hash: {hash_path}")
    return True


def main() -> int:
    create_argument_parser().parse_args()

    platform_key = detect_platform_key()
    settings = PLATFORM_SETTINGS[platform_key]
    release_dir = settings["release_dir"]
    icon = settings["icon"]

    print(f"Detected build environment: {platform_key}")

    failed_scripts = []

    # Continue building the remaining scripts if one script fails.
    for script_name in SCRIPTS:
        clear_previous_cache(script_name)

        success = run_pyinstaller(script_name, release_dir, icon)
        if not success:
            print(f"Error: PyInstaller failed for {script_name}.", file=sys.stderr)
            failed_scripts.append(script_name)
        else:
            copy_extra_data_files(script_name, release_dir)
            print(f"Build completed: {script_name}")

    if failed_scripts:
        print(f"Failed scripts: {', '.join(failed_scripts)}", file=sys.stderr)
        return 1

    archive_ok = create_release_archive(
        release_dir,
        settings["exe_suffix"],
        settings["archive_name"],
        settings["archive_format"],
    )
    if not archive_ok:
        print("Error: failed to create the distribution archive.", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
