"""remote_indipad_receiver.py / remote_indipad_sender.py を PyInstaller でビルドするスクリプト。

実行環境が Windows x64 の場合と Linux aarch64 の場合とで出力先を分けつつ、
どちらの環境でも両方のスクリプトを onefile / コンソール非表示でビルドする。
一方のビルドが失敗しても、もう一方のビルドは続行する。
"""

import hashlib
import platform
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
BUILD_DIR = ROOT_DIR / "build"

# ビルド対象スクリプト一覧。
SCRIPTS = ["remote_indipad_receiver.py", "remote_indipad_sender.py"]

# 実行ファイルと同じ場所に配置する追加データファイル（スクリプトごと）。
EXTRA_DATA_FILES = {
    "remote_indipad_sender.py": ["gamepad_profiles.json"],
}

# 実行環境ごとの出力先ディレクトリ名・アイコン・配布用アーカイブの設定。
PLATFORM_SETTINGS = {
    "windows-x64": {
        "release_dir": "windows-x64",
        # アイコンファイルが用意できたら .ico のパスを設定する。
        "icon": None,
        "exe_suffix": ".exe",
        "archive_name": "RemoteINDIPAD-windows-x64",
        "archive_format": "zip",
    },
    "linux-aarch64": {
        "release_dir": "linux-aarch64",
        "icon": None,
        "exe_suffix": "",
        "archive_name": "RemoteINDIPAD-linux-aarch64",
        "archive_format": "tar.gz",
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


def copy_extra_data_files(script_name: str, release_dir: str) -> None:
    """実行ファイルが実行時に読み込む追加データファイルを release へコピーする。

    既存ファイルは上書きする。
    """
    output_dir = ROOT_DIR / "release" / release_dir

    for filename in EXTRA_DATA_FILES.get(script_name, []):
        src = ROOT_DIR / filename
        dst = output_dir / filename

        if not src.exists():
            print(f"警告: {filename} が見つからないためコピーをスキップしました。", file=sys.stderr)
            continue

        shutil.copy2(src, dst)
        print(f"{filename} をコピーしました: {dst}")


def create_release_archive(
    release_dir: str,
    exe_suffix: str,
    archive_name: str,
    archive_format: str,
) -> bool:
    """実行ファイルと追加データファイルをアーカイブにまとめ、SHA256 を保存する。"""
    output_dir = ROOT_DIR / "release" / release_dir

    files_to_archive = []
    for script_name in SCRIPTS:
        exe_path = output_dir / f"{Path(script_name).stem}{exe_suffix}"
        if not exe_path.exists():
            print(f"エラー: 実行ファイルが見つかりません: {exe_path}", file=sys.stderr)
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
        print(f"エラー: 未対応のアーカイブ形式です: {archive_format}", file=sys.stderr)
        return False

    sha256 = hashlib.sha256()
    with open(archive_path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            sha256.update(chunk)

    hash_path.write_text(f"{sha256.hexdigest()}  {archive_path.name}\n", encoding="utf-8")

    print(f"{archive_path.name} を作成しました: {archive_path}")
    print(f"SHA256 を保存しました: {hash_path}")
    return True


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
            copy_extra_data_files(script_name, release_dir)
            print(f"ビルド完了: {script_name}")

    if failed_scripts:
        print(f"失敗したスクリプト: {', '.join(failed_scripts)}", file=sys.stderr)
        return 1

    archive_ok = create_release_archive(
        release_dir,
        settings["exe_suffix"],
        settings["archive_name"],
        settings["archive_format"],
    )
    if not archive_ok:
        print("エラー: 配布用アーカイブの作成に失敗しました。", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
