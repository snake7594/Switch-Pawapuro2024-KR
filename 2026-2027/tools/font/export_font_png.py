from pathlib import Path
import struct
import sys
import argparse

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rdblib


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RDB_DIR = Path(__file__).resolve().parent / "repack_out"
OUT_DIR = ROOT / "font_test"
COLS = 64


def sjis_indices(records):
    """Record indices for the 2024-compatible CP932 kanji sequence."""
    lo = bytes.fromhex("889f")
    hi = bytes.fromhex("94fc")
    keyed = []
    for i, (u, _, _) in enumerate(records):
        if not 0x4E00 <= u <= 0x9FFF:
            continue
        try:
            key = chr(u).encode("cp932")
        except UnicodeEncodeError:
            continue
        if len(key) == 2 and lo <= key <= hi:
            keyed.append((key, i))
    keyed.sort(key=lambda item: item[0])
    indices = [i for _, i in keyed]
    if len(indices) != 2350:
        raise RuntimeError(f"SJIS 한자 슬롯 수가 2350이 아닙니다: {len(indices)}")
    return indices


def parse_chunks(data):
    chunks = []
    pos = 0
    while True:
        magic = data.find(b"UNCDFONT", pos)
        if magic < 0:
            return chunks
        base = magic - 0x10
        count, width, height = struct.unpack_from("<III", data, base + 0x20)
        records = []
        for i in range(count):
            u, off, met = struct.unpack_from("<III", data, base + 0x3C + 12 * i)
            records.append((u, off, met))
        # Glyph offsets are relative to the UNCDFONT magic, not the chunk
        # header 0x10 bytes before it.
        chunks.append((base, magic, width, height, records))
        pos = magic + 8


def decode_glyph(data, base, width, height, off):
    size = width * height // 2
    raw = np.frombuffer(data[base + off:base + off + size], dtype=np.uint8)
    q = np.empty(width * height, dtype=np.uint8)
    # GBA-style 4bpp storage: the first pixel is the low nibble.
    q[0::2] = raw & 0x0F
    q[1::2] = raw >> 4
    return (q.reshape(height, width) * 17).astype(np.uint8)


def render_atlas(data, chunk, selected, out_path):
    base, data_base, width, height, records = chunk
    rows = (len(selected) + COLS - 1) // COLS
    atlas = np.zeros((rows * height, COLS * width), dtype=np.uint8)
    for i, record_index in enumerate(selected):
        _, off, _ = records[record_index]
        if off:
            glyph = decode_glyph(data, data_base, width, height, off)
            y, x = divmod(i, COLS)
            atlas[y * height:(y + 1) * height,
                  x * width:(x + 1) * width] = glyph
    cv2.imwrite(str(out_path), atlas)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, default=DEFAULT_RDB_DIR,
                    help="directory containing RES00.RDB/RES00.RDI")
    ap.add_argument("--prefix", default="COMMON_FONT",
                    help="output filename prefix")
    args = ap.parse_args()

    rdb = rdblib.RDB(str(args.source))
    body = rdb.read_body("COMMON_FONT.CHK")
    rdb.close()
    if body is None:
        raise RuntimeError("COMMON_FONT.CHK를 읽을 수 없습니다")
    chunks = parse_chunks(body)
    if len(chunks) < 2:
        raise RuntimeError("FNTL/FNTS 청크를 찾을 수 없습니다")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for chunk, name in zip(chunks[:2], ("fntl", "fnts")):
        _, _, width, height, records = chunk
        all_indices = list(range(len(records)))
        mapped = sjis_indices(records)
        render_atlas(body, chunk, all_indices,
                     OUT_DIR / f"{args.prefix}_{name}_full.png")
        render_atlas(body, chunk, mapped,
                     OUT_DIR / f"{args.prefix}_{name}_hangul2350.png")
        print(f"{name}: {width}x{height}, 전체 {len(all_indices)}개, "
              f"한글 매핑 {len(mapped)}개")


if __name__ == "__main__":
    main()
