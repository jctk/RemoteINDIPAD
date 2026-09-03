import json
import time
from typing import Any, Dict


def build_payload(axes: Dict[str, float], buttons: Dict[str, bool], mode: str = "slew") -> Dict[str, Any]:
    payload = {
        "ts": time.time(),
        "type": "axis",
        "device": "gamepad",
        "axes": axes,
        "buttons": buttons,
        "mode": mode,
    }
    return payload


def serialize_message(message: Dict[str, Any]) -> str:
    return json.dumps(message, separators=(",", ":"))


def parse_message(packet: str) -> Dict[str, Any]:
    return json.loads(packet)


def validate_message(message: Dict[str, Any]) -> bool:
    if not isinstance(message, dict):
        return False
    if "axes" not in message or "buttons" not in message or "mode" not in message:
        return False
    if not isinstance(message["axes"], dict):
        return False
    if not isinstance(message["buttons"], dict):
        return False
    if not isinstance(message["mode"], str):
        return False
    return True
