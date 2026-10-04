# `remote_indipad_sender.json` / `remote_indipad_receiver.json` Specification

## 1. Overview

These two files store values selected or changed in the RemoteINDIPAD GUIs so they can be restored on the next launch.

- `remote_indipad_sender.json` stores settings for the Windows Sender.
- `remote_indipad_receiver.json` stores settings for the Receiver, which runs on Linux and other supported platforms.

The gamepad-specific default mapping definitions used by the Sender are described in [`gamepad_profiles.md`](gamepad_profiles.md). The `action_mapping` in `remote_indipad_sender.json` stores mappings edited in the Sender GUI.

## 2. Common Behavior

- Each file is stored as a UTF-8 JSON object.
- When saved, the file is written as formatted JSON.
- If a file does not exist, cannot be loaded, or its root value is not a JSON object, the application starts with its defaults.
- Missing properties are filled with defaults. Numeric values with defined ranges are normalized when loaded.

## 3. `remote_indipad_sender.json`

### 3.1 Properties

| Property | Type | Default | Description |
| --- | --- | --- | --- |
| `controller` | string | `""` | Name of the selected gamepad. |
| `controller_guid` | string | `""` | GUID of the selected gamepad, used to distinguish devices with the same name. |
| `host` | string | `"localhost"` | Host name or IP address of the Receiver. |
| `port` | integer | `50007` | Receiver port to connect to. |
| `heartbeat` | boolean | `false` | Whether to display heartbeat logs. |
| `requests` | boolean | `false` | Whether to display logs of outgoing JSON packets. |
| `word_wrap` | boolean | `false` | Whether to wrap console lines. |
| `focus_step` | integer | `100` | Focuser movement step. Values are normalized to `1`–`5000` when loaded. |
| `deadzone` | number | `0.6` | Deadzone used to determine the center state of analog axes. Values are normalized to `0.0`–`1.0` when loaded. |
| `joystick_wait_max` | number | `2.0` | Maximum seconds to wait for the gamepad count to stabilize during startup. Negative or non-numeric values revert to the default. |
| `action_mapping` | object | `{"controllers":[]}` | Storage for mappings edited in the GUI. See below for its structure. |
| `window_geometry` | object | `{}` | Window position and size, stored as integer `x`, `y`, `width`, and `height` properties. |

`heartbeat` and `requests` control log output; they do not enable or disable network communication.

### 3.2 `action_mapping`

`action_mapping` stores GUI-edited mappings for selected controllers. The profile definitions themselves are in `gamepad_profiles.json`.

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

- `controllers` is an array of per-controller mapping entries.
- `name` and `guid` identify a controller, and `mapping` stores the assignments from D-pad, buttons, and axes to actions.
- If an entry's name and GUID match the selected device, its mapping is used. If there is no matching GUI-edited mapping, the applicable profile or default profile from [`gamepad_profiles.json`](gamepad_profiles.md) is used.
- Input keys and action names follow the [gamepad profile definition specification](gamepad_profiles.md).

### 3.3 Default Example

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

### 4.1 Properties

| Property | Type | Default | Description |
| --- | --- | --- | --- |
| `mount` | string | `""` | Name of the MOUNT INDI driver to use. |
| `focuser` | string | `""` | Name of the focuser INDI driver to use. |
| `filter` | string | `""` | Name of the filter wheel INDI driver to use. |
| `filter_slots` | integer | `0` | Number of filter wheel slots. Negative or non-integer values are normalized to `0`. |
| `rotator` | string | `""` | Name of the rotator INDI driver to use. |
| `host` | string | `"0.0.0.0"` | Listening IP address. Retained for compatibility with older files and synchronized with `listen_target.address` in the newer format. |
| `listen_target` | object | All IPv4 interfaces | Listening address selection and details. See below for its structure. |
| `port` | integer | `50007` | Listening port. |
| `heartbeat` | boolean | `false` | Whether to display heartbeat logs. |
| `requests` | boolean | `false` | Whether to display received JSON packet logs. |
| `actions` | boolean | `false` | Whether to display action execution logs. |
| `dbus` | boolean | `false` | Whether to display D-Bus call and result logs. |
| `word_wrap` | boolean | `false` | Whether to wrap console lines. |
| `start_on_launch` | boolean | `true` | When `true`, the Receiver performs the Start operation on launch and begins listening. When `false`, the Receiver does not listen on launch and must be started manually. `host` / `listen_target` and `port` are used when listening starts. |
| `window_geometry` | object | `{}` | Window position and size, stored as integer `x`, `y`, `width`, and `height` properties. |

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

| Property | Type | Description |
| --- | --- | --- |
| `mode` | string | Listening selection type: `all` (all interfaces), `localhost` (loopback), `address` (a specific address), or `unavailable` (a currently unavailable choice). |
| `family` | string | IP version: `ipv4` or `ipv6`. |
| `address` | string | IP address to listen on. |
| `interface` | string | Network interface name or IPv6 scope, when needed. |
| `scope_id` | integer | IPv6 interface scope ID. Usually `0`. |

If an older file does not contain `listen_target`, the listening target is reconstructed from `host`.

### 4.3 Default Example

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

## 5. File Locations

| Runtime | Sender | Receiver |
| --- | --- | --- |
| Source or executable | In the same folder as the executable or script | In the same folder as the executable or script |
| Installed package | `%APPDATA%\RemoteINDIPAD\` | `$XDG_CONFIG_HOME/RemoteINDIPAD/`. If `XDG_CONFIG_HOME` is unset, `~/.config/RemoteINDIPAD/`. |

On Windows, if `%APPDATA%` is unset, `%USERPROFILE%\AppData\Roaming\RemoteINDIPAD\` is used.

## 6. Saving and Applying Settings

Values selected or changed in the GUI are saved to the settings file and loaded on the next launch. `window_geometry` stores the window position and size for restoration. `gamepad_profiles.json` is a separate definition file distributed and synchronized with the package.
