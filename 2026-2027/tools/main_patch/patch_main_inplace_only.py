"""Create a hardware-safe NSO patch without changing its layout.

The normal main patcher relocates strings that do not fit their original
reserved slots and grows the NSO data segment.  That is convenient for an
emulator, but some Switch loaders reject the resulting executable.  This
variant deliberately performs only bounded, in-place replacements: strings
whose mapped game bytes would exceed their original slot are left untouched.
No pointers, instructions, section headers, or file length are changed.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from main_strings import NsoLayout


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MAIN = ROOT / "exefs" / "main"
DEFAULT_JSON = ROOT / "main_patch" / "main_strings_ko_menu_compact_patch.json"
DEFAULT_OUT = ROOT / "main_patch" / "main_hw_safe"


def patch_main_inplace_only(main_path: Path, json_path: Path, out_path: Path) -> dict:
    source = main_path.read_bytes()
    layout = NsoLayout.from_bytes(source)
    obj = json.loads(json_path.read_text(encoding="utf-8"))
    records = obj["strings"] if isinstance(obj, dict) else obj
    buf = bytearray(source)

    changed = 0
    inplace = 0
    unchanged = 0
    excluded = 0
    overflow: list[dict] = []
    invalid: list[dict] = []
    status_counts: Counter[str] = Counter()

    for rec in records:
        if (
            rec.get("patch_excluded")
            or rec.get("preserve_original")
            or rec.get("localization_target") == "no"
        ):
            excluded += 1
            status_counts[rec.get("target_status", "unspecified")] += 1
            continue

        try:
            off = int(rec["offset"])
            capacity = int(rec["capacity"])
        except (KeyError, TypeError, ValueError):
            invalid.append({"record": rec, "reason": "invalid_offset_or_capacity"})
            continue
        if off < 0 or capacity <= 0 or off + capacity > len(source):
            invalid.append({"offset": off, "capacity": capacity, "reason": "outside_file"})
            continue

        text = rec.get("game_text", rec.get("text", ""))
        try:
            encoded = text.encode("utf-8")
        except UnicodeEncodeError as exc:
            invalid.append({"offset": off, "capacity": capacity, "reason": f"utf8:{exc}"})
            continue

        original_slot = source[off:off + capacity]
        original_text = source[off:off + int(rec.get("byte_length", 0))]
        if encoded == original_text and original_slot[len(encoded):].rstrip(b"\0") == b"":
            unchanged += 1
            continue

        needed = len(encoded) + 1
        if needed > capacity:
            overflow.append({
                "offset": off,
                "capacity": capacity,
                "needed": needed,
                "source": rec.get("text"),
                "korean": rec.get("korean"),
                "game_text": text,
                "target_status": rec.get("target_status"),
                "semantic_role": rec.get("semantic_role"),
            })
            continue

        slot = encoded + b"\0"
        buf[off:off + capacity] = slot + b"\0" * (capacity - len(slot))
        changed += 1
        inplace += 1

    # Explicitly assert that this script never changes the NSO section model.
    if len(buf) != len(source) or buf[:0x40][0:4] != b"NSO0":
        raise AssertionError("in-place patch changed file size or NSO magic")
    if buf[0x38:0x3C] != source[0x38:0x3C]:
        raise AssertionError("in-place patch changed NSO data size")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(buf)
    report = {
        "format": 1,
        "mode": "inplace_only_no_relocation",
        "input": str(main_path),
        "output": str(out_path),
        "json": str(json_path),
        "input_size": len(source),
        "output_size": len(buf),
        "layout_unchanged": True,
        "nso_layout": {
            "text_file": layout.text_file,
            "text_mem": layout.text_mem,
            "text_size": layout.text_size,
            "ro_file": layout.ro_file,
            "ro_mem": layout.ro_mem,
            "ro_size": layout.ro_size,
            "data_file": layout.data_file,
            "data_mem": layout.data_mem,
            "data_size": layout.data_size,
            "bss_size": layout.bss_size,
        },
        "records_total": len(records),
        "records_changed": changed,
        "inplace": inplace,
        "unchanged": unchanged,
        "preserve_original_skipped": excluded,
        "preserve_original_status_counts": dict(status_counts),
        "overflow_left_original": len(overflow),
        "invalid": len(invalid),
        "overflow_records": overflow,
        "invalid_records": invalid,
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
    report = patch_main_inplace_only(args.main, args.json, args.out)
    print(json.dumps({k: v for k, v in report.items() if k not in ("overflow_records", "invalid_records")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
