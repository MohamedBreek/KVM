import io
import unittest

from common import encode_event, decode_stream


class TestCommon(unittest.TestCase):
    def test_encode_decode_roundtrip(self):
        ev = {"kind": "key", "action": "down", "key": {"type": "char", "value": "a"}}
        b = encode_event(ev)
        # ensure it ends with newline and is valid utf-8 JSON
        self.assertTrue(b.endswith(b"\n"))
        buf = bytearray()
        buf.extend(b)
        items = list(decode_stream(buf))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0], ev)


if __name__ == "__main__":
    unittest.main()
