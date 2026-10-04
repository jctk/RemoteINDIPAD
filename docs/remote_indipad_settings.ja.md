# `remote_indipad_sender.json` / `remote_indipad_receiver.json` 仕様

## 1. 概要

この2つのファイルは、RemoteINDIPAD の GUI で選択・変更した値を次回起動時に復元するための設定ファイルである。

- `remote_indipad_sender.json`: Windows の Sender の設定を保存する。
- `remote_indipad_receiver.json`: Linux などで動作する Receiver の設定を保存する。

Sender のゲームパッド別デフォルトマッピング定義は [`gamepad_profiles.ja.md`](gamepad_profiles.ja.md) に記載する。`remote_indipad_sender.json` の `action_mapping` は、GUI で編集したマッピングを Sender 側で保持するための設定である。

## 2. 共通事項

- UTF-8 の JSON オブジェクトとして保存される。
- 保存時は整形された JSON として書き込まれる。
- ファイルが存在しない、読み込めない、またはルートが JSON オブジェクトでない場合は、各アプリケーションの既定値で起動する。
- 未指定項目には既定値が補われる。範囲のある数値は読み込み時に補正される。

## 3. `remote_indipad_sender.json`

### 3.1 項目

| プロパティ | 型 | 既定値 | 説明 |
| --- | --- | --- | --- |
| `controller` | 文字列 | `""` | 選択中のゲームパッド名。 |
| `controller_guid` | 文字列 | `""` | 選択中のゲームパッドの GUID。名前が同じ複数のデバイスを識別するために使われる。 |
| `host` | 文字列 | `"localhost"` | Receiver の接続先ホスト名または IP アドレス。 |
| `port` | 整数 | `50007` | Receiver の接続先ポート。 |
| `heartbeat` | 真偽値 | `false` | Heartbeat のログ表示設定。 |
| `requests` | 真偽値 | `false` | 送信 JSON パケットのログ表示設定。 |
| `word_wrap` | 真偽値 | `false` | コンソールの行折り返し設定。 |
| `focus_step` | 整数 | `100` | FOCUSER の移動ステップ。読み込み時に `1`～`5000` に補正される。 |
| `deadzone` | 数値 | `0.6` | アナログ軸の中央判定に使うデッドゾーン。読み込み時に `0.0`～`1.0` に補正される。 |
| `joystick_wait_max` | 数値 | `2.0` | 起動時にゲームパッド検出数が安定するまで待つ最大秒数。負数または数値に変換できない値は既定値に戻る。 |
| `action_mapping` | オブジェクト | `{"controllers":[]}` | GUI で編集したマッピングの保存領域。構造の詳細は後述。 |
| `window_geometry` | オブジェクト | `{}` | ウィンドウ位置・サイズ。`x`、`y`、`width`、`height` を整数で保持する。 |

`heartbeat` と `requests` はログ出力の設定であり、ネットワーク通信自体の有効・無効を表すものではない。

### 3.2 `action_mapping`

`action_mapping` は、選択したコントローラーに対する GUI 編集済みマッピングを保存する。プロファイルの定義そのものは `gamepad_profiles.json` に置く。

```json
"action_mapping": {
  "controllers": [
    {
      "name": "Example Gamepad",
      "guid": "device-guid",
      "mapping": {
        "dpad_up": "MOUNT_NORTH",
        "button_1": "FOCUS_IN",
        "axis_1": {
          "NEGATIVE": "MOUNT_STEP_DOWN",
          "CENTER": "",
          "POSITIVE": "MOUNT_STEP_UP"
        }
      }
    }
  ]
}
```

- `controllers` はコントローラーごとのマッピング項目を持つ配列である。
- `name` と `guid` でコントローラーを識別し、`mapping` に D-pad、ボタン、軸と Action の対応を保存する。
- 選択中デバイスの名前と GUID が保存内容に一致する場合、このマッピングが使用される。一致する編集済みマッピングがない場合は、[`gamepad_profiles.json`](gamepad_profiles.ja.md) の該当プロファイルまたは既定プロファイルが使われる。
- 入力キーおよび Action 名は [ゲームパッド定義ファイルの仕様](gamepad_profiles.ja.md) に従う。

### 3.3 既定値の例

```json
{
  "controller": "",
  "controller_guid": "",
  "host": "localhost",
  "port": 50007,
  "heartbeat": false,
  "requests": false,
  "word_wrap": false,
  "focus_step": 100,
  "deadzone": 0.6,
  "joystick_wait_max": 2.0,
  "action_mapping": {
    "controllers": []
  },
  "window_geometry": {}
}
```

## 4. `remote_indipad_receiver.json`

### 4.1 項目

| プロパティ | 型 | 既定値 | 説明 |
| --- | --- | --- | --- |
| `mount` | 文字列 | `""` | 使用する MOUNT の INDI ドライバー名。 |
| `focuser` | 文字列 | `""` | 使用する Focuser の INDI ドライバー名。 |
| `filter` | 文字列 | `""` | 使用する Filter Wheel の INDI ドライバー名。 |
| `filter_slots` | 整数 | `0` | Filter Wheel のスロット数。負数または整数に変換できない値は `0` になる。 |
| `rotator` | 文字列 | `""` | 使用する Rotator の INDI ドライバー名。 |
| `host` | 文字列 | `"0.0.0.0"` | 待受 IP アドレス。旧形式との互換性のため保持される。新しい形式では `listen_target.address` と連動する。 |
| `listen_target` | オブジェクト | IPv4 全インターフェース | 待受アドレスの種類および詳細。構造は後述。 |
| `port` | 整数 | `50007` | 待受ポート。 |
| `heartbeat` | 真偽値 | `false` | Heartbeat のログ表示設定。 |
| `requests` | 真偽値 | `false` | 受信 JSON パケットのログ表示設定。 |
| `actions` | 真偽値 | `false` | Action 実行ログの表示設定。 |
| `dbus` | 真偽値 | `false` | D-Bus 呼び出し・結果ログの表示設定。 |
| `word_wrap` | 真偽値 | `false` | コンソールの行折り返し設定。 |
| `start_on_launch` | 真偽値 | `true` | `true` の場合は、アプリケーション起動時に Start 操作を行い待受を開始する。`false` の場合は起動時に待受を開始せず、手動で Start する。`host` / `listen_target` と `port` は待受の開始に使われる。 |
| `window_geometry` | オブジェクト | `{}` | ウィンドウ位置・サイズ。`x`、`y`、`width`、`height` を整数で保持する。 |

### 4.2 `listen_target`

```json
"listen_target": {
  "mode": "all",
  "family": "ipv4",
  "address": "0.0.0.0",
  "interface": "",
  "scope_id": 0
}
```

| プロパティ | 型 | 説明 |
| --- | --- | --- |
| `mode` | 文字列 | 待受の選択種別。`all`（全インターフェース）、`localhost`（ループバック）、`address`（特定アドレス）、`unavailable`（現在使用できない選択肢）。 |
| `family` | 文字列 | IP バージョン。`ipv4` または `ipv6`。 |
| `address` | 文字列 | 待受に使用する IP アドレス。 |
| `interface` | 文字列 | 必要に応じて使用するネットワークインターフェース名または IPv6 スコープ。 |
| `scope_id` | 整数 | IPv6 インターフェースのスコープ ID。通常は `0`。 |

旧バージョンのファイルなどで `listen_target` がない場合は、`host` の値から待受先が復元される。

### 4.3 既定値の例

```json
{
  "mount": "",
  "focuser": "",
  "filter": "",
  "filter_slots": 0,
  "rotator": "",
  "host": "0.0.0.0",
  "listen_target": {
    "mode": "all",
    "family": "ipv4",
    "address": "0.0.0.0",
    "interface": "",
    "scope_id": 0
  },
  "port": 50007,
  "heartbeat": false,
  "requests": false,
  "actions": false,
  "dbus": false,
  "word_wrap": false,
  "start_on_launch": true,
  "window_geometry": {}
}
```

## 5. 保存先

| 実行形態 | Sender | Receiver |
| --- | --- | --- |
| ソースまたは実行ファイル | 実行ファイル（またはスクリプト）と同じフォルダー | 実行ファイル（またはスクリプト）と同じフォルダー |
| インストール済みパッケージ | `%APPDATA%\RemoteINDIPAD\` | `$XDG_CONFIG_HOME/RemoteINDIPAD/`。`XDG_CONFIG_HOME` が未設定の場合は `~/.config/RemoteINDIPAD/`。 |

Windows で `%APPDATA%` が未設定の場合は、`%USERPROFILE%\AppData\Roaming\RemoteINDIPAD\` が使われる。

## 6. 保存と反映

GUI で選択・変更した設定は設定ファイルに保存され、次回起動時に読み込まれる。`window_geometry` は画面上の位置・サイズを復元するための情報である。`gamepad_profiles.json` は別の定義ファイルであり、パッケージからの配布・同期の対象である。
