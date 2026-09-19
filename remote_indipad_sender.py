import json
import os
import socket
import sys
import threading
import time
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
    from PySide6.QtCore import QObject, Signal
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QSpinBox, QTextEdit, QVBoxLayout, QWidget
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

    Signal = _FallbackSignal
    QFont = QCheckBox = QComboBox = QFormLayout = QHBoxLayout = QLabel = QLineEdit = QMainWindow = QMessageBox = QPushButton = QSpinBox = QTextEdit = QVBoxLayout = QWidget = object
    QApplication = None

import remote_indipad_protocol as protocol


HOST = "127.0.0.1"
PORT = 50007
DEADZONE = 0.08
_MODULE_DIR = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd()
GUI_SETTINGS_PATH = _MODULE_DIR / "remote_indipad_sender.json"
DEFAULT_AXIS_CONFIG = {
    "left_x": 0,
    "left_y": 1,
    "right_x": 2,
    "right_y": 4,
}
DEFAULT_ACTION_MAPPING = {
    "dpad_up": "MOUNT_SOUTH",
    "dpad_down": "MOUNT_NORTH",
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
    "left_x": "SKYMAP_MOVE",
    "left_y": "SKYMAP_MOVE",
    "right_x": "SKYMAP_ROTATE",
    "right_y": "SKYMAP_ZOOM",
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
    "SKYMAP_ZOOM",
    "SKYMAP_ROTATE",
]

_DEBUG_JSON_CURSOR_SAVED = False
_DEBUG_JSON_LAST_LINES = 0


def get_device_guid(joy) -> str:
    if joy is None:
        return ""
    guid = getattr(joy, "get_guid", lambda: "")()
    return str(guid or "")


def _resolve_flat_action_mapping(mapping: dict | None):
    resolved = DEFAULT_ACTION_MAPPING.copy()
    if not isinstance(mapping, dict):
        return resolved

    for key, value in mapping.items():
        if not isinstance(key, str):
            continue
        if not (key.startswith("dpad_") or key.startswith("button_") or key.startswith("left_") or key.startswith("right_")):
            continue
        if not isinstance(value, str):
            continue
        normalized = value.strip()
        if normalized:
            resolved[key] = normalized

    for key, value in DEFAULT_ACTION_MAPPING.items():
        if key not in resolved:
            resolved[key] = value

    return resolved


def _normalize_action_mapping_store(raw_mapping, controller_name: str | None = None, controller_guid: str | None = None):
    normalized_name = str(controller_name or "").strip()
    normalized_guid = str(controller_guid or "").strip()

    if isinstance(raw_mapping, dict) and ("controllers" in raw_mapping or "entries" in raw_mapping):
        container = raw_mapping.get("controllers", raw_mapping.get("entries", []))
        entries = []
        if isinstance(container, list):
            for entry in container:
                if not isinstance(entry, dict):
                    continue
                entry_name = str(entry.get("name", "")).strip()
                entry_guid = str(entry.get("guid", "")).strip()
                mapping_value = entry.get("mapping") if isinstance(entry.get("mapping"), dict) else entry
                entries.append({
                    "name": entry_name,
                    "guid": entry_guid,
                    "mapping": _resolve_flat_action_mapping(mapping_value),
                })

        current_mapping = _resolve_flat_action_mapping(raw_mapping.get("default") if isinstance(raw_mapping.get("default"), dict) else DEFAULT_ACTION_MAPPING.copy())
        if normalized_name or normalized_guid:
            entries = [entry for entry in entries if not (str(entry.get("name", "")).strip() == normalized_name and str(entry.get("guid", "")).strip() == normalized_guid)]
            entries.append({
                "name": normalized_name,
                "guid": normalized_guid,
                "mapping": current_mapping,
            })
        default_mapping = raw_mapping.get("default") if isinstance(raw_mapping.get("default"), dict) else DEFAULT_ACTION_MAPPING.copy()
        return {
            "default": _resolve_flat_action_mapping(default_mapping),
            "controllers": entries,
        }

    if isinstance(raw_mapping, dict) and isinstance(raw_mapping.get("mapping"), dict) and "name" in raw_mapping and "guid" in raw_mapping:
        current_mapping = _resolve_flat_action_mapping(raw_mapping.get("mapping"))
        return {
            "default": _resolve_flat_action_mapping(raw_mapping.get("default") if isinstance(raw_mapping.get("default"), dict) else current_mapping),
            "controllers": [{
                "name": str(raw_mapping.get("name", "")).strip(),
                "guid": str(raw_mapping.get("guid", "")).strip(),
                "mapping": current_mapping,
            }],
        }

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
            default_mapping = candidate.get("default")
            if isinstance(default_mapping, dict):
                return _resolve_flat_action_mapping(default_mapping)
            return resolved

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
        ("Button 1", "button_1"),
        ("Button 2", "button_2"),
        ("Button 3", "button_3"),
        ("Button 4", "button_4"),
        ("Button 5", "button_5"),
        ("Button 6", "button_6"),
        ("Button 7", "button_7"),
        ("Button 8", "button_8"),
        ("Button 9", "button_9"),
        ("Button 10", "button_10"),
        ("Button 11", "button_11"),
        ("Button 12", "button_12"),
        ("Left Stick X", "left_x"),
        ("Left Stick Y", "left_y"),
        ("Right Stick X", "right_x"),
        ("Right Stick Y", "right_y"),
    ]

    if selected_device is None:
        return rows

    lowered = selected_device.lower()
    if "jc-u3712t" in lowered or "elecom" in lowered:
        return rows

    return [row for row in rows if row[1] not in {"button_11", "button_12"}]


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


def load_gui_settings(path: str | Path | None = None):
    config_path = Path(path) if path is not None else GUI_SETTINGS_PATH
    defaults = {
        "controller": "",
        "controller_guid": "",
        "host": "localhost",
        "port": 50007,
        "heartbeat": False,
        "focus_step": 100,
        "action_mapping": {"default": DEFAULT_ACTION_MAPPING.copy(), "controllers": []},
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

    try:
        port_value = int(port)
    except (TypeError, ValueError):
        port_value = 50007

    raw_mapping = loaded.get("action_mapping", DEFAULT_ACTION_MAPPING.copy())
    normalized_mapping = _normalize_action_mapping_store(raw_mapping, controller_name=str(controller or ""), controller_guid=str(controller_guid or ""))

    return {
        "controller": str(controller) if controller is not None else "",
        "controller_guid": str(controller_guid) if controller_guid is not None else "",
        "host": str(host) if host is not None else "localhost",
        "port": port_value,
        "heartbeat": bool(heartbeat),
        "focus_step": focus_step,
        "action_mapping": normalized_mapping,
    }


def save_gui_settings(settings: dict, path: str | Path | None = None):
    config_path = Path(path) if path is not None else GUI_SETTINGS_PATH
    controller_name = str(settings.get("controller", "") or "")
    controller_guid = str(settings.get("controller_guid", "") or "")
    raw_mapping = settings.get("action_mapping", DEFAULT_ACTION_MAPPING.copy())
    payload = {
        "controller": controller_name,
        "controller_guid": controller_guid,
        "host": str(settings.get("host", "localhost") or "localhost"),
        "port": int(settings.get("port", 50007) or 50007),
        "heartbeat": bool(settings.get("heartbeat", False)),
        "focus_step": _clamp_focus_step(settings.get("focus_step", 100), default=100),
        "action_mapping": _normalize_action_mapping_store(raw_mapping, controller_name=controller_name, controller_guid=controller_guid),
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
        config["profiles"]["default"] = {"stick_axes": DEFAULT_AXIS_CONFIG.copy()}
        return config

    try:
        with open(config_path, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
    except (OSError, ValueError):
        config["profiles"]["default"] = {"stick_axes": DEFAULT_AXIS_CONFIG.copy()}
        return config

    if not isinstance(loaded, dict):
        config["profiles"]["default"] = {"stick_axes": DEFAULT_AXIS_CONFIG.copy()}
        return config

    config["default_device"] = str(loaded.get("default_device", ""))

    profiles = loaded.get("profiles")
    if isinstance(profiles, dict):
        for profile_name, profile_data in profiles.items():
            if not isinstance(profile_data, dict):
                continue
            stick_axes = profile_data.get("stick_axes")
            if not isinstance(stick_axes, dict):
                continue
            axis_map = DEFAULT_AXIS_CONFIG.copy()
            for key in axis_map:
                value = stick_axes.get(key)
                if isinstance(value, int):
                    axis_map[key] = value
            config["profiles"][str(profile_name)] = {"stick_axes": axis_map}

    legacy_axes = loaded.get("stick_axes")
    if isinstance(legacy_axes, dict):
        axis_map = DEFAULT_AXIS_CONFIG.copy()
        for key in axis_map:
            value = legacy_axes.get(key)
            if isinstance(value, int):
                axis_map[key] = value
        default_name = config["default_device"] or "default"
        config["profiles"][default_name] = {"stick_axes": axis_map}

    if not config["profiles"]:
        config["profiles"]["default"] = {"stick_axes": DEFAULT_AXIS_CONFIG.copy()}

    return config


def get_device_name(joy) -> str:
    name = getattr(joy, "get_name", lambda: "")()
    return str(name or "Unknown gamepad")


def select_device_profile(joy, config=None, forced_device: str | None = None):
    loaded = load_axis_config() if config is None else config
    profile_map = loaded.get("profiles", {}) if isinstance(loaded, dict) else {}
    if not isinstance(profile_map, dict):
        profile_map = {}

    device_name = (str(forced_device).strip() if forced_device else get_device_name(joy)).strip()

    if device_name:
        if device_name in profile_map:
            return profile_map[device_name]
        lower_name = device_name.lower()
        for profile_name, profile_data in profile_map.items():
            if str(profile_name).lower() == lower_name:
                return profile_data

    default_device = str(loaded.get("default_device", "")).strip()
    if default_device and default_device in profile_map:
        return profile_map[default_device]
    if default_device:
        for profile_name, profile_data in profile_map.items():
            if str(profile_name).lower() == default_device.lower():
                return profile_data

    if "default" in profile_map:
        return profile_map["default"]

    if profile_map:
        return next(iter(profile_map.values()))

    return {"stick_axes": DEFAULT_AXIS_CONFIG.copy()}


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


enable_windows_vt100()


def clear_console() -> None:
    if os.name == "nt":
        print("\x1b[2J\x1b[H", end="", flush=True)
        try:
            os.system("cls")
        except Exception:
            pass
    else:
        print("\033[2J\033[H", end="", flush=True)


clear_console()


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
    lines = [f"{label}:"] + rendered.splitlines()
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


def apply_deadzone(value: float) -> float:
    if abs(value) < DEADZONE:
        return 0.0
    return value


def normalize_axes(raw_axes):
    normalized = {}
    for key, value in raw_axes.items():
        normalized[key] = apply_deadzone(float(value))
    return normalized


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
    previous_dpad: dict | None = None,
    previous_buttons: dict | None = None,
    action_map: dict | None = None,
    focus_step: int | None = None,
    focus_step_state: dict | None = None,
    button_press_times: dict | None = None,
    now: float | None = None,
):
    dpad = {} if dpad is None else dpad
    buttons = {} if buttons is None else buttons
    previous_dpad = {} if previous_dpad is None else previous_dpad
    previous_buttons = {} if previous_buttons is None else previous_buttons
    if button_press_times is None:
        button_press_times = {}
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

    for name in dpad_names:
        current_pressed = bool(dpad.get(name))
        previous_pressed = bool(previous_dpad.get(name))
        if current_pressed != previous_pressed:
            action_name = resolved_map.get(name, DEFAULT_ACTION_MAPPING.get(name, name))
            events.append({"action": action_name, "pressed": current_pressed, "source": "dpad"})

    for key, action in resolved_map.items():
        if not key.startswith("button_"):
            continue
        if key in buttons:
            current_pressed = bool(buttons.get(key))
            previous_pressed = bool(previous_buttons.get(key))
            if current_pressed != previous_pressed:
                if action == "FOCUS_STEP_UP":
                    if current_pressed:
                        advance_step("up")
                    continue
                if action == "FOCUS_STEP_DOWN":
                    if current_pressed:
                        advance_step("down")
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


def resolve_right_stick_axes(joy, axis_config=None):
    config = axis_config if axis_config is not None else DEFAULT_AXIS_CONFIG.copy()
    if isinstance(config, dict) and "stick_axes" in config:
        config = config["stick_axes"]

    x_axis = int(config.get("right_x", DEFAULT_AXIS_CONFIG["right_x"]))
    y_axis = int(config.get("right_y", DEFAULT_AXIS_CONFIG["right_y"]))

    x_value = float(joy.get_axis(x_axis))
    y_value = float(joy.get_axis(y_axis))

    return x_value, y_value


def read_gamepad_state(joy, axis_config=None):
    config = axis_config if axis_config is not None else DEFAULT_AXIS_CONFIG.copy()
    if isinstance(config, dict) and "stick_axes" in config:
        config = config["stick_axes"]

    if pygame is not None and getattr(pygame, "get_init", lambda: False)():
        pygame.event.pump()

    left_x = joy.get_axis(int(config.get("left_x", DEFAULT_AXIS_CONFIG["left_x"])))
    left_y = joy.get_axis(int(config.get("left_y", DEFAULT_AXIS_CONFIG["left_y"])))
    right_x, right_y = resolve_right_stick_axes(joy, config)

    buttons = {}
    for i in range(min(12, joy.get_numbuttons())):
        buttons[f"button_{i + 1}"] = bool(joy.get_button(i))

    dpad = {}
    if hasattr(joy, "get_hat"):
        try:
            hat_x, hat_y = joy.get_hat(0)
        except TypeError:
            try:
                hat_x, hat_y = joy.get_hat()
            except TypeError:
                hat_x, hat_y = (0, 0)
        dpad["dpad_up"] = hat_y == -1
        dpad["dpad_down"] = hat_y == 1
        dpad["dpad_left"] = hat_x == -1
        dpad["dpad_right"] = hat_x == 1

    return {
        "left_x": left_x,
        "left_y": left_y,
        "right_x": right_x,
        "right_y": right_y,
    }, buttons, dpad


def demo_axes_state(step: int):
    phase = step % 16
    values = {
        0: {"left_x": 0.0, "left_y": 0.0, "right_x": 0.0, "right_y": 0.0},
        1: {"left_x": 0.25, "left_y": -0.15, "right_x": 0.0, "right_y": 0.2},
        2: {"left_x": 0.5, "left_y": -0.35, "right_x": 0.1, "right_y": 0.4},
        3: {"left_x": 0.75, "left_y": -0.5, "right_x": 0.25, "right_y": 0.6},
        4: {"left_x": 1.0, "left_y": -0.9, "right_x": 0.35, "right_y": 0.8},
        5: {"left_x": 0.75, "left_y": -0.5, "right_x": 0.2, "right_y": 0.6},
        6: {"left_x": 0.5, "left_y": -0.2, "right_x": 0.1, "right_y": 0.3},
        7: {"left_x": 0.2, "left_y": 0.1, "right_x": 0.0, "right_y": 0.0},
        8: {"left_x": 0.0, "left_y": 0.0, "right_x": 0.0, "right_y": 0.0},
        9: {"left_x": -0.2, "left_y": 0.1, "right_x": -0.1, "right_y": -0.2},
        10: {"left_x": -0.5, "left_y": 0.3, "right_x": -0.2, "right_y": -0.4},
        11: {"left_x": -0.75, "left_y": 0.5, "right_x": -0.3, "right_y": -0.6},
        12: {"left_x": -1.0, "left_y": 0.9, "right_x": -0.4, "right_y": -0.8},
        13: {"left_x": -0.75, "left_y": 0.5, "right_x": -0.3, "right_y": -0.6},
        14: {"left_x": -0.5, "left_y": 0.2, "right_x": -0.1, "right_y": -0.3},
        15: {"left_x": -0.2, "left_y": 0.1, "right_x": 0.0, "right_y": 0.0},
    }
    return values[phase % 16]


def demo_buttons(step: int):
    index = (step % 12) + 1
    buttons = {f"button_{i}": False for i in range(1, 13)}
    buttons[f"button_{index}"] = True
    return buttons


def send_loop(host: str = HOST, port: int = PORT, interval: float = 0.05, demo: bool = False, forced_device: str | None = None, action_map: dict | None = None):
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

    config = load_axis_config()
    device_profile = {"stick_axes": DEFAULT_AXIS_CONFIG.copy()}
    if joy is not None:
        device_profile = select_device_profile(joy, config, forced_device=forced_device)
    axis_config = device_profile.get("stick_axes", DEFAULT_AXIS_CONFIG.copy())

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
                axes, buttons, dpad = read_gamepad_state(joy, axis_config)
            axes = normalize_axes(axes)
            buttons = {k: bool(v) for k, v in buttons.items()}
            dpad = {k: bool(v) for k, v in dpad.items()}

            signature = state_signature(axes, buttons, dpad)
            if last_signature is None or signature != last_signature:
                focus_state = {"value": 100}
                action_events = build_action_events(
                    dpad=dpad,
                    buttons=buttons,
                    previous_dpad=previous_dpad,
                    previous_buttons=previous_buttons,
                    action_map=resolved_action_map,
                    focus_step=focus_state["value"],
                    focus_step_state=focus_state,
                    button_press_times=button_press_times,
                    now=now,
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
                last_signature = signature

            step += 1
            time.sleep(interval)


class SenderWorker(QObject):
    status_changed = Signal(str)
    log_received = Signal(str)
    connection_changed = Signal(str)

    def __init__(
        self,
        host: str,
        port: int,
        device_name: str | None = None,
        action_map: dict | None = None,
        focus_step: int = 100,
        focus_step_changed_callback=None,
    ):
        super().__init__()
        self.host = host
        self.port = port
        self.device_name = device_name
        self.action_map = resolve_action_mapping(action_map)
        self._focus_step = _clamp_focus_step(focus_step, default=100)
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
            button_press_times = {}
            while not self._stop_event.is_set():
                now = time.monotonic()
                if now - last_heartbeat >= 1.0:
                    heartbeat = protocol.build_heartbeat_payload()
                    packet = protocol.serialize_message(heartbeat)
                    self._socket.sendall((packet + "\n").encode("utf-8"))
                    self._safe_emit(self.log_received, f"[sender] heartbeat: {packet}")
                    last_heartbeat = now

                axes, buttons, dpad = read_gamepad_state(self._joy, load_axis_config())
                axes = normalize_axes(axes)
                buttons = {k: bool(v) for k, v in buttons.items()}
                dpad = {k: bool(v) for k, v in dpad.items()}

                focus_step_state = {"value": self._focus_step}
                previous_focus_step = self._focus_step
                action_events = build_action_events(
                    dpad=dpad,
                    buttons=buttons,
                    previous_dpad=previous_dpad,
                    previous_buttons=previous_buttons,
                    action_map=self.action_map,
                    focus_step=focus_step_state["value"],
                    focus_step_state=focus_step_state,
                    button_press_times=button_press_times,
                    now=now,
                )
                self._focus_step = _clamp_focus_step(focus_step_state["value"], default=100)
                if previous_focus_step != self._focus_step and self._focus_step_changed_callback is not None:
                    try:
                        self._focus_step_changed_callback(self._focus_step)
                    except Exception:
                        pass
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
                    self._safe_emit(self.log_received, json.dumps(message, ensure_ascii=False, separators=(",", ":")))

                previous_dpad = dpad.copy()
                previous_buttons = buttons.copy()
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
        self.gui_settings = load_gui_settings()

        central = QWidget(self)
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        form_layout = QFormLayout()

        self.controller_combo = QComboBox()
        self.host_edit = QLineEdit(self.gui_settings["host"])
        self.port_edit = QLineEdit(str(self.gui_settings["port"]))
        self.heartbeat_checkbox = QCheckBox("Heartbeat log")
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
        form_layout.addRow("Heartbeat", self.heartbeat_checkbox)
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

        main_layout.addLayout(form_layout)
        main_layout.addLayout(button_row)
        main_layout.addWidget(self.console)

        self.connection_button.clicked.connect(self.on_toggle_connection)
        self.mapping_button.clicked.connect(self.on_edit_mapping)
        self.close_button.clicked.connect(self.on_close)

        self.refresh_controllers()
        self.restore_saved_controller()
        self.log("Ready")

    def log(self, message: str):
        self.console.append(message)
        self.console.verticalScrollBar().setValue(self.console.verticalScrollBar().maximum())

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
            "action_mapping": self.gui_settings.get("action_mapping", DEFAULT_ACTION_MAPPING.copy()),
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

    def handle_log_message(self, message: str):
        if "heartbeat" in message.lower() and not self.heartbeat_checkbox.isChecked():
            return
        self.log(message)

    def set_connection_button_state(self, connected: bool):
        self.connection_button.setText("Disconnect" if connected else "Connect")
        self.connection_button.setStyleSheet("QPushButton { font-weight: bold; }" if connected else "")

    def _handle_connection_update(self, text: str):
        normalized = str(text or "").strip()
        if not normalized:
            return

        if normalized.lower().startswith("connected") or normalized.lower().startswith("ready"):
            self.set_connection_button_state(True)
            return

        if normalized.lower().startswith("error:") or normalized.lower() == "disconnected":
            self.set_connection_button_state(False)
            self.worker = None
            return

        if "disconnected" in normalized.lower():
            self.set_connection_button_state(False)
            self.worker = None
            return

        self.set_connection_button_state(False)

    def on_toggle_connection(self):
        if self.worker is None:
            self.on_connect()
        else:
            self.on_disconnect()

    def on_edit_mapping(self):
        editor = MappingEditorWindow(
            self,
            mapping=self.gui_settings.get("action_mapping", DEFAULT_ACTION_MAPPING.copy()),
            selected_device=self.controller_combo.currentText(),
        )
        editor.mapping_applied.connect(self._apply_mapping)
        editor.show()
        editor.raise_()

    def _apply_mapping(self, mapping: dict):
        self.gui_settings["action_mapping"] = resolve_action_mapping(mapping)
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
            "action_mapping": self.gui_settings.get("action_mapping", DEFAULT_ACTION_MAPPING.copy()),
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
            action_map=self.gui_settings.get("action_mapping"),
            focus_step=self.focus_step_spin.value(),
            focus_step_changed_callback=self._apply_focus_step_value,
        )
        self.worker.status_changed.connect(lambda text: self.log(f"[gui] status: {text}"))
        self.worker.log_received.connect(self.handle_log_message)
        self.worker.connection_changed.connect(self._handle_connection_update)
        self.worker.connection_changed.connect(lambda text: self.log(f"[gui] {text}"))

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
        self.log("[gui] disconnected")

    def on_close(self):
        self.save_settings()
        self.close()

    def closeEvent(self, event):
        self.save_settings()
        super().closeEvent(event)


class MappingEditorWindow(QMainWindow):
    mapping_applied = Signal(dict)

    def __init__(self, parent=None, mapping: dict | None = None, selected_device: str | None = None):
        super().__init__(parent)
        self.setWindowTitle("INDIPAD Mapping Editor")
        self.resize(760, 540)
        self.selected_device = selected_device
        config = load_axis_config()
        self.mapping = get_default_action_mapping(selected_device, config)
        if isinstance(mapping, dict):
            self.mapping = resolve_action_mapping(mapping)

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

        self.form = QWidget()
        self.form_layout = QFormLayout(self.form)
        self.input_rows = {}

        for label, key in get_gamepad_input_rows(self.selected_device):
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

    def reset_to_default(self):
        self.mapping = get_default_action_mapping(self.selected_device, load_axis_config())
        for key, combo in self.input_rows.items():
            value = self.mapping.get(key, "")
            if value and value in [item for item in AVAILABLE_ACTIONS if item]:
                combo.setCurrentText(value)
            else:
                combo.setCurrentIndex(0)

    def apply_mapping(self):
        next_mapping = {}
        for key, combo in self.input_rows.items():
            value = combo.currentText().strip()
            if value and value != "Unassigned":
                next_mapping[key] = value
        self.mapping = resolve_action_mapping(next_mapping)
        self.mapping_applied.emit(self.mapping)
        self.close()


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
