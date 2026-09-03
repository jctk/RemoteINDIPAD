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


HOST = "127.0.0.1"
PORT = 50007

_DEBUG_JSON_CURSOR_SAVED = False
_DEBUG_JSON_LAST_LINES = 0


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


def format_debug_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def extract_dpad_state(payload):
    if not isinstance(payload, dict):
        return {"pressed": [], "all": []}

    buttons = payload.get("buttons", {})
    if not isinstance(buttons, dict):
        return {"pressed": [], "all": []}

    dpad_keys = [key for key in buttons if key.startswith("dpad_")]
    pressed = [key for key in dpad_keys if bool(buttons.get(key))]
    return {"pressed": pressed, "all": dpad_keys}


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


class Receiver:
    def __init__(self, host: str = HOST, port: int = PORT):
        self.host = host
        self.port = port
        self._stop_event = threading.Event()

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
                    while not self._stop_event.is_set():
                        try:
                            data = conn.recv(4096)
                        except socket.timeout:
                            continue
                        if not data:
                            break
                        payload = data.decode("utf-8", errors="replace").strip()
                        if not payload:
                            continue
                        for line in payload.splitlines():
                            if not line.strip():
                                continue
                            try:
                                obj = json.loads(line)
                                extract_dpad_state(obj)
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
