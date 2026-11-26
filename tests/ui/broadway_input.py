"""Real keyboard and mouse input for the UI tests, through GTK's Broadway display server.

Broadway's web client sends input to the server over a WebSocket; this is a minimal
client doing the same with the standard library. Key presses then reach the app as real
GDK events and go through GTK's whole event dispatch (shortcuts, capture and bubble
phases, focus), unlike emitting "key-pressed" on one controller.

Protocol (gtk/gdk/broadway): each input message is a binary frame of big-endian int32s,
[event type, serial, time, ...]; key press is 7 and key release 8, followed by the
keysym and the modifier state. Pointer events (enter 0, move 2, button press 3, release 4)
carry the surface under the pointer, the surface the event is for, the root and surface
coordinates and the button/modifier state; enter adds the crossing mode, a button its number.
"""
from __future__ import annotations

import base64
import os
import socket
import struct
import sys
import threading
import time

ENTER, POINTER_MOVE, BUTTON_PRESS, BUTTON_RELEASE = 0, 2, 3, 4
KEY_PRESS, KEY_RELEASE, SCREEN_SIZE_CHANGED = 7, 8, 12
GRAB_NOTIFY, UNGRAB_NOTIFY, CONFIGURE_NOTIFY, ROUNDTRIP_NOTIFY = 9, 10, 11, 14
MASKS = {"shift": 1, "ctrl": 4, "alt": 8}
BUTTON_MASKS = {1: 1 << 8, 2: 1 << 9, 3: 1 << 10}

# Server commands: op (u8), serial (u32), then these fields (little-endian).
OP_GRAB, OP_UNGRAB, OP_NEW_SURFACE, OP_SHOW, OP_HIDE, OP_RAISE, OP_LOWER, OP_DESTROY = range(8)
OP_MOVE_RESIZE, OP_TRANSIENT, OP_DISCONNECTED, OP_UPDATE, OP_KEYBOARD = 8, 9, 10, 11, 12
OP_UPLOAD_TEXTURE, OP_RELEASE_TEXTURE, OP_SET_NODES, OP_ROUNDTRIP = 13, 14, 15, 16


class BroadwayInput:
    def __init__(self, address, width=1280, height=900):
        """address: the path of the server's unix socket (gtk4-broadwayd --unixsocket),
        or a TCP port on 127.0.0.1 (--port)."""
        if isinstance(address, int):
            self.sock = socket.create_connection(("127.0.0.1", address), timeout=5)
        else:
            self.sock = socket.socket(socket.AF_UNIX)
            self.sock.settimeout(5)
            self.sock.connect(str(address))
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((
            "GET /socket HTTP/1.1\r\n"
            "Host: localhost\r\n"
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
        self.surfaces = {}  # id -> [x, y, width, height]; written by the reader thread
        self.buttons = 0    # mask of the mouse buttons held down
        self.pos = (0, 0)   # where the pointer is, in the window's surface
        self.closed = None  # why the reader thread stopped, once it has
        self._time = 0      # the time stamp of the last event sent
        self._closing = False
        self._lock = threading.Lock()      # one frame at a time on the socket
        self._surfaces = threading.Lock()  # self.surfaces, shared with the reader thread
        self.sock.settimeout(None)
        # Answer the server the way the browser client does. Without roundtrip replies GTK's
        # frame clock stalls, and with it every animation (a revealer never opens).
        threading.Thread(target=self._read, daemon=True, name="broadway-input").start()
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
        except Exception as e:  # noqa: BLE001  (a thread can't raise into the tests)
            # Without this thread no frame is ever answered and every test would time out
            # one by one; say why instead (see _check).
            self.closed = f"{type(e).__name__}: {e}"
            if not self._closing:
                print(f"tests/ui/broadway_input.py: lost the Broadway display ({self.closed})", file=sys.stderr)

    def _check(self):
        if self.closed is not None:
            raise ConnectionError(f"the connection to Broadway is gone ({self.closed})")

    def _commands(self, data):
        pos = 0

        def take(fmt):
            nonlocal pos
            values = struct.unpack_from("<" + fmt, data, pos)
            pos += struct.calcsize("<" + fmt)
            return values

        while pos < len(data):
            op, self.serial = take("BI")
            if op == OP_DESTROY:
                sid = take("H")[0]
                with self._surfaces:
                    self.surfaces.pop(sid, None)
            elif op in (OP_SHOW, OP_HIDE, OP_RAISE, OP_LOWER, OP_KEYBOARD):
                take("H")
            elif op == OP_NEW_SURFACE:
                sid, x, y, w, h = take("HhhHH")
                with self._surfaces:
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
                moved = take("hh") if flags & 1 else None
                resized = take("HH") if flags & 2 else None
                with self._surfaces:
                    geo = self.surfaces.setdefault(sid, [0, 0, 0, 0])
                    if moved:
                        geo[0], geo[1] = moved
                    if resized:
                        geo[2], geo[3] = resized
                    geo = list(geo)
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
        """Send one event; returns its time stamp. The stamps only ever go up, so each
        event has its own: the app's events carry them (Gdk.Event.get_time()), which is
        how the tests tell that a key press or pointer movement has arrived."""
        self._check()
        with self._lock:
            self._time = stamp = max(int(time.monotonic() * 1000) & 0x7FFFFFFF, self._time + 1)
            payload = struct.pack(f">{3 + len(args)}i", event, self.serial & 0x7FFFFFFF, stamp, *args)
            mask = os.urandom(4)
            frame = bytes([0x82, 0x80 | len(payload)]) + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            self.sock.sendall(frame)
        return stamp

    def key(self, keysym, ctrl=False, shift=False, alt=False):
        """Press and release one key, with modifiers held. Returns the press's time stamp."""
        state = sum(MASKS[m] for m, on in (("ctrl", ctrl), ("shift", shift), ("alt", alt)) if on)
        stamp = self.send(KEY_PRESS, keysym, state)
        self.send(KEY_RELEASE, keysym, state)
        return stamp

    def main_surface(self):
        """(id, x, y, width, height) of the biggest surface: the app window (popovers are
        smaller ones)."""
        with self._surfaces:
            if not self.surfaces:
                raise ConnectionError("Broadway has shown no window yet")
            sid = max(self.surfaces, key=lambda s: self.surfaces[s][2] * self.surfaces[s][3])
            return (sid, *self.surfaces[sid])

    def _pointer(self, event, x, y, *extra):
        sid, sx, sy, _w, _h = self.main_surface()
        x, y = round(x), round(y)
        self.pos = (x, y)
        return self.send(event, sid, sid, sx + x, sy + y, x, y, self.buttons, *extra)

    def move(self, x, y):
        """Move the pointer to (x, y) in the window's surface, buttons held as they are.
        Like button(), returns the event's time stamp."""
        return self._pointer(POINTER_MOVE, x, y)

    def enter(self, x, y):
        return self._pointer(ENTER, x, y, 0)  # GDK_CROSSING_NORMAL

    def button(self, x, y, pressed, button=1):
        """Press or release a mouse button at (x, y) in the window's surface."""
        # The press or release itself carries the buttons as they were before it, as X11
        # and Wayland report it: GTK takes a press with no button in its state as the
        # start of a drag and keeps sending that drag's events to the widget pressed,
        # also from outside the window.
        if pressed:
            stamp = self._pointer(BUTTON_PRESS, x, y, button)
            self.buttons |= BUTTON_MASKS[button]
        else:
            stamp = self._pointer(BUTTON_RELEASE, x, y, button)
            self.buttons &= ~BUTTON_MASKS[button]
        # Then the server is told the new state at once, with a movement that goes nowhere.
        # It answers GDK's "which buttons are down?" from the last state it was sent, and
        # GTK asks that whenever it makes up a motion event of its own (after the layout
        # changes under the pointer). Without this, such an event right after a press said
        # "no button down", and the app ended the drag that had just begun: a drag test
        # failed whenever a layout happened to fall between the press and the first move.
        self._pointer(POINTER_MOVE, x, y)
        return stamp

    def close(self):
        self._closing = True
        try:
            self.sock.close()
        except OSError:
            pass
