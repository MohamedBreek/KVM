import argparse
import socket
from threading import Thread
from pynput import keyboard, mouse
from common import decode_stream

kctl = keyboard.Controller()
mctl = mouse.Controller()

SPECIAL_KEY_MAP = {name: getattr(keyboard.Key, name) for name in dir(keyboard.Key) if not name.startswith("_")}
BUTTON_MAP = {
	"left": mouse.Button.left,
	"right": mouse.Button.right,
	"middle": mouse.Button.middle,
	"x1": mouse.Button.x1 if hasattr(mouse.Button, "x1") else mouse.Button.left,
	"x2": mouse.Button.x2 if hasattr(mouse.Button, "x2") else mouse.Button.right,
}

def handle_event(evt):
	try:
		kind = evt.get("kind")
		if kind == "key":
			keyinfo = evt["key"]
			if keyinfo["type"] == "char":
				keyobj = keyinfo["value"]
			else:
				keyobj = SPECIAL_KEY_MAP.get(keyinfo["value"])
				if keyobj is None:
					print(f"Unknown key: {keyinfo['value']}")
					return
			if evt["action"] == "down":
				kctl.press(keyobj)
			else:
				kctl.release(keyobj)
		elif kind == "mouse":
			ev = evt.get("event")
			if ev == "move":
				dx = evt.get("dx", 0)
				dy = evt.get("dy", 0)
				if dx != 0 or dy != 0:
					mctl.move(dx, dy)
			elif ev == "click":
				btn = BUTTON_MAP.get(evt.get("button"))
				if not btn:
					print(f"Unknown mouse button: {evt.get('button')}")
					return
				if evt.get("action") == "down":
					mctl.press(btn)
				else:
					mctl.release(btn)
			elif ev == "scroll":
				dx = evt.get("dx", 0)
				dy = evt.get("dy", 0)
				mctl.scroll(dx, dy)
	except Exception as e:
		print(f"Error handling event: {e}")

def serve(port: int, bind: str):
	print(f"Client listening on {bind}:{port}")
	with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
		s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		s.bind((bind, port))
		s.listen(1)
		print("Waiting for connection...")
		while True:
			try:
				conn, addr = s.accept()
				print(f"Connected by {addr}")
				Thread(target=handle_conn, args=(conn,), daemon=True).start()
			except Exception as e:
				print(f"Error accepting connection: {e}")

def handle_conn(conn: socket.socket):
	buf = bytearray()
	with conn:
		while True:
			try:
				data = conn.recv(4096)
				if not data:
					print("Connection closed by peer")
					break
				buf.extend(data)
				for evt in decode_stream(buf):
					handle_event(evt)
			except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError) as e:
				print(f"Connection closed: {e}")
				break
			except Exception as e:
				print(f"Error in connection: {e}")
				break

def main():
	parser = argparse.ArgumentParser(description="Software KVM - Client (Device B)")
	parser.add_argument("--bind", default="192.168.0.105", help="IP address to bind to")
	parser.add_argument("--port", type=int, default=5001, help="Port number")
	args = parser.parse_args()
	
	try:
		serve(args.port, args.bind)
	except KeyboardInterrupt:
		print("\nClient stopped")
	except Exception as e:
		print(f"Error running client: {e}")

if __name__ == "__main__":
	main()