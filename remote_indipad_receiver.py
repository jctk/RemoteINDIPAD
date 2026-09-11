import json
import os
import socket
import threading
import time
from typing import Optional

try:
    import ctypes
except ImportError:  # pragma: no cover - fallback for missing ctypes
    ctypes = None


HOST = "0.0.0.0"
PORT = 50007



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


def _debug_dispatch(label: str, action: str, pressed: bool, source: str) -> None:
    print(f"[receiver] dispatch: {label} action={action} pressed={pressed} source={source}", flush=True)


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


def handle_focus_out(pressed: bool, source: str = "button") -> None:
    _debug_dispatch("FOCUS_OUT", "FOCUS_OUT", pressed, source)


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
    def __init__(self, host: str = HOST, port: int = PORT, heartbeat_timeout: float = 5.0):
        self.host = host
        self.port = port
        self.heartbeat_timeout = heartbeat_timeout
        self._stop_event = threading.Event()

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
                print(
                    f"[receiver] cannot bind {self.host}:{self.port}: {exc}. "
                    "Another receiver may already be running on this port. Stop it or use another port.",
                    flush=True,
                )
                return
            server.listen(5)
            print(f"[receiver] listening on {self.host}:{self.port}", flush=True)

            while not self._stop_event.is_set():
                try:
                    server.settimeout(0.5)
                    conn, addr = server.accept()
                except socket.timeout:
                    continue
                except OSError:
                    continue

                with conn:
                    print(f"[receiver] connected from {addr}", flush=True)
                    conn.settimeout(0.5)
                    heartbeat_lost = False
                    last_seen = time.monotonic()
                    while not self._stop_event.is_set():
                        try:
                            data = conn.recv(4096)
                        except socket.timeout:
                            if self.heartbeat_is_lost(last_seen, self.heartbeat_timeout):
                                if not heartbeat_lost:
                                    print(
                                        f"[receiver] heartbeat timeout: no valid message for {self.heartbeat_timeout:.1f}s",
                                        flush=True,
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
                                    continue
                                if obj.get("type") == "action":
                                    action = obj.get("action")
                                    pressed = bool(obj.get("pressed", False))
                                    source = obj.get("source", "unknown")
                                    dispatch_abstract_action(action, pressed, source)
                                else:
                                    extract_dpad_state(obj)
                                last_seen = time.monotonic()
                                heartbeat_lost = False
                                print_debug_json("[receiver] json", obj)
                            except json.JSONDecodeError as exc:
                                print(f"[receiver] invalid json: {line} ({exc})", flush=True)


if __name__ == "__main__":
    receiver = Receiver()
    receiver.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("[receiver] stopped")
        receiver.stop()
