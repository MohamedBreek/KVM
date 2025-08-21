import argparse
import socket
import threading
import time
from typing import Optional

from pynput import keyboard, mouse

from common import encode_event

class RemoteSender:
	def __init__(self, host: str, port: int):
		self.host = host
		self.port = port
		self.sock: Optional[socket.socket] = None
		self.lock = threading.Lock()
		self._connect_thread = threading.Thread(target=self._connect_loop, daemon=True)
		self._connect_thread.start()

	def _connect_loop(self):
		while True:
			if self.sock is None:
				try:
					s = socket.create_connection((self.host, self.port), timeout=5)
					s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
					with self.lock:
						self.sock = s
					print(f"Connected to {self.host}:{self.port}")
				except Exception as e:
					print(f"Connection failed: {e}. Retrying in 2s...")
					time.sleep(2)
			time.sleep(0.5)

	def send(self, event: dict):
		with self.lock:
			s = self.sock
		if not s:
			return
		try:
			s.sendall(encode_event(event))
		except Exception as e:
			print(f"Send error: {e}")
			with self.lock:
				try:
					self.sock.close()
				except Exception:
					pass
				self.sock = None

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
		print(f"Switched to {self.active.upper()}")

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
		try:
			target = self._is_toggle_key(key)
			if target:
				self._switch(target)
				return
			if self.active == "remote":
				self.sender.send({"kind": "key", "action": "down", "key": self._key_to_payload(key)})
		except Exception as e:
			print(f"Error handling key press: {e}")

	def _on_key_release(self, key):
		try:
			target = self._is_toggle_key(key)
			if target:
				# already switched on press; ignore release
				return
			if self.active == "remote":
				self.sender.send({"kind": "key", "action": "up", "key": self._key_to_payload(key)})
		except Exception as e:
			print(f"Error handling key release: {e}")

	def _on_move(self, x, y):
		# We send relative moves to reduce jitter; pynput gives us absolute here; instead we track deltas.
		# For simplicity, we won't compute deltas from absolute; we'll just skip move if local.
		# Use on_move only when remote; client will move relatively by dx,dy from on_move calls.
		# pynput doesn't provide dx,dy directly; workaround: use a small accumulator with last pos.
		pass  # We will rely on on_move with deltas via a separate listener below.

	def _on_click(self, x, y, button, pressed):
		try:
			if self.active != "remote":
				return
			self.sender.send({
				"kind": "mouse",
				"event": "click",
				"button": str(button).split(".")[-1],
				"action": "down" if pressed else "up",
			})
		except Exception as e:
			print(f"Error handling click: {e}")

	def _on_scroll(self, x, y, dx, dy):
		try:
			if self.active != "remote":
				return
			self.sender.send({
				"kind": "mouse",
				"event": "scroll",
				"dx": dx,
				"dy": dy
			})
		except Exception as e:
			print(f"Error handling scroll: {e}")

def main():
	parser = argparse.ArgumentParser(description="Software KVM - Server (Device A)")
	parser.add_argument("--target", default="192.168.0.105", help="IP/hostname of Device B (default: 127.0.0.1 for local testing)")
	parser.add_argument("--port", type=int, default=5001, help="Port number")
	args = parser.parse_args()

	print(f"Starting server to connect to {args.target}:{args.port}")
	sender = RemoteSender(args.target, args.port)
	switch = KVMSwitch(sender)

	# Separate low-level mouse hook to compute relative movement deltas
	from pynput import _util
	last = {"x": None, "y": None}

	def on_move(x, y):
		try:
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
		except Exception as e:
			print(f"Error handling mouse movement: {e}")

	# A second listener only for move tracking, no suppression (suppression handled by main mouse listener)
	move_listener = mouse.Listener(on_move=on_move, suppress=False)
	move_listener.start()

	print("Server running. Press F1 for LOCAL, F2 for REMOTE (Device B).")
	try:
		while True:
			time.sleep(1)
	except KeyboardInterrupt:
		print("\nServer stopped")
	except Exception as e:
		print(f"Error running server: {e}")

if __name__ == "__main__":
	main()