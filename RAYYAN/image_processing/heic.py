"""
قراءة HEIC (صور iPhone) دون pillow-heif — بديل احتياطي.
يحلل حاوية HEIF، ويستخرج بلاطات الصورة، ويفك ترميز HEVC بـ ffmpeg، ثم يجمعها ويطبق الدوران.
تُستخدم الملفات المؤقتة فقط؛ الملف الأصلي يُقرأ ولا يُعدَّل.
"""
from __future__ import annotations

import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

from PIL import Image


def boxes(buf: bytes, start: int, end: int):
    i = start
    while i < end:
        size, typ = struct.unpack(">I4s", buf[i:i + 8])
        hdr = 8
        if size == 1:
            size = struct.unpack(">Q", buf[i + 8:i + 16])[0]; hdr = 16
        elif size == 0:
            size = end - i
        yield typ.decode("latin1"), i + hdr, i + size
        i += size


def find(buf, start, end, typ):
    for t, s, e in boxes(buf, start, end):
        if t == typ:
            return s, e
    return None


def parse_heif(buf: bytes):
    meta = find(buf, 0, len(buf), "meta")
    ms, me = meta[0] + 4, meta[1]  # full box
    info = {"items": {}, "loc": {}, "props": [], "assoc": {}, "refs": {}}
    s, e = find(buf, ms, me, "pitm")
    ver = buf[s]
    info["primary"] = struct.unpack(">H" if ver == 0 else ">I", buf[s + 4:s + 6 if ver == 0 else s + 8])[0]
    idat = find(buf, ms, me, "idat")
    info["idat"] = idat[0] if idat else None
    # iinf
    s, e = find(buf, ms, me, "iinf")
    ver = buf[s]; p = s + 4 + (2 if ver == 0 else 4)
    for t, bs, be in boxes(buf, p, e):
        v = buf[bs]
        if v >= 2:
            if v == 2:
                iid = struct.unpack(">H", buf[bs + 4:bs + 6])[0]; q = bs + 8
            else:
                iid = struct.unpack(">I", buf[bs + 4:bs + 8])[0]; q = bs + 10
            info["items"][iid] = buf[q:q + 4].decode("latin1")
    # iloc
    s, e = find(buf, ms, me, "iloc")
    ver = buf[s]; p = s + 4
    b1, b2 = buf[p], buf[p + 1]; p += 2
    off_sz, len_sz, base_sz = b1 >> 4, b1 & 15, b2 >> 4
    idx_sz = (b2 & 15) if ver in (1, 2) else 0
    rd = lambda n, q: (int.from_bytes(buf[q:q + n], "big") if n else 0, q + n)
    cnt, p = rd(2 if ver < 2 else 4, p)
    for _ in range(cnt):
        iid, p = rd(2 if ver < 2 else 4, p)
        method = 0
        if ver in (1, 2):
            m, p = rd(2, p); method = m & 15
        _, p = rd(2, p)  # data ref idx
        base, p = rd(base_sz, p)
        ec, p = rd(2, p)
        exts = []
        for _ in range(ec):
            _, p = rd(idx_sz, p)
            off, p = rd(off_sz, p); ln, p = rd(len_sz, p)
            exts.append((base + off, ln))
        info["loc"][iid] = (method, exts)
    # iprp
    s, e = find(buf, ms, me, "iprp")
    cs, ce = find(buf, s, e, "ipco")
    for t, bs, be in boxes(buf, cs, ce):
        info["props"].append((t, bs, be))
    s2, e2 = find(buf, s, e, "ipma")
    ver, flags = buf[s2], int.from_bytes(buf[s2 + 1:s2 + 4], "big"); p = s2 + 4
    n = struct.unpack(">I", buf[p:p + 4])[0]; p += 4
    for _ in range(n):
        if ver < 1:
            iid = struct.unpack(">H", buf[p:p + 2])[0]; p += 2
        else:
            iid = struct.unpack(">I", buf[p:p + 4])[0]; p += 4
        k = buf[p]; p += 1; lst = []
        for _ in range(k):
            if flags & 1:
                v = struct.unpack(">H", buf[p:p + 2])[0] & 0x7FFF; p += 2
            else:
                v = buf[p] & 0x7F; p += 1
            lst.append(v)
        info["assoc"][iid] = lst
    # iref (dimg)
    r = find(buf, ms, me, "iref")
    if r:
        ver = buf[r[0]]; p = r[0] + 4
        for t, bs, be in boxes(buf, p, r[1]):
            q = bs
            frm = struct.unpack(">H" if ver == 0 else ">I", buf[q:q + (2 if ver == 0 else 4)])[0]; q += 2 if ver == 0 else 4
            c = struct.unpack(">H", buf[q:q + 2])[0]; q += 2
            to = []
            for _ in range(c):
                to.append(struct.unpack(">H" if ver == 0 else ">I", buf[q:q + (2 if ver == 0 else 4)])[0]); q += 2 if ver == 0 else 4
            info["refs"].setdefault((t, frm), []).extend(to)
    return info


def item_data(buf, info, iid):
    method, exts = info["loc"][iid]
    if method == 0:  # من الملف مباشرة
        return b"".join(buf[o:o + l] for o, l in exts)
    if method == 1:  # من صندوق idat داخل meta
        base = info["idat"]
        return b"".join(buf[base + o:base + o + l] for o, l in exts)
    raise ValueError("iloc construction method غير مدعوم")


def item_prop(buf, info, iid, typ):
    for idx in info["assoc"].get(iid, []):
        if idx == 0:
            continue
        t, s, e = info["props"][idx - 1]
        if t == typ:
            return s, e
    return None


def hvcc_annexb(buf, s, e) -> bytes:
    p = s + 22
    n = buf[p]; p += 1
    out = b""
    for _ in range(n):
        p += 1
        k = struct.unpack(">H", buf[p:p + 2])[0]; p += 2
        for _ in range(k):
            ln = struct.unpack(">H", buf[p:p + 2])[0]; p += 2
            out += b"\x00\x00\x00\x01" + buf[p:p + ln]; p += ln
    return out


def to_annexb(data: bytes) -> bytes:
    out, i = b"", 0
    while i + 4 <= len(data):
        ln = struct.unpack(">I", data[i:i + 4])[0]
        out += b"\x00\x00\x00\x01" + data[i + 4:i + 4 + ln]; i += 4 + ln
    return out


def decode_hevc(buf, info, iid, tmp: Path) -> Image.Image:
    hs, he = item_prop(buf, info, iid, "hvcC")
    stream = hvcc_annexb(buf, hs, he) + to_annexb(item_data(buf, info, iid))
    src, dst = tmp / f"t{iid}.hevc", tmp / f"t{iid}.png"
    src.write_bytes(stream)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "hevc", "-i", str(src),
                    "-frames:v", "1", str(dst)], check=True)
    return Image.open(dst).convert("RGB")


def read_heic(src: Path) -> Image.Image:
    """يفك صورة HEIC ويعيدها كصورة Pillow (لا يكتب أي ملف بجانب الأصل)."""
    if not shutil.which("ffmpeg"):
        raise RuntimeError("صيغة HEIC تحتاج pillow-heif (pip install pillow-heif) أو ffmpeg")
    buf = src.read_bytes()
    info = parse_heif(buf)
    pid = info["primary"]
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        if info["items"][pid] == "grid":
            g = item_data(buf, info, pid)
            flags = g[1]; rows, cols = g[2] + 1, g[3] + 1
            fmt = ">I" if flags & 1 else ">H"; n = 4 if flags & 1 else 2
            W = struct.unpack(fmt, g[4:4 + n])[0]; H = struct.unpack(fmt, g[4 + n:4 + 2 * n])[0]
            tiles = [decode_hevc(buf, info, t, tmp) for t in info["refs"][("dimg", pid)]]
            tw, th = tiles[0].size
            canvas = Image.new("RGB", (cols * tw, rows * th))
            for k, t in enumerate(tiles):
                canvas.paste(t, ((k % cols) * tw, (k // cols) * th))
            img = canvas.crop((0, 0, W, H))
        else:
            img = decode_hevc(buf, info, pid, tmp)
    rot = item_prop(buf, info, pid, "irot")
    if rot:
        angle = (buf[rot[0]] & 3) * 90  # anticlockwise
        if angle:
            img = img.rotate(angle, expand=True)
    return img
