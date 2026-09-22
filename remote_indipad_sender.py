# Remote INDI Pad Sender Module

import json
import os
import socket
import sys
import threading
import time
from datetime import datetime
import builtins
from pathlib import Path

try:
    import ctypes
except ImportError:  # pragma: no cover - fallback for missing ctypes
    ctypes = None

try:
    import pygame
except ImportError:  # pragma: no cover - fallback for missing joystick package
    pygame = None

try:
    from PySide6.QtCore import QObject, Qt, QTimer, Signal
    from PySide6.QtGui import QColor, QFont, QPalette
    from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QFormLayout, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QSpinBox, QTextEdit, QVBoxLayout, QWidget, QSizePolicy
except ImportError:  # pragma: no cover - GUI is optional unless GUI mode is used
    class QObject:
        def __init__(self, *args, **kwargs):
            pass

    class _FallbackSignal:
        def __init__(self, *args, **kwargs):
            pass

        def connect(self, *args, **kwargs):
            return None

        def emit(self, *args, **kwargs):
            return None

    QTimer = None
    Signal = _FallbackSignal
    QColor = QPalette = QFont = QCheckBox = QComboBox = QFormLayout = QGridLayout = QHBoxLayout = QLabel = QLineEdit = QMainWindow = QMessageBox = QPushButton = QSpinBox = QTextEdit = QVBoxLayout = QWidget = object
    QApplication = None

import remote_indipad_protocol as protocol

# Configuration and Constants
HOST = "127.0.0.1"
PORT = 50007
DEADZONE = 0.08
_MODULE_DIR = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd()
GUI_SETTINGS_PATH = _MODULE_DIR / "remote_indipad_sender.json"
DEFAULT_ACTION_MAPPING = {
    "dpad_up": "MOUNT_NORTH",
    "dpad_down": "MOUNT_SOUTH",
    "dpad_left": "MOUNT_WEST",
    "dpad_right": "MOUNT_EAST",
    "button_1": "FOCUS_STEP_UP",
    "button_2": "FOCUS_STEP_DOWN",
    "button_3": "CAA_ROTATE_COUNTER_CLOCKWISE",
    "button_4": "CAA_ROTATE_CLOCKWISE",
    "button_5": "MOUNT_STEP_UP",
    "button_6": "FOCUS_IN",
    "button_7": "MOUNT_STEP_DOWN",
    "button_8": "FOCUS_OUT",
    "button_9": "MOUNT_STOP",
    "button_10": "FOCUS_STOP",
    "button_11": "FILTERWHEEL_PREV",
    "button_12": "FILTERWHEEL_NEXT",
    "axis_1": "SKYMAP_MOVE",
    "axis_2": "SKYMAP_MOVE",
    "axis_3": "SKYMAP_ROTATE",
    "axis_4": "SKYMAP_ZOOM",
    "axis_5": "",
    "axis_6": "",
}
AVAILABLE_ACTIONS = [
    "",
    "MOUNT_NORTH",
    "MOUNT_SOUTH",
    "MOUNT_WEST",
    "MOUNT_EAST",
    "MOUNT_STEP_UP",
    "MOUNT_STEP_DOWN",
    "MOUNT_STOP",
    "FOCUS_IN",
    "FOCUS_OUT",
    "FOCUS_STEP_UP",
    "FOCUS_STEP_DOWN",
    "FOCUS_STOP",
    "FILTERWHEEL_PREV",
    "FILTERWHEEL_NEXT",
    "CAA_ROTATE_COUNTER_CLOCKWISE",
    "CAA_ROTATE_CLOCKWISE",
    "SKYMAP_MOVE",
    "SKYMAP_ZOOM_IN",
    "SKYMAP_ZOOM_OUT",
    "SKYMAP_ROTATE_UP",
    "SKYMAP_ROTATE_DOWN",
]
AXIS_STATE_NAMES = {-1: "NEGATIVE", 0: "CENTER", 1: "POSITIVE"}
AXIS_STATES = ("NEGATIVE", "CENTER", "POSITIVE")

_DEBUG_JSON_CURSOR_SAVED = False
_DEBUG_JSON_LAST_LINES = 0


def get_device_guid(joy) -> str:
    if joy is None:
        return ""
    guid = getattr(joy, "get_guid", lambda: "")()
    return str(guid or "")


def _action_mapping_sort_key(item):
    key = item[0]
    if key in {"dpad_up", "dpad_down", "dpad_left", "dpad_right"}:
        return (0, ("dpad_up", "dpad_down", "dpad_left", "dpad_right").index(key))
    if isinstance(key, str) and key.startswith("button_") and key[7:].isdigit():
        return (1, int(key[7:]))
    if isinstance(key, str) and key.startswith("axis_") and key[5:].isdigit():
        return (2, int(key[5:]))
    return (3, str(key))


def _resolve_flat_action_mapping(mapping: dict | None):
    resolved = DEFAULT_ACTION_MAPPING.copy()
    if not isinstance(mapping, dict):
        return resolved

    for key, value in mapping.items():
        if not isinstance(key, str):
            continue
        if not (key.startswith("dpad_") or key.startswith("button_") or key.startswith("axis_")):
            continue
        if key.startswith("axis_") and isinstance(value, dict):
            resolved[key] = _axis_state_mapping_for_value(value)
            continue
        if not isinstance(value, str):
            continue
        resolved[key] = value.strip()

    for key, value in DEFAULT_ACTION_MAPPING.items():
        if key not in resolved:
            resolved[key] = value

    return dict(sorted(resolved.items(), key=_action_mapping_sort_key))


def _normalize_action_mapping_store(raw_mapping, controller_name: str | None = None, controller_guid: str | None = None):
    normalized_name = str(controller_name or "").strip()
    normalized_guid = str(controller_guid or "").strip()

    if isinstance(raw_mapping, dict) and ("controllers" in raw_mapping or "entries" in raw_mapping):
        container = raw_mapping.get("controllers", raw_mapping.get("entries", []))
        entries = []
        selected_default_mapping = get_default_action_mapping(normalized_name or None, load_axis_config())
        matched_selected = False

        if isinstance(container, list):
            for entry in container:
                if not isinstance(entry, dict):
                    continue
                entry_name = str(entry.get("name", "")).strip()
                entry_guid = str(entry.get("guid", "")).strip()
                mapping_value = entry.get("mapping") if isinstance(entry.get("mapping"), dict) else entry
                resolved_mapping = _resolve_flat_action_mapping(mapping_value)

                if normalized_name and normalized_guid:
                    matches_selected = entry_name == normalized_name and entry_guid == normalized_guid
                elif normalized_name:
                    matches_selected = entry_name == normalized_name
                elif normalized_guid:
                    matches_selected = entry_guid == normalized_guid
                else:
                    matches_selected = False

                if matches_selected:
                    matched_selected = True
                    entries.append({
                        "name": normalized_name or entry_name,
                        "guid": normalized_guid or entry_guid,
                        "mapping": resolved_mapping,
                    })
                    continue

                entries.append({
                    "name": entry_name,
                    "guid": entry_guid,
                    "mapping": resolved_mapping,
                })

        if normalized_name or normalized_guid:
            if not matched_selected:
                entries.append({
                    "name": normalized_name,
                    "guid": normalized_guid,
                    "mapping": selected_default_mapping,
                })

        return {"controllers": entries}

    if isinstance(raw_mapping, dict) and isinstance(raw_mapping.get("mapping"), dict) and "name" in raw_mapping and "guid" in raw_mapping:
        current_mapping = _resolve_flat_action_mapping(raw_mapping.get("mapping"))
        return {"controllers": [{
            "name": str(raw_mapping.get("name", "")).strip(),
            "guid": str(raw_mapping.get("guid", "")).strip(),
            "mapping": current_mapping,
        }]}

    current_mapping = _resolve_flat_action_mapping(raw_mapping)
    containers = []
    if normalized_name or normalized_guid:
        containers.append({
            "name": normalized_name,
            "guid": normalized_guid,
            "mapping": current_mapping,
        })
    return {
        "default": current_mapping,
        "controllers": containers,
    }


def resolve_action_mapping(source: dict | None = None, device_name: str | None = None, device_guid: str | None = None):
    resolved = DEFAULT_ACTION_MAPPING.copy()
    if not isinstance(source, dict):
        return resolved

    candidate = source.get("action_mapping") if isinstance(source.get("action_mapping"), dict) else source
    if not isinstance(candidate, dict):
        return resolved

    if device_name is None:
        device_name = source.get("controller")
    if device_guid is None:
        device_guid = source.get("controller_guid")

    if "controllers" in candidate or "entries" in candidate:
        controller_entries = candidate.get("controllers", candidate.get("entries", []))
        if isinstance(controller_entries, list):
            normalized_name = str(device_name or "").strip()
            normalized_guid = str(device_guid or "").strip()
            for entry in controller_entries:
                if not isinstance(entry, dict):
                    continue
                name_match = str(entry.get("name", "")).strip() == normalized_name
                guid_match = str(entry.get("guid", "")).strip() == normalized_guid
                if name_match and guid_match:
                    mapping = entry.get("mapping")
                    return _resolve_flat_action_mapping(mapping)
            return get_default_action_mapping(normalized_name or None, load_axis_config())

    if "name" in candidate and "guid" in candidate and isinstance(candidate.get("mapping"), dict):
        normalized_name = str(device_name or "").strip()
        normalized_guid = str(device_guid or "").strip()
        if str(candidate.get("name", "")).strip() == normalized_name and str(candidate.get("guid", "")).strip() == normalized_guid:
            return _resolve_flat_action_mapping(candidate.get("mapping"))

    if isinstance(candidate.get("default"), dict):
        return _resolve_flat_action_mapping(candidate.get("default"))

    return _resolve_flat_action_mapping(candidate)


def get_default_action_mapping(device_name: str | None = None, config: dict | None = None):
    loaded = load_axis_config() if config is None else config
    profile_map = loaded.get("profiles", {}) if isinstance(loaded, dict) else {}
    if not isinstance(profile_map, dict):
        profile_map = {}

    query = (str(device_name or "").strip() if device_name is not None else "").strip()
    if query:
        if query in profile_map:
            profile = profile_map[query]
            if isinstance(profile, dict):
                mapping = profile.get("action_mapping")
                if isinstance(mapping, dict):
                    return resolve_action_mapping(mapping)
        lowered = query.lower()
        for profile_name, profile_data in profile_map.items():
            if str(profile_name).lower() == lowered and isinstance(profile_data, dict):
                mapping = profile_data.get("action_mapping")
                if isinstance(mapping, dict):
                    return resolve_action_mapping(mapping)

    default_device = str(loaded.get("default_device", "")).strip()
    if default_device and default_device in profile_map:
        profile = profile_map[default_device]
        if isinstance(profile, dict):
            mapping = profile.get("action_mapping")
            if isinstance(mapping, dict):
                return resolve_action_mapping(mapping)

    default_profile = profile_map.get("default")
    if isinstance(default_profile, dict):
        mapping = default_profile.get("action_mapping")
        if isinstance(mapping, dict):
            return resolve_action_mapping(mapping)

    return DEFAULT_ACTION_MAPPING.copy()


def get_gamepad_input_rows(selected_device: str | None = None):
    rows = [
        ("DPAD Up", "dpad_up"),
        ("DPAD Down", "dpad_down"),
        ("DPAD Left", "dpad_left"),
        ("DPAD Right", "dpad_right"),
    ]

    axis_count = 0
    button_count = 0
    if selected_device:
        try:
            if pygame is not None and getattr(pygame, "get_init", lambda: False)():
                pygame.joystick.init()
                for idx in range(int(getattr(pygame.joystick, "get_count", lambda: 0)())):
                    joy = pygame.joystick.Joystick(idx)
                    joy.init()
                    if str(get_device_name(joy)).lower() == str(selected_device).lower():
                        axis_count = max(axis_count, int(getattr(joy, "get_numaxes", lambda: 0)()))
                        button_count = max(button_count, int(getattr(joy, "get_numbuttons", lambda: 0)()))
                        break
        except Exception:
            axis_count = 0
            button_count = 0

    if axis_count <= 0 or button_count <= 0:
        config = load_axis_config()
        mapping = get_default_action_mapping(selected_device, config)
        if axis_count <= 0:
            axis_count = max(
                [int(key.split("_", 1)[1]) for key in mapping if isinstance(key, str) and key.startswith("axis_")],
                default=6,
            )
        if button_count <= 0:
            button_count = max(
                [int(key.split("_", 1)[1]) for key in mapping if isinstance(key, str) and key.startswith("button_")],
                default=12,
            )

    rows.extend((f"Button {index}", f"button_{index}") for index in range(1, button_count + 1))
    rows.extend((f"Axis {index}", f"axis_{index}") for index in range(1, axis_count + 1))
    return rows


def _clamp_focus_step(value: object, default: int = 100) -> int:
    try:
        step = int(value)
    except (TypeError, ValueError):
        return default
    if step < 1:
        return 1
    if step > 5000:
        return 5000
    return step


def _clamp_deadzone(value: object, default: float = DEADZONE) -> float:
    try:
        deadzone = float(value)
    except (TypeError, ValueError):
        return default
    return min(max(deadzone, 0.0), 1.0)


def load_gui_settings(path: str | Path | None = None):
    config_path = Path(path) if path is not None else GUI_SETTINGS_PATH
    defaults = {
        "controller": "",
        "controller_guid": "",
        "host": "localhost",
        "port": 50007,
        "heartbeat": False,
        "focus_step": 100,
        "deadzone": DEADZONE,
        "action_mapping": {"controllers": []},
        "window_geometry": {},
    }

    if not config_path.exists():
        return defaults.copy()

    try:
        with open(config_path, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
    except (OSError, ValueError):
        return defaults.copy()

    if not isinstance(loaded, dict):
        return defaults.copy()

    controller = loaded.get("controller", "")
    controller_guid = loaded.get("controller_guid", "")
    host = loaded.get("host", "localhost")
    port = loaded.get("port", 50007)
    heartbeat = loaded.get("heartbeat", False)
    focus_step = _clamp_focus_step(loaded.get("focus_step", 100), default=100)
    deadzone = _clamp_deadzone(loaded.get("deadzone", DEADZONE))
    window_geometry = loaded.get("window_geometry", {})
    if not isinstance(window_geometry, dict):
        window_geometry = {}
    normalized_geometry = {}
    for key in ("x", "y", "width", "height"):
        try:
            normalized_geometry[key] = int(window_geometry[key])
        except (KeyError, TypeError, ValueError):
            pass

    try:
        port_value = int(port)
    except (TypeError, ValueError):
        port_value = 50007

    raw_mapping = loaded.get("action_mapping", {"controllers": []})
    normalized_mapping = _normalize_action_mapping_store(raw_mapping, controller_name=str(controller or ""), controller_guid=str(controller_guid or ""))

    return {
        "controller": str(controller) if controller is not None else "",
        "controller_guid": str(controller_guid) if controller_guid is not None else "",
        "host": str(host) if host is not None else "localhost",
        "port": port_value,
        "heartbeat": bool(heartbeat),
        "focus_step": focus_step,
        "deadzone": deadzone,
        "action_mapping": normalized_mapping,
        "window_geometry": normalized_geometry,
    }


def save_gui_settings(settings: dict, path: str | Path | None = None):
    config_path = Path(path) if path is not None else GUI_SETTINGS_PATH
    controller_name = str(settings.get("controller", "") or "")
    controller_guid = str(settings.get("controller_guid", "") or "")
    raw_mapping = settings.get("action_mapping", {"controllers": []})
    window_geometry = settings.get("window_geometry", {})
    if not isinstance(window_geometry, dict):
        window_geometry = {}
    normalized_geometry = {}
    for key in ("x", "y", "width", "height"):
        try:
            normalized_geometry[key] = int(window_geometry[key])
        except (KeyError, TypeError, ValueError):
            pass
    payload = {
        "controller": controller_name,
        "controller_guid": controller_guid,
        "host": str(settings.get("host", "localhost") or "localhost"),
        "port": int(settings.get("port", 50007) or 50007),
        "heartbeat": bool(settings.get("heartbeat", False)),
        "focus_step": _clamp_focus_step(settings.get("focus_step", 100), default=100),
        "deadzone": _clamp_deadzone(settings.get("deadzone", DEADZONE)),
        "action_mapping": _normalize_action_mapping_store(raw_mapping, controller_name=controller_name, controller_guid=controller_guid),
        "window_geometry": normalized_geometry,
    }

    with open(config_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def load_axis_config(path: str | Path | None = None):
    if path is not None:
        config_path = Path(path)
    else:
        config_path = (_MODULE_DIR / "gamepad_profiles.json")
    config = {"default_device": "", "profiles": {}}

    if not config_path.exists():
        config["profiles"]["default"] = {}
        return config

    try:
        with open(config_path, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
    except (OSError, ValueError):
        config["profiles"]["default"] = {}
        return config

    if not isinstance(loaded, dict):
        config["profiles"]["default"] = {}
        return config

    config["default_device"] = str(loaded.get("default_device", ""))

    profiles = loaded.get("profiles")
    if isinstance(profiles, dict):
        for profile_name, profile_data in profiles.items():
            if not isinstance(profile_data, dict):
                continue
            config["profiles"][str(profile_name)] = profile_data

    if not config["profiles"]:
        config["profiles"]["default"] = {}

    return config


def get_device_name(joy) -> str:
    name = getattr(joy, "get_name", lambda: "")()
    return str(name or "Unknown gamepad")

# Windows VT100 console support
def enable_windows_vt100() -> None:
    if os.name != "nt" or ctypes is None:
        return
    try:
        handle = ctypes.windll.kernel32.GetStdHandle(-11)
        if handle == 0 or handle == ctypes.c_void_p(-1).value:
            return
        mode = ctypes.c_ulong()
        if ctypes.windll.kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            ctypes.windll.kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass

# Enable Windows VT100 console support
enable_windows_vt100()

# Clear the console screen
def clear_console() -> None:
    if os.name == "nt":
        print("\x1b[2J\x1b[H", end="", flush=True)
        try:
            os.system("cls")
        except Exception:
            pass
    else:
        print("\033[2J\033[H", end="", flush=True)

# Timestamped console print functions
_ORIGINAL_PRINT = builtins.print
_LOG_TIMESTAMP_LENGTH = len("0000-00-00 00:00:00.000")

# Format the current timestamp for log messages
def format_log_timestamp() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

# Prepend a timestamp to the log message if it doesn't already have one
def timestamp_log_message(message: str) -> str:
    text = str(message)
    if len(text) >= _LOG_TIMESTAMP_LENGTH and text[_LOG_TIMESTAMP_LENGTH - 3] == "." and text[4] == "-" and text[7] == "-":
        return text
    return f"{format_log_timestamp()} {text}"

# Generate a protocol-specific log suffix based on the payload's timestamp
def protocol_log_suffix(payload: dict | None) -> str:
    if not isinstance(payload, dict):
        return ""
    timestamp = payload.get("ts")
    if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)):
        return ""
    try:
        local_time = datetime.fromtimestamp(timestamp).astimezone().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
    except (OverflowError, OSError, ValueError):
        return ""
    return f" ts={local_time}"

# Append the protocol-specific log time to a message
def append_protocol_log_time(message: str, payload: dict | None = None) -> str:
    return f"{message}{protocol_log_suffix(payload)}"

# Console print function with timestamping
def console_print(*values, **kwargs):
    if values and not any("\x1b" in str(value) for value in values):
        values = (timestamp_log_message(kwargs.get("sep", " ").join(str(value) for value in values)),)
        kwargs = {key: value for key, value in kwargs.items() if key != "sep"}
    builtins.print(*values, **kwargs)

# Override the built-in print function with the timestamped console print function
print = console_print

# JSON formatting and debug printing functions
def _normalize_json_for_display(value):
    if isinstance(value, dict):
        normalized = {}
        for key, item in value.items():
            normalized[key] = _normalize_json_for_display(item)

        if all(isinstance(key, str) and key.startswith("button_") for key in normalized):
            normalized = dict(sorted(normalized.items(), key=lambda pair: _button_sort_key(pair[0])))
        return normalized
    if isinstance(value, list):
        return [_normalize_json_for_display(item) for item in value]
    return value


def _button_sort_key(key: str):
    if isinstance(key, str) and key.startswith("button_"):
        suffix = key[len("button_") :]
        if suffix.isdigit():
            return (0, int(suffix))
    return (1, str(key))


def format_debug_json(value) -> str:
    return json.dumps(_normalize_json_for_display(value), ensure_ascii=False, separators=(",", ":"))


def print_debug_json(label: str, value) -> None:
    global _DEBUG_JSON_CURSOR_SAVED, _DEBUG_JSON_LAST_LINES

    rendered = format_debug_json(value)
    rendered_lines = rendered.splitlines()
    if rendered_lines:
        rendered_lines[-1] += protocol_log_suffix(value)
    lines = [f"{format_log_timestamp()} {label}:"] + rendered_lines
    total_lines = len(lines)

    if not _DEBUG_JSON_CURSOR_SAVED:
        print("\n", end="", flush=True)
        print("\x1b[s", end="", flush=True)
        _DEBUG_JSON_CURSOR_SAVED = True
    else:
        print("\x1b[u", end="", flush=True)

    for index in range(max(_DEBUG_JSON_LAST_LINES, total_lines)):
        if index < total_lines:
            line = lines[index]
            print("\x1b[2K" + line, end="\n" if index < total_lines - 1 else "", flush=True)
        else:
            print("\x1b[2K", end="\n", flush=True)

    _DEBUG_JSON_LAST_LINES = total_lines


def apply_deadzone(value: float, deadzone: float | None = None) -> float:
    zone = DEADZONE if deadzone is None else _clamp_deadzone(deadzone)
    if abs(value) < zone:
        return 0.0
    return value


def normalize_axis_value(value: float, deadzone: float | None = None) -> int:
    zone = float(DEADZONE if deadzone is None else deadzone)
    numeric = float(value)
    if numeric < -zone:
        return -1
    if abs(numeric) <= zone:
        return 0
    return 1


def normalize_axes(raw_axes, deadzone: float | None = None):
    normalized = {}
    for key, value in raw_axes.items():
        normalized[key] = apply_deadzone(float(value), deadzone)
    return normalized


def _axis_state_mapping_for_value(value):
    if isinstance(value, dict):
        normalized = {}
        for state_name in AXIS_STATES:
            action = value.get(state_name, "")
            if isinstance(action, str):
                normalized[state_name] = action.strip()
            else:
                normalized[state_name] = ""
        return normalized
    if isinstance(value, str):
        return {"NEGATIVE": "", "CENTER": "", "POSITIVE": value.strip()}
    return {"NEGATIVE": "", "CENTER": "", "POSITIVE": ""}


def _coerce_axis_mapping(mapping: dict | None):
    if not isinstance(mapping, dict):
        return {}
    coerced = {}
    for key, value in mapping.items():
        if not isinstance(key, str) or not key.startswith("axis_"):
            continue
        coerced[key] = _axis_state_mapping_for_value(value)
    return coerced


def state_signature(axes, buttons, dpad=None):
    dpad = {} if dpad is None else dpad
    return (
        tuple(sorted((k, round(float(v), 4)) for k, v in axes.items())),
        tuple(sorted((k, bool(v)) for k, v in dpad.items())),
        tuple(sorted((k, bool(v)) for k, v in buttons.items())),
    )


def build_action_events(
    dpad: dict | None = None,
    buttons: dict | None = None,
    axes: dict | None = None,
    previous_axes: dict | None = None,
    previous_dpad: dict | None = None,
    previous_buttons: dict | None = None,
    action_map: dict | None = None,
    focus_step: int | None = None,
    focus_step_state: dict | None = None,
    button_press_times: dict | None = None,
    now: float | None = None,
    deadzone: float | None = None,
):
    dpad = {} if dpad is None else dpad
    buttons = {} if buttons is None else buttons
    axes = {} if axes is None else axes
    previous_axes = {} if previous_axes is None else previous_axes
    previous_dpad = {} if previous_dpad is None else previous_dpad
    previous_buttons = {} if previous_buttons is None else previous_buttons
    if button_press_times is None:
        button_press_times = {}
    if previous_axes and previous_buttons == {} and all(isinstance(key, str) and key.startswith("button_") for key in previous_axes):
        previous_buttons = dict(previous_axes)
        previous_axes = {}
    now = time.monotonic() if now is None else float(now)
    events = []
    resolved_map = resolve_action_mapping(action_map)
    current_focus_step = _clamp_focus_step(focus_step, default=100) if focus_step is not None else 100
    base_focus_step = current_focus_step
    if focus_step_state is not None:
        focus_step_state["value"] = current_focus_step

    dpad_names = ("dpad_up", "dpad_down", "dpad_left", "dpad_right")
    def advance_step(direction: str) -> int:
        nonlocal current_focus_step
        step_sequence = [5, 10, 50, 100, 500]
        current_value = _clamp_focus_step(current_focus_step, default=100)
        try:
            index = step_sequence.index(current_value)
        except ValueError:
            index = step_sequence.index(100)
        if direction == "up":
            next_index = min(index + 1, len(step_sequence) - 1)
        elif direction == "down":
            next_index = max(index - 1, 0)
        else:
            return current_value
        current_focus_step = step_sequence[next_index]
        if focus_step_state is not None:
            focus_step_state["value"] = current_focus_step
        return current_focus_step

    def apply_focus_step_action(action: str) -> bool:
        if action == "FOCUS_STEP_UP":
            advance_step("up")
            return True
        if action == "FOCUS_STEP_DOWN":
            advance_step("down")
            return True
        return False

    for name in dpad_names:
        current_pressed = bool(dpad.get(name))
        previous_pressed = bool(previous_dpad.get(name))
        if current_pressed != previous_pressed:
            action_name = resolved_map.get(name, DEFAULT_ACTION_MAPPING.get(name, name))
            if action_name:
                events.append({"action": action_name, "pressed": current_pressed, "source": "dpad"})

    for key, action in resolved_map.items():
        if not key.startswith("button_"):
            continue
        if key in buttons:
            current_pressed = bool(buttons.get(key))
            previous_pressed = bool(previous_buttons.get(key))
            if current_pressed != previous_pressed:
                if not action:
                    continue
                if current_pressed and apply_focus_step_action(action):
                    continue
                if action in {"CAA_ROTATE_CLOCKWISE", "CAA_ROTATE_COUNTER_CLOCKWISE"}:
                    if current_pressed != previous_pressed:
                        button_press_times[key] = now if current_pressed else button_press_times.get(key, now)
                        events.append({"action": action, "pressed": current_pressed, "source": "button"})
                    elif current_pressed:
                        button_press_times[key] = now
                    continue
                event = {"action": action, "pressed": current_pressed, "source": "button"}
                if action in {"FOCUS_IN", "FOCUS_OUT"}:
                    event["step"] = base_focus_step
                events.append(event)

    for axis_key, raw_value in (axes or {}).items():
        if not isinstance(axis_key, str) or not axis_key.startswith("axis_"):
            continue
        axis_state = normalize_axis_value(raw_value, deadzone)
        previous_value = previous_axes.get(axis_key)
        previous_state = None if previous_value is None else normalize_axis_value(previous_value, deadzone)
        state_mapping = _axis_state_mapping_for_value(resolved_map.get(axis_key, {}))
        if previous_state is None:
            current_action = state_mapping.get(AXIS_STATE_NAMES.get(axis_state, "CENTER"), "")
            if current_action and not apply_focus_step_action(current_action):
                events.append({"action": current_action, "pressed": True, "source": "axis"})
            continue
        if previous_state == axis_state:
            continue
        previous_action = state_mapping.get(AXIS_STATE_NAMES.get(previous_state, "CENTER"), "")
        current_action = state_mapping.get(AXIS_STATE_NAMES.get(axis_state, "CENTER"), "")
        if previous_action and previous_action not in {"FOCUS_STEP_UP", "FOCUS_STEP_DOWN"}:
            events.append({"action": previous_action, "pressed": False, "source": "axis"})
        if current_action and not apply_focus_step_action(current_action):
            events.append({"action": current_action, "pressed": True, "source": "axis"})

    for key in list(button_press_times):
        if key.startswith("button_") and key in buttons and not bool(buttons.get(key)):
            button_press_times.pop(key, None)

    if focus_step_state is not None:
        focus_step_state["value"] = current_focus_step
    return events


def get_gamepad_name(joy) -> str:
    name = getattr(joy, "get_name", lambda: "")()
    return str(name or "Unknown gamepad")


def resolve_gamepad_selection(gamepad_names, selected_device: str | None = None):
    names = [str(name or "Unknown gamepad") for name in gamepad_names]
    if not names:
        raise RuntimeError("No gamepad found")

    def normalize_index(raw_value: str):
        if not raw_value:
            return None
        if raw_value.isdigit():
            numeric = int(raw_value)
            if 1 <= numeric <= len(names):
                return numeric - 1
        return None

    if selected_device is not None and str(selected_device).strip():
        query = str(selected_device).strip()
        if query.isdigit():
            numeric_index = normalize_index(query)
            if numeric_index is not None:
                return numeric_index
            raise ValueError(f"Gamepad index {query} is out of range. Choose a value from 1-{len(names)}.")

        lowered_query = query.lower()
        exact_matches = [idx for idx, name in enumerate(names) if name.lower() == lowered_query]
        if exact_matches:
            return exact_matches[0]

        contains_matches = [idx for idx, name in enumerate(names) if lowered_query in name.lower()]
        if contains_matches:
            return contains_matches[0]

        raise ValueError(f"Gamepad '{query}' not found. Available: {', '.join(f'{i + 1}: {name}' for i, name in enumerate(names))}")

    if len(names) == 1:
        print(f"[sender] connected gamepad: {names[0]}", flush=True)
        return 0

    print("[sender] available gamepads:")
    for index, name in enumerate(names):
        print(f"  [{index + 1}] {name}", flush=True)

    while True:
        response = input("[sender] select gamepad index: ").strip()
        numeric_index = normalize_index(response)
        if numeric_index is not None:
            return numeric_index

        if response.isdigit():
            print(
                f"[sender] invalid selection: {response}. "
                f"Choose a value from 1-{len(names)} or type a gamepad name.",
                flush=True,
            )
            continue

        lowered = response.lower()
        match = None
        for idx, name in enumerate(names):
            if name.lower() == lowered or lowered in name.lower():
                match = idx
                break
        if match is not None:
            return match

        print(
            f"[sender] invalid selection: {response}. "
            f"Choose a value from 1-{len(names)} or type a gamepad name.",
            flush=True,
        )


def init_gamepad(selected_device: str | None = None):
    if pygame is None:
        raise RuntimeError("pygame is not installed")
    pygame.init()
    pygame.joystick.init()
    count = pygame.joystick.get_count()
    if count == 0:
        raise RuntimeError("No gamepad found")

    names = [pygame.joystick.Joystick(index).get_name() for index in range(count)]
    selected_index = resolve_gamepad_selection(names, selected_device)
    joy = pygame.joystick.Joystick(selected_index)
    joy.init()
    return joy


def _safe_joystick_axis(joy, index: int) -> float:
    try:
        total = int(getattr(joy, "get_numaxes", lambda: 0)())
    except Exception:
        return 0.0

    if index < 0 or index >= total:
        return 0.0

    try:
        return float(joy.get_axis(index))
    except Exception:
        return 0.0

# Gamepad State Reading Functions
def read_gamepad_state(joy):
    # axis_N always maps 1:1 to the physical joystick axis index (N - 1)
    if pygame is not None and getattr(pygame, "get_init", lambda: False)():
        pygame.event.pump()

    total_axes = int(getattr(joy, "get_numaxes", lambda: 0)())
    axes = {}
    for index in range(1, total_axes + 1):
        axes[f"axis_{index}"] = _safe_joystick_axis(joy, index - 1)

    # Read the number of buttons available on the joystick
    button_count = int(getattr(joy, "get_numbuttons", lambda: 0)())
    buttons = {}
    for i in range(min(16, button_count)):
        try:
            buttons[f"button_{i + 1}"] = bool(joy.get_button(i))
        except Exception:
            buttons[f"button_{i + 1}"] = False

    # Read the state of the directional pad (D-pad) if available
    dpad = {}
    if hasattr(joy, "get_hat"):
        try:
            hat_count = int(getattr(joy, "get_numhats", lambda: 1)())
        except Exception:
            hat_count = 1
        if hat_count <= 0:
            hat_count = 1
        try:
            hat_x, hat_y = joy.get_hat(0)
        except TypeError:
            try:
                hat_x, hat_y = joy.get_hat()
            except TypeError:
                hat_x, hat_y = (0, 0)
        except Exception:
            hat_x, hat_y = (0, 0)
        dpad["dpad_up"] = hat_y == 1
        dpad["dpad_down"] = hat_y == -1
        dpad["dpad_left"] = hat_x == -1
        dpad["dpad_right"] = hat_x == 1

    return axes, buttons, dpad


def build_gamepad_monitor_snapshot(
    device_name: str | None = None,
    guid: str | None = None,
    axes: dict | None = None,
    buttons: dict | None = None,
    dpad: dict | None = None,
    axis_count: int = 0,
    button_count: int = 0,
    hat_count: int = 0,
    instance_id: str | int | None = None,
    trackballs: int = 0,
):
    normalized_axes = {}
    for key, value in (axes or {}).items():
        normalized_axes[str(key)] = float(value)

    normalized_buttons = {}
    for key, value in (buttons or {}).items():
        normalized_buttons[str(key)] = bool(value)

    normalized_dpad = {}
    for key, value in (dpad or {}).items():
        normalized_dpad[str(key)] = bool(value)

    count_axes = int(axis_count or max((int(key.split("_", 1)[1]) for key in normalized_axes if str(key).startswith("axis_")), default=0))
    count_buttons = int(button_count or max((int(key.split("_", 1)[1]) for key in normalized_buttons if str(key).startswith("button_")), default=0))
    count_hats = int(hat_count or (1 if any(str(key).startswith("dpad_") for key in normalized_dpad) else 0))

    return {
        "device_name": str(device_name or "Unknown gamepad"),
        "device_guid": str(guid or ""),
        "instance_id": str(instance_id or ""),
        "axis_count": count_axes,
        "button_count": count_buttons,
        "hat_count": count_hats,
        "trackballs": int(trackballs),
        "axes": normalized_axes,
        "buttons": normalized_buttons,
        "dpad": normalized_dpad,
    }


def demo_axes_state(step: int):
    phase = step % 16
    values = {
        0: {"axis_1": 0.0, "axis_2": 0.0, "axis_3": 0.0, "axis_4": 0.0},
        1: {"axis_1": 0.25, "axis_2": -0.15, "axis_3": 0.0, "axis_4": 0.2},
        2: {"axis_1": 0.5, "axis_2": -0.35, "axis_3": 0.1, "axis_4": 0.4},
        3: {"axis_1": 0.75, "axis_2": -0.5, "axis_3": 0.25, "axis_4": 0.6},
        4: {"axis_1": 1.0, "axis_2": -0.9, "axis_3": 0.35, "axis_4": 0.8},
        5: {"axis_1": 0.75, "axis_2": -0.5, "axis_3": 0.2, "axis_4": 0.6},
        6: {"axis_1": 0.5, "axis_2": -0.2, "axis_3": 0.1, "axis_4": 0.3},
        7: {"axis_1": 0.2, "axis_2": 0.1, "axis_3": 0.0, "axis_4": 0.0},
        8: {"axis_1": 0.0, "axis_2": 0.0, "axis_3": 0.0, "axis_4": 0.0},
        9: {"axis_1": -0.2, "axis_2": 0.1, "axis_3": -0.1, "axis_4": -0.2},
        10: {"axis_1": -0.5, "axis_2": 0.3, "axis_3": -0.2, "axis_4": -0.4},
        11: {"axis_1": -0.75, "axis_2": 0.5, "axis_3": -0.3, "axis_4": -0.6},
        12: {"axis_1": -1.0, "axis_2": 0.9, "axis_3": -0.4, "axis_4": -0.8},
        13: {"axis_1": -0.75, "axis_2": 0.5, "axis_3": -0.3, "axis_4": -0.6},
        14: {"axis_1": -0.5, "axis_2": 0.2, "axis_3": -0.1, "axis_4": -0.3},
        15: {"axis_1": -0.2, "axis_2": 0.1, "axis_3": 0.0, "axis_4": 0.0},
    }
    return values[phase % 16]


def demo_buttons(step: int):
    index = (step % 12) + 1
    buttons = {f"button_{i}": False for i in range(1, 13)}
    buttons[f"button_{index}"] = True
    return buttons


def send_loop(host: str = HOST, port: int = PORT, interval: float = 0.05, demo: bool = False, forced_device: str | None = None, action_map: dict | None = None, deadzone: float = DEADZONE):
    joy = None
    resolved_action_map = resolve_action_mapping(action_map)
    if demo:
        print("[sender] demo mode enabled", flush=True)
    else:
        try:
            joy = init_gamepad(forced_device)
            gamepad_name = get_gamepad_name(joy)
            print(f"[sender] connected gamepad: {gamepad_name}", flush=True)
        except RuntimeError as exc:
            print(f"[sender] no gamepad available: {exc}; switching to demo mode", flush=True)
            demo = True

    if forced_device:
        print(f"[sender] forced device profile: {forced_device}", flush=True)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(2.0)
        print(f"[sender] connecting to {host}:{port}...", flush=True)
        try:
            sock.connect((host, port))
        except OSError as exc:
            print(
                f"[sender] failed to connect to {host}:{port}: {exc}. "
                "Make sure the receiver is running and that the port is not already occupied by another process.",
                flush=True,
            )
            raise
        print(f"[sender] connected to {host}:{port}", flush=True)

        step = 0
        last_signature = None
        last_heartbeat = 0.0
        heartbeat_interval = 1.0
        previous_dpad = {}
        previous_buttons = {}
        previous_axes = {}
        button_press_times = {}
        while True:
            now = time.monotonic()
            if now - last_heartbeat >= heartbeat_interval:
                heartbeat = protocol.build_heartbeat_payload()
                if protocol.validate_message(heartbeat):
                    packet = protocol.serialize_message(heartbeat)
                    sock.sendall((packet + "\n").encode("utf-8"))
                    print_debug_json("[sender] heartbeat", heartbeat)
                last_heartbeat = now

            if demo:
                axes = demo_axes_state(step)
                buttons = demo_buttons(step)
                dpad = {"dpad_up": False, "dpad_down": False, "dpad_left": False, "dpad_right": False}
            else:
                axes, buttons, dpad = read_gamepad_state(joy)
            axes = normalize_axes(axes, deadzone)
            buttons = {k: bool(v) for k, v in buttons.items()}
            dpad = {k: bool(v) for k, v in dpad.items()}

            signature = state_signature(axes, buttons, dpad)
            if last_signature is None or signature != last_signature:
                focus_state = {"value": 100}
                action_events = build_action_events(
                    dpad=dpad,
                    buttons=buttons,
                    axes=axes,
                    previous_axes=previous_axes,
                    previous_dpad=previous_dpad,
                    previous_buttons=previous_buttons,
                    action_map=resolved_action_map,
                    focus_step=focus_state["value"],
                    focus_step_state=focus_state,
                    button_press_times=button_press_times,
                    now=now,
                    deadzone=deadzone,
                )
                for event in action_events:
                    message = protocol.build_action_payload(
                        action=event["action"],
                        pressed=event["pressed"],
                        source=event["source"],
                        step=event.get("step"),
                        angle=event.get("angle"),
                    )
                    if protocol.validate_message(message):
                        packet = protocol.serialize_message(message)
                        print_debug_json("[sender] json", message)
                        sock.sendall((packet + "\n").encode("utf-8"))
                previous_dpad = dpad.copy()
                previous_buttons = buttons.copy()
                previous_axes = axes.copy()
                last_signature = signature

            step += 1
            time.sleep(interval)


class SenderWorker(QObject):
    status_changed = Signal(str)
    log_received = Signal(str)
    connection_changed = Signal(str)
    monitor_updated = Signal(object)

    def __init__(
        self,
        host: str,
        port: int,
        device_name: str | None = None,
        controller_guid: str | None = None,
        action_map: dict | None = None,
        focus_step: int = 100,
        deadzone: float = DEADZONE,
        focus_step_changed_callback=None,
    ):
        super().__init__()
        self.host = host
        self.port = port
        self.device_name = device_name
        self.controller_guid = controller_guid
        self.action_map = resolve_action_mapping(
            action_map,
            device_name=device_name,
            device_guid=controller_guid,
        )
        self._focus_step = _clamp_focus_step(focus_step, default=100)
        self._deadzone = _clamp_deadzone(deadzone)
        self._focus_step_changed_callback = focus_step_changed_callback
        self._stop_event = threading.Event()
        self._socket = None
        self._joy = None

    def stop(self):
        self._stop_event.set()
        if self._socket is not None:
            try:
                self._socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None

    def _safe_emit(self, signal, value):
        try:
            signal.emit(value)
        except RuntimeError:
            pass

    def run(self):
        try:
            self._joy = init_gamepad(self.device_name)
            self._safe_emit(self.connection_changed, f"Connected: {get_gamepad_name(self._joy)}")
            self._safe_emit(self.status_changed, "Ready")
            self._socket = socket.create_connection((self.host, self.port), timeout=2.0)
            self._socket.settimeout(0.25)
            self._safe_emit(self.log_received, f"Connected to {self.host}:{self.port}")

            last_heartbeat = 0.0
            previous_dpad = {}
            previous_buttons = {}
            previous_axes = {}
            button_press_times = {}
            previous_signature = None
            last_snapshot = None
            while not self._stop_event.is_set():
                now = time.monotonic()
                if now - last_heartbeat >= 1.0:
                    heartbeat = protocol.build_heartbeat_payload()
                    packet = protocol.serialize_message(heartbeat)
                    self._socket.sendall((packet + "\n").encode("utf-8"))
                    self._safe_emit(self.log_received, append_protocol_log_time(f"[sender] heartbeat: {packet}", heartbeat))
                    last_heartbeat = now

                axes, buttons, dpad = read_gamepad_state(self._joy)
                axes = normalize_axes(axes, self._deadzone)
                buttons = {k: bool(v) for k, v in buttons.items()}
                dpad = {k: bool(v) for k, v in dpad.items()}
                snapshot = build_gamepad_monitor_snapshot(
                    device_name=get_gamepad_name(self._joy),
                    guid=get_device_guid(self._joy),
                    axes=axes,
                    buttons=buttons,
                    dpad=dpad,
                    axis_count=int(getattr(self._joy, "get_numaxes", lambda: 0)()),
                    button_count=int(getattr(self._joy, "get_numbuttons", lambda: 0)()),
                    hat_count=int(getattr(self._joy, "get_numhats", lambda: 0)()),
                    instance_id=getattr(self._joy, "get_instance_id", lambda: "")(),
                )
                if snapshot != last_snapshot:
                    self._safe_emit(self.monitor_updated, snapshot)
                    last_snapshot = snapshot

                focus_step_state = {"value": self._focus_step}
                previous_focus_step = self._focus_step
                signature = state_signature(axes, buttons, dpad)
                if previous_signature is None or signature != previous_signature:
                    action_events = build_action_events(
                        dpad=dpad,
                        buttons=buttons,
                        axes=axes,
                        previous_axes=previous_axes,
                        previous_dpad=previous_dpad,
                        previous_buttons=previous_buttons,
                        action_map=self.action_map,
                        focus_step=focus_step_state["value"],
                        focus_step_state=focus_step_state,
                        button_press_times=button_press_times,
                        now=now,
                        deadzone=self._deadzone,
                    )
                    for event in action_events:
                        if event["action"] in {"FOCUS_STEP_UP", "FOCUS_STEP_DOWN"}:
                            continue
                        message = protocol.build_action_payload(
                            action=event["action"],
                            pressed=event["pressed"],
                            source=event["source"],
                            step=event.get("step"),
                            angle=event.get("angle"),
                        )
                        packet = protocol.serialize_message(message)
                        self._socket.sendall((packet + "\n").encode("utf-8"))
                        self._safe_emit(
                            self.log_received,
                            append_protocol_log_time(
                                json.dumps(message, ensure_ascii=False, separators=(",", ":")),
                                message,
                            ),
                        )
                    previous_dpad = dpad.copy()
                    previous_buttons = buttons.copy()
                    previous_axes = axes.copy()
                    previous_signature = signature

                self._focus_step = _clamp_focus_step(focus_step_state["value"], default=100)
                if previous_focus_step != self._focus_step and self._focus_step_changed_callback is not None:
                    try:
                        self._focus_step_changed_callback(self._focus_step)
                    except Exception:
                        pass
                time.sleep(0.05)
        except Exception as exc:  # pragma: no cover - runtime behavior
            self._safe_emit(self.connection_changed, f"Error: {exc}")
            self._safe_emit(self.status_changed, "Disconnected")
            self._safe_emit(self.log_received, f"[sender] error: {exc}")
        finally:
            self._safe_emit(self.connection_changed, "Disconnected")
            self._safe_emit(self.status_changed, "Disconnected")
            if self._socket is not None:
                try:
                    self._socket.close()
                except OSError:
                    pass
                self._socket = None


class IndipadWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("INDIPAD")
        self.resize(720, 520)
        self.worker = None
        self.worker_thread = None
        self.mapping_editor = None
        self.gui_settings = load_gui_settings()
        geometry = self.gui_settings.get("window_geometry", {})
        if all(key in geometry for key in ("x", "y", "width", "height")):
            self.setGeometry(geometry["x"], geometry["y"], max(300, geometry["width"]), max(240, geometry["height"]))

        # Central widget and main layout
        central = QWidget(self)
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        form_layout = QFormLayout()

        self.controller_combo = QComboBox()
        self.host_edit = QLineEdit(self.gui_settings["host"])
        self.port_edit = QLineEdit(str(self.gui_settings["port"]))
        self.heartbeat_checkbox = QCheckBox("Heartbeat")
        self.heartbeat_checkbox.setChecked(bool(self.gui_settings["heartbeat"]))
        self.focus_step_spin = QSpinBox()
        self.focus_step_spin.setRange(1, 5000)
        self.focus_step_spin.setValue(int(self.gui_settings.get("focus_step", 100)))
        self.focus_step_spin.valueChanged.connect(self._on_focus_step_changed)

        form_layout.addRow("Controller", self.controller_combo)

        host_port_row = QHBoxLayout()
        host_port_row.addWidget(self.host_edit)
        host_port_row.addWidget(self.port_edit)
        form_layout.addRow("Host / Port", host_port_row)
        form_layout.addRow("Logs", self.heartbeat_checkbox)
        form_layout.addRow("Focus step", self.focus_step_spin)

        button_row = QHBoxLayout()
        self.connection_button = QPushButton("Connect")
        self.mapping_button = QPushButton("Edit Mapping")
        self.close_button = QPushButton("Close")
        button_row.addWidget(self.connection_button)
        button_row.addWidget(self.mapping_button)
        button_row.addWidget(self.close_button)

        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setFont(QFont("Consolas", 10))
        self.console.setPlainText("INDIPAD console\n")
        self.clear_console_button = QPushButton("Clear")
        self.clear_console_button.clicked.connect(self.clear_console_log)
        console_button_row = QHBoxLayout()
        console_button_row.addStretch()
        console_button_row.addWidget(self.clear_console_button)

        self.monitor_widget = QWidget()
        self.monitor_layout = QVBoxLayout(self.monitor_widget)
        self.monitor_layout.setContentsMargins(0, 0, 0, 0)
        self.monitor_layout.setSpacing(6)

        self.monitor_title = QLabel("MONITOR")
        self.monitor_title.setStyleSheet("font-weight: bold;")
        self.monitor_layout.addWidget(self.monitor_title)

        self.monitor_summary = QWidget()
        self.monitor_summary_layout = QHBoxLayout(self.monitor_summary)
        self.monitor_summary_layout.setContentsMargins(0, 0, 0, 0)
        self.monitor_summary_layout.setSpacing(8)
        self.monitor_summary_layout.setStretch(0, 0)
        self.monitor_summary_layout.setStretch(1, 0)
        self.monitor_summary_layout.setStretch(2, 0)
        self.monitor_summary_layout.setStretch(3, 0)

        self.monitor_detail = QWidget()
        self.monitor_detail.setFixedWidth(270)
        self.monitor_detail_layout = QFormLayout(self.monitor_detail)
        self.monitor_detail_layout.setContentsMargins(0, 0, 0, 0)
        self.monitor_detail_layout.setHorizontalSpacing(8)
        self.monitor_detail_layout.setVerticalSpacing(1)
        self.monitor_instance_label = QLabel("0")
        self.monitor_guid_label = QLabel("-")
        self.monitor_guid_label.setWordWrap(False)
        self.monitor_axes_count = QLabel("0")
        self.monitor_buttons_count = QLabel("0")
        self.monitor_hats_count = QLabel("0")
        self.monitor_trackballs_count = QLabel("0")
        self.monitor_detail_layout.addRow("Instance Id:", self.monitor_instance_label)
        self.monitor_detail_layout.addRow("Guid:", self.monitor_guid_label)
        self.monitor_detail_layout.addRow("Axes:", self.monitor_axes_count)
        self.monitor_detail_layout.addRow("Buttons:", self.monitor_buttons_count)
        self.monitor_detail_layout.addRow("Hats:", self.monitor_hats_count)
        self.monitor_detail_layout.addRow("Trackballs:", self.monitor_trackballs_count)
        self.monitor_summary_layout.addWidget(self.monitor_detail)

        self.monitor_axis_labels = {}
        self.monitor_axis_panel = QWidget()
        self.monitor_axis_panel.setFixedWidth(170)
        self.monitor_axis_layout = QVBoxLayout(self.monitor_axis_panel)
        self.monitor_axis_layout.setContentsMargins(0, 0, 0, 0)
        self.monitor_axis_layout.setSpacing(1)
        self.monitor_axis_layout.addWidget(QLabel("AXES"))
        for index in range(1, 7):
            label = QLabel(f"Axis {index}: 0.000")
            label.setFixedWidth(150)
            label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            self.monitor_axis_labels[f"axis_{index}"] = label
            self.monitor_axis_layout.addWidget(label)

        self.monitor_axis_panel.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Maximum)
        self.monitor_summary_layout.addWidget(self.monitor_axis_panel, 0, Qt.AlignTop)

        self.monitor_dpad_labels = {}

        self.monitor_dpad_panel = QWidget()
        self.monitor_dpad_panel.setFixedWidth(170)

        self.monitor_dpad_layout = QFormLayout(self.monitor_dpad_panel)
        self.monitor_dpad_layout.setContentsMargins(0, 0, 0, 0)
        self.monitor_dpad_layout.setHorizontalSpacing(8)
        self.monitor_dpad_layout.setVerticalSpacing(1)

        title = QLabel("DPAD")
        self.monitor_dpad_layout.addRow(title)

        for direction in ("Up", "Down", "Left", "Right"):
            value_label = QLabel("Released")
            self.monitor_dpad_labels[f"dpad_{direction.lower()}"] = value_label
            self.monitor_dpad_layout.addRow(f"{direction}:", value_label)

        self.monitor_dpad_panel.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Maximum)
        self.monitor_summary_layout.addWidget(self.monitor_dpad_panel, 0, Qt.AlignTop)

        self.monitor_button_labels = {}
        self.monitor_button_panel = QWidget()
        self.monitor_button_panel.setFixedWidth(200)
        self.monitor_button_layout = QGridLayout(self.monitor_button_panel)
        self.monitor_button_layout.setContentsMargins(0, 0, 8, 0)
        self.monitor_button_layout.setHorizontalSpacing(6)
        self.monitor_button_layout.setVerticalSpacing(1)
        self.monitor_button_layout.addWidget(QLabel("BUTTONS"), 0, 0, 1, 2)
        for index in range(1, 17):
            label = QLabel(f"{index}: Released")
            label.setMinimumWidth(80)
            self.monitor_button_labels[f"button_{index}"] = label
            column = 0 if index <= 8 else 1
            row = index if index <= 8 else index - 8
            self.monitor_button_layout.addWidget(label, row + 1, column)
        self.monitor_summary_layout.addWidget(self.monitor_button_panel)
        self.monitor_summary_layout.addStretch(1)

        self.monitor_layout.addWidget(self.monitor_summary)
        self.monitor_widget.setStyleSheet(
            "QWidget { color: #e5e7eb; } "
            "QLabel { qproperty-alignment: AlignLeft; margin: 0px; padding: 0px; }"
        )
        self.monitor_widget.setContentsMargins(0, 0, 0, 10)

        main_layout.setSpacing(8)
        main_layout.addLayout(form_layout)
        main_layout.addLayout(button_row)
        main_layout.addWidget(self.monitor_widget)
        self.console.setContentsMargins(0, 8, 0, 0)
        main_layout.addWidget(self.console)
        main_layout.addLayout(console_button_row)

        self.connection_button.clicked.connect(self.on_toggle_connection)
        self.mapping_button.clicked.connect(self.on_edit_mapping)
        self.close_button.clicked.connect(self.on_close)
        self.controller_combo.currentIndexChanged.connect(self._on_controller_changed)

        self.refresh_controllers()
        self.restore_saved_controller()
        self._monitor_preview_timer = None
        self._start_monitor_preview_timer()
        self.update_monitor_snapshot(build_gamepad_monitor_snapshot(
            device_name=self.controller_combo.currentText() if self.controller_combo.count() else "",
            guid="",
            axes={},
            buttons={},
            dpad={},
            axis_count=6,
            button_count=16,
            hat_count=1,
        ))
        self.log("Ready")

    def log(self, message: str):
        self.console.append(timestamp_log_message(message))
        self.console.verticalScrollBar().setValue(self.console.verticalScrollBar().maximum())

    def clear_console_log(self):
        self.console.clear()

    def _apply_focus_step_value(self, value: int):
        clamped = _clamp_focus_step(value, default=100)
        self.gui_settings["focus_step"] = clamped
        self.focus_step_spin.setValue(clamped)
        if self.worker is not None:
            self.worker._focus_step = clamped

    def _on_focus_step_changed(self, value: int):
        self.gui_settings["focus_step"] = _clamp_focus_step(value, default=100)
        if self.worker is not None:
            self.worker._focus_step = self.gui_settings["focus_step"]

    def save_settings(self):
        controller_name = self.controller_combo.currentText() if self.controller_combo.count() else ""
        controller_guid = ""
        if controller_name and controller_name not in {"No controller found", "Controller unavailable"}:
            try:
                import pygame as gui_pygame
                if not gui_pygame.get_init():
                    gui_pygame.init()
                if not gui_pygame.joystick.get_init():
                    gui_pygame.joystick.init()
                for index in range(gui_pygame.joystick.get_count()):
                    joy = gui_pygame.joystick.Joystick(index)
                    joy.init()
                    if get_device_name(joy) == controller_name:
                        controller_guid = get_device_guid(joy)
                        break
            except Exception:
                controller_guid = ""

        settings = {
            "controller": controller_name,
            "controller_guid": controller_guid,
            "host": self.host_edit.text().strip() or "localhost",
            "port": int(self.port_edit.text().strip() or 50007),
            "heartbeat": self.heartbeat_checkbox.isChecked(),
            "focus_step": self.focus_step_spin.value(),
            "deadzone": self.gui_settings.get("deadzone", DEADZONE),
            "action_mapping": self.gui_settings.get("action_mapping", DEFAULT_ACTION_MAPPING.copy()),
            "window_geometry": {
                "x": self.x(),
                "y": self.y(),
                "width": self.width(),
                "height": self.height(),
            },
        }
        if settings["controller"] in {"No controller found", "Controller unavailable"}:
            settings["controller"] = ""
        self.gui_settings = settings
        save_gui_settings(settings)

    def restore_saved_controller(self):
        saved_controller = self.gui_settings.get("controller", "")
        if not saved_controller:
            return
        for index in range(self.controller_combo.count()):
            if self.controller_combo.itemText(index) == saved_controller:
                self.controller_combo.setCurrentIndex(index)
                return

    def _on_controller_changed(self, _index: int):
        if self.worker is None:
            self._start_monitor_preview_timer()
            return

        device_name = self.controller_combo.currentText()
        if device_name in {"No controller found", "Controller unavailable"}:
            self.log("[gui] controller change ignored: no controller is available")
            return

        previous_worker = self.worker
        previous_worker.stop()
        self.worker = None
        self.log(f"[gui] switching controller to {device_name}")
        self.on_connect()

    def _start_monitor_preview_timer(self):
        if not hasattr(self, "_monitor_preview_timer") or self._monitor_preview_timer is None:
            from PySide6.QtCore import QTimer
            self._monitor_preview_timer = QTimer(self)
            self._monitor_preview_timer.setInterval(100)
            self._monitor_preview_timer.timeout.connect(self._refresh_monitor_preview)
        if self.worker is not None:
            self._monitor_preview_timer.stop()
            return
        if self.controller_combo.count() == 0:
            return
        self._monitor_preview_timer.start()

    def _refresh_monitor_preview(self):
        if self.worker is not None:
            return
        try:
            import pygame as gui_pygame
            if not gui_pygame.get_init():
                gui_pygame.init()
            if not gui_pygame.joystick.get_init():
                gui_pygame.joystick.init()
            selected_index = self.controller_combo.currentIndex()
            if selected_index < 0 or selected_index >= gui_pygame.joystick.get_count():
                return
            selected_joy = gui_pygame.joystick.Joystick(selected_index)
            selected_joy.init()
            axes, buttons, dpad = read_gamepad_state(selected_joy)
            axes = normalize_axes(axes, self.gui_settings.get("deadzone", DEADZONE))
            buttons = {k: bool(v) for k, v in buttons.items()}
            dpad = {k: bool(v) for k, v in dpad.items()}
            self.update_monitor_snapshot(build_gamepad_monitor_snapshot(
                device_name=get_gamepad_name(selected_joy),
                guid=get_device_guid(selected_joy),
                axes=axes,
                buttons=buttons,
                dpad=dpad,
                axis_count=int(getattr(selected_joy, "get_numaxes", lambda: 0)()),
                button_count=int(getattr(selected_joy, "get_numbuttons", lambda: 0)()),
                hat_count=int(getattr(selected_joy, "get_numhats", lambda: 0)()),
                instance_id=getattr(selected_joy, "get_instance_id", lambda: "")(),
            ))
        except Exception:
            return

    def update_monitor_snapshot(self, snapshot: dict):
        if not isinstance(snapshot, dict):
            return

        device_name = str(snapshot.get("device_name") or self.controller_combo.currentText() or "Unknown gamepad")
        guid = str(snapshot.get("device_guid") or "")
        if not guid and self.controller_combo.count():
            try:
                import pygame as gui_pygame
                if not gui_pygame.get_init():
                    gui_pygame.init()
                if not gui_pygame.joystick.get_init():
                    gui_pygame.joystick.init()
                for index in range(gui_pygame.joystick.get_count()):
                    joy = gui_pygame.joystick.Joystick(index)
                    joy.init()
                    if get_device_name(joy) == device_name:
                        guid = get_device_guid(joy)
                        break
            except Exception:
                guid = ""
        self.monitor_instance_label.setText(str(snapshot.get("instance_id") or "0"))
        self.monitor_guid_label.setText(guid or "-")
        self.monitor_axes_count.setText(str(snapshot.get("axis_count") or 0))
        self.monitor_buttons_count.setText(str(snapshot.get("button_count") or 0))
        self.monitor_hats_count.setText(str(snapshot.get("hat_count") or 0))
        self.monitor_trackballs_count.setText(str(snapshot.get("trackballs") or 0))

        axis_count = max(int(snapshot.get("axis_count") or 0), 0)
        axis_values = snapshot.get("axes", {})
        for axis_index in range(1, 7):
            axis_key = f"axis_{axis_index}"
            label = self.monitor_axis_labels.get(axis_key)
            if label is None:
                continue
            if axis_index <= axis_count:
                value = float(axis_values.get(axis_key, 0.0))
                label.setText(f"Axis {axis_index}: {value:.3f}")
            else:
                label.setText("")

        dpad_values = snapshot.get("dpad", {})
        for key, label in self.monitor_dpad_labels.items():
            pressed = bool(dpad_values.get(key, False))
            label.setText("Pressed" if pressed else "Released")

        button_count = max(int(snapshot.get("button_count") or 0), 0)
        button_values = snapshot.get("buttons", {})
        for index in range(1, 17):
            button_key = f"button_{index}"
            label = self.monitor_button_labels.get(button_key)
            if label is None:
                continue
            if index <= button_count:
                pressed = bool(button_values.get(button_key, False))
                label.setText(f"{index}: {'Pressed' if pressed else 'Released'}")
            else:
                label.setText("")

    def handle_log_message(self, message: str):
        if "heartbeat" in message.lower() and not self.heartbeat_checkbox.isChecked():
            return
        self.log(message)

    def set_connection_button_state(self, connected: bool):
        self.connection_button.setText("Disconnect" if connected else "Connect")
        self.connection_button.setStyleSheet("QPushButton { font-weight: bold; }" if connected else "")

    def _handle_connection_update(self, text: str, worker=None):
        normalized = str(text or "").strip()
        if not normalized:
            return
        if worker is not None and worker is not self.worker:
            return

        if normalized.lower().startswith("connected") or normalized.lower().startswith("ready"):
            self.set_connection_button_state(True)
            return

        if normalized.lower().startswith("error:") or normalized.lower() == "disconnected":
            self.set_connection_button_state(False)
            if worker is None or worker is self.worker:
                self.worker = None
            return

        if "disconnected" in normalized.lower():
            self.set_connection_button_state(False)
            if worker is None or worker is self.worker:
                self.worker = None
            return

        self.set_connection_button_state(False)

    def on_toggle_connection(self):
        if self.worker is None:
            self.on_connect()
        else:
            self.on_disconnect()

    def on_edit_mapping(self):
        if self.mapping_editor is not None:
            self.mapping_editor.raise_()
            self.mapping_editor.activateWindow()
            return

        editor = MappingEditorWindow(
            self,
            mapping=self.gui_settings.get("action_mapping", DEFAULT_ACTION_MAPPING.copy()),
            selected_device=self.controller_combo.currentText(),
        )
        editor.mapping_applied.connect(self._apply_mapping)
        editor.closed.connect(self._on_mapping_editor_closed)
        self.mapping_editor = editor
        self.mapping_button.setEnabled(False)
        editor.show()
        editor.raise_()

    def _on_mapping_editor_closed(self):
        self.mapping_editor = None
        self.mapping_button.setEnabled(True)

    def _apply_mapping(self, mapping: dict):
        combo = getattr(self, "controller_combo", None)
        selected_device = combo.currentText() if combo is not None else self.gui_settings.get("controller", "")
        selected_guid = str(self.gui_settings.get("controller_guid", "") or "")
        if selected_device and selected_device not in {"No controller found", "Controller unavailable"}:
            try:
                import pygame as gui_pygame
                if not gui_pygame.get_init():
                    gui_pygame.init()
                if not gui_pygame.joystick.get_init():
                    gui_pygame.joystick.init()
                for index in range(gui_pygame.joystick.get_count()):
                    joy = gui_pygame.joystick.Joystick(index)
                    joy.init()
                    if get_device_name(joy) == selected_device:
                        selected_guid = get_device_guid(joy)
                        break
            except Exception:
                pass

        current_mapping = self.gui_settings.get("action_mapping", {"controllers": []})
        if not isinstance(current_mapping, dict):
            current_mapping = {"controllers": []}

        next_payload = {"controllers": []}

        selected_entry = {
            "name": selected_device or "",
            "guid": selected_guid,
            "mapping": _resolve_flat_action_mapping(mapping),
        }

        found = False
        for entry in current_mapping.get("controllers", []):
            if not isinstance(entry, dict):
                continue
            name_match = str(entry.get("name", "")).strip() == str(selected_device or "").strip()
            guid_match = str(entry.get("guid", "")).strip() == str(selected_guid or "").strip()
            if name_match and guid_match:
                next_payload["controllers"].append(selected_entry)
                found = True
            else:
                next_payload["controllers"].append(entry)

        if not found and (selected_device or selected_guid):
            next_payload["controllers"].append(selected_entry)

        self.gui_settings["action_mapping"] = _normalize_action_mapping_store(
            next_payload,
            controller_name=selected_device,
            controller_guid=selected_guid,
        )
        self.save_settings()

    def refresh_controllers(self):
        try:
            import pygame as gui_pygame
            gui_pygame.init()
            gui_pygame.joystick.init()
            names = [gui_pygame.joystick.Joystick(idx).get_name() for idx in range(gui_pygame.joystick.get_count())]
            self.controller_combo.clear()
            if names:
                self.controller_combo.addItems(names)
            else:
                self.controller_combo.addItem("No controller found")
        except Exception as exc:  # pragma: no cover - runtime behavior
            self.controller_combo.clear()
            self.controller_combo.addItem("Controller unavailable")
            self.log(f"[gui] controller scan failed: {exc}")

    def on_connect(self):
        if self.worker is not None:
            self.log("[gui] already connected")
            return
        if hasattr(self, "_monitor_preview_timer"):
            self._monitor_preview_timer.stop()

        device_name = self.controller_combo.currentText()
        if device_name in {"No controller found", "Controller unavailable"}:
            device_name = None

        host = self.host_edit.text().strip() or "localhost"
        port_text = self.port_edit.text().strip() or "50007"
        try:
            port = int(port_text)
        except ValueError:
            QMessageBox.critical(self, "Invalid port", "Port must be an integer.")
            return

        controller_guid = ""
        if device_name:
            try:
                import pygame as gui_pygame
                if not gui_pygame.get_init():
                    gui_pygame.init()
                if not gui_pygame.joystick.get_init():
                    gui_pygame.joystick.init()
                for index in range(gui_pygame.joystick.get_count()):
                    joy = gui_pygame.joystick.Joystick(index)
                    joy.init()
                    if get_device_name(joy) == device_name:
                        controller_guid = get_device_guid(joy)
                        break
            except Exception:
                controller_guid = ""

        self.gui_settings = {
            "controller": device_name or "",
            "controller_guid": controller_guid,
            "host": host,
            "port": port,
            "heartbeat": self.heartbeat_checkbox.isChecked(),
            "focus_step": self.focus_step_spin.value(),
            "deadzone": self.gui_settings.get("deadzone", DEADZONE),
            "action_mapping": self.gui_settings.get("action_mapping", {"controllers": []}),
        }
        self.gui_settings["action_mapping"] = _normalize_action_mapping_store(
            self.gui_settings.get("action_mapping", DEFAULT_ACTION_MAPPING.copy()),
            controller_name=device_name or "",
            controller_guid=controller_guid,
        )
        save_gui_settings(self.gui_settings)

        self.log(f"[gui] connecting to {host}:{port} using {device_name or 'auto'}")
        self.worker = SenderWorker(
            host=host,
            port=port,
            device_name=device_name,
            controller_guid=controller_guid,
            action_map=self.gui_settings.get("action_mapping"),
            focus_step=self.focus_step_spin.value(),
            deadzone=self.gui_settings.get("deadzone", DEADZONE),
            focus_step_changed_callback=self._apply_focus_step_value,
        )
        self.worker.status_changed.connect(lambda text: self.log(f"[gui] status: {text}"))
        self.worker.log_received.connect(self.handle_log_message)
        self.worker.connection_changed.connect(
            lambda text, worker=self.worker: self._handle_connection_update(text, worker)
        )
        self.worker.connection_changed.connect(lambda text: self.log(f"[gui] {text}"))
        self.worker.monitor_updated.connect(self.update_monitor_snapshot)

        self.worker_thread = threading.Thread(target=self.worker.run, daemon=True)
        self.worker_thread.start()
        self.set_connection_button_state(True)

    def on_disconnect(self):
        if self.worker is None:
            self.log("[gui] not connected")
            return
        self.worker.stop()
        self.worker = None
        self.save_settings()
        self.set_connection_button_state(False)
        if hasattr(self, "_monitor_preview_timer"):
            self._monitor_preview_timer.start()
        self.log("[gui] disconnected")

    def on_close(self):
        self.save_settings()
        self.close()

    def closeEvent(self, event):
        self.save_settings()
        super().closeEvent(event)


class MappingEditorWindow(QMainWindow):
    mapping_applied = Signal(dict)
    closed = Signal()

    def __init__(self, parent=None, mapping: dict | None = None, selected_device: str | None = None):
        super().__init__(parent)
        self.setWindowTitle("INDIPAD Mapping Editor")
        self.resize(760, 540)
        self.selected_device = selected_device
        self._joy = None
        self._input_status_timer = None
        self._input_default_palettes = {}
        self._deadzone = _clamp_deadzone(
            getattr(parent, "gui_settings", {}).get("deadzone", DEADZONE)
            if parent is not None else DEADZONE
        )
        config = load_axis_config()
        self.mapping = get_default_action_mapping(selected_device, config)
        parent_settings = getattr(parent, "gui_settings", {}) if parent is not None else {}
        parent_guid = str(parent_settings.get("controller_guid", "") or "")
        if isinstance(mapping, dict):
            resolved = resolve_action_mapping(mapping, device_name=selected_device, device_guid=parent_guid)
            self.mapping = resolved
        elif isinstance(parent_settings.get("action_mapping", None), dict):
            self.mapping = resolve_action_mapping(
                parent_settings.get("action_mapping"),
                device_name=selected_device,
                device_guid=parent_guid,
            )

        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        top_row = QHBoxLayout()
        self.device_label = QLabel(f"Selected gamepad: {selected_device or 'auto'}")
        top_row.addWidget(self.device_label)
        top_row.addStretch()
        self.reset_button = QPushButton("Reset to default")
        self.reset_button.clicked.connect(self.reset_to_default)
        top_row.addWidget(self.reset_button)
        layout.addLayout(top_row)

        self.reconnect_note = QLabel("The changes will take effect after reconnect to the host.")
        self.reconnect_note.setWordWrap(True)
        self.reconnect_note.setStyleSheet("color: #f0f0f0;")
        layout.addWidget(self.reconnect_note)

        self.form = QWidget()
        self.form_layout = QFormLayout(self.form)
        self.input_rows = {}

        for label, key in get_gamepad_input_rows(self.selected_device):
            if key.startswith("axis_"):
                axis_row = QWidget()
                axis_layout = QHBoxLayout(axis_row)
                axis_layout.setContentsMargins(0, 0, 0, 0)
                axis_layout.setSpacing(8)
                axis_states = {}
                axis_mapping = self.mapping.get(key, {}) if isinstance(self.mapping.get(key, {}), dict) else {}
                for state_name, state_value in zip(AXIS_STATES, (-1, 0, 1)):
                    box = QComboBox()
                    box.addItems(["Unassigned"] + AVAILABLE_ACTIONS[1:])
                    current_value = str(axis_mapping.get(state_name, "") or "")
                    match_index = 0
                    for index in range(box.count()):
                        if box.itemText(index) == current_value:
                            match_index = index
                            break
                    box.setCurrentIndex(match_index)
                    axis_states[state_name] = box
                    axis_layout.addWidget(QLabel(str(state_value)))
                    axis_layout.addWidget(box)
                self.input_rows[key] = axis_states
                self.form_layout.addRow(label, axis_row)
                continue

            box = QComboBox()
            box.addItems(["Unassigned"] + AVAILABLE_ACTIONS[1:])
            current_value = self.mapping.get(key, "")
            match_index = 0
            for index in range(box.count()):
                if box.itemText(index) == current_value:
                    match_index = index
                    break
            box.setCurrentIndex(match_index)
            self.input_rows[key] = box
            self.form_layout.addRow(label, box)

        scroll = QWidget()
        scroll_layout = QVBoxLayout(scroll)
        scroll_layout.addWidget(self.form)
        scroll_layout.addStretch()

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.addWidget(scroll)
        layout.addWidget(container)

        button_row = QHBoxLayout()
        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self.apply_mapping)
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.close)
        button_row.addStretch()
        button_row.addWidget(self.save_button)
        button_row.addWidget(self.close_button)
        layout.addLayout(button_row)

        if QTimer is not None:
            self._input_status_timer = QTimer(self)
            self._input_status_timer.setInterval(100)
            self._input_status_timer.timeout.connect(self._refresh_input_status)
            self._input_status_timer.start()

    def _set_input_pressed(self, combo, pressed: bool):
        if combo not in self._input_default_palettes:
            self._input_default_palettes[combo] = combo.palette()

        if not pressed:
            combo.setPalette(self._input_default_palettes[combo])
            return

        palette = combo.palette()
        palette.setColor(QPalette.ColorRole.Base, QColor("#313141"))
        palette.setColor(QPalette.ColorRole.Button, QColor("#313141"))
        combo.setPalette(palette)

    def _find_selected_joystick(self):
        try:
            import pygame as gui_pygame
            if not gui_pygame.get_init():
                gui_pygame.init()
            if not gui_pygame.joystick.get_init():
                gui_pygame.joystick.init()

            selected_name = str(self.selected_device or "").strip().lower()
            for index in range(gui_pygame.joystick.get_count()):
                joy = gui_pygame.joystick.Joystick(index)
                joy.init()
                if not selected_name or get_gamepad_name(joy).lower() == selected_name:
                    return joy
        except Exception:
            return None
        return None

    def _refresh_input_status(self):
        try:
            joy = self._find_selected_joystick()
            if joy is None:
                raise RuntimeError("gamepad unavailable")
            axes, buttons, dpad = read_gamepad_state(joy)

            for key, combo in self.input_rows.items():
                if key.startswith("axis_") and isinstance(combo, dict):
                    axis_state = normalize_axis_value(axes.get(key, 0.0), self._deadzone)
                    state_name = AXIS_STATE_NAMES[axis_state]
                    for name, state_combo in combo.items():
                        self._set_input_pressed(state_combo, name == state_name)
                elif key.startswith("button_"):
                    self._set_input_pressed(combo, bool(buttons.get(key, False)))
                elif key.startswith("dpad_"):
                    self._set_input_pressed(combo, bool(dpad.get(key, False)))
        except Exception:
            for combo in self.input_rows.values():
                if isinstance(combo, dict):
                    for state_combo in combo.values():
                        self._set_input_pressed(state_combo, False)
                else:
                    self._set_input_pressed(combo, False)

    def reset_to_default(self):
        self.mapping = get_default_action_mapping(self.selected_device, load_axis_config())
        for key, combo in self.input_rows.items():
            if key.startswith("axis_") and isinstance(combo, dict):
                current_map = self.mapping.get(key, {}) if isinstance(self.mapping.get(key, {}), dict) else {}
                for state_name, state_combo in combo.items():
                    value = current_map.get(state_name, "")
                    if value and value in [item for item in AVAILABLE_ACTIONS if item]:
                        state_combo.setCurrentText(value)
                    else:
                        state_combo.setCurrentIndex(0)
                continue

            value = self.mapping.get(key, "")
            if value and value in [item for item in AVAILABLE_ACTIONS if item]:
                combo.setCurrentText(value)
            else:
                combo.setCurrentIndex(0)

    def apply_mapping(self):
        next_mapping = {}
        for key, combo in self.input_rows.items():
            if key.startswith("axis_") and isinstance(combo, dict):
                next_mapping[key] = {}
                for state_name, state_combo in combo.items():
                    value = state_combo.currentText().strip()
                    if value == "Unassigned":
                        next_mapping[key][state_name] = ""
                    elif value:
                        next_mapping[key][state_name] = value
                continue
            value = combo.currentText().strip()
            if value == "Unassigned":
                next_mapping[key] = ""
                continue
            if value:
                next_mapping[key] = value
        self.mapping = resolve_action_mapping(next_mapping)
        self.mapping_applied.emit(self.mapping)

    def closeEvent(self, event):
        if self._input_status_timer is not None:
            self._input_status_timer.stop()
        self.closed.emit()
        super().closeEvent(event)


def run_gui():
    if QObject is None or QApplication is None:
        raise RuntimeError("PySide6 is required to run the GUI sender. Install it with: pip install pyside6")
    app = QApplication([])
    window = IndipadWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    try:
        args = sys.argv[1:]
        if "--gui" in args or "-g" in args or not args:
            raise SystemExit(run_gui())

        host = HOST
        port = PORT
        demo = False
        forced_device = None

        index = 0
        while index < len(args):
            arg = args[index]
            if arg in ("--demo", "-d"):
                demo = True
            elif arg in ("--host", "-H"):
                if index + 1 < len(args):
                    host = args[index + 1]
                    index += 1
            elif arg in ("--port", "-p"):
                if index + 1 < len(args):
                    port = int(args[index + 1])
                    index += 1
            elif arg in ("--device", "-D"):
                if index + 1 < len(args):
                    forced_device = args[index + 1]
                    index += 1
            elif not arg.startswith("-"):
                if host == HOST:
                    host = arg
                else:
                    port = int(arg)
            index += 1

        send_loop(host=host, port=port, demo=demo, forced_device=forced_device)
    except KeyboardInterrupt:
        print("[sender] stopped")
    except Exception as exc:
        print(f"[sender] error: {exc}")
        raise
