# INDIPAD JSON Protocol

## Overview

The sender and receiver communicate over a TCP connection. The sender writes UTF-8 JSON messages, one message per line, with a newline (`\n`) after each JSON object. A receiver may receive part of a line or several lines in one TCP read; TCP packet boundaries do not delimit messages.

The default receiver port is `50007`. The receiver does not send protocol responses or acknowledgements.

The sender transmits `heartbeat` and `action` messages. Axis input changes are represented as `action` messages with `source: "axis"`.

## Common conventions

- `ts`: Unix timestamp in seconds, represented as a JSON number.
- `device`: sender device identifier. The built-in sender uses `"gamepad"`.
- JSON object property names are case-sensitive.
- Each complete JSON object must end with a newline. Messages are UTF-8 encoded.
- The JSON Schema for one message is [protocol.schema.json](protocol.schema.json) (Draft 2020-12). It describes the message object, not the TCP newline framing.

## Heartbeat

The sender sends a heartbeat approximately once per second while connected.

```json
{"ts":1780000000.25,"type":"heartbeat","device":"gamepad","status":"alive"}
```

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `ts` | number | Yes | Unix timestamp in seconds |
| `type` | string | Yes | The literal `"heartbeat"` |
| `device` | string | Yes | Sender device identifier |
| `status` | string | Yes | The literal `"alive"` |

The receiver uses incoming messages to track connection liveness. If no message arrives for the configured heartbeat timeout (5 seconds by default), or the connection closes, it logs heartbeat loss and triggers emergency stop handling for active mount or rotator movement.

## Action

Action messages represent a mapped input event. A press and release are separate messages, distinguished by `pressed`. For example, a directional mount action sends `pressed: true` when activated and `pressed: false` when released.

```json
{"ts":1780000000.3,"type":"action","device":"gamepad","action":"MOUNT_NORTH","pressed":true,"source":"dpad"}
```

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `ts` | number | Yes | Unix timestamp in seconds |
| `type` | string | Yes | The literal `"action"` |
| `device` | string | Yes | Sender device identifier |
| `action` | string | Yes | Abstract action name (see below) |
| `pressed` | boolean | Yes | `true` for press/activation; `false` for release |
| `source` | string | Yes | Input source, commonly `"dpad"`, `"button"`, or `"axis"` |
| `step` | integer | No | Focus movement step, sent with `FOCUS_IN` and `FOCUS_OUT` when configured by the sender |
| `angle` | integer | No | Optional rotation angle; protocol validation accepts values from `-360` through `360` |

Supported action names in the sender mapping:

- `MOUNT_NORTH`, `MOUNT_SOUTH`, `MOUNT_WEST`, `MOUNT_EAST`
- `MOUNT_STEP_UP`, `MOUNT_STEP_DOWN`, `MOUNT_STOP`
- `FOCUS_IN`, `FOCUS_OUT`, `FOCUS_STEP_UP`, `FOCUS_STEP_DOWN`
- `FILTERWHEEL_PREV`, `FILTERWHEEL_NEXT`
- `CAA_ROTATE_COUNTER_CLOCKWISE`, `CAA_ROTATE_CLOCKWISE`, `CAA_ROTATE_ABORT`
- `SKYMAP_ZOOM_IN`, `SKYMAP_ZOOM_OUT`
- `SKYMAP_ROTATE_UP`, `SKYMAP_ROTATE_DOWN`

`FOCUS_STEP_UP` and `FOCUS_STEP_DOWN` are handled locally by the sender to change its focus step; they do not produce action packets. Sky-map zoom and rotation actions are dispatched on press only.

## Receiver behavior and validation notes

The receiver buffers incoming bytes until it finds a newline, parses each non-empty line as one JSON value, and dispatches objects with `type: "heartbeat"` or `type: "action"`. The protocol module provides `validate_message`, but the receiver's network loop does not call it before dispatch. Senders should therefore use the documented fields and types rather than relying on receiver-side validation.

The validator requires the listed fields for heartbeat and action messages. For action messages, it checks that `step` is an integer (not a boolean) when present and that `angle` is an integer (not a boolean) in the range `-360..360`. Other message types are rejected.
