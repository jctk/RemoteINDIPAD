import os
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def get_user_config_dir() -> Path:
    if os.name == "nt":
        config_root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        config_root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return config_root / "RemoteINDIPAD"


def get_installed_package_version() -> str | None:
    for distribution in ("RemoteINDIPAD-Sender", "RemoteINDIPAD-Receiver", "RemoteINDIPAD"):
        try:
            return version(distribution)
        except PackageNotFoundError:
            continue
    return None