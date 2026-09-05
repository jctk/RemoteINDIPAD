import json
import time
from typing import Any, Dict


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
