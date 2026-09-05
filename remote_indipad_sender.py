import json
import os
import socket
import sys
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

import remote_indipad_protocol as protocol


HOST = "127.0.0.1"
PORT = 50007
DEADZONE = 0.08
DEFAULT_AXIS_CONFIG = {
    "left_x": 0,
    "left_y": 1,
    "right_x": 2,
    "right_y": 4,
}

_DEBUG_JSON_CURSOR_SAVED = False
_DEBUG_JSON_LAST_LINES = 0


def load_axis_config(path: str | Path | None = None):
    config_path = Path(path) if path is not None else Path(__file__).with_suffix(".json")
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
    return json.dumps(_normalize_json_for_display(value), ensure_ascii=False, indent=2)


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


def send_loop(host: str = HOST, port: int = PORT, interval: float = 0.05, demo: bool = False, forced_device: str | None = None):
    joy = None
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
        while True:
            now = time.monotonic()
            if now - last_heartbeat >= heartbeat_interval:
                heartbeat = protocol.build_heartbeat_payload()
                if protocol.validate_message(heartbeat):
                    packet = protocol.serialize_message(heartbeat)
                    sock.sendall((packet + "\n").encode("utf-8"))
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
                message = protocol.build_payload(axes=axes, buttons=buttons, dpad=dpad, mode="slew")
                if protocol.validate_message(message):
                    packet = protocol.serialize_message(message)
                    print_debug_json("[sender] json", message)
                    sock.sendall((packet + "\n").encode("utf-8"))
                last_signature = signature

            step += 1
            time.sleep(interval)


if __name__ == "__main__":
    try:
        args = sys.argv[1:]
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
