import json
from pathlib import Path
import time
from typing import Any, Dict


def strip_json_comments(source: str) -> str:
    """Remove JSONC-style comments while preserving string literals."""
    result: list[str] = []
    index = 0
    in_string = False
    escaped = False

    while index < len(source):
        character = source[index]
        next_character = source[index + 1] if index + 1 < len(source) else ""

        if in_string:
            result.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            index += 1
            continue

        if character == '"':
            in_string = True
            result.append(character)
            index += 1
        elif character == "#" or (character == "/" and next_character == "/"):
            if character == "/":
                index += 1
            index += 1
            while index < len(source) and source[index] not in "\r\n":
                index += 1
        elif character == "/" and next_character == "*":
            index += 2
            while index < len(source) and not (source[index] == "*" and index + 1 < len(source) and source[index + 1] == "/"):
                if source[index] in "\r\n":
                    result.append(source[index])
                index += 1
            if index < len(source):
                index += 2
        else:
            result.append(character)
            index += 1

    return "".join(result)


def load_json_file(path: str | Path) -> Any:
    """Load a local JSON configuration file that may contain comments."""
    with open(path, "r", encoding="utf-8") as handle:
        return json.loads(strip_json_comments(handle.read()))


def build_payload(
    axes: Dict[str, float],
    buttons: Dict[str, bool] | None = None,
    mode: str = "slew",
    dpad: Dict[str, bool] | None = None,
) -> Dict[str, Any]:
    payload = {
        "ts": time.time(),
        "type": "axis",
        "device": "gamepad",
        "axes": axes,
        "dpad": dpad if dpad is not None else {},
        "buttons": buttons if buttons is not None else {},
        "mode": mode,
    }
    return payload


def build_action_payload(
    action: str,
    pressed: bool,
    source: str = "dpad",
    device: str = "gamepad",
    step: int | None = None,
    angle: int | None = None,
) -> Dict[str, Any]:
    payload = {
        "ts": time.time(),
        "type": "action",
        "device": device,
        "action": action,
        "pressed": bool(pressed),
        "source": source,
    }
    if step is not None:
        payload["step"] = int(step)
    if angle is not None:
        payload["angle"] = int(angle)
    return payload


def build_heartbeat_payload() -> Dict[str, Any]:
    return {
        "ts": time.time(),
        "type": "heartbeat",
        "device": "gamepad",
        "status": "alive",
    }


def serialize_message(message: Dict[str, Any]) -> str:
    return json.dumps(message, separators=(",", ":"))


def parse_message(packet: str) -> Dict[str, Any]:
    return json.loads(packet)


def validate_message(message: Dict[str, Any]) -> bool:
    if not isinstance(message, dict):
        return False

    msg_type = message.get("type")
    if msg_type == "heartbeat":
        required = {"ts", "type", "device", "status"}
        if not required.issubset(message):
            return False
        if not isinstance(message["ts"], (int, float)):
            return False
        if not isinstance(message["device"], str):
            return False
        if message["status"] != "alive":
            return False
        return True

    if msg_type == "action":
        required = {"ts", "type", "device", "action", "pressed", "source"}
        if not required.issubset(message):
            return False
        if not isinstance(message["ts"], (int, float)):
            return False
        if not isinstance(message["device"], str):
            return False
        if not isinstance(message["action"], str):
            return False
        if not isinstance(message["pressed"], bool):
            return False
        if not isinstance(message["source"], str):
            return False
        if "step" in message and (not isinstance(message["step"], int) or isinstance(message["step"], bool)):
            return False
        if "angle" in message:
            angle = message["angle"]
            if not isinstance(angle, int) or isinstance(angle, bool):
                return False
            if angle < -360 or angle > 360:
                return False
        return True

    if msg_type != "axis":
        return False

    if "axes" not in message or "dpad" not in message or "buttons" not in message or "mode" not in message:
        return False
    if not isinstance(message["axes"], dict):
        return False
    if not isinstance(message["dpad"], dict):
        return False
    if not isinstance(message["buttons"], dict):
        return False
    if not isinstance(message["mode"], str):
        return False
    return True
