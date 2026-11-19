"""VESC Tool's side of the firmware's UART protocol (comm/packet.c, comm/commands.c) on USART3, where the default app
(APP_UART, 115200) listens. Scripted host: asks for the firmware version, polls COMM_GET_VALUES, sends COMM_SET_DUTY."""
import struct

COMM_FW_VERSION, COMM_GET_VALUES, COMM_SET_DUTY, COMM_SET_CURRENT = 0, 4, 5, 6
# (seconds, duty): sent every 20 ms inside the firmware's 1 s app timeout
DUTY = [(8.0, 0.05), (9.0, 0.10), (10.0, 0.20), (11.0, 0.0)]


def crc16(b):
    c = 0
    for x in b:
        c ^= x << 8
        for _ in range(8):
            c = ((c << 1) ^ 0x1021) if c & 0x8000 else c << 1
            c &= 0xFFFF
    return c


def frame(p):
    head = bytes([2, len(p)]) if len(p) < 256 else bytes([3]) + struct.pack(">H", len(p))
    return head + p + struct.pack(">H", crc16(p)) + b"\x03"


class Peer:
    def __init__(self, ctx):
        self.ctx, self.buf, self.n, self.cmd = ctx, bytearray(), 0, None
        ctx.schedule_periodic(10_000)

    def send(self, cmd, body=b""):
        self.ctx.send(frame(bytes([cmd]) + body))

    def on_timer(self):
        t = self.n * 0.01
        self.n += 1
        if self.n % 50 == 0 and self.n < 1000:
            self.send(COMM_FW_VERSION)
        if self.n % 5 == 0:
            self.send(COMM_GET_VALUES)
        if t >= DUTY[0][0] and self.n % 2 == 0:
            d = [v for at, v in DUTY if t >= at][-1]
            if d != self.cmd:
                self.cmd = d
                self.ctx.info(f"CMD t={t:.2f} COMM_SET_DUTY {d}")
            self.send(COMM_SET_DUTY, struct.pack(">i", int(d * 100000)))

    def on_byte(self, b):
        self.buf.append(b)
        if self.buf[0] not in (2, 3):
            self.buf.clear()
            return
        hl = 2 if self.buf[0] == 2 else 3
        if len(self.buf) < hl:
            return
        n = self.buf[1] if hl == 2 else self.buf[1] << 8 | self.buf[2]
        if len(self.buf) < hl + n + 3:
            return
        p = bytes(self.buf[hl:hl + n])
        ok = struct.unpack(">H", self.buf[hl + n:hl + n + 2])[0] == crc16(p)
        self.buf.clear()
        if ok and p:
            self.packet(p)

    def packet(self, p):
        t = self.n * 0.01
        if p[0] == COMM_FW_VERSION:
            name = p[3:p.index(0, 3)].decode(errors="replace")
            self.ctx.info(f"FWV t={t:.2f} version={p[1]}.{p[2]:02d} hw={name}")
        elif p[0] == COMM_GET_VALUES and len(p) >= 54:
            g16 = lambda o, s: struct.unpack(">h", p[1 + o:3 + o])[0] / s
            g32 = lambda o, s: struct.unpack(">i", p[1 + o:5 + o])[0] / s
            self.ctx.info(f"VESC t={t:.2f} erpm={g32(22, 1):.0f} imot={g32(4, 100):.2f} ibat={g32(8, 100):.2f} "
                          f"iq={g32(16, 100):.2f} duty={g16(20, 1000):.3f} vin={g16(26, 10):.1f} "
                          f"tfet={g16(0, 10):.1f} fault={p[1 + 52]}")
