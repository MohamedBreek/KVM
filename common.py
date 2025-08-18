import json

def encode_event(event: dict) -> bytes:
	return (json.dumps(event, separators=(",", ":")) + "\n").encode("utf-8")

def decode_stream(buffer: bytearray):
	while True:
		try:
			i = buffer.index(ord("\n"))
		except ValueError:
			return
		line = buffer[:i].decode("utf-8")
		del buffer[: i + 1]
		yield json.loads(line)