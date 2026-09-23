# RemoteINDIPAD

Windows に接続したゲームパッドの入力を、LAN 経由で Linux（StellarMate OS や Ubuntu など）側の KStars / Ekos / INDI に伝送し、フォーカサー・フィルターホイール・ローテーター・KStarsのSkyMapなどの観測機器を操作するためのツールです。

## 概要

- 送信側と受信側の二つのプログラムで構成されます。
- 送信側（Windows）: ゲームパッド入力を取得し、抽象化した操作に変換してネットワーク経由で送信します。
- 受信側（Linux）: 受信した抽象化操作を KStars / Ekos / INDI への D-BUS 制御コマンドに変換して観測機器を操作します。

> ⚠️このプログラムはほぼ GitHub Copilot で開発されています。
想像もしていない方法での実装・冗長なコード・不具合などが残されている可能性があります。

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

Current Version: 0.9.0

以下のリンクの Sender で Windows 用と Receiver から StellarMate OS 用をダウンロードし、それぞれの OS の任意のフォルダーへ保存してください。

#### Sender

| File | Architecture | Descritption | Release Date | SHA256 |
| - | - | - | - | - |
| [remote_indipad_sender.exe](https://github.com/) | Windows x64 | | 2026-9-xx | |

#### Receiver

| File | Architecture | Descritption | Release Date | SHA256 |
| - | - | - | - | - |
| [remote_indipad_receiver](https://github.com/) | StellarMate OS aarch64 | | 2026-9-xx | |
| [remote_indipad_reciever.exe](https://github.com/) | Windows x64 | 試験用。応答はしますがKStars/Ekos/INDIの操作はできません。 | 2026-9-xx | |

### 使い方

1. StellarMate OS で KStars を起動し Ekos Profile を Start する。MountはUnparkしておく。
1. StellarMate OS で `remote_indipad_receiver` を起動する。
1. Windows PC に GAMEPAD を接続する。
1. Windows で `remote_indipad_sender.exe` を起動する。
1. `[Controller]` で接続した GAMEPAD を選択し `[Edit Mapping]` ボタン INDIPAD Mapping Editor を開き DPAD/Buttons/Axes にKStars/INDI の操作をマッピングする。マッピングを終えたら `[Close]`で INDIPAD Mapping Editor を閉じる。
1. `[Host]`にStellarMate OSのIPアドレスを記入し、`[Connect]`ボタンで StellarMate OS の `remote_indipad_receiver` に接続する。接続すると両方のコンソールにその旨ログが表示される。
1. GAMEPADで操作する。

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

## Usage

### 送信側（Windows）を起動する

```powershell
python remote_indipad_sender.py
```

- GUI 上でコントローラー・接続先ホスト / ポートを選択し、"Connect" で接続を開始します。
- "Edit Mapping" からゲームパッドの DPAD / ボタン / スティックと抽象化操作の対応を編集できます。

### 受信側（Linux）を起動する

```bash
python remote_indipad_receiver.py
```

- GUI 上で "Scan INDI" を押すと、利用可能なマウント / フォーカサー / フィルターホイール / ローテーターを検出します。
- リスニング IP / ポートを設定し、送信側からの接続を待ち受けます。

## Configuration

- `remote_indipad_sender.json`: 送信側の接続設定・マッピング・ウィンドウ位置などを保存します。
- `remote_indipad_receiver.json`: 受信側の接続設定・デバイス選択・ウィンドウ位置などを保存します。
- `gamepad_profiles.json`: ゲームパッドの機種ごとの既定マッピングを定義します。

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
