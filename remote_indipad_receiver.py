import asyncio
import json
import os
import queue
import socket
import sys
import threading
import time
from datetime import datetime
import builtins
from pathlib import Path
from typing import Optional

try:
    import ctypes
except ImportError:  # pragma: no cover - fallback for missing ctypes
    ctypes = None

try:
    from PySide6.QtCore import QObject, Qt, QTimer
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QPushButton, QSizePolicy, QTextEdit, QVBoxLayout, QWidget
except ImportError:  # pragma: no cover - GUI is optional unless GUI mode is used
    class QObject:
        def __init__(self, *args, **kwargs):
            pass

    QTimer = None
    QFont = QCheckBox = QComboBox = QFormLayout = QHBoxLayout = QLabel = QLineEdit = QMainWindow = QPushButton = QSizePolicy = QTextEdit = QVBoxLayout = QWidget = object
    QApplication = None


HOST = "0.0.0.0"
PORT = 50007
_MODULE_DIR = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd()
GUI_SETTINGS_PATH = _MODULE_DIR / "remote_indipad_receiver.json"
DEFAULT_GUI_SETTINGS = {
    "mount": "",
    "focuser": "",
    "filter": "",
    "filter_slots": 0,
    "rotator": "",
    "host": "0.0.0.0",
    "port": 50007,
    "heartbeat": False,
    "window_geometry": {},
}

TELESCOPE_INTERFACE = 1 << 0
FOCUSER_INTERFACE = 1 << 3
FILTER_INTERFACE = 1 << 4
ROTATOR_INTERFACE = 1 << 12

try:
    from dbus_next.aio.message_bus import MessageBus
    from dbus_next.constants import BusType
except ImportError:  # pragma: no cover - optional dependency for D-Bus discovery
    MessageBus = None
    BusType = None



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


_ORIGINAL_PRINT = builtins.print
_LOG_TIMESTAMP_LENGTH = len("0000-00-00 00:00:00.000")


def format_log_timestamp() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def timestamp_log_message(message: str) -> str:
    text = str(message)
    if len(text) >= _LOG_TIMESTAMP_LENGTH and text[_LOG_TIMESTAMP_LENGTH - 3] == "." and text[4] == "-" and text[7] == "-":
        return text
    return f"{format_log_timestamp()} {text}"


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


def append_protocol_log_time(message: str, payload: dict | None = None) -> str:
    return f"{message}{protocol_log_suffix(payload)}"


def console_print(*values, **kwargs):
    if values and not any("\x1b" in str(value) for value in values):
        values = (timestamp_log_message(kwargs.get("sep", " ").join(str(value) for value in values)),)
        kwargs = {key: value for key, value in kwargs.items() if key != "sep"}
    builtins.print(*values, **kwargs)


print = console_print


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


def extract_dpad_state(payload):
    if not isinstance(payload, dict):
        return {"pressed": [], "all": []}

    dpad = payload.get("dpad", {})
    if not isinstance(dpad, dict):
        dpad = payload.get("buttons", {})

    if not isinstance(dpad, dict):
        return {"pressed": [], "all": []}

    dpad_keys = [key for key in dpad if key.startswith("dpad_")]
    pressed = [key for key in dpad_keys if bool(dpad.get(key))]
    return {"pressed": pressed, "all": dpad_keys}


def print_debug_json(label: str, value) -> None:
    rendered = format_debug_json(value)
    print(f"{label}: {rendered}{protocol_log_suffix(value)}", flush=True)


def _split_complete_json_lines(buffer: str) -> tuple[list[str], str]:
    lines: list[str] = []
    while True:
        newline_index = buffer.find("\n")
        if newline_index < 0:
            break
        line = buffer[:newline_index].strip()
        buffer = buffer[newline_index + 1 :]
        if line:
            lines.append(line)
    return lines, buffer


class QueueLogHandler:
    def __init__(self):
        self._messages = queue.Queue()

    def emit(self, message: str) -> None:
        if message is None:
            return
        self._messages.put(str(message))

    def drain(self) -> list[str]:
        messages = []
        while True:
            try:
                messages.append(self._messages.get_nowait())
            except queue.Empty:
                break
        return messages


def _debug_dispatch(label: str, action: str, pressed: bool, source: str) -> None:
    print(f"[receiver] dispatch: {label} action={action} pressed={pressed} source={source}", flush=True)


ACTIVE_INDI_DEVICE_NAMES = {"mount": "", "focuser": "", "filter": "", "rotator": ""}
_ROTATOR_HOLD_EVENTS: dict[str, threading.Event] = {}
_ROTATOR_RELEASE_COUNTS: dict[str, int] = {}


def stop_rotator_hold(direction: str | None = None) -> None:
    directions = [direction] if direction is not None else ["CAA_ROTATE_CLOCKWISE", "CAA_ROTATE_COUNTER_CLOCKWISE"]
    for active_direction in directions:
        event = _ROTATOR_HOLD_EVENTS.pop(active_direction, None)
        if event is not None:
            event.set()


def set_active_indi_device(device_type: str, name: str | None) -> None:
    if device_type not in ACTIVE_INDI_DEVICE_NAMES:
        return
    ACTIVE_INDI_DEVICE_NAMES[device_type] = (name or "").strip()


def get_active_indi_device(device_type: str) -> str:
    return str(ACTIVE_INDI_DEVICE_NAMES.get(device_type, "") or "").strip()


_INDI_METHOD_NAMES = {
    "getText": "call_get_text",
    "getNumber": "call_get_number",
    "getPropertyState": "call_get_property_state",
    "getSwitch": "call_get_switch",
    "setSwitch": "call_set_switch",
    "sendProperty": "call_send_property",
    "setNumber": "call_set_number",
    "getProperties": "call_get_properties",
}

ACTIVE_INDI_SLEW_RATES: dict[str, list[str]] = {}


def _check_indi_call_result(method_name: str, args: tuple, result) -> None:
    """KStars INDI D-Bus methods return a bool success flag; surface a clear error when it is False."""
    value = _dbus_value(result)
    if isinstance(value, bool) and not value:
        raise RuntimeError(f"KStars rejected {method_name}{args} (returned False; check property/argument types)")


async def _run_indi_calls(calls: list[tuple[str, tuple]]):
    """Execute a sequence of INDI D-Bus calls over a single connection."""
    if MessageBus is None or BusType is None:
        raise RuntimeError("dbus-next is required for INDI operations")

    bus = MessageBus(bus_type=BusType.SESSION)
    await bus.connect()
    try:
        introspection = await bus.introspect("org.kde.kstars", "/KStars/INDI")
        proxy = bus.get_proxy_object("org.kde.kstars", "/KStars/INDI", introspection)
        interface = proxy.get_interface("org.kde.kstars.INDI")
        results = []
        for method_name, args in calls:
            method = getattr(interface, _INDI_METHOD_NAMES[method_name])
            try:
                result = await method(*args)
            except Exception as exc:
                raise RuntimeError(f"D-Bus call {method_name}{args} failed: {exc}") from exc
            _check_indi_call_result(method_name, args, result)
            results.append(result)
        return results
    finally:
        bus.disconnect()


async def _call_indi_method(method_name: str, *args):
    results = await _run_indi_calls([(method_name, args)])
    return results[0]


async def _get_filter_slot_count(driver_name: str) -> int:
    driver_name = str(driver_name or "").strip()
    if not driver_name:
        return 0

    slot_count = 0
    for slot_index in range(1, 11):
        try:
            result = await _call_indi_method(
                "getText", driver_name, "FILTER_NAME", f"FILTER_SLOT_NAME_{slot_index}"
            )
        except Exception:
            break

        result = _dbus_value(result)
        if not result:
            continue

        if isinstance(result, (tuple, list)):
            if not result:
                break
            value = str(_dbus_value(result[0])).strip()
        else:
            value = str(result).strip()

        if value.lower() == "invalid":
            break
        slot_count = slot_index

    return slot_count


def get_filter_slot_count(driver_name: str) -> int:
    return asyncio.run(_get_filter_slot_count(driver_name))


async def _fetch_mount_slew_rates_async(driver_name: str) -> list[str]:
    driver_name = str(driver_name or "").strip()
    if not driver_name:
        return []
    if MessageBus is None or BusType is None:
        raise RuntimeError("dbus-next is required for INDI operations")

    bus = MessageBus(bus_type=BusType.SESSION)
    await bus.connect()
    try:
        introspection = await bus.introspect("org.kde.kstars", "/KStars/INDI")
        proxy = bus.get_proxy_object("org.kde.kstars", "/KStars/INDI", introspection)
        interface = proxy.get_interface("org.kde.kstars.INDI")

        method = getattr(interface, "call_get_properties", None)
        if method is None:
            method = getattr(interface, "get_properties", None)
        if method is None:
            raise AttributeError("org.kde.kstars.INDI does not expose getProperties")

        result = await method(driver_name)
        values = []

        def collect(value):
            if isinstance(value, (list, tuple, set)):
                for item in value:
                    collect(item)
            elif isinstance(value, dict):
                for item in value.values():
                    collect(item)
            elif isinstance(value, str):
                values.append(value)

        collect(result)

        rates: list[str] = []
        for value in values:
            label = str(value).strip()
            if not label or ".TELESCOPE_SLEW_RATE." not in label:
                continue
            rate_name = label.split(".TELESCOPE_SLEW_RATE.", 1)[1].strip()
            if rate_name:
                rates.append(rate_name)
        return list(dict.fromkeys(rates))
    finally:
        bus.disconnect()


def get_mount_slew_rates(driver_name: str) -> list[str]:
    driver_name = str(driver_name or "").strip()
    if not driver_name:
        return []
    cached = ACTIVE_INDI_SLEW_RATES.get(driver_name)
    if cached:
        return list(cached)
    try:
        rates = asyncio.run(_fetch_mount_slew_rates_async(driver_name))
    except Exception:
        rates = []
    if rates:
        ACTIVE_INDI_SLEW_RATES[driver_name] = rates
    return rates


async def _get_mount_slew_switch_state_async(driver_name: str, slew_rate: str) -> bool:
    driver_name = str(driver_name or "").strip()
    slew_rate = str(slew_rate or "").strip()
    if not driver_name or not slew_rate:
        return False
    if MessageBus is None or BusType is None:
        raise RuntimeError("dbus-next is required for INDI operations")

    bus = MessageBus(bus_type=BusType.SESSION)
    await bus.connect()
    try:
        introspection = await bus.introspect("org.kde.kstars", "/KStars/INDI")
        proxy = bus.get_proxy_object("org.kde.kstars", "/KStars/INDI", introspection)
        interface = proxy.get_interface("org.kde.kstars.INDI")

        method = getattr(interface, "call_get_switch", None)
        if method is None:
            method = getattr(interface, "get_switch", None)
        if method is None:
            raise AttributeError("org.kde.kstars.INDI does not expose getSwitch")

        result = await method(driver_name, "TELESCOPE_SLEW_RATE", slew_rate)
        value = _dbus_value(result)
        if isinstance(value, (tuple, list)):
            value = value[0] if value else False
        if isinstance(value, str):
            return value.strip().lower() in {"on", "true", "1"}
        return bool(value)
    finally:
        bus.disconnect()


def get_current_mount_slew_rate(driver_name: str) -> str:
    driver_name = str(driver_name or "").strip()
    if not driver_name:
        return ""
    rates = get_mount_slew_rates(driver_name)
    if not rates:
        return ""
    for rate in rates:
        try:
            if asyncio.run(_get_mount_slew_switch_state_async(driver_name, rate)):
                return rate
        except Exception:
            continue
    return rates[0]


def set_mount_slew_rate(driver_name: str, slew_rate: str) -> bool:
    driver_name = str(driver_name or "").strip()
    slew_rate = str(slew_rate or "").strip()
    if not driver_name or not slew_rate:
        return False

    calls = [
        ("setSwitch", (driver_name, "TELESCOPE_SLEW_RATE", slew_rate, "On")),
        ("sendProperty", (driver_name, "TELESCOPE_SLEW_RATE")),
    ]
    try:
        asyncio.run(_run_indi_calls(calls))
    except Exception as exc:
        print(f"[receiver] TELESCOPE_SLEW_RATE/{slew_rate} D-Bus call error: {exc}", flush=True)
        return False

    print(f"[receiver] set mount slew rate to {slew_rate} on {driver_name}", flush=True)
    return True


def build_focus_dbus_calls(driver_name: str, direction: str, step: int | None = None) -> list[tuple[str, tuple[str, ...]]]:
    driver_name = str(driver_name or "").strip()
    if not driver_name:
        raise ValueError("driver_name is required")

    direction = str(direction).upper()
    if direction == "FOCUS_IN":
        motion = "FOCUS_INWARD"
    elif direction == "FOCUS_OUT":
        motion = "FOCUS_OUTWARD"
    else:
        raise ValueError(f"unsupported focus direction: {direction}")

    step_value = 100
    if step is not None:
        try:
            step_value = max(1, int(step))
        except (TypeError, ValueError):
            step_value = 100

    return [
        ("setSwitch", (driver_name, "FOCUS_MOTION", motion, "On")),
        ("sendProperty", (driver_name, "FOCUS_MOTION")),
        ("setNumber", (driver_name, "REL_FOCUS_POSITION", "FOCUS_RELATIVE_POSITION", float(step_value))),
        ("sendProperty", (driver_name, "REL_FOCUS_POSITION")),
    ]


def execute_focus_action(direction: str, driver_name: str | None = None, step: int | None = None) -> None:
    direction = str(direction).upper()
    target_name = (driver_name or get_active_indi_device("focuser") or "").strip()
    if not target_name:
        print(f"[receiver] no focuser selected; cannot execute {direction}", flush=True)
        return

    calls = build_focus_dbus_calls(target_name, direction, step=step)
    try:
        asyncio.run(_run_indi_calls(calls))
    except Exception as exc:
        print(f"[receiver] {direction} D-Bus call error: {exc}", flush=True)
        return

    print(f"[receiver] executed {direction} on {target_name}", flush=True)


async def _execute_filterwheel_action_async(driver_name: str, direction: str):
    """Read the slot count/current slot and apply the move over one bus connection."""
    if MessageBus is None or BusType is None:
        raise RuntimeError("dbus-next is required for INDI operations")

    bus = MessageBus(bus_type=BusType.SESSION)
    await bus.connect()
    try:
        introspection = await bus.introspect("org.kde.kstars", "/KStars/INDI")
        proxy = bus.get_proxy_object("org.kde.kstars", "/KStars/INDI", introspection)
        interface = proxy.get_interface("org.kde.kstars.INDI")

        slot_count = 0
        for slot_index in range(1, 11):
            try:
                result = await interface.call_get_text(driver_name, "FILTER_NAME", f"FILTER_SLOT_NAME_{slot_index}")
            except Exception as exc:
                if slot_index == 1:
                    print(f"[receiver] D-Bus call error: getText(FILTER_NAME, FILTER_SLOT_NAME_1) -> {exc}", flush=True)
                break

            result = _dbus_value(result)
            if not result:
                continue

            if isinstance(result, (tuple, list)):
                if not result:
                    break
                value = str(_dbus_value(result[0])).strip()
            else:
                value = str(result).strip()

            if value.lower() == "invalid":
                break
            slot_count = slot_index

        if slot_count <= 0:
            return None, None, 0, False

        try:
            current_result = await interface.call_get_number(driver_name, "FILTER_SLOT", "FILTER_SLOT_VALUE")
        except Exception as exc:
            print(f"[receiver] D-Bus call error: getNumber(FILTER_SLOT, FILTER_SLOT_VALUE) -> {exc}", flush=True)
            return None, None, slot_count, False

        current_result = _dbus_value(current_result)
        if isinstance(current_result, (tuple, list)):
            if not current_result:
                return None, None, slot_count, False
            current_result = _dbus_value(current_result[0])

        try:
            current_slot = int(float(current_result))
        except (TypeError, ValueError):
            return None, None, slot_count, False

        try:
            state_result = await interface.call_get_property_state(driver_name, "FILTER_SLOT")
        except Exception as exc:
            print(f"[receiver] D-Bus call error: getPropertyState(FILTER_SLOT) -> {exc}", flush=True)
            return current_slot, current_slot, slot_count, False

        state_value = _dbus_value(state_result)
        if isinstance(state_value, (tuple, list)):
            state_value = _dbus_value(state_value[0]) if state_value else ""
        if str(state_value).strip().lower() == "busy":
            return current_slot, current_slot, slot_count, True

        if direction == "FILTERWHEEL_PREV":
            if current_slot <= 1:
                target_slot = slot_count
            else:
                target_slot = current_slot - 1
        elif direction == "FILTERWHEEL_NEXT":
            if current_slot >= slot_count:
                target_slot = 1
            else:
                target_slot = current_slot + 1
        else:
            raise ValueError(f"unsupported filterwheel direction: {direction}")

        if target_slot != current_slot:
            set_args = (driver_name, "FILTER_SLOT", "FILTER_SLOT_VALUE", float(target_slot))
            try:
                set_result = await interface.call_set_number(*set_args)
            except Exception as exc:
                raise RuntimeError(f"D-Bus call setNumber{set_args} failed: {exc}") from exc
            _check_indi_call_result("setNumber", set_args, set_result)

            send_args = (driver_name, "FILTER_SLOT")
            try:
                send_result = await interface.call_send_property(*send_args)
            except Exception as exc:
                raise RuntimeError(f"D-Bus call sendProperty{send_args} failed: {exc}") from exc
            _check_indi_call_result("sendProperty", send_args, send_result)

        return current_slot, target_slot, slot_count, False
    finally:
        bus.disconnect()


def execute_filterwheel_action(direction: str, driver_name: str | None = None) -> None:
    direction = str(direction).upper()
    target_name = (driver_name or get_active_indi_device("filter") or "").strip()
    if not target_name:
        print(f"[receiver] no filter wheel selected; cannot execute {direction}", flush=True)
        return

    try:
        current_slot, target_slot, slot_count, busy = asyncio.run(_execute_filterwheel_action_async(target_name, direction))
    except Exception as exc:
        print(f"[receiver] {direction} D-Bus call error: {exc}", flush=True)
        return

    if slot_count <= 0:
        print(f"[receiver] unable to determine filter slot count for {target_name}", flush=True)
        return

    if current_slot is None:
        print(f"[receiver] unable to read current filter slot for {target_name}", flush=True)
        return

    if busy:
        print(f"[receiver] {direction} ignored; {target_name} FILTER_SLOT is Busy", flush=True)
        return

    if target_slot == current_slot:
        print(f"[receiver] {direction} ignored; slot {current_slot} already at limit", flush=True)
        return

    print(f"[receiver] executed {direction} on {target_name}: slot {current_slot} -> {target_slot}", flush=True)


def normalize_rotator_target_angle(current_angle, delta_angle, max_rotation=360.0) -> float:
    try:
        current_value = float(current_angle)
    except (TypeError, ValueError):
        current_value = 0.0

    try:
        delta_value = float(delta_angle)
    except (TypeError, ValueError):
        delta_value = 0.0

    max_value = 360.0
    try:
        _ = float(max_rotation)
    except (TypeError, ValueError):
        pass

    target_value = current_value + delta_value
    if target_value < 0:
        target_value = 0.0
    elif target_value > max_value:
        target_value = max_value
    return float(target_value)


async def _execute_rotator_action_async(driver_name: str, direction: str, angle: int | float | None = None):
    """Read the rotator state, clamp the target angle to the fixed 0..360 range, and move it in one bus session."""
    if MessageBus is None or BusType is None:
        raise RuntimeError("dbus-next is required for INDI operations")

    bus = MessageBus(bus_type=BusType.SESSION)
    await bus.connect()
    try:
        introspection = await bus.introspect("org.kde.kstars", "/KStars/INDI")
        proxy = bus.get_proxy_object("org.kde.kstars", "/KStars/INDI", introspection)
        interface = proxy.get_interface("org.kde.kstars.INDI")

        try:
            state_result = await interface.call_get_property_state(driver_name, "ABS_ROTATOR_ANGLE")
        except Exception as exc:
            print(f"[receiver] D-Bus call error: getPropertyState(ABS_ROTATOR_ANGLE) -> {exc}", flush=True)
            return None, None, 360.0, False

        state_value = _dbus_value(state_result)
        if isinstance(state_value, (tuple, list)):
            state_value = _dbus_value(state_value[0]) if state_value else ""
        if str(state_value).strip().lower() == "busy":
            return None, None, 360.0, True

        try:
            current_result = await interface.call_get_number(driver_name, "ABS_ROTATOR_ANGLE", "ANGLE")
        except Exception as exc:
            print(f"[receiver] D-Bus call error: getNumber(ABS_ROTATOR_ANGLE, ANGLE) -> {exc}", flush=True)
            return None, None, 360.0, False

        current_value = _dbus_value(current_result)
        if isinstance(current_value, (tuple, list)):
            current_value = _dbus_value(current_value[0]) if current_value else 0
        try:
            current_angle = float(current_value)
        except (TypeError, ValueError):
            return None, None, 360.0, False

        if angle is None:
            target_angle = current_angle
        else:
            try:
                delta = float(angle)
            except (TypeError, ValueError):
                delta = 0.0
            target_angle = normalize_rotator_target_angle(current_angle, delta, 360.0)

        if target_angle == current_angle:
            return current_angle, target_angle, 360.0, False

        set_args = (driver_name, "ABS_ROTATOR_ANGLE", "ANGLE", float(target_angle))
        try:
            set_result = await interface.call_set_number(*set_args)
        except Exception as exc:
            raise RuntimeError(f"D-Bus call setNumber{set_args} failed: {exc}") from exc
        _check_indi_call_result("setNumber", set_args, set_result)

        send_args = (driver_name, "ABS_ROTATOR_ANGLE")
        try:
            send_result = await interface.call_send_property(*send_args)
        except Exception as exc:
            raise RuntimeError(f"D-Bus call sendProperty{send_args} failed: {exc}") from exc
        _check_indi_call_result("sendProperty", send_args, send_result)

        return current_angle, float(target_angle), 360.0, False
    finally:
        bus.disconnect()


def read_rotator_state(driver_name: str | None = None) -> str:
    target_name = (driver_name or get_active_indi_device("rotator") or "").strip()
    if not target_name:
        return ""
    if MessageBus is None or BusType is None:
        return ""

    async def _read_state_async():
        bus = MessageBus(bus_type=BusType.SESSION)
        await bus.connect()
        try:
            introspection = await bus.introspect("org.kde.kstars", "/KStars/INDI")
            proxy = bus.get_proxy_object("org.kde.kstars", "/KStars/INDI", introspection)
            interface = proxy.get_interface("org.kde.kstars.INDI")
            result = await interface.call_get_property_state(target_name, "ABS_ROTATOR_ANGLE")
            value = _dbus_value(result)
            if isinstance(value, (tuple, list)):
                value = _dbus_value(value[0]) if value else ""
            return str(value).strip().lower()
        finally:
            bus.disconnect()

    try:
        return asyncio.run(_read_state_async())
    except Exception as exc:
        print(f"[receiver] D-Bus call error: getPropertyState(ABS_ROTATOR_ANGLE) -> {exc}", flush=True)
        return ""


def _run_rotator_hold_loop(direction: str, driver_name: str, stop_event: threading.Event, interval: float = 0.05, executor=None) -> None:
    if executor is None:
        executor = execute_rotator_action

    direction = str(direction).upper()
    if not driver_name:
        return

    rotation_count = 0
    sign = 1.0 if direction == "CAA_ROTATE_CLOCKWISE" else -1.0
    try:
        while not stop_event.is_set():
            state = read_rotator_state(driver_name)
            if state != "busy":
                rotation_count += 1
                if rotation_count <= 5:
                    step_angle = sign * 1.0
                elif rotation_count <= 8:
                    step_angle = sign * 5.0
                else:
                    step_angle = sign * 10.0
                executor(direction, step_angle, driver_name=driver_name)
            time.sleep(interval)
    finally:
        stop_rotator_hold(direction)


def execute_rotator_action(direction: str, angle: int | float | None = None, driver_name: str | None = None) -> float | None:
    direction = str(direction).upper()
    target_name = (driver_name or get_active_indi_device("rotator") or "").strip()
    if not target_name:
        print(f"[receiver] no rotator selected; cannot execute {direction}", flush=True)
        return None

    if direction not in {"CAA_ROTATE_COUNTER_CLOCKWISE", "CAA_ROTATE_CLOCKWISE"}:
        return None

    try:
        current_angle, target_angle, max_rotation, busy = asyncio.run(_execute_rotator_action_async(target_name, direction, angle))
    except Exception as exc:
        print(f"[receiver] {direction} D-Bus call error: {exc}", flush=True)
        return None

    if busy:
        print(f"[receiver] {direction} ignored; {target_name} ABS_ROTATOR_ANGLE is Busy", flush=True)
        return None

    if current_angle is None:
        print(f"[receiver] unable to read current rotator angle for {target_name}", flush=True)
        return None

    print(
        f"[receiver] executed {direction} on {target_name}: angle {current_angle} -> {target_angle} (limit=360)",
        flush=True,
    )
    return float(target_angle)


async def _execute_rotator_abort_async(driver_name: str):
    """Abort the current rotator motion using the INDI abort switch."""
    if MessageBus is None or BusType is None:
        raise RuntimeError("dbus-next is required for INDI operations")

    bus = MessageBus(bus_type=BusType.SESSION)
    await bus.connect()
    try:
        introspection = await bus.introspect("org.kde.kstars", "/KStars/INDI")
        proxy = bus.get_proxy_object("org.kde.kstars", "/KStars/INDI", introspection)
        interface = proxy.get_interface("org.kde.kstars.INDI")

        set_args = (driver_name, "ROTATOR_ABORT_MOTION", "ABORT", "On")
        try:
            set_result = await interface.call_set_switch(*set_args)
        except Exception as exc:
            raise RuntimeError(f"D-Bus call setSwitch{set_args} failed: {exc}") from exc
        _check_indi_call_result("setSwitch", set_args, set_result)

        send_args = (driver_name, "ROTATOR_ABORT_MOTION")
        try:
            send_result = await interface.call_send_property(*send_args)
        except Exception as exc:
            raise RuntimeError(f"D-Bus call sendProperty{send_args} failed: {exc}") from exc
        _check_indi_call_result("sendProperty", send_args, send_result)

        return True
    finally:
        bus.disconnect()


def execute_rotator_abort(driver_name: str | None = None) -> bool:
    target_name = (driver_name or get_active_indi_device("rotator") or "").strip()
    if not target_name:
        print("[receiver] no rotator selected; cannot abort rotation", flush=True)
        return False

    try:
        result = asyncio.run(_execute_rotator_abort_async(target_name))
    except Exception as exc:
        print(f"[receiver] CAA_ROTATE_ABORT D-Bus call error: {exc}", flush=True)
        return False

    print(f"[receiver] executed CAA_ROTATE_ABORT on {target_name}", flush=True)
    return bool(result)


def load_gui_settings(path: str | Path | None = None):
    config_path = Path(path) if path is not None else GUI_SETTINGS_PATH
    defaults = DEFAULT_GUI_SETTINGS.copy()

    if not config_path.exists():
        return defaults.copy()

    try:
        with open(config_path, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
    except (OSError, ValueError):
        return defaults.copy()

    if not isinstance(loaded, dict):
        return defaults.copy()

    port_value = loaded.get("port", 50007)
    try:
        port_value = int(port_value)
    except (TypeError, ValueError):
        port_value = 50007

    filter_slots = loaded.get("filter_slots", 0)
    try:
        filter_slots = max(0, int(filter_slots))
    except (TypeError, ValueError):
        filter_slots = 0

    window_geometry = loaded.get("window_geometry", {})
    if not isinstance(window_geometry, dict):
        window_geometry = {}
    normalized_geometry = {}
    for key in ("x", "y", "width", "height"):
        try:
            normalized_geometry[key] = int(window_geometry[key])
        except (KeyError, TypeError, ValueError):
            pass

    return {
        "mount": str(loaded.get("mount", "") or ""),
        "focuser": str(loaded.get("focuser", "") or ""),
        "filter": str(loaded.get("filter", "") or ""),
        "filter_slots": filter_slots,
        "rotator": str(loaded.get("rotator", "") or ""),
        "host": str(loaded.get("host", "0.0.0.0") or "0.0.0.0"),
        "port": port_value,
        "heartbeat": bool(loaded.get("heartbeat", False)),
        "window_geometry": normalized_geometry,
    }


def save_gui_settings(settings: dict, path: str | Path | None = None):
    config_path = Path(path) if path is not None else GUI_SETTINGS_PATH
    port_value = settings.get("port", 50007)
    try:
        port_value = int(port_value)
    except (TypeError, ValueError):
        port_value = 50007

    filter_slots = settings.get("filter_slots", 0)
    try:
        filter_slots = max(0, int(filter_slots))
    except (TypeError, ValueError):
        filter_slots = 0

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
        "mount": str(settings.get("mount", "") or ""),
        "focuser": str(settings.get("focuser", "") or ""),
        "filter": str(settings.get("filter", "") or ""),
        "filter_slots": filter_slots,
        "rotator": str(settings.get("rotator", "") or ""),
        "host": str(settings.get("host", "0.0.0.0") or "0.0.0.0"),
        "port": port_value,
        "heartbeat": bool(settings.get("heartbeat", False)),
        "window_geometry": normalized_geometry,
    }
    with open(config_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def _dbus_value(value):
    return getattr(value, "value", value)


def classify_indi_driver(driver_interface_value) -> dict[str, bool]:
    try:
        driver_interface = int(_dbus_value(driver_interface_value))
    except (TypeError, ValueError):
        return {"mount": False, "focuser": False, "filter": False, "rotator": False}

    return {
        "mount": bool(driver_interface & TELESCOPE_INTERFACE),
        "focuser": bool(driver_interface & FOCUSER_INTERFACE),
        "filter": bool(driver_interface & FILTER_INTERFACE),
        "rotator": bool(driver_interface & ROTATOR_INTERFACE),
    }


async def fetch_indi_device_list():
    if MessageBus is None or BusType is None:
        raise RuntimeError("dbus-next is required for INDI scanning")

    bus = MessageBus(bus_type=BusType.SESSION)
    await bus.connect()
    try:
        root = await bus.introspect("org.kde.kstars", "/KStars/INDI/GenericDevice")
        discovered = {"mount": [], "focuser": [], "filter": [], "rotator": []}

        for node in getattr(root, "nodes", []) or []:
            node_name = str(getattr(node, "name", "")).strip()
            if not node_name:
                continue
            object_path = f"/KStars/INDI/GenericDevice/{node_name}"
            try:
                node_introspection = await bus.introspect("org.kde.kstars", object_path)
                proxy = bus.get_proxy_object("org.kde.kstars", object_path, node_introspection)
                properties = proxy.get_interface("org.freedesktop.DBus.Properties")
                name_value = _dbus_value(await properties.call_get("org.kde.kstars.INDI.GenericDevice", "name"))
                interface_value = _dbus_value(await properties.call_get("org.kde.kstars.INDI.GenericDevice", "driverInterface"))
            except Exception:
                continue

            driver_name = str(name_value).strip() if name_value is not None else ""
            if not driver_name:
                continue

            classification = classify_indi_driver(interface_value)
            for category, is_match in classification.items():
                if is_match:
                    discovered[category].append(driver_name)

        for category in discovered:
            discovered[category] = sorted(dict.fromkeys(discovered[category]))

        for driver_name in discovered.get("mount", []):
            try:
                ACTIVE_INDI_SLEW_RATES[driver_name] = await _fetch_mount_slew_rates_async(driver_name)
            except Exception:
                ACTIVE_INDI_SLEW_RATES[driver_name] = []
        return discovered
    finally:
        bus.disconnect()


class GuiConsoleStream:
    def __init__(self, window):
        self.window = window
        self._buffer = ""

    def write(self, text):
        if not text:
            return
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if line:
                self.window.log(line)
        if self._buffer and not text.endswith("\n"):
            self.window.log(self._buffer)
            self._buffer = ""

    def flush(self):
        if self._buffer:
            self.window.log(self._buffer)
            self._buffer = ""

    def isatty(self):
        return True


class ReceiverWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("INDIPAD HOST")
        self.resize(720, 420)
        self.gui_settings = load_gui_settings()
        geometry = self.gui_settings.get("window_geometry", {})
        if all(key in geometry for key in ("x", "y", "width", "height")):
            self.setGeometry(geometry["x"], geometry["y"], max(300, geometry["width"]), max(240, geometry["height"]))
        self.log_queue = QueueLogHandler()
        self.receiver = Receiver(
            host=self.gui_settings.get("host", HOST),
            port=int(self.gui_settings.get("port", PORT)),
            log_callback=self.log_queue.emit,
        )
        self.receiver_thread = None
        self._original_stdout = sys.stdout
        self._original_stderr = sys.stderr
        self._gui_stdout = GuiConsoleStream(self)
        self._gui_stderr = GuiConsoleStream(self)
        sys.stdout = self._gui_stdout
        sys.stderr = self._gui_stderr

        self._log_timer = QTimer(self)
        self._log_timer.timeout.connect(self._flush_log_queue)
        self._log_timer.start(50)

        central = QWidget(self)
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        form_layout = QFormLayout()

        self.mount_combo = QComboBox()
        self.mount_combo.addItems(["Not scanned", "Mount 1", "Mount 2"])
        self.focuser_combo = QComboBox()
        self.focuser_combo.addItems(["Not scanned", "Focuser 1", "Focuser 2"])
        self.filter_combo = QComboBox()
        self.filter_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.filter_combo.addItems(["Not scanned", "Filter Wheel 1", "Filter Wheel 2"])
        self.filter_slots_edit = QLineEdit()
        self.filter_slots_edit.setReadOnly(True)
        self.filter_slots_edit.setAlignment(Qt.AlignRight)
        self.filter_slots_edit.setFixedWidth(64)
        self.filter_slots_edit.setPlaceholderText("0")
        self.rotator_combo = QComboBox()
        self.rotator_combo.addItems(["Not scanned", "Rotator 1", "Rotator 2"])
        self.host_edit = QLineEdit(str(self.gui_settings.get("host", "0.0.0.0")))
        self.port_edit = QLineEdit(str(self.gui_settings.get("port", 50007)))

        self.heartbeat_checkbox = QCheckBox("Heartbeat")
        self.heartbeat_checkbox.setChecked(bool(self.gui_settings.get("heartbeat", False)))

        filter_row = QHBoxLayout()
        filter_row.setContentsMargins(0, 0, 0, 0)
        filter_row.addWidget(self.filter_combo, 1)
        filter_row.addSpacing(0)
        filter_row.addWidget(self.filter_slots_edit)

        form_layout.addRow("Mount", self.mount_combo)
        form_layout.addRow("Focuser", self.focuser_combo)
        form_layout.addRow("Filter Wheel", filter_row)
        form_layout.addRow("Rotator", self.rotator_combo)
        host_port_row = QHBoxLayout()
        host_port_row.addWidget(self.host_edit)
        host_port_row.addWidget(self.port_edit)
        form_layout.addRow("Listening IP / Port", host_port_row)
        form_layout.addRow("Logs", self.heartbeat_checkbox)

        button_row = QHBoxLayout()
        self.scan_button = QPushButton("Scan INDI")
        self.restart_button = QPushButton("Restart")
        self.close_button = QPushButton("Close")

        for button in (self.scan_button, self.restart_button, self.close_button):
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            button_row.addWidget(button)

        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setFont(QFont("Consolas", 10))
        self.console.setPlainText("INDIPAD HOST console\n")
        self.clear_console_button = QPushButton("Clear")
        self.clear_console_button.clicked.connect(self.clear_console_log)
        console_button_row = QHBoxLayout()
        console_button_row.addStretch()
        console_button_row.addWidget(self.clear_console_button)

        main_layout.addLayout(form_layout)
        main_layout.addLayout(button_row)
        main_layout.addWidget(self.console)
        main_layout.addLayout(console_button_row)

        self.restore_saved_values()
        self.mount_combo.currentIndexChanged.connect(self._sync_active_indi_devices)
        self.focuser_combo.currentIndexChanged.connect(self._sync_active_indi_devices)
        self.filter_combo.currentIndexChanged.connect(self._refresh_filter_slot_count)
        self.rotator_combo.currentIndexChanged.connect(self._sync_active_indi_devices)
        self.heartbeat_checkbox.toggled.connect(self.on_heartbeat_toggled)
        self.start_receiver()
        self.scan_button.clicked.connect(self.on_scan_indi)
        self.restart_button.clicked.connect(self.on_restart)
        self.close_button.clicked.connect(self.on_close)
        QTimer.singleShot(0, self.on_scan_indi)
        self.log("Ready")

    def _append_log(self, message: str):
        self.console.append(message)
        self.console.verticalScrollBar().setValue(self.console.verticalScrollBar().maximum())

    def clear_console_log(self):
        self.console.clear()

    def _flush_log_queue(self):
        for message in self.log_queue.drain():
            self._append_log(message)

    def log(self, message: str):
        if threading.current_thread() is threading.main_thread():
            self._append_log(str(message))
            return
        self.log_queue.emit(str(message))

    def _refresh_filter_slot_count(self):
        self._sync_active_indi_devices()
        driver_name = self.filter_combo.currentText().strip()
        if not driver_name or driver_name in {"Not scanned"}:
            self.filter_slots_edit.setText("")
            return

        try:
            slot_count = get_filter_slot_count(driver_name)
        except Exception as exc:
            self.log(f"[gui] failed to get filter slot count for {driver_name}: {exc}")
            self.filter_slots_edit.setText("")
            return

        self.filter_slots_edit.setText(str(slot_count))
        self.gui_settings["filter_slots"] = slot_count

    def restore_saved_values(self):
        for combo, saved_value, options in (
            (self.mount_combo, self.gui_settings.get("mount", ""), ["Not scanned", "Mount 1", "Mount 2"]),
            (self.focuser_combo, self.gui_settings.get("focuser", ""), ["Not scanned", "Focuser 1", "Focuser 2"]),
            (self.filter_combo, self.gui_settings.get("filter", ""), ["Not scanned", "Filter Wheel 1", "Filter Wheel 2"]),
            (self.rotator_combo, self.gui_settings.get("rotator", ""), ["Not scanned", "Rotator 1", "Rotator 2"]),
        ):
            if not saved_value:
                combo.setCurrentIndex(0)
                continue
            for index in range(combo.count()):
                if combo.itemText(index) == saved_value:
                    combo.setCurrentIndex(index)
                    break
            else:
                combo.setCurrentIndex(0)

        slot_count = int(self.gui_settings.get("filter_slots", 0) or 0)
        self.filter_slots_edit.setText(str(slot_count) if slot_count > 0 else "")
        self._refresh_filter_slot_count()

    def _sync_active_indi_devices(self):
        for combo, kind in (
            (self.mount_combo, "mount"),
            (self.focuser_combo, "focuser"),
            (self.filter_combo, "filter"),
            (self.rotator_combo, "rotator"),
        ):
            text = combo.currentText().strip()
            if text in {"", "Not scanned"}:
                set_active_indi_device(kind, "")
            else:
                set_active_indi_device(kind, text)

    def save_settings(self):
        self._sync_active_indi_devices()
        settings = {
            "mount": self.mount_combo.currentText() if self.mount_combo.count() else "",
            "focuser": self.focuser_combo.currentText() if self.focuser_combo.count() else "",
            "filter": self.filter_combo.currentText() if self.filter_combo.count() else "",
            "filter_slots": self.filter_slots_edit.text().strip() or 0,
            "rotator": self.rotator_combo.currentText() if self.rotator_combo.count() else "",
            "host": self.host_edit.text().strip() or "0.0.0.0",
            "port": self.port_edit.text().strip() or "50007",
            "heartbeat": self.heartbeat_checkbox.isChecked(),
            "window_geometry": {
                "x": self.x(),
                "y": self.y(),
                "width": self.width(),
                "height": self.height(),
            },
        }
        if settings["mount"] in {"Not scanned"}:
            settings["mount"] = ""
        if settings["focuser"] in {"Not scanned"}:
            settings["focuser"] = ""
        if settings["filter"] in {"Not scanned"}:
            settings["filter"] = ""
        if settings["rotator"] in {"Not scanned"}:
            settings["rotator"] = ""
        self.gui_settings = settings
        save_gui_settings(settings)

    def on_heartbeat_toggled(self, enabled: bool):
        if hasattr(self, "receiver"):
            self.receiver.log_heartbeat = bool(enabled)
        self.log(f"[gui] heartbeat log {'enabled' if enabled else 'disabled'}")

    def start_receiver(self):
        self.save_settings()
        host = self.host_edit.text().strip() or "0.0.0.0"
        port_text = self.port_edit.text().strip() or "50007"
        try:
            port = int(port_text)
        except ValueError:
            self.log("[gui] invalid port value; using default 50007")
            port = 50007
        self.receiver = Receiver(host=host, port=port, log_heartbeat=self.heartbeat_checkbox.isChecked())
        self.receiver_thread = self.receiver.start()
        self.log(f"[gui] listening on {host}:{port}")

    def restart_receiver(self):
        self.receiver.stop()
        self.save_settings()
        self.log("[gui] restarting listener...")
        host = self.host_edit.text().strip() or "0.0.0.0"
        port_text = self.port_edit.text().strip() or "50007"
        try:
            port = int(port_text)
        except ValueError:
            self.log("[gui] invalid port value; using default 50007")
            port = 50007
        self.receiver = Receiver(host=host, port=port, log_heartbeat=self.heartbeat_checkbox.isChecked())
        self.receiver_thread = self.receiver.start()
        self.log(f"[gui] restarted listener on {host}:{port}")

    def on_scan_indi(self):
        self.log("[gui] scanning INDI devices...")

        def apply_scan_result(result):
            self.mount_combo.clear()
            self.focuser_combo.clear()
            self.filter_combo.clear()
            self.rotator_combo.clear()

            mount_options = ["Not scanned"] + result.get("mount", [])
            focuser_options = ["Not scanned"] + result.get("focuser", [])
            filter_options = ["Not scanned"] + result.get("filter", [])
            rotator_options = ["Not scanned"] + result.get("rotator", [])

            self.mount_combo.addItems(mount_options)
            self.focuser_combo.addItems(focuser_options)
            self.filter_combo.addItems(filter_options)
            self.rotator_combo.addItems(rotator_options)

            self.mount_combo.setCurrentIndex(0 if not result.get("mount") else 1)
            self.focuser_combo.setCurrentIndex(0 if not result.get("focuser") else 1)
            self.filter_combo.setCurrentIndex(0 if not result.get("filter") else 1)
            self.rotator_combo.setCurrentIndex(0 if not result.get("rotator") else 1)

            self._sync_active_indi_devices()
            self._refresh_filter_slot_count()

            if result.get("mount") or result.get("focuser") or result.get("filter") or result.get("rotator"):
                self.log("[gui] INDI scan complete")
            else:
                self.log("[gui] no supported INDI devices found")

        try:
            result = asyncio.run(fetch_indi_device_list())
            apply_scan_result(result)
        except Exception as exc:
            self.log(f"[gui] failed to scan INDI devices: {exc}")
            self.mount_combo.clear(); self.focuser_combo.clear(); self.filter_combo.clear(); self.rotator_combo.clear()
            self.mount_combo.addItems(["Not scanned"])
            self.focuser_combo.addItems(["Not scanned"])
            self.filter_combo.addItems(["Not scanned"])
            self.rotator_combo.addItems(["Not scanned"])
            self.mount_combo.setCurrentIndex(0)
            self.focuser_combo.setCurrentIndex(0)
            self.filter_combo.setCurrentIndex(0)
            self.rotator_combo.setCurrentIndex(0)

    def on_restart(self):
        self.restart_receiver()

    def on_close(self):
        self.save_settings()
        self.receiver.stop()
        self.close()

    def closeEvent(self, event):
        self.save_settings()
        self.receiver.stop()
        if hasattr(self, "_log_timer"):
            self._log_timer.stop()
        if hasattr(self, "_original_stdout"):
            sys.stdout = self._original_stdout
        if hasattr(self, "_original_stderr"):
            sys.stderr = self._original_stderr
        super().closeEvent(event)


def run_gui():
    if QObject is None or QApplication is None:
        raise RuntimeError("PySide6 is required to run the receiver GUI. Install it with: pip install pyside6")
    app = QApplication([])
    window = ReceiverWindow()
    window.show()
    return app.exec()


def _execute_mount_switch_action(driver_name: str, property_name: str, switch_name: str, enabled: bool) -> None:
    driver_name = str(driver_name or "").strip()
    if not driver_name:
        print("[receiver] no mount selected; cannot execute mount motion", flush=True)
        return

    state = "On" if bool(enabled) else "Off"
    calls = [
        ("setSwitch", (driver_name, property_name, switch_name, state)),
        ("sendProperty", (driver_name, property_name)),
    ]
    try:
        asyncio.run(_run_indi_calls(calls))
    except Exception as exc:
        print(f"[receiver] {property_name}/{switch_name} D-Bus call error: {exc}", flush=True)
        return

    print(f"[receiver] executed mount {property_name}/{switch_name} -> {state} on {driver_name}", flush=True)


def _execute_mount_abort_action(driver_name: str | None = None) -> None:
    driver_name = str(driver_name or get_active_indi_device("mount") or "").strip()
    if not driver_name:
        print("[receiver] no mount selected; cannot abort slewing", flush=True)
        return

    calls = [
        ("setSwitch", (driver_name, "TELESCOPE_ABORT_MOTION", "ABORT", "On")),
        ("sendProperty", (driver_name, "TELESCOPE_ABORT_MOTION")),
    ]
    try:
        asyncio.run(_run_indi_calls(calls))
    except Exception as exc:
        print(f"[receiver] TELESCOPE_ABORT_MOTION D-Bus call error: {exc}", flush=True)
        return

    print(f"[receiver] executed ABORT on {driver_name}", flush=True)


def handle_mount_north(pressed: bool, source: str = "dpad") -> None:
    _debug_dispatch("MOUNT_NORTH", "MOUNT_NORTH", pressed, source)
    if pressed:
        _execute_mount_switch_action(get_active_indi_device("mount"), "TELESCOPE_MOTION_NS", "MOTION_NORTH", True)
    else:
        _execute_mount_switch_action(get_active_indi_device("mount"), "TELESCOPE_MOTION_NS", "MOTION_NORTH", False)


def handle_mount_south(pressed: bool, source: str = "dpad") -> None:
    _debug_dispatch("MOUNT_SOUTH", "MOUNT_SOUTH", pressed, source)
    if pressed:
        _execute_mount_switch_action(get_active_indi_device("mount"), "TELESCOPE_MOTION_NS", "MOTION_SOUTH", True)
    else:
        _execute_mount_switch_action(get_active_indi_device("mount"), "TELESCOPE_MOTION_NS", "MOTION_SOUTH", False)


def handle_mount_west(pressed: bool, source: str = "dpad") -> None:
    _debug_dispatch("MOUNT_WEST", "MOUNT_WEST", pressed, source)
    if pressed:
        _execute_mount_switch_action(get_active_indi_device("mount"), "TELESCOPE_MOTION_WE", "MOTION_WEST", True)
    else:
        _execute_mount_switch_action(get_active_indi_device("mount"), "TELESCOPE_MOTION_WE", "MOTION_WEST", False)


def handle_mount_east(pressed: bool, source: str = "dpad") -> None:
    _debug_dispatch("MOUNT_EAST", "MOUNT_EAST", pressed, source)
    if pressed:
        _execute_mount_switch_action(get_active_indi_device("mount"), "TELESCOPE_MOTION_WE", "MOTION_EAST", True)
    else:
        _execute_mount_switch_action(get_active_indi_device("mount"), "TELESCOPE_MOTION_WE", "MOTION_EAST", False)


def handle_mount_step_up(pressed: bool, source: str = "button") -> None:
    _debug_dispatch("MOUNT_STEP_UP", "MOUNT_STEP_UP", pressed, source)
    if not pressed:
        return

    driver_name = get_active_indi_device("mount")
    rates = get_mount_slew_rates(driver_name)
    if not rates:
        print(f"[receiver] no mount slew rates available for {driver_name}", flush=True)
        return

    current = get_current_mount_slew_rate(driver_name)
    if current not in rates:
        current_index = 0
    else:
        current_index = rates.index(current)
    next_index = min(len(rates) - 1, current_index + 1)
    set_mount_slew_rate(driver_name, rates[next_index])


def handle_mount_step_down(pressed: bool, source: str = "button") -> None:
    _debug_dispatch("MOUNT_STEP_DOWN", "MOUNT_STEP_DOWN", pressed, source)
    if not pressed:
        return

    driver_name = get_active_indi_device("mount")
    rates = get_mount_slew_rates(driver_name)
    if not rates:
        print(f"[receiver] no mount slew rates available for {driver_name}", flush=True)
        return

    current = get_current_mount_slew_rate(driver_name)
    if current not in rates:
        current_index = len(rates) - 1
    else:
        current_index = rates.index(current)
    previous_index = max(0, current_index - 1)
    set_mount_slew_rate(driver_name, rates[previous_index])


def handle_mount_stop(pressed: bool, source: str = "dpad") -> None:
    _debug_dispatch("MOUNT_STOP", "MOUNT_STOP", pressed, source)
    if pressed:
        _execute_mount_abort_action()


def handle_focus_in(pressed: bool, source: str = "button", step: int | None = None) -> None:
    _debug_dispatch("FOCUS_IN", "FOCUS_IN", pressed, source)
    if pressed:
        execute_focus_action("FOCUS_IN", step=step)


def handle_focus_out(pressed: bool, source: str = "button", step: int | None = None) -> None:
    _debug_dispatch("FOCUS_OUT", "FOCUS_OUT", pressed, source)
    if pressed:
        execute_focus_action("FOCUS_OUT", step=step)


def handle_focus_step_up(pressed: bool, source: str = "button") -> None:
    _debug_dispatch("FOCUS_STEP_UP", "FOCUS_STEP_UP", pressed, source)


def handle_focus_step_down(pressed: bool, source: str = "button") -> None:
    _debug_dispatch("FOCUS_STEP_DOWN", "FOCUS_STEP_DOWN", pressed, source)


def handle_focus_stop(pressed: bool, source: str = "button") -> None:
    _debug_dispatch("FOCUS_STOP", "FOCUS_STOP", pressed, source)


def handle_filterwheel_prev(pressed: bool, source: str = "button") -> None:
    _debug_dispatch("FILTERWHEEL_PREV", "FILTERWHEEL_PREV", pressed, source)
    if pressed:
        execute_filterwheel_action("FILTERWHEEL_PREV")


def handle_filterwheel_next(pressed: bool, source: str = "button") -> None:
    _debug_dispatch("FILTERWHEEL_NEXT", "FILTERWHEEL_NEXT", pressed, source)
    if pressed:
        execute_filterwheel_action("FILTERWHEEL_NEXT")


def _start_rotator_hold(direction: str, target_name: str) -> None:
    normalized = str(direction).upper()
    if not target_name:
        return
    stop_rotator_hold(normalized)
    _ROTATOR_RELEASE_COUNTS[normalized] = 0
    stop_event = threading.Event()
    _ROTATOR_HOLD_EVENTS[normalized] = stop_event
    thread = threading.Thread(
        target=_run_rotator_hold_loop,
        args=(normalized, target_name, stop_event),
        daemon=True,
    )
    thread.start()


def _start_rotator_abort_background(target_name: str | None = None) -> None:
    driver_name = (target_name or get_active_indi_device("rotator") or "").strip()
    if not driver_name:
        return
    thread = threading.Thread(target=execute_rotator_abort, args=(driver_name,), daemon=True)
    thread.start()


def _should_abort_rotator_release(direction: str) -> bool:
    normalized = str(direction).upper()
    previous = int(_ROTATOR_RELEASE_COUNTS.get(normalized, 0))
    _ROTATOR_RELEASE_COUNTS[normalized] = previous + 1
    return True


def handle_caa_rotate_counter_clockwise(pressed: bool, source: str = "button", angle: int | None = None) -> None:
    _debug_dispatch("CAA_ROTATE_COUNTER_CLOCKWISE", "CAA_ROTATE_COUNTER_CLOCKWISE", pressed, source)
    target_name = (get_active_indi_device("rotator") or "").strip()
    if pressed:
        _start_rotator_hold("CAA_ROTATE_COUNTER_CLOCKWISE", target_name)
        return
    stop_rotator_hold("CAA_ROTATE_COUNTER_CLOCKWISE")
    if _should_abort_rotator_release("CAA_ROTATE_COUNTER_CLOCKWISE"):
        _start_rotator_abort_background(target_name)


def handle_caa_rotate_clockwise(pressed: bool, source: str = "button", angle: int | None = None) -> None:
    _debug_dispatch("CAA_ROTATE_CLOCKWISE", "CAA_ROTATE_CLOCKWISE", pressed, source)
    target_name = (get_active_indi_device("rotator") or "").strip()
    if pressed:
        _start_rotator_hold("CAA_ROTATE_CLOCKWISE", target_name)
        return
    stop_rotator_hold("CAA_ROTATE_CLOCKWISE")
    if _should_abort_rotator_release("CAA_ROTATE_CLOCKWISE"):
        _start_rotator_abort_background(target_name)


def handle_caa_rotate_abort(pressed: bool, source: str = "button") -> None:
    _debug_dispatch("CAA_ROTATE_ABORT", "CAA_ROTATE_ABORT", pressed, source)
    if not pressed:
        _start_rotator_abort_background()


def handle_skymap_move(pressed: bool, source: str = "stick") -> None:
    _debug_dispatch("SKYMAP_MOVE", "SKYMAP_MOVE", pressed, source)


async def _get_skymap_rotation_async() -> float:
    if MessageBus is None or BusType is None:
        raise RuntimeError("dbus-next is required for KStars sky map operations")

    bus = MessageBus(bus_type=BusType.SESSION)
    await bus.connect()
    try:
        introspection = await bus.introspect("org.kde.kstars", "/KStars")
        proxy = bus.get_proxy_object("org.kde.kstars", "/KStars", introspection)
        interface = proxy.get_interface("org.kde.kstars")
        method = getattr(interface, "call_get_sky_map_rotation", None)
        if method is None:
            method = getattr(interface, "getSkyMapRotation", None)
        if method is None:
            raise AttributeError("org.kde.kstars does not expose getSkyMapRotation")
        value = await method()
        rotation = float(_dbus_value(value))
        return rotation
    finally:
        bus.disconnect()


async def _set_skymap_rotation_async(angle: float) -> None:
    if MessageBus is None or BusType is None:
        raise RuntimeError("dbus-next is required for KStars sky map operations")

    bus = MessageBus(bus_type=BusType.SESSION)
    await bus.connect()
    try:
        introspection = await bus.introspect("org.kde.kstars", "/KStars")
        proxy = bus.get_proxy_object("org.kde.kstars", "/KStars", introspection)
        interface = proxy.get_interface("org.kde.kstars")
        method = getattr(interface, "call_set_sky_map_rotation", None)
        if method is None:
            method = getattr(interface, "setSkyMapRotation", None)
        if method is None:
            raise AttributeError("org.kde.kstars does not expose setSkyMapRotation")
        await method(float(angle))
    finally:
        bus.disconnect()


def _wrap_skymap_rotation(angle: float) -> float:
    wrapped = float(angle) % 360.0
    if wrapped < 0.0:
        wrapped += 360.0
    return wrapped


def execute_skymap_rotate(direction: str) -> bool:
    direction = str(direction).strip().lower()
    if direction not in {"up", "down"}:
        raise ValueError(f"unsupported skymap rotation direction: {direction!r}")

    try:
        current_rotation = asyncio.run(_get_skymap_rotation_async())
        delta = 5.0 if direction == "up" else -5.0
        next_rotation = _wrap_skymap_rotation(current_rotation + delta)
        asyncio.run(_set_skymap_rotation_async(next_rotation))
        return True
    except Exception as exc:
        print(f"[receiver] KStars sky map rotate {direction} D-Bus call error: {exc}", flush=True)
        return False


async def _execute_skymap_zoom_action(method_name: str) -> None:
    if MessageBus is None or BusType is None:
        raise RuntimeError("dbus-next is required for KStars sky map operations")

    bus = MessageBus(bus_type=BusType.SESSION)
    await bus.connect()
    try:
        introspection = await bus.introspect("org.kde.kstars", "/KStars")
        proxy = bus.get_proxy_object("org.kde.kstars", "/KStars", introspection)
        interface = proxy.get_interface("org.kde.kstars")
        method = getattr(interface, f"call_{method_name}", None)
        if method is None:
            method = getattr(interface, method_name, None)
        if method is None:
            raise AttributeError(f"org.kde.kstars does not expose {method_name}")
        await method()
    finally:
        bus.disconnect()


def execute_skymap_zoom(direction: str) -> bool:
    direction = str(direction).strip().lower()
    if direction not in {"in", "out"}:
        raise ValueError(f"unsupported skymap zoom direction: {direction!r}")

    try:
        asyncio.run(_execute_skymap_zoom_action(f"zoom_{direction}"))
        return True
    except Exception as exc:
        print(f"[receiver] KStars sky map zoom {direction} D-Bus call error: {exc}", flush=True)
        return False


def handle_skymap_zoom_in(pressed: bool, source: str = "button") -> None:
    _debug_dispatch("SKYMAP_ZOOM_IN", "SKYMAP_ZOOM_IN", pressed, source)
    if pressed:
        execute_skymap_zoom("in")


def handle_skymap_zoom_out(pressed: bool, source: str = "button") -> None:
    _debug_dispatch("SKYMAP_ZOOM_OUT", "SKYMAP_ZOOM_OUT", pressed, source)
    if pressed:
        execute_skymap_zoom("out")


def handle_skymap_rotate_up(pressed: bool, source: str = "stick") -> None:
    _debug_dispatch("SKYMAP_ROTATE_UP", "SKYMAP_ROTATE_UP", pressed, source)
    if pressed:
        execute_skymap_rotate("up")


def handle_skymap_rotate_down(pressed: bool, source: str = "stick") -> None:
    _debug_dispatch("SKYMAP_ROTATE_DOWN", "SKYMAP_ROTATE_DOWN", pressed, source)
    if pressed:
        execute_skymap_rotate("down")


def handle_skymap_rotate(pressed: bool, source: str = "stick") -> None:
    _debug_dispatch("SKYMAP_ROTATE", "SKYMAP_ROTATE", pressed, source)


_DISPATCH_TABLE = {
    "MOUNT_NORTH": handle_mount_north,
    "MOUNT_SOUTH": handle_mount_south,
    "MOUNT_WEST": handle_mount_west,
    "MOUNT_EAST": handle_mount_east,
    "MOUNT_STEP_UP": handle_mount_step_up,
    "MOUNT_STEP_DOWN": handle_mount_step_down,
    "MOUNT_STOP": handle_mount_stop,
    "FOCUS_IN": handle_focus_in,
    "FOCUS_OUT": handle_focus_out,
    "FOCUS_STEP_UP": handle_focus_step_up,
    "FOCUS_STEP_DOWN": handle_focus_step_down,
    "FOCUS_STOP": handle_focus_stop,
    "FILTERWHEEL_PREV": handle_filterwheel_prev,
    "FILTERWHEEL_NEXT": handle_filterwheel_next,
    "CAA_ROTATE_COUNTER_CLOCKWISE": handle_caa_rotate_counter_clockwise,
    "CAA_ROTATE_CLOCKWISE": handle_caa_rotate_clockwise,
    "CAA_ROTATE_ABORT": handle_caa_rotate_abort,
    "SKYMAP_MOVE": handle_skymap_move,
    "SKYMAP_ZOOM_IN": handle_skymap_zoom_in,
    "SKYMAP_ZOOM_OUT": handle_skymap_zoom_out,
    "SKYMAP_ROTATE": handle_skymap_rotate,
    "SKYMAP_ROTATE_UP": handle_skymap_rotate_up,
    "SKYMAP_ROTATE_DOWN": handle_skymap_rotate_down,
}


def dispatch_abstract_action(action: str, pressed: bool, source: str = "unknown", step: int | None = None, angle: int | None = None) -> None:
    handler = _DISPATCH_TABLE.get(action)
    if handler is None:
        print(f"[receiver] unknown action: {action} pressed={pressed} source={source}", flush=True)
        return
    if action in {"FOCUS_IN", "FOCUS_OUT"}:
        handler(bool(pressed), str(source), step=step)
        return
    if action in {"CAA_ROTATE_CLOCKWISE", "CAA_ROTATE_COUNTER_CLOCKWISE"}:
        handler(bool(pressed), str(source), angle=angle)
        return
    if action == "CAA_ROTATE_ABORT":
        handler(bool(pressed), str(source))
        return
    if action in {"SKYMAP_ZOOM_IN", "SKYMAP_ZOOM_OUT", "SKYMAP_ROTATE_UP", "SKYMAP_ROTATE_DOWN"}:
        if bool(pressed):
            handler(True, str(source))
        return
    handler(bool(pressed), str(source))


class Receiver:
    def __init__(self, host: str = HOST, port: int = PORT, heartbeat_timeout: float = 5.0, log_heartbeat: bool = False, log_callback=None):
        self.host = host
        self.port = port
        self.heartbeat_timeout = heartbeat_timeout
        self.log_heartbeat = bool(log_heartbeat)
        self.log_callback = log_callback
        self._stop_event = threading.Event()

    def _emit_log(self, message: str, payload: dict | None = None):
        if message is None:
            return
        message = append_protocol_log_time(message, payload)
        if self.log_callback is not None:
            try:
                self.log_callback(timestamp_log_message(message))
                return
            except Exception:
                pass
        print(str(message), flush=True)

    @staticmethod
    def heartbeat_is_lost(last_seen: float, heartbeat_timeout: float, now: Optional[float] = None) -> bool:
        if now is None:
            now = time.monotonic()
        return (now - last_seen) > heartbeat_timeout

    def start(self):
        thread = threading.Thread(target=self._serve, daemon=True)
        thread.start()
        return thread

    def stop(self):
        self._stop_event.set()

    def _serve(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                server.bind((self.host, self.port))
            except OSError as exc:
                self._emit_log(
                    f"[receiver] cannot bind {self.host}:{self.port}: {exc}. "
                    "Another receiver may already be running on this port. Stop it or use another port."
                )
                return
            server.listen(5)
            self._emit_log(f"[receiver] listening on {self.host}:{self.port}")

            while not self._stop_event.is_set():
                try:
                    server.settimeout(0.5)
                    conn, addr = server.accept()
                except socket.timeout:
                    continue
                except OSError:
                    continue

                with conn:
                    self._emit_log(f"[receiver] connected from {addr}")
                    conn.settimeout(0.5)
                    heartbeat_lost = False
                    last_seen = time.monotonic()
                    recv_buffer = ""
                    while not self._stop_event.is_set():
                        try:
                            data = conn.recv(4096)
                        except socket.timeout:
                            if self.heartbeat_is_lost(last_seen, self.heartbeat_timeout):
                                if not heartbeat_lost:
                                    self._emit_log(
                                        f"[receiver] heartbeat timeout: no valid message for {self.heartbeat_timeout:.1f}s"
                                    )
                                    stop_rotator_hold()
                                    _start_rotator_abort_background()
                                    heartbeat_lost = True
                            continue
                        except OSError:
                            if not heartbeat_lost:
                                print(
                                    f"[receiver] heartbeat timeout: no valid message for {self.heartbeat_timeout:.1f}s",
                                    flush=True,
                                )
                                stop_rotator_hold()
                                _start_rotator_abort_background()
                                heartbeat_lost = True
                            break

                        if not data:
                            if not heartbeat_lost:
                                print(
                                    f"[receiver] heartbeat timeout: no valid message for {self.heartbeat_timeout:.1f}s",
                                    flush=True,
                                )
                                stop_rotator_hold()
                                _start_rotator_abort_background()
                                heartbeat_lost = True
                            break

                        recv_buffer += data.decode("utf-8", errors="replace")
                        lines, recv_buffer = _split_complete_json_lines(recv_buffer)
                        for line in lines:
                            if not line.strip():
                                continue
                            try:
                                obj = json.loads(line)
                                if obj.get("type") == "heartbeat":
                                    last_seen = time.monotonic()
                                    heartbeat_lost = False
                                    if self.log_heartbeat:
                                        self._emit_log(f"[receiver] heartbeat: {line}", payload=obj)
                                    continue
                                if obj.get("type") == "action":
                                    action = obj.get("action")
                                    pressed = bool(obj.get("pressed", False))
                                    source = obj.get("source", "unknown")
                                    step = obj.get("step")
                                    angle = obj.get("angle")
                                    try:
                                        step_value = int(step) if step is not None else None
                                    except (TypeError, ValueError):
                                        step_value = None
                                    try:
                                        angle_value = int(angle) if angle is not None else None
                                    except (TypeError, ValueError):
                                        angle_value = None
                                    self._emit_log(
                                        f"[receiver] action: {action} pressed={pressed} source={source} step={step_value} angle={angle_value}"
                                    )
                                    dispatch_abstract_action(action, pressed, source, step=step_value, angle=angle_value)
                                else:
                                    extract_dpad_state(obj)
                                last_seen = time.monotonic()
                                heartbeat_lost = False
                                print_debug_json("[receiver] json", obj)
                            except json.JSONDecodeError as exc:
                                self._emit_log(f"[receiver] invalid json: {line} ({exc})")


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--gui" in args or "-g" in args or not args:
        raise SystemExit(run_gui())

    receiver = Receiver()
    receiver.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("[receiver] stopped")
        receiver.stop()
