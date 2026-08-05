from pathlib import Path
import struct
import cv2
import numpy as np
from fontTools.ttLib import TTFont
from fontTools.pens.basePen import BasePen
from fontTools.pens.boundsPen import BoundsPen
import sys

ROOT = Path(__file__).resolve().parents[2]
TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import rdblib

# Requested final font: Binggrae regular.
FONT = ROOT / "Binggrae_TTF" / "Binggrae.ttf"
ORIG_DIR = ROOT / "romfs" / "cdvdroot"
OUT_CHK = Path(__file__).resolve().parent / "repack_in" / "COMMON_FONT.CHK"
PREVIEW = ROOT / "font_test" / "font_preview_regular.png"


def hangul_2350():
    out = []
    for lead in range(0xB0, 0xC9):
        for trail in range(0xA1, 0xFF):
            try:
                ch = bytes([lead, trail]).decode("euc_kr")
            except UnicodeDecodeError:
                continue
            if ch not in out:
                out.append(ch)
    assert len(out) == 2350
    return out


def sjis_targets(records):
    """Return the 2350 Japanese slots used by the 2024 Korean font map.

    The game table is stored in Unicode order, but the 2024 replacement map
    follows the JIS/Shift-JIS kanji sequence.  Its 2350 slots are the valid
    CP932 kanji encodings from 0x889F through 0x94FC, inclusive.
    """
    lo = bytes.fromhex("889f")
    hi = bytes.fromhex("94fc")
    keyed = []
    for u in records:
        if not 0x4E00 <= u <= 0x9FFF:
            continue
        try:
            key = chr(u).encode("cp932")
        except UnicodeEncodeError:
            continue
        if len(key) == 2 and lo <= key <= hi:
            keyed.append((key, u))
    keyed.sort(key=lambda item: item[0])
    targets = [u for _, u in keyed]
    assert len(targets) == 2350, len(targets)
    return targets


class OutlinePen(BasePen):
    def __init__(self, glyphSet):
        super().__init__(glyphSet)
        self.contours = []
        self.cur = None
        self.path = None

    def _moveTo(self, p):
        self.path = [p]
        self.contours.append(self.path)
        self.cur = p

    def _lineTo(self, p):
        self.path.append(p)
        self.cur = p

    def _curveToOne(self, p1, p2, p3):
        p0 = self.cur
        for j in range(1, 17):
            t = j / 16.0
            u = 1.0 - t
            self.path.append((u**3*p0[0] + 3*u*u*t*p1[0] + 3*u*t*t*p2[0] + t**3*p3[0],
                              u**3*p0[1] + 3*u*u*t*p1[1] + 3*u*t*t*p2[1] + t**3*p3[1]))
        self.cur = p3

    def _qCurveToOne(self, p1, p2):
        p0 = self.cur
        for j in range(1, 17):
            t = j / 16.0
            u = 1.0 - t
            self.path.append((u*u*p0[0] + 2*u*t*p1[0] + t*t*p2[0],
                              u*u*p0[1] + 2*u*t*p1[1] + t*t*p2[1]))
        self.cur = p2

    def _closePath(self):
        self.cur = None
        self.path = None

    def _endPath(self):
        self.cur = None
        self.path = None


def render_glyph(glyphSet, glyphName, slot, px_scale, left_shift=0):
    pen = OutlinePen(glyphSet)
    glyphSet[glyphName].draw(pen)
    mask = np.zeros((slot * 8, slot * 8), np.uint8)
    polys = []
    for contour in pen.contours:
        if len(contour) >= 3:
            polys.append(np.array(contour, dtype=np.float32))
    if not polys:
        return bytes(slot * slot // 2), mask[::8, ::8]

    allpts = np.concatenate(polys)
    xmin, ymin = allpts.min(axis=0)
    xmax, ymax = allpts.max(axis=0)
    iw = (xmax - xmin) * px_scale
    ih = (ymax - ymin) * px_scale
    ox = (slot - iw) / 2.0 + left_shift
    oy = (slot - ih) / 2.0
    transformed = []
    for poly in polys:
        q = np.empty_like(poly)
        q[:, 0] = (poly[:, 0] - xmin) * px_scale + ox
        q[:, 1] = (ymax - poly[:, 1]) * px_scale + oy
        transformed.append(np.round(q * 8).astype(np.int32))
    # XOR contours so counters remain holes.
    for poly in transformed:
        layer = np.zeros_like(mask)
        cv2.fillPoly(layer, [poly], 255)
        mask ^= layer
    small = cv2.resize(mask, (slot, slot), interpolation=cv2.INTER_AREA)
    q = np.clip(np.rint(small.astype(np.float32) * 15 / 255), 0, 15).astype(np.uint8)
    # GBA-style 4bpp storage: the first pixel is the low nibble.
    packed = (q[:, 0::2] | (q[:, 1::2] << 4)).tobytes()
    return packed, small


def parse_chunks(data):
    out = []
    pos = 0
    while True:
        magic = data.find(b"UNCDFONT", pos)
        if magic < 0:
            return out
        base = magic - 0x10
        count = struct.unpack_from("<I", data, base + 0x20)[0]
        width = struct.unpack_from("<I", data, base + 0x24)[0]
        height = struct.unpack_from("<I", data, base + 0x28)[0]
        records = {}
        for k in range(count):
            u, off, met = struct.unpack_from("<III", data, base + 0x3C + 12*k)
            records[u] = (off, met)
        # Glyph offsets in this format are relative to the UNCDFONT magic
        # (the chunk's +0x10 position), not to the preceding chunk header.
        out.append((base, magic, width, height, records))
        pos = magic + 8


def main():
    font = TTFont(str(FONT))
    glyphSet = font.getGlyphSet()
    cmap = {}
    for table in font["cmap"].tables:
        if table.isUnicode():
            cmap.update(table.cmap)
    hangul = hangul_2350()
    R = rdblib.RDB(str(ORIG_DIR))
    body = bytearray(R.read_body("COMMON_FONT.CHK"))
    R.close()
    chunks = parse_chunks(body)
    targets = sjis_targets(chunks[0][4])
    bounds = []
    for ch in hangul:
        pen = BoundsPen(glyphSet)
        glyphSet[cmap[ord(ch)]].draw(pen)
        if pen.bounds:
            bounds.append(pen.bounds)
    max_width = max(x2 - x1 for x1, y1, x2, y2 in bounds)
    max_height = max(y2 - y1 for x1, y1, x2, y2 in bounds)
    # Use one uniform scale per atlas. Leave only one pixel on each side so
    # the largest glyph fits without clipping while all glyphs share the
    # same point size.
    max_extent = max(max_width, max_height)
    preview = np.zeros((5*56, 20*56), np.uint8)
    for ci, (base, data_base, width, height, records) in enumerate(chunks[:2]):
        assert (width, height) in ((56, 56), (44, 44))
        slot = width * height // 2
        scale = (width - 2.0) / max_extent
        for idx, (u, ch) in enumerate(zip(targets, hangul)):
            off, _ = records[u]
            glyphName = cmap[ord(ch)]
            # NanumSquareRoundB is centered in the same em-sized slot as the
            # original CJK glyphs; keep the initial pass metrically neutral.
            packed, small = render_glyph(glyphSet, glyphName, width, scale, left_shift=0)
            assert len(packed) == slot
            start = data_base + off
            body[start:start+slot] = packed
            if ci == 0 and idx < 100:
                y, x = divmod(idx, 20)
                preview[y*56:(y+1)*56, x*56:(x+1)*56] = small
    OUT_CHK.parent.mkdir(exist_ok=True)
    file_header = b"COMMON_FONT.CHK" + b"\x00" * (32 - len(b"COMMON_FONT.CHK"))
    OUT_CHK.write_bytes(file_header + body)
    cv2.imwrite(str(PREVIEW), preview)
    print(f"NanumSquareRoundB 적용: {len(targets)}개, 출력 {OUT_CHK}")


if __name__ == "__main__":
    main()
