import os
import sys
from pathlib import Path

from setuptools import setup


ROOT_DIR = Path(__file__).resolve().parent
VERSION = (ROOT_DIR / "VERSION").read_text(encoding="utf-8").strip()

TARGETS = {
    "sender": {
        "name": "RemoteINDIPAD-Sender",
        "modules": [
            "remote_indipad_paths",
            "remote_indipad_protocol",
            "remote_indipad_sender",
        ],
        "dependencies": ["PySide6", "pygame; sys_platform == 'win32'"],
        "script": "remote_indipad_sender=remote_indipad_sender:run_gui",
        "data_files": [
            ("share/RemoteINDIPAD", ["gamepad_profiles.json"]),
            ("share/RemoteINDIPAD/resources", ["resources/icon.png"]),
        ],
    },
    "receiver": {
        "name": "RemoteINDIPAD-Receiver",
        "modules": [
            "remote_indipad_paths",
            "remote_indipad_protocol",
            "remote_indipad_receiver",
        ],
        "dependencies": ["PySide6"],
        "script": "remote_indipad_receiver=remote_indipad_receiver:run_gui",
        "data_files": [
            ("share/RemoteINDIPAD/resources", ["resources/icon.png"]),
        ],
    },
}

target_name = os.environ.get("REMOTEINDIPAD_WHEEL_TARGET")
if target_name is None:
    target_name = {"win32": "sender", "linux": "receiver"}.get(sys.platform)

if target_name not in TARGETS:
    raise RuntimeError(
        "Could not select a wheel target for this platform. Build on Windows "
        "to create the Sender wheel or Linux to create the Receiver wheel, or "
        "set REMOTEINDIPAD_WHEEL_TARGET to 'sender' or 'receiver'."
    )

target = TARGETS[target_name]
setup(
    name=target["name"],
    version=VERSION,
    description="Gamepad-based remote control for KStars, Ekos, and INDI",
    long_description=(ROOT_DIR / "README.md").read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
    python_requires=">=3.10",
    project_urls={
        "Homepage": "https://github.com/jctk/RemoteINDIPAD",
        "Issues": "https://github.com/jctk/RemoteINDIPAD/issues",
    },
    install_requires=target["dependencies"],
    entry_points={"console_scripts": [target["script"]]},
    py_modules=target["modules"],
    data_files=[
        (destination, [str(ROOT_DIR / filename) for filename in filenames])
        for destination, filenames in target["data_files"]
    ],
    options={"build": {"build_base": str(ROOT_DIR / "build" / f"wheel-{target_name}")}},
)
