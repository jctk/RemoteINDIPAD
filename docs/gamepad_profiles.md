# `gamepad_profiles.json` Specification

## 1. Purpose

`gamepad_profiles.json` is a sender-side definition file that defines how each gamepad's physical inputs (D-pad, buttons, and analog axes) map to RemoteINDIPAD abstract actions.

## 2. File Format

- The file must be encoded in UTF-8.
- The root value must be a JSON object.
- Comments in the `//`, `#`, and `/* ... */` formats are allowed. Comments are removed when the file is loaded.
- Apart from comments, the file must follow standard JSON syntax. Trailing commas are not allowed.
- Property names and action names are case-sensitive.

## 3. Top-Level Structure

| Property | Type | Description |
| --- | --- | --- |
| `default_device` | string | Profile name to use when no profile matches the device name. This normally refers to a key in `profiles`. |
| `profiles` | object | An object whose keys are profile names and whose values are profile definitions. |

`default_device` is optional. If it is omitted or the specified profile is unavailable, `profiles.default` is used if present.

## 4. Profile Definition

Each profile in `profiles` is an object with the following properties.

| Property | Type | Required | Description |
| --- | --- | --- | --- |
| `manufacturer` | string | No | Manufacturer name. For display and identification only; it is not used to select a profile. |
| `model` | string | No | Product or model name. For display and identification only; it is not used to select a profile. |
| `label` | string | No | Display name for the profile. |
| `description` | string | No | Description of the profile. |
| `action_mapping` | object | No | Mapping from physical inputs to actions. |

The profile key is the name matched against the device name reported by the gamepad. An exact match is tried first, followed by a case-insensitive exact match. `manufacturer`, `model`, and `label` are not used for matching.

## 5. Input Mapping

Keys in `action_mapping` are input names, and their values are action names. Use the empty string `""` to leave an input unassigned.

### D-pad

| Key | Input |
| --- | --- |
| `dpad_up` | D-pad up |
| `dpad_down` | D-pad down |
| `dpad_left` | D-pad left |
| `dpad_right` | D-pad right |

### Buttons

Keys from `button_1` through `button_16` can be specified. Each number is one greater than the corresponding button index in the gamepad API. Physical button labels and positions vary by device.

### Analog Axes

Keys from `axis_1` through `axis_6` can be specified. Each number is one greater than the corresponding axis index in the gamepad API. Assign actions for each axis state: `NEGATIVE`, `CENTER`, and `POSITIVE`.

| State | Condition |
| --- | --- |
| `NEGATIVE` | Input value is below the negative deadzone threshold. |
| `CENTER` | Input value is within the deadzone. |
| `POSITIVE` | Input value is above the positive deadzone threshold. |

Define an axis as an object containing the states, as shown below. Any omitted state is treated as unassigned.

```json
"axis_1": {
  "NEGATIVE": "MOUNT_STEP_DOWN",
  "CENTER": "",
  "POSITIVE": "MOUNT_STEP_UP"
}
```

The numeric deadzone setting is managed in the sender configuration, not in this file.

## 6. Action Names

The following action names can be used in mappings.

| Action | Operation |
| --- | --- |
| `MOUNT_NORTH` | Move the mount north |
| `MOUNT_SOUTH` | Move the mount south |
| `MOUNT_WEST` | Move the mount west |
| `MOUNT_EAST` | Move the mount east |
| `MOUNT_STEP_UP` | Increase mount movement speed |
| `MOUNT_STEP_DOWN` | Decrease mount movement speed |
| `MOUNT_STOP` | Stop the mount |
| `FOCUS_IN` | Move the focuser inward |
| `FOCUS_OUT` | Move the focuser outward |
| `FOCUS_STEP_UP` | Increase the focuser movement step |
| `FOCUS_STEP_DOWN` | Decrease the focuser movement step |
| `FOCUS_STOP` | Stop the focuser |
| `FILTERWHEEL_PREV` | Move the filter wheel to the previous slot |
| `FILTERWHEEL_NEXT` | Move the filter wheel to the next slot |
| `CAA_ROTATE_COUNTER_CLOCKWISE` | Rotate the CAA counterclockwise |
| `CAA_ROTATE_CLOCKWISE` | Rotate the CAA clockwise |
| `CAA_ROTATE_ABORT` | Stop CAA rotation |
| `SKYMAP_MOVE` | Move the SkyMap |
| `SKYMAP_ZOOM_IN` | Zoom in on the SkyMap |
| `SKYMAP_ZOOM_OUT` | Zoom out on the SkyMap |
| `SKYMAP_ROTATE_UP` | Rotate the SkyMap upward |
| `SKYMAP_ROTATE_DOWN` | Rotate the SkyMap downward |

Action names must match exactly. An empty string means "unassigned." Unknown action names are treated as unassigned when loaded.

`FOCUS_STEP_UP` and `FOCUS_STEP_DOWN` change the focuser step value locally in the sender; they do not send action messages over the network.

## 7. Profile Selection and Fallback

Profiles are selected in the following order:

1. The key in `profiles` that matches the connected gamepad's name.
2. The profile specified by `default_device`.
3. `profiles.default`.

If a matching profile does not contain a valid `action_mapping` object, the next candidate is tried. If no usable mapping is found, inputs remain unassigned.

## 8. Example

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

## 9. File Location and Updates

- When running from source or as a Windows executable, place the distributed `gamepad_profiles.json` in the same folder as the sender program.
- Installed packages use the file in the user's configuration folder. The packaged profiles are synchronized on the first launch or when the package version changes. User edits are preserved when restarting the same package version.
- If the file does not exist, cannot be loaded, or its root value is not a JSON object, it is treated as equivalent to an empty `default` profile.
