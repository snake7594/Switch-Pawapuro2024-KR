"""Extract and prepare UTF-8 strings from the 2026 NSO main executable.

The 2024 Korean patch does not put UTF-8 Hangul in the executable.  It puts
the Hangul syllables in the 2350 CJK slots which are replaced in the font
atlas.  This module therefore exposes the same two conversions:

    Japanese UTF-8 -> Korean UTF-8 (JSON)
    Korean UTF-8 -> mapped CJK UTF-8 (game bytes)

The patcher keeps offsets and capacities in the JSON.  A later stage can move
an over-capacity string into an appended pool and update its references.
"""

from __future__ import annotations

import argparse
import json
import re
import struct
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable


WORKSPACE = Path(__file__).resolve().parents[2]
DEFAULT_MAIN = WORKSPACE / "exefs" / "main"
DEFAULT_FONT = WORKSPACE / "font_test" / "tools" / "repack_in" / "COMMON_FONT.CHK"


@dataclass(frozen=True)
class NsoLayout:
    text_file: int
    text_mem: int
    text_size: int
    ro_file: int
    ro_mem: int
    ro_size: int
    data_file: int
    data_mem: int
    data_size: int
    bss_size: int

    @classmethod
    def from_bytes(cls, data: bytes) -> "NsoLayout":
        if data[:4] != b"NSO0":
            raise ValueError("not an NSO0 file")
        u = lambda off: struct.unpack_from("<I", data, off)[0]
        return cls(
            u(0x10), u(0x14), u(0x18),
            u(0x20), u(0x24), u(0x28),
            u(0x30), u(0x34), u(0x38), u(0x3C),
        )

    def file_to_mem(self, off: int) -> int | None:
        if self.ro_file <= off < self.ro_file + self.ro_size:
            return self.ro_mem + off - self.ro_file
        if self.data_file <= off < self.data_file + self.data_size:
            return self.data_mem + off - self.data_file
        if self.text_file <= off < self.text_file + self.text_size:
            return self.text_mem + off - self.text_file
        return None

    def mem_to_file(self, addr: int) -> int | None:
        if self.ro_mem <= addr < self.ro_mem + self.ro_size:
            return self.ro_file + addr - self.ro_mem
        if self.data_mem <= addr < self.data_mem + self.data_size:
            return self.data_file + addr - self.data_mem
        if self.text_mem <= addr < self.text_mem + self.text_size:
            return self.text_file + addr - self.text_mem
        return None


def hangul_2350() -> list[str]:
    """Return the complete EUC-KR 2350 syllables in the game's order."""
    out: list[str] = []
    for lead in range(0xB0, 0xC9):
        for trail in range(0xA1, 0xFF):
            try:
                ch = bytes([lead, trail]).decode("euc_kr")
            except UnicodeDecodeError:
                continue
            if ch not in out:
                out.append(ch)
    if len(out) != 2350:
        raise AssertionError(len(out))
    return out


def _font_records(path: Path) -> list[int]:
    """Read the Unicode record table of the first UNCDFONT chunk."""
    data = path.read_bytes()
    # COMMON_FONT.CHK has a 32-byte file name header; COMMON_2D-o.CHK may be
    # supplied either with or without it.  Searching for the magic keeps this
    # independent of that wrapper.
    magic = data.find(b"UNCDFONT")
    if magic < 0:
        raise ValueError(f"UNCDFONT not found in {path}")
    base = magic - 0x10
    count = struct.unpack_from("<I", data, base + 0x20)[0]
    return [struct.unpack_from("<I", data, base + 0x3C + 12 * i)[0]
            for i in range(count)]


def sjis_targets(font_path: Path) -> list[int]:
    """Return the 2350 CP932/JIS slots used by the 2024 font patch."""
    lo, hi = bytes.fromhex("889f"), bytes.fromhex("94fc")
    keyed: list[tuple[bytes, int]] = []
    for u in _font_records(font_path):
        if not 0x4E00 <= u <= 0x9FFF:
            continue
        try:
            key = chr(u).encode("cp932")
        except UnicodeEncodeError:
            continue
        if len(key) == 2 and lo <= key <= hi:
            keyed.append((key, u))
    keyed.sort(key=lambda x: x[0])
    targets = [u for _, u in keyed]
    if len(targets) != 2350:
        raise AssertionError(f"expected 2350 SJIS slots, got {len(targets)}")
    return targets


def korean_to_cjk(font_path: Path) -> dict[str, str]:
    return dict(zip(hangul_2350(), map(chr, sjis_targets(font_path))))


def cjk_to_korean(font_path: Path) -> dict[str, str]:
    return {v: k for k, v in korean_to_cjk(font_path).items()}


def _printable_ratio(text: str) -> float:
    return sum(c.isprintable() or c in "\r\n\t" for c in text) / max(1, len(text))


def is_game_japanese(text: str) -> bool:
    # UTF-8 CJK/kana strings in rodata are the user-visible text pool.  A few
    # arbitrary binary sequences decode as UTF-8, so require at least one
    # Japanese/Kanji code point and a mostly printable string.
    jp = sum(("\u3040" <= c <= "\u30FF") or ("\u3400" <= c <= "\u9FFF")
             for c in text)
    return bool(jp and _printable_ratio(text) >= 0.70)


def scan_rodata(data: bytes) -> list[dict]:
    layout = NsoLayout.from_bytes(data)
    out: list[dict] = []
    start, end = layout.ro_file, layout.ro_file + layout.ro_size
    pos = start
    while pos < end:
        nul = data.find(b"\0", pos, end)
        if nul < 0:
            break
        raw = data[pos:nul]
        current = pos
        pos = nul + 1
        if not raw or len(raw) > 0x10000:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if not is_game_japanese(text):
            continue
        # A run of NULs is reserved space in several tables.  It is safe to
        # use that space before resorting to relocation, so record it as the
        # original slot capacity.
        z = nul + 1
        while z < end and data[z] == 0:
            z += 1
        capacity = z - current
        out.append({
            "offset": current,
            "byte_length": len(raw),
            "capacity": capacity,
            "text": text,
        })
    return out


def load_json_records(path: Path) -> list[dict]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(obj, dict):
        return obj["strings"]
    return obj


def extract_main(main_path: Path, out_path: Path) -> list[dict]:
    data = main_path.read_bytes()
    records = scan_rodata(data)
    obj = {
        "format": 1,
        "source": str(main_path),
        "encoding": "utf-8",
        "section": "rodata",
        "count": len(records),
        "strings": records,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return records


def _patched_text_at(data: bytes, off: int, section_end: int) -> str | None:
    nul = data.find(b"\0", off, section_end)
    if nul < 0:
        return None
    try:
        return data[off:nul].decode("utf-8")
    except UnicodeDecodeError:
        return None


def make_2024_dictionary(
    original_main: Path,
    patched_main: Path,
    original_font: Path,
) -> tuple[dict[str, str], dict[str, list[str]]]:
    """Recover Japanese->Korean text from the 2024 patched main.

    The patch keeps each string at its original offset.  The CJK code points
    in the patched file are converted back through the 2350 SJIS font map.
    """
    old = original_main.read_bytes()
    new = patched_main.read_bytes()
    old_layout = NsoLayout.from_bytes(old)
    new_layout = NsoLayout.from_bytes(new)
    if (old_layout.ro_file, old_layout.ro_size) != (new_layout.ro_file, new_layout.ro_size):
        raise ValueError("2024 original/patched rodata layout differs")
    cjk_to_ko = cjk_to_korean(original_font)
    candidates = scan_rodata(old)
    section_end = old_layout.ro_file + old_layout.ro_size
    variants: dict[str, Counter[str]] = defaultdict(Counter)
    for rec in candidates:
        patched = _patched_text_at(new, rec["offset"], section_end)
        if patched is None or patched == rec["text"]:
            continue
        decoded = "".join(cjk_to_ko.get(ch, ch) for ch in patched)
        # Padding NULs are outside the decoded text because the first NUL is
        # the logical string terminator.
        variants[rec["text"]][decoded] += 1
    dictionary: dict[str, str] = {}
    ambiguous: dict[str, list[str]] = {}
    for source, counter in variants.items():
        best = counter.most_common()
        dictionary[source] = best[0][0]
        if len(best) > 1:
            ambiguous[source] = [x[0] for x in best]
    return dictionary, ambiguous


def write_korean_json(
    records: list[dict],
    dictionary: dict[str, str],
    out_path: Path,
    *,
    extra_dictionary: dict[str, str] | None = None,
) -> dict:
    """Add Korean fields and mapped game text to extracted records."""
    mapping = dict(dictionary)
    if extra_dictionary:
        mapping.update(extra_dictionary)
    game_map = korean_to_cjk(DEFAULT_FONT)
    unsupported: Counter[str] = Counter()
    out: list[dict] = []
    known = 0
    for rec in records:
        ko = mapping.get(rec["text"], rec["text"])
        source = "2024" if rec["text"] in dictionary else ("extra" if extra_dictionary and rec["text"] in extra_dictionary else "untranslated")
        if source != "untranslated":
            known += 1
        encoded_chars: list[str] = []
        for ch in ko:
            if "\uAC00" <= ch <= "\uD7A3":
                mapped = game_map.get(ch)
                if mapped is None:
                    unsupported[ch] += 1
                    encoded_chars.append(ch)
                else:
                    encoded_chars.append(mapped)
            else:
                encoded_chars.append(ch)
        encoded = "".join(encoded_chars)
        item = dict(rec)
        item.update({
            "korean": ko,
            "game_text": encoded,
            "translation_source": source,
            "game_byte_length": len(encoded.encode("utf-8")),
            "needs_expansion": len(encoded.encode("utf-8")) + 1 > rec["capacity"],
        })
        out.append(item)
    obj = {
        "format": 2,
        "source": "2026 exefs/main",
        "encoding": "utf-8",
        "mapping": "SJIS 0x889F-0x94FC -> EUC-KR 2350",
        "count": len(out),
        "translated_count": known,
        "untranslated_count": len(out) - known,
        "unsupported_hangul": dict(unsupported),
        "strings": out,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return obj


def _find_2024_files() -> tuple[Path, Path, Path]:
    desktop = Path("C:/Users/Jay/Desktop/z")
    original = next(p for p in desktop.rglob("main") if p.is_file() and p.stat().st_size == 106034273 and "mods" not in str(p).lower())
    patched = WORKSPACE / "font_test" / "main2024_v14_patched"
    font = next(p for p in desktop.rglob("COMMON_2D-o.CHK") if p.is_file())
    return original, patched, font


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p_extract = sub.add_parser("extract")
    p_extract.add_argument("--main", type=Path, default=DEFAULT_MAIN)
    p_extract.add_argument("--out", type=Path, default=WORKSPACE / "main_patch" / "main_strings_ja.json")
    p_known = sub.add_parser("known")
    p_known.add_argument("--main", type=Path, default=DEFAULT_MAIN)
    p_known.add_argument("--ja", type=Path, default=WORKSPACE / "main_patch" / "main_strings_ja.json")
    p_known.add_argument("--out", type=Path, default=WORKSPACE / "main_patch" / "main_strings_ko.json")
    p_known.add_argument("--main24", type=Path)
    p_known.add_argument("--patched24", type=Path)
    p_known.add_argument("--font24", type=Path)
    args = parser.parse_args()

    if args.command == "extract":
        records = extract_main(args.main, args.out)
        print(json.dumps({"count": len(records), "out": str(args.out)}, ensure_ascii=False))
        return
    if args.command == "known":
        if not args.ja.exists():
            records = extract_main(args.main, args.ja)
        else:
            records = load_json_records(args.ja)
        main24, patched24, font24 = _find_2024_files()
        dictionary, ambiguous = make_2024_dictionary(
            args.main24 or main24, args.patched24 or patched24, args.font24 or font24
        )
        obj = write_korean_json(records, dictionary, args.out)
        (args.out.parent / "main_translation_2024_ambiguous.json").write_text(
            json.dumps(ambiguous, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
        print(json.dumps({"count": obj["count"], "translated": obj["translated_count"], "untranslated": obj["untranslated_count"], "out": str(args.out)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
