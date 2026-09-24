# RemoteINDIPAD

[English README](README.md)

Windows に接続したゲームパッドの入力を、LAN 経由で Linux（StellarMate OS や Ubuntu など）側の KStars / Ekos / INDI に伝送し、フォーカサー・フィルターホイール・ローテーター・KStarsのSkyMapなどの観測機器を操作するためのツールです。

## 概要

- 送信側と受信側の二つのプログラムで構成されます。
- 送信側（Windows）: ゲームパッド入力を取得し、抽象化した操作に変換してネットワーク経由で送信します。
- 受信側（Linux）: 受信した抽象化操作を KStars / Ekos / INDI への D-BUS 制御コマンドに変換して観測機器を操作します。

> ⚠️このプログラムはほぼ GitHub Copilot で開発されています。
開発者が想像もしていない方法での実装・冗長なコード・不具合などが残されている可能性があります。

![Diagram](images/diagram.png)

## 確認済みのデバイス

### GAMEPAD

- Microsoft XBox ワイヤレスコントローラー
- ELECOM JC-U3712T
- 8BitDo Zero 2

### INDIデバイス

- Juwei 17
- GEMINI EAF
- ZWO CAA
- ToupTek AWF-L

## 操作可能な KStars/Ekos/INDI の機能

### KStars

- SkyMap: Zoom In、Zoom Out、視野回転

### INDI

- MOUNT: Slew、速度の増減、Slew停止
- FOCUSER: Focus In、Focus Out、ステップ数の増減
- ローテーター: 回転、回転停止
- フィルターホイール フィルタースロット変更

## 配布

- 配布形態は二種類です。
- 一つは実行ファイル形式、もう一つはスクリプト形式です。
- いずれか一方をご利用ください。

## 実行ファイル形式

- 実行ファイル形式は後述のスクリプト形式のファイルを pyinstaller で単一のファイルで実行可能にしたファイルです。
- この他に追加が必要なファイルはありません。（本当に追加ファイルが不要か未検証です。）
- Windows x64 用、Linux aarch64 用があります。
- Linux aarch64 用は StellarMate OS など Raspberry PI で利用します。

### ダウンロード

[Releases](https://github.com/jctk/RemoteINDIPAD/releases) からファイルを Windows 用の `RemoteINDIPAD-windows-x64.zip` と StellarMate OS 用の `RemoteINDIPAD-linux-aarch64.tar.gz` をダウンロードしてください。

### インストール

1. Windows で `RemoteINDIPAD-windows-x64.zip` を展開し `remote_indipad_sender.exe` と `gamepad_profiles.json` を任意の同じフォルダーに展開してください。
2. StellarMate OS で `RemoteINDIPAD-linux-aarch64.tar.gz` を展開し `remote_indipad_reciever` を任意のフォルダーに展開してください。

### 使い方

1. StellarMate OS で KStars を起動し Ekos Profile を Start する。Mount を使用する場合は Unpark しておく。
1. StellarMate OS で `remote_indipad_receiver` を起動する。
1. Mount / Focuser / Filter Wheel / Rotator のドロップダウンリストに Start 済みの Ekos Profile のデバイスが記入される。同一種類のデバイスが複数接続されている場合はドロップダウンリストから手動選択する。
1. Windows PC に GAMEPAD を接続する。
1. Windows で `remote_indipad_sender.exe` を起動する。
1. `[Controller]` で使用する GAMEPAD を選択し `[Edit Mapping]` ボタン INDIPAD Mapping Editor を開き DPAD/Buttons/Axes にKStars/INDI の操作をマッピングする。マッピングを終えたら `[Close]`で INDIPAD Mapping Editor を閉じる。
1. `[Host]`に StellarMate OS のIPアドレスを記入し、`[Connect]`ボタンで StellarMate OS の `remote_indipad_receiver` に接続する。接続すると両方のコンソールにその旨ログが表示される。
1. GAMEPADで操作する。

> ⚠️最初は控えめな操作で動作を確認してください。特にマウントやローテーターが異常な動作をする場合は機材が損傷する恐れがあります。いつでも機材を停止できるように心がけてください。

## スクリプト形式

スクリプト形式は RemoteINDIPAD の開発用の環境です。

### Requirements

- 送信側（Windows）
  - Windows 11
  - Python 3.10 以降
  - `pygame`（ゲームパッド入力取得）
  - `pyside6`（GUI）
- 受信側（Linux）
  - StellarMate OS 2.x または Ubuntu などの Linux 環境
  - Python 3 系
  - `pyside6`（GUI）
  - `dbus-next`（KStars / Ekos / INDI との D-BUS 連携）

### Installation

### 送信側（Windows）

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

### 受信側（Linux）

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

## 起動方法

- 各スクリプトを python で起動してください。
- 起動方法以外の使用方法は [使い方](#使い方) に記載の通りです。

### Windows の場合

```powershell
python remote_indipad_sender.py
```

### StellarMate OS の場合

```bash
python remote_indipad_receiver.py
```

## License

本プロジェクトに含まれる RemoteINDIPAD のソースコード、設定ファイル、ドキュメントなどの著作物（第三者ライブラリを除く）は、MIT License の条件に従って利用、改変、再配布できます。

本プロジェクトで使用している第三者ライブラリおよび配布物に含まれる関連コンポーネントは、それぞれのライセンス条件に従います。利用、改変、再配布の際は、各ライブラリのライセンスおよび著作権表示をご確認ください。

現在確認している主な依存ライブラリは次のとおりです。

- `pygame`: GNU LGPL 2.1
- `PySide6` / Qt for Python: LGPL 3.0、GPL、または商用ライセンス
- `dbus-next`: MIT License
- `PyInstaller`: GPL 2.0以降（PyInstallerで作成したアプリケーションの配布を認める特別例外付き）
- Python標準ライブラリ: Python Software Foundation License

確認したライセンス本文は [license](license/) フォルダーに保存しています。PySide6、Qt、pygameが内部で利用するコンポーネントなど、ここに掲載していない依存物についても、実際に使用するバージョンおよび配布形態に応じたライセンス条件を確認してください。

特にPySide6を使用した実行ファイルを配布する場合は、LGPLの条件に従い、Qt / PySide6のライセンス表示を保持し、利用者による対象ライブラリの置き換えを不当に妨げないようにしてください。PyInstallerで作成した実行ファイルについても、PyInstaller自身の例外だけでなく、同梱されるすべての依存ライブラリの条件が適用されます。
