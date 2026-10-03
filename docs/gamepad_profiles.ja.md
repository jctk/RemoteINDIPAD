# `gamepad_profiles.json` 仕様

## 1. 目的

`gamepad_profiles.json` は、ゲームパッドごとに入力（十字キー、ボタン、アナログ軸）と RemoteINDIPAD の抽象化操作（Action）の対応を定義する、送信側の定義ファイルである。

## 2. ファイル形式

- UTF-8 で記述する。
- JSON オブジェクトをルートとする。
- `//`、`#`、`/* ... */` 形式のコメントを記述できる。コメントは読み込み時に取り除かれる。
- コメント以外は標準 JSON の構文に従う。末尾カンマは使用できない。
- プロパティ名と Action 名は大文字・小文字を区別する。

## 3. トップレベル構造

| プロパティ | 型 | 説明 |
| --- | --- | --- |
| `default_device` | 文字列 | デバイス名に一致するプロファイルがない場合に使用するプロファイル名。通常は `profiles` 内のキーを指定する。 |
| `profiles` | オブジェクト | プロファイル名をキー、そのプロファイル定義を値とするオブジェクト。 |

`default_device` は省略可能である。省略時、または指定されたプロファイルが使用できない場合は、`profiles.default` があればそれを使用する。

## 4. プロファイル定義

`profiles` 内の各プロファイルは、次のプロパティを持つオブジェクトである。

| プロパティ | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `manufacturer` | 文字列 | いいえ | メーカー名。表示・識別用の情報であり、プロファイル選択には使用しない。 |
| `model` | 文字列 | いいえ | 製品名またはモデル名。表示・識別用の情報であり、プロファイル選択には使用しない。 |
| `label` | 文字列 | いいえ | プロファイルの表示名。 |
| `description` | 文字列 | いいえ | プロファイルの説明。 |
| `action_mapping` | オブジェクト | いいえ | 物理入力と Action の対応。 |

プロファイルのキーは、ゲームパッドから取得したデバイス名と照合する名前である。デバイス名との照合は完全一致を優先し、その後、大文字・小文字を無視した完全一致を試みる。`manufacturer`、`model`、`label` は照合キーではない。

## 5. 入力マッピング

`action_mapping` のキーは入力名、値は Action 名である。未割り当てにする場合は空文字列 `""` を指定する。

### 十字キー

| キー | 入力 |
| --- | --- |
| `dpad_up` | 十字キー上 |
| `dpad_down` | 十字キー下 |
| `dpad_left` | 十字キー左 |
| `dpad_right` | 十字キー右 |

### ボタン

`button_1` から `button_16` を指定できる。番号はゲームパッド API のボタン番号に 1 を加えた値である（物理ボタンのラベルや位置はデバイスによって異なる）。

### アナログ軸

`axis_1` から `axis_6` を指定できる。番号はゲームパッド API の軸番号に 1 を加えた値である。各軸の値は `NEGATIVE`、`CENTER`、`POSITIVE` の状態ごとに割り当てる。

| 状態 | 判定 |
| --- | --- |
| `NEGATIVE` | 入力値がデッドゾーンより小さい側 |
| `CENTER` | 入力値がデッドゾーン内 |
| `POSITIVE` | 入力値がデッドゾーンより大きい側 |

軸の定義は、次のように各状態を持つオブジェクトで記述する。状態を省略した場合は未割り当てとして扱う。

```json
"axis_1": {
  "NEGATIVE": "MOUNT_STEP_DOWN",
  "CENTER": "",
  "POSITIVE": "MOUNT_STEP_UP"
}
```

デッドゾーンの数値設定はこのファイルではなく、送信側の設定で管理する。

## 6. Action 名

マッピングで使用できる Action 名は次のとおり。

| Action | 操作 |
| --- | --- |
| `MOUNT_NORTH` | マウント北方向 |
| `MOUNT_SOUTH` | マウント南方向 |
| `MOUNT_WEST` | マウント西方向 |
| `MOUNT_EAST` | マウント東方向 |
| `MOUNT_STEP_UP` | マウント操作速度を上げる |
| `MOUNT_STEP_DOWN` | マウント操作速度を下げる |
| `MOUNT_STOP` | マウント停止 |
| `FOCUS_IN` | フォーカサーを内側へ動かす |
| `FOCUS_OUT` | フォーカサーを外側へ動かす |
| `FOCUS_STEP_UP` | フォーカサー移動ステップを上げる |
| `FOCUS_STEP_DOWN` | フォーカサー移動ステップを下げる |
| `FOCUS_STOP` | フォーカサー停止 |
| `FILTERWHEEL_PREV` | フィルターホイールの前のスロットへ移動 |
| `FILTERWHEEL_NEXT` | フィルターホイールの次のスロットへ移動 |
| `CAA_ROTATE_COUNTER_CLOCKWISE` | CAA を反時計回りに回転 |
| `CAA_ROTATE_CLOCKWISE` | CAA を時計回りに回転 |
| `CAA_ROTATE_ABORT` | CAA の回転を停止 |
| `SKYMAP_MOVE` | SkyMap 移動 |
| `SKYMAP_ZOOM_IN` | SkyMap を拡大 |
| `SKYMAP_ZOOM_OUT` | SkyMap を縮小 |
| `SKYMAP_ROTATE_UP` | SkyMap を上方向に回転 |
| `SKYMAP_ROTATE_DOWN` | SkyMap を下方向に回転 |

Action 名は完全一致が必要である。空文字列は「割り当てなし」を表す。不明な Action 名は読み込み時に割り当てなしとして扱われる。

`FOCUS_STEP_UP` と `FOCUS_STEP_DOWN` は送信側のフォーカサーステップ値を変更するローカル操作であり、ネットワークへ Action メッセージを送らない。

## 7. プロファイル選択とフォールバック

プロファイルは次の順に選択される。

1. 接続中のゲームパッド名と一致する `profiles` のキー。
2. `default_device` で指定されたプロファイル。
3. `profiles.default`。

プロファイル名の照合に一致しても、その定義に有効な `action_mapping` オブジェクトがない場合は次の候補へ進む。最終的に使用できるマッピングがない場合、入力は割り当てなしとなる。

## 8. 記述例

```json
{
  "default_device": "default",
  "profiles": {
    "Example Gamepad": {
      "manufacturer": "Example",
      "model": "Controller 1",
      "label": "Example Controller",
      "description": "Example gamepad profile.",
      "action_mapping": {
        "dpad_up": "MOUNT_NORTH",
        "dpad_down": "MOUNT_SOUTH",
        "dpad_left": "MOUNT_WEST",
        "dpad_right": "MOUNT_EAST",
        "button_1": "FOCUS_IN",
        "button_2": "FOCUS_OUT",
        "button_3": "",
        "axis_1": {
          "NEGATIVE": "MOUNT_STEP_DOWN",
          "CENTER": "",
          "POSITIVE": "MOUNT_STEP_UP"
        }
      }
    },
    "default": {
      "action_mapping": {
        "dpad_up": "MOUNT_NORTH",
        "dpad_down": "MOUNT_SOUTH",
        "dpad_left": "MOUNT_WEST",
        "dpad_right": "MOUNT_EAST"
      }
    }
  }
}
```

## 9. 配置ファイルの配置と更新

- ソース実行時および Windows 実行ファイルでは、配布された `gamepad_profiles.json` を送信側プログラムと同じフォルダーに配置する。
- インストール済みパッケージでは、ユーザー設定フォルダーのファイルが使用される。配布プロファイルはパッケージのバージョンに応じて初回起動時またはバージョン更新時に同期される。同じバージョンで再起動した場合、ユーザーが行った編集は維持される。
- ファイルが存在しない、読み込みに失敗する、またはルートが JSON オブジェクトでない場合、空の `default` プロファイル相当として扱われる。
