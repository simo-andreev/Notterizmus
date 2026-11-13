"""Real keyboard input for the UI tests, through GTK's Broadway display server.

Broadway's web client sends input to the server over a WebSocket; this is a minimal
client doing the same with the standard library. Key presses then reach the app as real
GDK events and go through GTK's whole event dispatch (shortcuts, capture and bubble
phases, focus), unlike emitting "key-pressed" on one controller.

Protocol (gtk/gdk/broadway): each input message is a binary frame of big-endian int32s,
[event type, serial, time, ...]; key press is 7 and key release 8, followed by the
keysym and the modifier state.
"""
from __future__ import annotations

import base64
import os
import socket
import struct
import threading
import time

KEY_PRESS, KEY_RELEASE, SCREEN_SIZE_CHANGED = 7, 8, 12
GRAB_NOTIFY, UNGRAB_NOTIFY, CONFIGURE_NOTIFY, ROUNDTRIP_NOTIFY = 9, 10, 11, 14
MASKS = {"shift": 1, "ctrl": 4, "alt": 8}

# Server commands: op (u8), serial (u32), then these fields (little-endian).
OP_GRAB, OP_UNGRAB, OP_NEW_SURFACE, OP_SHOW, OP_HIDE, OP_RAISE, OP_LOWER, OP_DESTROY = range(8)
OP_MOVE_RESIZE, OP_TRANSIENT, OP_DISCONNECTED, OP_UPDATE, OP_KEYBOARD = 8, 9, 10, 11, 12
OP_UPLOAD_TEXTURE, OP_RELEASE_TEXTURE, OP_SET_NODES, OP_ROUNDTRIP = 13, 14, 15, 16


class BroadwayInput:
    def __init__(self, port, width=1280, height=900):
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=5)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((
            "GET /socket HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{port}\r\n"
            "Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n"
            "Sec-WebSocket-Protocol: broadway\r\n\r\n").encode())
        reply = b""
        while b"\r\n\r\n" not in reply:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("Broadway closed the connection during the handshake")
            reply += chunk
        if b" 101 " not in reply.split(b"\r\n", 1)[0]:
            raise ConnectionError(f"Broadway refused the WebSocket: {reply[:80]!r}")
        self.serial = 0
        self.surfaces = {}  # id -> [x, y, width, height]
        self._lock = threading.Lock()
        self.sock.settimeout(None)
        # Answer the server the way the browser client does. Without roundtrip replies GTK's
        # frame clock stalls, and with it every animation (a revealer never opens).
        threading.Thread(target=self._read, daemon=True).start()
        self.send(SCREEN_SIZE_CHANGED, width, height, 1)

    def _read(self):
        try:
            while True:
                head = self._recv(2)
                length = head[1] & 0x7F
                if length == 126:
                    length = struct.unpack(">H", self._recv(2))[0]
                elif length == 127:
                    length = struct.unpack(">Q", self._recv(8))[0]
                payload = self._recv(length) if length else b""
                if head[0] & 0x0F == 2:
                    self._commands(payload)
        except OSError:
            pass

    def _commands(self, data):
        pos = 0

        def take(fmt):
            nonlocal pos
            values = struct.unpack_from("<" + fmt, data, pos)
            pos += struct.calcsize("<" + fmt)
            return values

        while pos < len(data):
            op, self.serial = take("BI")
            if op in (OP_SHOW, OP_HIDE, OP_RAISE, OP_LOWER, OP_DESTROY, OP_KEYBOARD):
                take("H")
            elif op == OP_NEW_SURFACE:
                sid, x, y, w, h = take("HhhHH")
                self.surfaces[sid] = [x, y, w, h]
                self.send(CONFIGURE_NOTIFY, sid, x, y, w, h)
            elif op == OP_TRANSIENT:
                take("HH")
            elif op == OP_ROUNDTRIP:
                sid, tag = take("HI")
                self._vblank()
                self.send(ROUNDTRIP_NOTIFY, sid, tag)
            elif op == OP_MOVE_RESIZE:
                sid, flags = take("HB")
                geo = self.surfaces.setdefault(sid, [0, 0, 0, 0])
                if flags & 1:
                    geo[0], geo[1] = take("hh")
                if flags & 2:
                    geo[2], geo[3] = take("HH")
                self.send(CONFIGURE_NOTIFY, sid, *geo)
            elif op == OP_UPLOAD_TEXTURE:
                _tid, size = take("II")
                pos += size
            elif op == OP_RELEASE_TEXTURE:
                take("I")
            elif op == OP_SET_NODES:
                _sid, count = take("HI")
                pos += count * 4
            elif op == OP_GRAB:
                take("HB")
                self.send(GRAB_NOTIFY)
            elif op == OP_UNGRAB:
                self.send(UNGRAB_NOTIFY)
            elif op in (OP_DISCONNECTED, OP_UPDATE):
                pass
            else:
                return  # unknown: skip the rest of this message

    def _vblank(self, hz=60):
        """Pace frames like a 60 Hz screen: unpaced, Broadway paints as fast as it can,
        catching frames no real screen would show."""
        period = 1 / hz
        now = time.monotonic()
        time.sleep(period - (now % period))

    def _recv(self, n):
        data = b""
        while len(data) < n:
            chunk = self.sock.recv(n - len(data))
            if not chunk:
                raise OSError("closed")
            data += chunk
        return data

    def send(self, event, *args):
        payload = struct.pack(f">{3 + len(args)}i", event, self.serial & 0x7FFFFFFF,
                              int(time.monotonic() * 1000) & 0x7FFFFFFF, *args)
        mask = os.urandom(4)
        frame = bytes([0x82, 0x80 | len(payload)]) + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        with self._lock:
            self.sock.sendall(frame)

    def key(self, keysym, ctrl=False, shift=False, alt=False):
        """Press and release one key, with modifiers held."""
        state = sum(MASKS[m] for m, on in (("ctrl", ctrl), ("shift", shift), ("alt", alt)) if on)
        self.send(KEY_PRESS, keysym, state)
        self.send(KEY_RELEASE, keysym, state)

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass
