import os
import sys
from pathlib import Path

from setuptools import build_meta


ROOT_DIR = Path(__file__).resolve().parent
TARGETS = ("sender", "receiver")


def get_requires_for_build_wheel(config_settings=None):
    return build_meta.get_requires_for_build_wheel(config_settings)


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    previous_target = os.environ.get("REMOTEINDIPAD_WHEEL_TARGET")
    wheel_names = {}
    try:
        for target in TARGETS:
            os.environ["REMOTEINDIPAD_WHEEL_TARGET"] = target
            wheel_names[target] = build_meta.build_wheel(
                wheel_directory,
                config_settings=config_settings,
            )
    finally:
        if previous_target is None:
            os.environ.pop("REMOTEINDIPAD_WHEEL_TARGET", None)
        else:
            os.environ["REMOTEINDIPAD_WHEEL_TARGET"] = previous_target

    default_target = "sender" if sys.platform == "win32" else "receiver"
    return wheel_names[default_target]
