import argparse
import socket
import threading
import time
from typing import Optional

from pynput import keyboard, mouse
from common import encode_event


class RemoteSender:
    def __init__(self, port: int, bind: str = "0.0.0.0"):
        self.port = port
        self.bind = bind
        self.sock: Optional[socket.socket] = None
        self.conn: Optional[socket.socket] = None
        self.lock = threading.Lock()
        self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._accept_thread.start()

    def _accept_loop(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((self.bind, self.port))
            s.listen(1)
            print(f"[Server] Listening on {self.bind}:{self.port}")
            while True:
                conn, addr = s.accept()
                with self.lock:
                    if self.conn:
                        self.conn.close()
                    self.conn = conn
                print(f"[Server] Client connected from {addr}")

    def send(self, event: dict):
        with self.lock:
            conn = self.conn
        if not conn:
            return
        try:
            conn.sendall(encode_event(event))
        except Exception as e:
            print(f"[Server] Send error: {e}")
            with self.lock:
                try:
                    conn.close()
                except Exception:
                    pass
                self.conn = None


class KVMSwitch:
    def __init__(self, sender: RemoteSender):
        self.sender = sender
        self.active = "local"  # 'local' or 'remote'
        self.k_listener: Optional[keyboard.Listener] = None
        self.m_listener: Optional[mouse.Listener] = None
        self.k_controller = keyboard.Controller()
        self._start_listeners(suppress=False)

    def _start_listeners(self, suppress: bool):
        if self.k_listener:
            self.k_listener.stop()
        if self.m_listener:
            self.m_listener.stop()

        self.k_listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release,
            suppress=suppress,
        )
        self.m_listener = mouse.Listener(
            on_move=self._on_move,
            on_click=self._on_click,
            on_scroll=self._on_scroll,
            suppress=suppress,
        )
        self.k_listener.start()
        self.m_listener.start()

    def _switch(self, target: str):
        if target == self.active:
            return
        self.active = target
        self._start_listeners(suppress=(self.active == "remote"))
        print(f"[Server] Switched to {self.active.upper()}")

    def _is_toggle_key(self, key) -> Optional[str]:
        try:
            if key == keyboard.Key.f1:
                return "local"
            if key == keyboard.Key.f2:
                return "remote"
        except Exception:
            pass
        return None

    def _key_to_payload(self, key):
        try:
            if isinstance(key, keyboard.KeyCode) and key.char is not None:
                return {"type": "char", "value": key.char}
            else:
                return {"type": "special", "value": str(key).split(".")[-1]}
        except Exception as e:
            print(f"Error converting key: {e}")
            return {"type": "special", "value": "unknown"}

    def _on_key_press(self, key):
        target = self._is_toggle_key(key)
        if target:
            self._switch(target)
            return
        if self.active == "remote":
            self.sender.send({"kind": "key", "action": "down", "key": self._key_to_payload(key)})

    def _on_key_release(self, key):
        target = self._is_toggle_key(key)
        if target:
            return
        if self.active == "remote":
            self.sender.send({"kind": "key", "action": "up", "key": self._key_to_payload(key)})

    def _on_move(self, x, y):
        # We don’t handle absolute move here, handled separately
        pass

    def _on_click(self, x, y, button, pressed):
        if self.active != "remote":
            return
        self.sender.send({
            "kind": "mouse",
            "event": "click",
            "button": str(button).split(".")[-1],
            "action": "down" if pressed else "up",
        })

    def _on_scroll(self, x, y, dx, dy):
        if self.active != "remote":
            return
        self.sender.send({
            "kind": "mouse",
            "event": "scroll",
            "dx": dx,
            "dy": dy
        })


def main():
    parser = argparse.ArgumentParser(description="Software KVM - Server (Device A)")
    parser.add_argument("--bind", default="0.0.0.0", help="Address to bind on")
    parser.add_argument("--port", type=int, default=5001, help="Port number")
    args = parser.parse_args()

    sender = RemoteSender(port=args.port, bind=args.bind)
    switch = KVMSwitch(sender)

    # Separate listener for relative mouse move
    last = {"x": None, "y": None}

    def on_move(x, y):
        if switch.active != "remote":
            last["x"], last["y"] = x, y
            return
        if last["x"] is None:
            last["x"], last["y"] = x, y
            return
        dx = x - last["x"]
        dy = y - last["y"]
        last["x"], last["y"] = x, y
        if dx or dy:
            sender.send({"kind": "mouse", "event": "move", "dx": dx, "dy": dy})

    move_listener = mouse.Listener(on_move=on_move, suppress=False)
    move_listener.start()

    print(f"[Server] Running on {args.bind}:{args.port}. Press F1=LOCAL, F2=REMOTE")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[Server] Stopped")


if __name__ == "__main__":
    main()
