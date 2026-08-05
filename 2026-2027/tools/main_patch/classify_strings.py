"""Classify extracted main strings using content and binary references.

The NSO header describes section boundaries, not the semantic type of each
string.  This tool therefore combines three independent signals:

* text shape (newlines, sentence punctuation, placeholders, identifier-like
  text, and length),
* direct ARM64 ADRP+ADD references from executable text, and
* exact 64/32-bit pointers found only in rodata/data (never in instructions).

The output is deliberately a review aid, not an automatic translation rule.
Short labels, names and templates are marked as likely non-dialogue while
long/newline strings are retained as prose/message candidates.
"""

from __future__ import annotations

import argparse
import json
import re
import struct
import sys
from collections import Counter
from pathlib import Path

try:
    import numpy as np
except ImportError:  # pragma: no cover - the bundled runtime has numpy
    np = None

from main_strings import NsoLayout


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MAIN = ROOT / "exefs" / "main"
DEFAULT_JSON = ROOT / "main_patch" / "main_strings_ko.json"
DEFAULT_OUT = ROOT / "main_patch" / "main_string_analysis.json"
DEFAULT_CANDIDATES_OUT = ROOT / "main_patch" / "main_non_dialogue_candidates.json"

FORMAT_RE = re.compile(r"%(?:[0-9$+\-.*]*)(?:[diuoxXfFeEgGcs])")
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_./\\:#$@+\-=%]+$")
INTERNAL_MARKER_RE = re.compile(
    r"(?:^|[_:#/\\])(?:DEV|DEBUG|TEST|RESULT|DATA|ID|KEY|NAME|TEXT|VOICE)(?:$|[_:#/\\0-9])",
    re.IGNORECASE,
)


def load_records(path: Path) -> list[dict]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    return obj["strings"] if isinstance(obj, dict) else obj


def section_name(layout: NsoLayout, offset: int) -> str:
    if layout.text_file <= offset < layout.text_file + layout.text_size:
        return "text"
    if layout.ro_file <= offset < layout.ro_file + layout.ro_size:
        return "rodata"
    if layout.data_file <= offset < layout.data_file + layout.data_size:
        return "data"
    return "outside"


def _is_cjk_or_kana(ch: str) -> bool:
    return ("\u3040" <= ch <= "\u30ff") or ("\u3400" <= ch <= "\u9fff")


def text_features(text: str, capacity: int) -> dict:
    no_nl = text.replace("\r", "").replace("\n", "")
    fmt = FORMAT_RE.findall(text)
    sentence = any(c in text for c in "。！？!?．")
    control = [c for c in text if ord(c) < 0x20 and c not in "\r\n\t"]
    cjk_kana = sum(_is_cjk_or_kana(c) for c in text)
    ascii_count = sum(ord(c) < 0x80 for c in text)
    lines = text.count("\n") + 1
    # The source text is used for semantic classification.  The translated
    # text may be longer or shorter, but this keeps the categories stable.
    name_like = (
        not text.count("\n")
        and not sentence
        and len(text) <= 10
        and cjk_kana >= max(1, len(text) // 2)
    )
    identifier_like = bool(IDENTIFIER_RE.fullmatch(text)) or bool(control)
    marker_like = bool(INTERNAL_MARKER_RE.search(text))
    template_like = bool(fmt) or "%" in text
    label_like = not text.count("\n") and not sentence and len(text) <= 24
    prose_like = bool(text.count("\n") or sentence or len(text) >= 30)
    return {
        "char_length": len(text),
        "line_count": lines,
        "has_newline": bool(text.count("\n")),
        "has_sentence_punctuation": sentence,
        "format_tokens": fmt,
        "has_control_code": bool(control),
        "cjk_kana_ratio": round(cjk_kana / max(1, len(text)), 4),
        "ascii_ratio": round(ascii_count / max(1, len(text)), 4),
        "capacity": capacity,
        "name_like": name_like,
        "identifier_like": identifier_like,
        "internal_marker_like": marker_like,
        "template_like": template_like,
        "label_like": label_like,
        "prose_like": prose_like,
    }


def direct_code_refs(data: bytes, layout: NsoLayout, offset_to_index: dict[int, int], count: int) -> list[int]:
    """Count direct ADRP+ADD references to candidate file offsets."""
    out = [0] * count
    start = layout.text_file + 0x20
    end = layout.text_file + layout.text_size - 16
    usable = (end - start) // 4 * 4
    if np is None:
        # A portable fallback; normally the numpy path is used.
        words = None
        for off in range(start, start + usable, 4):
            word = int.from_bytes(data[off:off + 4], "little")
            if word & 0x9F000000 != 0x90000000:
                continue
            imm = ((word >> 29) & 3) | (((word >> 5) & 0x7FFFF) << 2)
            if imm & (1 << 20):
                imm -= 1 << 21
            pc_mem = layout.text_mem + off - layout.text_file
            page = (pc_mem & ~0xFFF) + (imm << 12)
            rd = word & 31
            for j in range(1, 5):
                add = int.from_bytes(data[off + j * 4:off + j * 4 + 4], "little")
                if add & 0x7F000000 != 0x11000000 or ((add >> 5) & 31) != rd:
                    continue
                shift = (add >> 22) & 3
                if shift not in (0, 1):
                    continue
                imm12 = (add >> 10) & 0xFFF
                target = page + (imm12 << 12 if shift == 1 else imm12)
                file_off = layout.mem_to_file(target)
                idx = offset_to_index.get(file_off)
                if idx is not None:
                    out[idx] += 1
                break
        return out

    words = np.frombuffer(data, dtype="<u4", count=usable // 4, offset=start)
    candidates = np.nonzero((words & 0x9F000000) == 0x90000000)[0]
    for i in candidates.tolist():
        word = int(words[i])
        imm = ((word >> 29) & 3) | (((word >> 5) & 0x7FFFF) << 2)
        if imm & (1 << 20):
            imm -= 1 << 21
        off = start + i * 4
        pc_mem = layout.text_mem + off - layout.text_file
        page = (pc_mem & ~0xFFF) + (imm << 12)
        rd = word & 31
        for j in range(1, 5):
            add = int(words[i + j])
            if add & 0x7F000000 != 0x11000000 or ((add >> 5) & 31) != rd:
                continue
            shift = (add >> 22) & 3
            if shift not in (0, 1):
                continue
            imm12 = (add >> 10) & 0xFFF
            target = page + (imm12 << 12 if shift == 1 else imm12)
            file_off = layout.mem_to_file(target)
            idx = offset_to_index.get(file_off)
            if idx is not None:
                out[idx] += 1
            break
    return out


def _pointer_scan_numpy(
    data: bytes,
    ranges: list[tuple[int, int]],
    mems: list[int],
    width: int,
) -> list[int]:
    """Find unaligned exact candidate addresses in the supplied ranges."""
    if np is None:
        raise RuntimeError("numpy is required for the pointer scan")
    n = len(mems)
    # mems are in file-offset order, hence sorted and index-stable.
    addresses = np.asarray(mems, dtype=np.uint64)
    result = np.zeros(n, dtype=np.int64)
    dtype = "<u8" if width == 8 else "<u4"
    for start, end in ranges:
        # Every byte alignment is checked because generated tables are not
        # guaranteed to be naturally aligned.
        for align in range(width):
            begin = start + align
            usable = (end - begin) // width * width
            if usable <= 0:
                continue
            values = np.frombuffer(data, dtype=dtype, count=usable // width, offset=begin)
            pos = np.searchsorted(addresses, values, side="left")
            valid = pos < n
            if not np.any(valid):
                continue
            valid_pos = pos[valid]
            valid_values = values[valid]
            exact = addresses[valid_pos] == valid_values
            if np.any(exact):
                result += np.bincount(valid_pos[exact], minlength=n).astype(np.int64)
    return result.tolist()


def pointer_refs(data: bytes, layout: NsoLayout, mems: list[int]) -> tuple[list[int], list[int]]:
    ranges = [
        (layout.ro_file, layout.ro_file + layout.ro_size),
        (layout.data_file, min(len(data), layout.data_file + layout.data_size)),
    ]
    ptr64 = _pointer_scan_numpy(data, ranges, mems, 8)
    ptr32 = _pointer_scan_numpy(data, ranges, mems, 4)
    return ptr64, ptr32


def classify(features: dict, direct: int, ptr64: int, ptr32: int, source: str) -> tuple[str, int, list[str]]:
    reasons: list[str] = []
    score = 0
    if features["has_newline"]:
        score -= 4
        reasons.append("newline/prose block")
    if features["has_sentence_punctuation"]:
        score -= 3
        reasons.append("sentence punctuation")
    if features["name_like"]:
        score += 4
        reasons.append("short CJK/kana name-like text")
    elif features["label_like"]:
        score += 2
        reasons.append("short label-like text")
    if features["identifier_like"]:
        score += 4
        reasons.append("identifier/control-code shape")
    if features["internal_marker_like"]:
        score += 3
        reasons.append("internal marker")
    if features["template_like"]:
        score += 3
        reasons.append("format/placeholder template")
    if features["char_length"] >= 30 and not features["has_newline"] and not features["has_sentence_punctuation"]:
        score += 1
        reasons.append("long noun phrase without sentence ending")
    if direct:
        reasons.append(f"direct_code_refs={direct}")
    if ptr64:
        reasons.append(f"pointer64_refs={ptr64}")
    if ptr32:
        reasons.append(f"pointer32_refs={ptr32}")
    if source == "untranslated":
        reasons.append("not translated in current JSON")

    # Categories intentionally describe review priority, not game ownership.
    if features["identifier_like"] or features["internal_marker_like"]:
        category = "internal_or_binary"
    elif features["template_like"] and not features["has_newline"]:
        category = "format_template"
    elif features["name_like"]:
        category = "name_or_table"
    elif features["has_newline"] or features["has_sentence_punctuation"]:
        category = "message_or_dialogue"
    elif features["char_length"] >= 30:
        category = "long_label_or_description"
    elif features["label_like"]:
        category = "ui_label"
    else:
        category = "unknown"

    # A high score is a likely non-dialogue candidate.  Negative prose signals
    # reduce confidence even when a placeholder is present.
    confidence = max(0, min(100, 50 + score * 10))
    if category in {"message_or_dialogue", "long_label_or_description"}:
        confidence = min(confidence, 35)
    return category, confidence, reasons


def reference_class(direct: int, ptr64: int) -> str:
    if direct and ptr64:
        return "direct_code_and_pointer_table"
    if direct:
        return "direct_code_only"
    if ptr64:
        return "pointer_table_only"
    return "no_exact_ref_found"


def analyze(main_path: Path, json_path: Path, out_path: Path, candidates_out: Path | None = None) -> dict:
    data = main_path.read_bytes()
    layout = NsoLayout.from_bytes(data)
    records = load_records(json_path)
    offset_to_index = {int(r["offset"]): i for i, r in enumerate(records)}
    mems = [layout.file_to_mem(int(r["offset"])) for r in records]
    if any(x is None for x in mems):
        raise ValueError("a candidate string is outside the NSO sections")
    mems = [int(x) for x in mems]

    direct = direct_code_refs(data, layout, offset_to_index, len(records))
    ptr64, ptr32 = pointer_refs(data, layout, mems)

    category_counts = Counter()
    translated_category_counts = Counter()
    reference_counts = Counter()
    source_counts = Counter()
    candidates: list[dict] = []
    all_analysis: list[dict] = []
    for i, r in enumerate(records):
        source = r.get("translation_source", "untranslated")
        source_counts[source] += 1
        feat = text_features(r["text"], int(r.get("capacity", 0)))
        category, confidence, reasons = classify(feat, direct[i], ptr64[i], ptr32[i], source)
        ref_class = reference_class(direct[i], ptr64[i])
        category_counts[category] += 1
        reference_counts[ref_class] += 1
        if source != "untranslated":
            translated_category_counts[category] += 1
        item = {
            "offset": r["offset"],
            "section": section_name(layout, int(r["offset"])),
            "text": r["text"],
            "korean": r.get("korean", ""),
            "translation_source": source,
            "game_text": r.get("game_text", ""),
            "category": category,
            "confidence_non_dialogue": confidence,
            "reasons": reasons,
            "features": feat,
            "reference_class": ref_class,
            "direct_code_refs": direct[i],
            "pointer64_refs_rodata_data": ptr64[i],
            "pointer32_refs_rodata_data": ptr32[i],
        }
        # Keep a compact per-string index for every record and a full review
        # item only for likely non-dialogue candidates.
        all_analysis.append({
            "offset": r["offset"],
            "category": category,
            "confidence_non_dialogue": confidence,
            "reference_class": ref_class,
            "direct_code_refs": direct[i],
            "pointer64_refs_rodata_data": ptr64[i],
            "pointer32_refs_rodata_data": ptr32[i],
        })
        if source != "untranslated" and confidence >= 60:
            candidates.append(item)

    result = {
        "format": 1,
        "input_main": str(main_path),
        "input_strings": str(json_path),
        "header": {
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
            "semantic_dialogue_flag": False,
        },
        "reference_scan": {
            "direct_code_unique": sum(x > 0 for x in direct),
            "direct_code_total": sum(direct),
            "pointer64_unique": sum(x > 0 for x in ptr64),
            "pointer64_total": sum(ptr64),
            "pointer32_unique": sum(x > 0 for x in ptr32),
            "pointer32_total": sum(ptr32),
            "pointer_scan_sections": ["rodata", "data"],
            "text_pointer_scan": False,
        },
        "counts": {
            "total": len(records),
            "translated": sum(1 for r in records if r.get("translation_source") != "untranslated"),
            "candidate_non_dialogue_translated": len(candidates),
            "category_all": dict(category_counts),
            "category_translated": dict(translated_category_counts),
            "reference_class_all": dict(reference_counts),
            "translation_source": dict(source_counts),
        },
        "limitations": [
            "The NSO header contains section offsets/sizes only; it has no per-string dialogue/UI flag.",
            "An exact pointer proves storage/reference provenance, not whether the text is dialogue.",
            "The candidate list is a review queue. Names, menu labels and format templates should not be batch-translated without context.",
            "32-bit pointer hits are weaker evidence than 64-bit hits; many are the low 32 bits of the same 64-bit pointer.",
        ],
        "candidate_strings": candidates,
        "index": all_analysis,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    if candidates_out is not None:
        candidates_out.parent.mkdir(parents=True, exist_ok=True)
        candidates_out.write_text(json.dumps({
            "format": 1,
            "source_analysis": str(out_path),
            "count": len(candidates),
            "criteria": "translated strings with confidence_non_dialogue >= 60",
            "strings": candidates,
        }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--main", type=Path, default=DEFAULT_MAIN)
    parser.add_argument("--strings", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--candidates-out", type=Path, default=DEFAULT_CANDIDATES_OUT)
    args = parser.parse_args()
    result = analyze(args.main, args.strings, args.out, args.candidates_out)
    print(json.dumps({"out": str(args.out), "candidates_out": str(args.candidates_out), **result["counts"], **result["reference_scan"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
