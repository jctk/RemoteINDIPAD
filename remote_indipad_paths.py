import os
import sysconfig
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def get_user_config_dir() -> Path:
    if os.name == "nt":
        config_root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        config_root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return config_root / "RemoteINDIPAD"


def get_version() -> str:
    module_dir = Path(__file__).resolve().parent
    version_files = (
        module_dir / "VERSION",
        Path(sysconfig.get_path("data")) / "share" / "RemoteINDIPAD" / "VERSION",
    )
    for version_file in version_files:
        if version_file.is_file():
            app_version = version_file.read_text(encoding="utf-8").strip()
            if not app_version:
                raise ValueError(f"VERSION file is empty: {version_file}")
            return app_version

    searched_files = ", ".join(str(path) for path in version_files)
    raise FileNotFoundError(f"VERSION file not found. Searched: {searched_files}")


def get_installed_package_version() -> str | None:
    for distribution in ("RemoteINDIPAD-Sender", "RemoteINDIPAD-Receiver", "RemoteINDIPAD"):
        try:
            return version(distribution)
        except PackageNotFoundError:
            continue
    return None