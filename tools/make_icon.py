#!/usr/bin/env python3
"""128x128 mod ikonu uretir (harici kutuphane gerektirmez).

Basit bir "gercekci dunya" sahnesi cizer: gokyuzu gradyani, gunes,
karli zirveli siradaglar ve deniz.
"""

import struct
import zlib
from pathlib import Path

W = H = 128
OUT = Path(__file__).resolve().parent.parent / \
    "src/main/resources/assets/realisticworld/icon.png"


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def ridge(x, seed, base, amp):
    """Deterministik dagsirti profili (ust uste binen ucgen dalgalar)."""
    h = 0.0
    for octave, freq in enumerate((0.055, 0.13, 0.31)):
        p = (x * freq + seed * (octave + 3) * 1.7) % 2.0
        tri = p if p < 1.0 else 2.0 - p
        h += tri * amp / (2 ** octave)
    return int(base - h)


rows = []
sea_y = 104
for y in range(H):
    row = bytearray()
    for x in range(W):
        t = y / H
        col = lerp((110, 165, 215), (205, 228, 240), t)          # gokyuzu
        if (x - 96) ** 2 + (y - 22) ** 2 <= 81:                  # gunes
            col = (250, 235, 170)
        back = ridge(x, 7.3, 92, 34)                             # arka sira
        front = ridge(x, 2.1, 108, 30)                           # on sira
        if y >= back:
            col = (128, 134, 146)
            if y <= back + 7 and back < 78:
                col = (240, 244, 248)                            # kar
        if y >= front:
            col = (86, 118, 74)                                  # yamac
            if y <= front + 5 and front < 88:
                col = (250, 252, 254)                            # kar
            elif y <= front + 2:
                col = (104, 96, 84)                              # sirt kayasi
        if y >= sea_y and y >= front:                            # deniz
            col = lerp((52, 96, 158), (24, 52, 108), (y - sea_y) / (H - sea_y))
        row += bytes(col)
    rows.append(bytes(row))

raw = b"".join(b"\x00" + r for r in rows)


def chunk(tag, data):
    c = tag + data
    return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c))


png = (b"\x89PNG\r\n\x1a\n"
       + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
       + chunk(b"IDAT", zlib.compress(raw, 9))
       + chunk(b"IEND", b""))
OUT.write_bytes(png)
print(f"yazildi: {OUT} ({len(png)} bayt)")
