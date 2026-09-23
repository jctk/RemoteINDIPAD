"""remote_indipad_receiver.py / remote_indipad_sender.py を PyInstaller でビルドするスクリプト。

実行環境が Windows x64 の場合と Linux aarch64 の場合とで出力先を分けつつ、
どちらの環境でも両方のスクリプトを onefile / コンソール非表示でビルドする。
一方のビルドが失敗しても、もう一方のビルドは続行する。
"""

import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
BUILD_DIR = ROOT_DIR / "build"

# ビルド対象スクリプト一覧。
SCRIPTS = ["remote_indipad_receiver.py", "remote_indipad_sender.py"]

# 実行環境ごとの出力先ディレクトリ名とアイコンの対応。
PLATFORM_SETTINGS = {
    "windows-x64": {
        "release_dir": "windows-x64",
        # アイコンファイルが用意できたら .ico のパスを設定する。
        "icon": None,
    },
    "linux-aarch64": {
        "release_dir": "linux-aarch64",
        "icon": None,
    },
}


def detect_platform_key() -> str:
    """実行環境から PLATFORM_SETTINGS のキーを判定する。"""
    system = platform.system()
    machine = platform.machine().lower()

    if system == "Windows" and machine in ("amd64", "x86_64"):
        return "windows-x64"
    if system == "Linux" and machine in ("aarch64", "arm64"):
        return "linux-aarch64"

    raise RuntimeError(f"サポートされていない実行環境です: system={system}, machine={machine}")


def clear_previous_cache(script_name: str) -> None:
    """前回ビルドのキャッシュ（build/ と *.spec）を削除する。"""
    script_stem = Path(script_name).stem

    script_build_dir = BUILD_DIR / script_stem
    if script_build_dir.exists():
        shutil.rmtree(script_build_dir)

    spec_file = ROOT_DIR / f"{script_stem}.spec"
    if spec_file.exists():
        spec_file.unlink()


def run_pyinstaller(script_name: str, release_dir: str, icon: str | None) -> bool:
    """PyInstaller を実行する。成功時は True、失敗時は False を返す。"""
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
    ]

    if icon:
        command += ["--icon", icon]

    print(f"=== PyInstaller 実行: {script_name} -> {output_dir} ===")
    result = subprocess.run(command, cwd=ROOT_DIR)
    return result.returncode == 0


def main() -> int:
    platform_key = detect_platform_key()
    settings = PLATFORM_SETTINGS[platform_key]
    release_dir = settings["release_dir"]
    icon = settings["icon"]

    print(f"検出した実行環境: {platform_key}")

    failed_scripts = []

    # 一方のスクリプトが失敗しても、残りのスクリプトのビルドは続行する。
    for script_name in SCRIPTS:
        clear_previous_cache(script_name)

        success = run_pyinstaller(script_name, release_dir, icon)
        if not success:
            print(f"エラー: {script_name} の PyInstaller 実行に失敗しました。", file=sys.stderr)
            failed_scripts.append(script_name)
        else:
            print(f"ビルド完了: {script_name}")

    if failed_scripts:
        print(f"失敗したスクリプト: {', '.join(failed_scripts)}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
