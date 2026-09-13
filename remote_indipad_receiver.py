import asyncio
import json
import os
import queue
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

try:
    import ctypes
except ImportError:  # pragma: no cover - fallback for missing ctypes
    ctypes = None

try:
    from PySide6.QtCore import QObject, QTimer
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
    "rotator": "",
    "host": "0.0.0.0",
    "port": 50007,
    "heartbeat": False,
}

TELESCOPE_INTERFACE = 1 << 0
FOCUSER_INTERFACE = 1 << 3
FILTER_INTERFACE = 1 << 4
ROTATOR_INTERFACE = 1 << 12

try:
    from dbus_next.aio import MessageBus
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
    print(f"{label}: {rendered}", flush=True)


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


def set_active_indi_device(device_type: str, name: str | None) -> None:
    if device_type not in ACTIVE_INDI_DEVICE_NAMES:
        return
    ACTIVE_INDI_DEVICE_NAMES[device_type] = (name or "").strip()


def get_active_indi_device(device_type: str) -> str:
    return str(ACTIVE_INDI_DEVICE_NAMES.get(device_type, "") or "").strip()


def build_focus_gdbus_commands(driver_name: str, direction: str) -> list[list[str]]:
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

    return [
        [
            "gdbus", "call", "--session", "--dest", "org.kde.kstars",
            "--object-path", "/KStars/INDI", "--method",
            "org.kde.kstars.INDI.setSwitch",
            driver_name, "FOCUS_MOTION", motion, "On",
        ],
        [
            "gdbus", "call", "--session", "--dest", "org.kde.kstars",
            "--object-path", "/KStars/INDI", "--method",
            "org.kde.kstars.INDI.sendProperty",
            driver_name, "FOCUS_MOTION",
        ],
        [
            "gdbus", "call", "--session", "--dest", "org.kde.kstars",
            "--object-path", "/KStars/INDI", "--method",
            "org.kde.kstars.INDI.setNumber",
            driver_name, "REL_FOCUS_POSITION", "FOCUS_RELATIVE_POSITION", "100",
        ],
        [
            "gdbus", "call", "--session", "--dest", "org.kde.kstars",
            "--object-path", "/KStars/INDI", "--method",
            "org.kde.kstars.INDI.sendProperty",
            driver_name, "REL_FOCUS_POSITION",
        ],
    ]


def execute_focus_action(direction: str, driver_name: str | None = None) -> None:
    direction = str(direction).upper()
    target_name = (driver_name or get_active_indi_device("focuser") or "").strip()
    if not target_name:
        print(f"[receiver] no focuser selected; cannot execute {direction}", flush=True)
        return

    commands = build_focus_gdbus_commands(target_name, direction)
    for command in commands:
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                print(f"[receiver] {direction} command failed: {' '.join(command)}", flush=True)
                if result.stderr:
                    print(f"[receiver] {result.stderr.strip()}", flush=True)
                return
        except Exception as exc:
            print(f"[receiver] {direction} command error: {exc}", flush=True)
            return

    print(f"[receiver] executed {direction} on {target_name}", flush=True)


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

    return {
        "mount": str(loaded.get("mount", "") or ""),
        "focuser": str(loaded.get("focuser", "") or ""),
        "filter": str(loaded.get("filter", "") or ""),
        "rotator": str(loaded.get("rotator", "") or ""),
        "host": str(loaded.get("host", "0.0.0.0") or "0.0.0.0"),
        "port": port_value,
        "heartbeat": bool(loaded.get("heartbeat", False)),
    }


def save_gui_settings(settings: dict, path: str | Path | None = None):
    config_path = Path(path) if path is not None else GUI_SETTINGS_PATH
    port_value = settings.get("port", 50007)
    try:
        port_value = int(port_value)
    except (TypeError, ValueError):
        port_value = 50007

    payload = {
        "mount": str(settings.get("mount", "") or ""),
        "focuser": str(settings.get("focuser", "") or ""),
        "filter": str(settings.get("filter", "") or ""),
        "rotator": str(settings.get("rotator", "") or ""),
        "host": str(settings.get("host", "0.0.0.0") or "0.0.0.0"),
        "port": port_value,
        "heartbeat": bool(settings.get("heartbeat", False)),
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
        self.filter_combo.addItems(["Not scanned", "Filter Wheel 1", "Filter Wheel 2"])
        self.rotator_combo = QComboBox()
        self.rotator_combo.addItems(["Not scanned", "Rotator 1", "Rotator 2"])
        self.host_edit = QLineEdit(str(self.gui_settings.get("host", "0.0.0.0")))
        self.port_edit = QLineEdit(str(self.gui_settings.get("port", 50007)))

        self.heartbeat_checkbox = QCheckBox("Heartbeat log")
        self.heartbeat_checkbox.setChecked(bool(self.gui_settings.get("heartbeat", False)))

        form_layout.addRow("Mount", self.mount_combo)
        form_layout.addRow("Focuser", self.focuser_combo)
        form_layout.addRow("Filter Wheel", self.filter_combo)
        form_layout.addRow("Rotator", self.rotator_combo)
        host_port_row = QHBoxLayout()
        host_port_row.addWidget(self.host_edit)
        host_port_row.addWidget(self.port_edit)
        form_layout.addRow("Listening IP / Port", host_port_row)
        form_layout.addRow("Heartbeat", self.heartbeat_checkbox)

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

        main_layout.addLayout(form_layout)
        main_layout.addLayout(button_row)
        main_layout.addWidget(self.console)

        self.restore_saved_values()
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

    def _flush_log_queue(self):
        for message in self.log_queue.drain():
            self._append_log(message)

    def log(self, message: str):
        if threading.current_thread() is threading.main_thread():
            self._append_log(str(message))
            return
        self.log_queue.emit(str(message))

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
            "rotator": self.rotator_combo.currentText() if self.rotator_combo.count() else "",
            "host": self.host_edit.text().strip() or "0.0.0.0",
            "port": self.port_edit.text().strip() or "50007",
            "heartbeat": self.heartbeat_checkbox.isChecked(),
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


def handle_mount_north(pressed: bool, source: str = "dpad") -> None:
    _debug_dispatch("MOUNT_NORTH", "MOUNT_NORTH", pressed, source)


def handle_mount_south(pressed: bool, source: str = "dpad") -> None:
    _debug_dispatch("MOUNT_SOUTH", "MOUNT_SOUTH", pressed, source)


def handle_mount_west(pressed: bool, source: str = "dpad") -> None:
    _debug_dispatch("MOUNT_WEST", "MOUNT_WEST", pressed, source)


def handle_mount_east(pressed: bool, source: str = "dpad") -> None:
    _debug_dispatch("MOUNT_EAST", "MOUNT_EAST", pressed, source)


def handle_mount_step_up(pressed: bool, source: str = "button") -> None:
    _debug_dispatch("MOUNT_STEP_UP", "MOUNT_STEP_UP", pressed, source)


def handle_mount_step_down(pressed: bool, source: str = "button") -> None:
    _debug_dispatch("MOUNT_STEP_DOWN", "MOUNT_STEP_DOWN", pressed, source)


def handle_mount_stop(pressed: bool, source: str = "dpad") -> None:
    _debug_dispatch("MOUNT_STOP", "MOUNT_STOP", pressed, source)


def handle_focus_in(pressed: bool, source: str = "button") -> None:
    _debug_dispatch("FOCUS_IN", "FOCUS_IN", pressed, source)
    if pressed:
        execute_focus_action("FOCUS_IN")


def handle_focus_out(pressed: bool, source: str = "button") -> None:
    _debug_dispatch("FOCUS_OUT", "FOCUS_OUT", pressed, source)
    if pressed:
        execute_focus_action("FOCUS_OUT")


def handle_focus_step_up(pressed: bool, source: str = "button") -> None:
    _debug_dispatch("FOCUS_STEP_UP", "FOCUS_STEP_UP", pressed, source)


def handle_focus_step_down(pressed: bool, source: str = "button") -> None:
    _debug_dispatch("FOCUS_STEP_DOWN", "FOCUS_STEP_DOWN", pressed, source)


def handle_focus_stop(pressed: bool, source: str = "button") -> None:
    _debug_dispatch("FOCUS_STOP", "FOCUS_STOP", pressed, source)


def handle_caa_rotate_counter_clockwise(pressed: bool, source: str = "button") -> None:
    _debug_dispatch("CAA_ROTATE_COUNTER_CLOCKWISE", "CAA_ROTATE_COUNTER_CLOCKWISE", pressed, source)


def handle_caa_rotate_clockwise(pressed: bool, source: str = "button") -> None:
    _debug_dispatch("CAA_ROTATE_CLOCKWISE", "CAA_ROTATE_CLOCKWISE", pressed, source)


def handle_skymap_move(pressed: bool, source: str = "stick") -> None:
    _debug_dispatch("SKYMAP_MOVE", "SKYMAP_MOVE", pressed, source)


def handle_skymap_zoom(pressed: bool, source: str = "stick") -> None:
    _debug_dispatch("SKYMAP_ZOOM", "SKYMAP_ZOOM", pressed, source)


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
    "CAA_ROTATE_COUNTER_CLOCKWISE": handle_caa_rotate_counter_clockwise,
    "CAA_ROTATE_CLOCKWISE": handle_caa_rotate_clockwise,
    "SKYMAP_MOVE": handle_skymap_move,
    "SKYMAP_ZOOM": handle_skymap_zoom,
    "SKYMAP_ROTATE": handle_skymap_rotate,
}


def dispatch_abstract_action(action: str, pressed: bool, source: str = "unknown") -> None:
    handler = _DISPATCH_TABLE.get(action)
    if handler is None:
        print(f"[receiver] unknown action: {action} pressed={pressed} source={source}", flush=True)
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

    def _emit_log(self, message: str):
        if message is None:
            return
        if self.log_callback is not None:
            try:
                self.log_callback(str(message))
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
                    while not self._stop_event.is_set():
                        try:
                            data = conn.recv(4096)
                        except socket.timeout:
                            if self.heartbeat_is_lost(last_seen, self.heartbeat_timeout):
                                if not heartbeat_lost:
                                    self._emit_log(
                                        f"[receiver] heartbeat timeout: no valid message for {self.heartbeat_timeout:.1f}s"
                                    )
                                    heartbeat_lost = True
                            continue
                        except OSError:
                            if not heartbeat_lost:
                                print(
                                    f"[receiver] heartbeat timeout: no valid message for {self.heartbeat_timeout:.1f}s",
                                    flush=True,
                                )
                                heartbeat_lost = True
                            break

                        if not data:
                            if not heartbeat_lost:
                                print(
                                    f"[receiver] heartbeat timeout: no valid message for {self.heartbeat_timeout:.1f}s",
                                    flush=True,
                                )
                                heartbeat_lost = True
                            break

                        payload = data.decode("utf-8", errors="replace").strip()
                        if not payload:
                            continue
                        for line in payload.splitlines():
                            if not line.strip():
                                continue
                            try:
                                obj = json.loads(line)
                                if obj.get("type") == "heartbeat":
                                    last_seen = time.monotonic()
                                    heartbeat_lost = False
                                    if self.log_heartbeat:
                                        self._emit_log(f"[receiver] heartbeat: {line}")
                                    continue
                                if obj.get("type") == "action":
                                    action = obj.get("action")
                                    pressed = bool(obj.get("pressed", False))
                                    source = obj.get("source", "unknown")
                                    self._emit_log(f"[receiver] action: {action} pressed={pressed} source={source}")
                                    dispatch_abstract_action(action, pressed, source)
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
