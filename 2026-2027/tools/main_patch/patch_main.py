"""Patch the 2026 NSO main with mapped Korean strings.

Strings that fit their original NUL-reserved slot are replaced in place.  A
longer string is copied to an appended pool in the data segment; all matching
64/32-bit pointers and direct ARM64 ADRP+ADD references are redirected.  The
NSO data size is extended to include that pool, leaving the original text and
rodata offsets unchanged.
"""

from __future__ import annotations

import argparse
import json
import struct
from collections import Counter, defaultdict
from pathlib import Path

from main_strings import DEFAULT_FONT, NsoLayout


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MAIN = ROOT / "exefs" / "main"
DEFAULT_JSON = ROOT / "main_patch" / "main_strings_ko.json"
DEFAULT_OUT = ROOT / "main_patch" / "main_ko"


def align_up(value: int, alignment: int) -> int:
    return (value + alignment - 1) & ~(alignment - 1)


def safe_prefix(encoded: bytes, capacity: int) -> bytes:
    """Return a UTF-8-safe prefix which fits before a NUL terminator."""
    limit = max(0, capacity - 1)
    cut = encoded[:limit]
    while cut:
        try:
            cut.decode("utf-8")
            return cut
        except UnicodeDecodeError:
            cut = cut[:-1]
    return b""


def adrp_target(word: int, pc_mem: int) -> int | None:
    if word & 0x9F000000 != 0x90000000:
        return None
    imm = ((word >> 29) & 3) | (((word >> 5) & 0x7FFFF) << 2)
    if imm & (1 << 20):
        imm -= 1 << 21
    return (pc_mem & ~0xFFF) + (imm << 12)


def add_immediate(word: int, rn: int) -> tuple[int, int] | None:
    # ADD (immediate), both 32- and 64-bit forms.
    if word & 0x7F000000 != 0x11000000 or ((word >> 5) & 31) != rn:
        return None
    shift = (word >> 22) & 3
    if shift not in (0, 1):
        return None
    imm12 = (word >> 10) & 0xFFF
    return imm12, shift


def encode_adrp(old: int, pc_mem: int, target_mem: int) -> int:
    delta = (target_mem & ~0xFFF) - (pc_mem & ~0xFFF)
    if delta % 0x1000:
        raise ValueError("unaligned ADRP delta")
    imm = delta // 0x1000
    if not -(1 << 20) <= imm < (1 << 20):
        raise ValueError(f"ADRP target out of range: {imm}")
    word = old & ~0x60FFFFE0
    imm21 = imm & 0x1FFFFF
    word |= (imm21 & 3) << 29
    word |= (imm21 >> 2) << 5
    return word


def encode_add(old: int, target_mem: int, shift: int) -> int:
    low = target_mem & 0xFFF
    if shift == 1:
        if low:
            raise ValueError(f"ADD #imm12,lsl#12 cannot encode {target_mem:#x}")
        value = (target_mem >> 12) & 0xFFF
    else:
        value = low
    return (old & ~0x003FFC00) | (value << 10)


def code_references(
    data: bytearray,
    layout: NsoLayout,
    old_to_new: dict[int, int],
) -> tuple[int, int, list[dict]]:
    """Redirect direct ADRP+ADD pointers to moved strings."""
    start = layout.text_file + 0x20
    end = layout.text_file + layout.text_size - 16
    patched_pairs = 0
    failures = 0
    details: list[dict] = []
    for off in range(start, end, 4):
        old_adrp = int.from_bytes(data[off:off + 4], "little")
        pc_mem = layout.text_mem + off - layout.text_file
        page = adrp_target(old_adrp, pc_mem)
        if page is None:
            continue
        rd = old_adrp & 31
        for j in range(1, 5):
            add_off = off + 4 * j
            word = int.from_bytes(data[add_off:add_off + 4], "little")
            parsed = add_immediate(word, rd)
            if parsed is None:
                continue
            imm12, shift = parsed
            old_mem = page + (imm12 << 12 if shift == 1 else imm12)
            old_file = layout.mem_to_file(old_mem)
            if old_file not in old_to_new:
                continue
            new_mem = old_to_new[old_file]
            try:
                new_adrp = encode_adrp(old_adrp, pc_mem, new_mem)
                new_add = encode_add(word, new_mem, shift)
            except ValueError:
                failures += 1
                details.append({"kind": "ADRP+ADD", "offset": off, "old": old_file, "new_mem": new_mem})
                continue
            data[off:off + 4] = new_adrp.to_bytes(4, "little")
            data[add_off:add_off + 4] = new_add.to_bytes(4, "little")
            patched_pairs += 1
            details.append({"kind": "ADRP+ADD", "offset": off, "add_offset": add_off, "old": old_file, "new_mem": new_mem})
            break
    return patched_pairs, failures, details


def replace_pointer_values(
    data: bytearray,
    replacements: dict[int, int],
    ranges: list[tuple[int, int]],
) -> tuple[int, int]:
    """Replace exact 64-bit and 32-bit memory-pointer values.

    The executable's generated pointer tables are not uniformly aligned, so
    this deliberately scans byte offsets rather than assuming 8-byte alignment.
    Values are restricted to moved-string addresses, making accidental integer
    replacements vanishingly unlikely.
    """
    old32 = {old & 0xFFFFFFFF: new & 0xFFFFFFFF for old, new in replacements.items()}
    count64 = count32 = 0
    # Never scan executable text as raw integers: a 32-bit address can occur
    # inside an unrelated ARM64 instruction.  Direct text references are
    # handled by code_references(); generated pointer tables live in rodata or
    # data and may be unaligned there.
    for start, end in ranges:
        for off in range(start, end - 7):
            value = int.from_bytes(data[off:off + 8], "little")
            new = replacements.get(value)
            if new is not None:
                data[off:off + 8] = new.to_bytes(8, "little")
                count64 += 1
                continue
            if off < end - 3:
                value32 = value & 0xFFFFFFFF
                new32 = old32.get(value32)
                if new32 is not None:
                    data[off:off + 4] = new32.to_bytes(4, "little")
                    count32 += 1
    return count64, count32


def patch_main(main_path: Path, json_path: Path, out_path: Path) -> dict:
    source = main_path.read_bytes()
    buf = bytearray(source)
    layout = NsoLayout.from_bytes(source)
    obj = json.loads(json_path.read_text(encoding="utf-8"))
    records = obj["strings"]

    # Only patch strings whose game bytes differ.  Untranslated records retain
    # their Japanese bytes until a later translation pass fills them.
    work: list[tuple[dict, bytes]] = []
    preserve_skipped = 0
    preserve_status_counts: Counter[str] = Counter()
    for rec in records:
        # The refined review JSON marks runtime input/profanity dictionaries
        # and binary/debug false positives explicitly.  Keep their original
        # bytes even when a provisional Korean mapping is present; the field
        # is absent in the original JSON, so existing patch workflows are
        # unchanged.
        if (
            rec.get("patch_excluded")
            or rec.get("preserve_original")
            or rec.get("localization_target") == "no"
        ):
            preserve_skipped += 1
            preserve_status_counts[rec.get("target_status", "unspecified")] += 1
            continue
        text = rec.get("game_text", rec["text"])
        encoded = text.encode("utf-8")
        original = source[rec["offset"]:rec["offset"] + rec["byte_length"]]
        if encoded != original:
            work.append((rec, encoded))

    # A page-aligned appended pool remains in the data segment's address space;
    # the NSO data size is enlarged below.  Keep a small gap for alignment.
    old_end = layout.data_file + layout.data_size
    pool_mem = align_up(layout.data_mem + layout.data_size, 0x1000)
    pool_file = layout.data_file + (pool_mem - layout.data_mem)
    if pool_file > len(buf):
        buf.extend(b"\0" * (pool_file - len(buf)))
    elif pool_file < len(buf):
        # This should not occur for an uncompressed NSO, but avoid overwriting
        # a non-data trailer if one is present.
        pool_file = align_up(len(buf), 0x1000)
        buf.extend(b"\0" * (pool_file - len(buf)))
        pool_mem = layout.data_mem + (pool_file - layout.data_file)

    old_to_new_mem: dict[int, int] = {}
    moved: list[dict] = []
    inplace = 0
    skipped = 0
    for rec, encoded in work:
        off = rec["offset"]
        capacity = rec["capacity"]
        needed = len(encoded) + 1
        if needed <= capacity:
            slot = encoded + b"\0"
            buf[off:off + capacity] = slot + b"\0" * (capacity - len(slot))
            inplace += 1
            continue

        # Leave a safe, visibly Korean prefix in the old slot as a fallback
        # for an unrecognised reference, and put the complete string in the
        # appended pool for all redirected references.
        prefix = safe_prefix(encoded, capacity)
        old_slot = prefix + b"\0"
        buf[off:off + capacity] = old_slot + b"\0" * (capacity - len(old_slot))
        new_file = len(buf)
        new_mem = layout.data_mem + (new_file - layout.data_file)
        buf.extend(encoded + b"\0")
        old_mem = layout.file_to_mem(off)
        if old_mem is None:
            skipped += 1
            continue
        old_to_new_mem[old_mem] = new_mem
        moved.append({
            "offset": off,
            "new_file": new_file,
            "new_mem": new_mem,
            "old_mem": old_mem,
            "old_capacity": capacity,
            "new_bytes": len(encoded) + 1,
        })

    # Patch direct code references before pointer scanning.  The pointer scan
    # only touches exact old addresses and is independent of instruction data.
    old_to_new_file = {m["offset"]: m["new_mem"] for m in moved}
    code_patched, code_failures, code_details = code_references(buf, layout, old_to_new_file)

    ptr64, ptr32 = replace_pointer_values(
        buf,
        old_to_new_mem,
        [
            (layout.ro_file, layout.ro_file + layout.ro_size),
            (layout.data_file, layout.data_file + layout.data_size),
        ],
    )

    # Keep the output file's section model valid.  The original NSO has no
    # compressed sections and data_file + data_size equals the file length.
    new_data_size = len(buf) - layout.data_file
    struct.pack_into("<I", buf, 0x38, new_data_size)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(buf)

    report = {
        "input": str(main_path),
        "output": str(out_path),
        "input_size": len(source),
        "output_size": len(buf),
        "records_changed": len(work),
        "preserve_original_skipped": preserve_skipped,
        "preserve_original_status_counts": dict(preserve_status_counts),
        "inplace": inplace,
        "moved": len(moved),
        "skipped": skipped,
        "pool_file": pool_file,
        "pool_mem": pool_mem,
        "new_data_size": new_data_size,
        "code_adrp_add_patched": code_patched,
        "code_adrp_add_failures": code_failures,
        "pointer64_patched": ptr64,
        "pointer32_patched": ptr32,
        "moved_records": moved,
        "code_details": code_details,
    }
    report_path = out_path.with_suffix(out_path.suffix + ".report.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--main", type=Path, default=DEFAULT_MAIN)
    ap.add_argument("--json", type=Path, default=DEFAULT_JSON)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()
    report = patch_main(args.main, args.json, args.out)
    print(json.dumps({k: v for k, v in report.items() if k not in ("moved_records", "code_details")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
