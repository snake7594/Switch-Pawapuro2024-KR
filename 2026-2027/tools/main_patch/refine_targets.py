"""Add localization-target roles to the extracted Korean translation JSON.

The first pass classified text by length and references.  This pass adds the
structural cases that matter for patch safety:

* repeated one-character alphabets followed by offensive-word lists are name
  input/profanity-filter data and must remain unchanged;
* fixed-capacity runs are name/menu tables (names need transliteration, not
  free machine translation);
* control-prefixed strings need their control bytes preserved;
* printf-style placeholders are checked independently of the Korean prose.

The original JSON is not overwritten.  The enriched copy can still be passed
to patch_main.py because it retains all original fields.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASE = ROOT / "main_patch" / "main_strings_ko.json"
DEFAULT_ANALYSIS = ROOT / "main_patch" / "main_string_analysis.json"
DEFAULT_OUT = ROOT / "main_patch" / "main_strings_ko_review.json"
DEFAULT_REPORT = ROOT / "main_patch" / "main_target_review.json"

# Keep conversion letters and order; flags/widths do not change the argument
# count.  This treats "% d" and "%d" as the same argument while still
# catching a missing "%s".
FORMAT_RE = re.compile(r"%(?:[0-9]+\$)?[-+# 0-9.*hlLjzt]*[diuoxXfFeEgGcs]")
SENTINEL_RE = re.compile(r"QZZ[0-9]+ZQ")
FILTER_LABEL_RE = re.compile(
    r"(入力|英字|漢字|カナ|かな|音声検索|無変換|変換|不適切|１文字消す|文字を入力)"
)
MENU_TABLE_RE = re.compile(r"(デッキ|マイ設定|コーチ|ＯＢ|OB)")


def load_records(path: Path) -> list[dict]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    return obj["strings"] if isinstance(obj, dict) else obj


def is_char_slot(rec: dict) -> bool:
    text = rec["text"]
    if "\n" in text or rec.get("capacity") not in (4, 8):
        return False
    if len(text) == 1:
        return True
    # A few Japanese glyphs carry an IVS selector and occupy an 8-byte slot.
    return len(text) == 2 and any(ord(ch) >= 0xE0000 for ch in text)


def is_short_token(rec: dict) -> bool:
    text = rec["text"]
    return (
        "\n" not in text
        and len(text) <= 24
        and rec.get("capacity", 0) <= 80
        and not any(ch in text for ch in "。！？!?．")
    )


def find_dictionary_blocks(records: list[dict]) -> tuple[dict[int, dict], list[dict]]:
    """Find character alphabets and their adjacent profanity-filter lists."""
    runs: list[list[dict]] = []
    current: list[dict] = []
    for rec in records:
        if not is_char_slot(rec):
            if len(current) >= 20:
                runs.append(current)
            current = []
            continue
        if current and rec["offset"] - current[-1]["offset"] > 0x20:
            if len(current) >= 20:
                runs.append(current)
            current = []
        current.append(rec)
    if len(current) >= 20:
        runs.append(current)

    by_offset = {rec["offset"]: i for i, rec in enumerate(records)}
    roles: dict[int, dict] = {}
    blocks: list[dict] = []
    for block_num, run in enumerate(runs, 1):
        block_id = f"input_filter_{block_num:02d}"
        for rec in run:
            roles[rec["offset"]] = {
                "role": "input_character_alphabet",
                "block_id": block_id,
                "preserve": True,
            }

        # The first long, dense short-token segment after the alphabet is the
        # corresponding disallowed-word list.  Visible input labels inside it
        # remain translatable; the actual filter entries do not.
        last_index = by_offset[run[-1]["offset"]]
        post: list[tuple[dict, int]] = []
        previous = run[-1]
        for rec in records[last_index + 1:last_index + 251]:
            gap = rec["offset"] - previous["offset"]
            if gap > 0x200:
                break
            post.append((rec, gap))
            previous = rec

        segment: list[dict] | None = None
        candidate: list[dict] = []
        previous_rec: dict | None = None
        for rec, gap in post:
            dense = is_short_token(rec) and (previous_rec is None or gap <= 0x60)
            if not dense:
                if len(candidate) >= 20:
                    segment = candidate
                    break
                candidate = []
            if dense:
                candidate.append(rec)
            previous_rec = rec
        if segment is None and len(candidate) >= 20:
            segment = candidate

        filter_entries = 0
        label_entries = 0
        if segment:
            for rec in segment:
                if FILTER_LABEL_RE.search(rec["text"]):
                    roles[rec["offset"]] = {
                        "role": "input_filter_ui_label",
                        "block_id": block_id,
                        "preserve": False,
                    }
                    label_entries += 1
                else:
                    roles[rec["offset"]] = {
                        "role": "profanity_filter_entry",
                        "block_id": block_id,
                        "preserve": True,
                    }
                    filter_entries += 1

        blocks.append({
            "block_id": block_id,
            "alphabet_start": run[0]["offset"],
            "alphabet_end": run[-1]["offset"],
            "alphabet_entries": len(run),
            "filter_start": segment[0]["offset"] if segment else None,
            "filter_end": segment[-1]["offset"] if segment else None,
            "filter_entries": filter_entries,
            "filter_ui_labels": label_entries,
        })
    return roles, blocks


def find_fixed_slot_runs(records: list[dict], reserved: set[int]) -> tuple[dict[int, dict], list[dict]]:
    """Find repeated fixed-capacity name/menu tables."""
    def eligible(rec: dict) -> bool:
        return (
            rec["offset"] not in reserved
            and "\n" not in rec["text"]
            and len(rec["text"]) <= 20
            and rec.get("capacity") in (10, 82, 84, 85)
        )

    runs: list[list[dict]] = []
    current: list[dict] = []
    for rec in records:
        if not eligible(rec):
            if len(current) >= 10:
                runs.append(current)
            current = []
            continue
        if current:
            cap_gap = abs(rec["capacity"] - current[-1]["capacity"])
            gap_limit = 0x20 if rec["capacity"] == 10 else 0x100
            if cap_gap > 1 or rec["offset"] - current[-1]["offset"] > gap_limit:
                if len(current) >= 10:
                    runs.append(current)
                current = []
        current.append(rec)
    if len(current) >= 10:
        runs.append(current)

    roles: dict[int, dict] = {}
    report: list[dict] = []
    for run_num, run in enumerate(runs, 1):
        if run[0]["capacity"] == 10:
            kind = "name_generation_table"
        elif any(MENU_TABLE_RE.search(rec["text"]) for rec in run):
            kind = "fixed_menu_table"
        else:
            kind = "fixed_name_table"
        run_id = f"fixed_slots_{run_num:02d}"
        for rec in run:
            roles[rec["offset"]] = {
                "role": kind,
                "run_id": run_id,
                "preserve": False,
            }
        report.append({
            "run_id": run_id,
            "kind": kind,
            "start": run[0]["offset"],
            "end": run[-1]["offset"],
            "entries": len(run),
            "capacities": sorted({rec["capacity"] for rec in run}),
            "sample_start": [rec["text"] for rec in run[:5]],
            "sample_end": [rec["text"] for rec in run[-5:]],
        })
    return roles, report


def format_tokens(text: str) -> list[str]:
    return FORMAT_RE.findall(text)


def format_signature(text: str) -> list[str]:
    return [token[-1] for token in format_tokens(text)]


def control_bytes(text: str) -> list[int]:
    return [ord(ch) for ch in text if ord(ch) < 0x20 and ch not in "\r\n\t"]


def visible_without_controls(text: str) -> str:
    return "".join(ch for ch in text if ord(ch) >= 0x20 or ch in "\r\n\t")


def has_kana(text: str) -> bool:
    return any("\u3040" <= ch <= "\u30FF" for ch in text)


def cjk_count(text: str) -> int:
    return sum("\u3400" <= ch <= "\u9FFF" for ch in text)


def binary_suspect(rec: dict, pointer64: int, direct: int) -> bool:
    text = rec["text"]
    visible = visible_without_controls(text)
    ascii_count = sum(ord(ch) < 0x80 for ch in visible)
    cjk = cjk_count(visible)
    kana = has_kana(visible)
    controls = bool(control_bytes(text))
    if text.startswith("DEV:"):
        return True
    # These are real visible achievement/menu fragments (for example
    # "+2回").  They have no independent pointer because they sit in a
    # contiguous string table, but must not be treated as binary data.
    if re.fullmatch(r"\+\d+回", text):
        return False
    # Tiny ASCII/CJK mixtures and the late data-section outliers are not
    # Japanese prose; they are binary/metadata false positives from the UTF-8
    # scanner.  Requiring no exact/direct reference prevents over-filtering
    # legitimate short Japanese labels.
    if not kana and not direct and not pointer64:
        if controls and len(visible) <= 8 and ascii_count >= 2 and cjk <= 1:
            return True
        if "=" in visible and len(visible) <= 8 and ascii_count >= 1 and cjk >= 1:
            return True
        if len(visible) <= 3 and rec["capacity"] <= 8 and rec["offset"] >= 0x4B00000:
            return True
        # The UTF-8 scanner also sees a handful of one-glyph entries inside
        # RGB/RGBA tables.  Their three-byte UTF-8 sequence has the repeated
        # second/third byte pattern of the underlying pixel data; with a
        # four-byte slot and no references this is a reliable false-positive
        # signature for this build.
        if rec["capacity"] == 4 and len(text) == 1:
            encoded = text.encode("utf-8")
            if len(encoded) == 3 and encoded[1] == encoded[2]:
                return True
        if ascii_count >= 1 and cjk == 1 and len(visible) <= 8:
            return True
    return False


def compact_record(rec: dict) -> dict:
    keys = (
        "offset", "text", "korean", "translation_source", "target_status",
        "localization_target", "semantic_role", "target_confidence",
        "review_flags", "reference_class", "direct_code_refs",
        "pointer64_refs_rodata_data", "structure_id",
    )
    return {key: rec[key] for key in keys if key in rec}


def refine(base_path: Path, analysis_path: Path, out_path: Path, report_path: Path) -> dict:
    base_obj = json.loads(base_path.read_text(encoding="utf-8"))
    records = base_obj["strings"] if isinstance(base_obj, dict) else base_obj
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    index = analysis["index"]
    if len(records) != len(index):
        raise ValueError("base JSON and analysis index counts differ")

    dictionary_roles, dictionary_blocks = find_dictionary_blocks(records)
    fixed_roles, fixed_runs = find_fixed_slot_runs(records, set(dictionary_roles))

    status_counts = Counter()
    target_counts = Counter()
    role_counts = Counter()
    format_issues: list[dict] = []
    non_targets: list[dict] = []
    manual_review: list[dict] = []
    enriched: list[dict] = []

    for rec, info in zip(records, index):
        offset = rec["offset"]
        source = rec.get("translation_source", "untranslated")
        category = info.get("category", "unknown")
        direct = int(info.get("direct_code_refs", 0))
        pointer64 = int(info.get("pointer64_refs_rodata_data", 0))
        ref_class = info.get("reference_class", "unknown")
        flags: list[str] = []
        structure_id: str | None = None
        role = category
        target_status = "review"
        target = "review"
        confidence = 35

        dictionary = dictionary_roles.get(offset)
        fixed = fixed_roles.get(offset)
        controls = control_bytes(rec["text"])
        visible = visible_without_controls(rec["text"])

        source_sig = format_signature(rec["text"])
        korean_sig = format_signature(rec.get("korean", ""))
        game_sig = format_signature(rec.get("game_text", ""))
        sentinels = sorted(set(SENTINEL_RE.findall(rec.get("korean", "") + rec.get("game_text", ""))))
        format_integrity = source_sig == korean_sig == game_sig
        if source_sig and (not format_integrity or sentinels):
            flags.append("format_token_mismatch")
            if sentinels:
                flags.append("translation_sentinel_leaked")
            format_issues.append({
                "offset": offset,
                "text": rec["text"],
                "korean": rec.get("korean", ""),
                "game_text": rec.get("game_text", ""),
                "source_signature": source_sig,
                "korean_signature": korean_sig,
                "game_signature": game_sig,
                "sentinels": sentinels,
            })

        if dictionary:
            structure_id = dictionary.get("block_id")
            role = dictionary["role"]
            if dictionary["preserve"]:
                target_status = "preserve_internal_dictionary"
                target = "no"
                confidence = 99
                flags.append("runtime_name_or_profanity_filter")
            else:
                target_status = "translate_input_filter_ui"
                target = "yes"
                confidence = 88
                flags.append("visible_input_ui")
        elif binary_suspect(rec, pointer64, direct):
            role = "debug_or_binary_metadata"
            target_status = "preserve_debug_or_binary"
            target = "no"
            confidence = 96
            flags.append("UTF8_scanner_false_positive_or_debug")
        elif fixed:
            structure_id = fixed.get("run_id")
            role = fixed["role"]
            if fixed["role"] == "fixed_menu_table":
                target_status = "translate_fixed_menu"
                target = "yes"
                confidence = 94
                flags.append("fixed_capacity_menu_table")
            else:
                target_status = "name_transliteration_review"
                target = "yes"
                confidence = 94
                flags.append("fixed_capacity_name_table")
                flags.append("use_name_reading_not_machine_translation")
        elif controls:
            role = "control_prefixed_or_suffixed_text"
            target_status = "translate_keep_control_bytes"
            target = "yes"
            confidence = 78
            flags.append("control_bytes_must_be_preserved")
            if visible != rec["text"]:
                flags.append("visible_text_extracted_for_review")
        elif "format_token_mismatch" in flags:
            role = "format_template"
            target_status = "review_format_token_mismatch"
            target = "yes"
            confidence = 99
        elif category == "format_template":
            role = "format_template"
            target_status = "translate_keep_format_tokens"
            target = "yes"
            confidence = 94
            flags.append("format_tokens_must_be_preserved")
        elif category in {"message_or_dialogue", "long_label_or_description"}:
            role = category
            target_status = "translate_text"
            target = "yes"
            confidence = 86
        elif category == "ui_label":
            role = "ui_label"
            target_status = "translate_ui_label"
            target = "yes"
            confidence = 88
        elif category == "name_or_table":
            role = "short_name_or_table_entry"
            target_status = "review_short_name_or_table"
            target = "yes"
            confidence = 62
            flags.append("not_dialogue_but_may_need_name_or_label_localization")
        elif source == "untranslated":
            role = "untranslated_review"
            target_status = "review_untranslated"
            target = "review"
            confidence = 45
            flags.append("not_translated_in_current_json")
        else:
            role = category
            target_status = "review_unknown"
            target = "review"
            confidence = 35

        if source == "untranslated" and "not_translated_in_current_json" not in flags:
            flags.append("not_translated_in_current_json")
        if ref_class == "no_exact_ref_found":
            flags.append("no_exact_pointer_or_direct_code_reference")
        if source_sig:
            flags.append("has_printf_arguments")

        item = dict(rec)
        item.update({
            "string_category": category,
            "reference_class": ref_class,
            "direct_code_refs": direct,
            "pointer64_refs_rodata_data": pointer64,
            "localization_target": target,
            "localization_decision": {
                "yes": "translate",
                "no": "preserve_original",
                "review": "manual_review",
            }[target],
            "preserve_original": target == "no",
            "target_status": target_status,
            "semantic_role": role,
            "target_confidence": confidence,
            "review_flags": sorted(set(flags)),
            "structure_id": structure_id,
            "control_bytes": controls,
            "visible_text": visible if controls else None,
            "format_tokens_source": format_tokens(rec["text"]),
            "format_tokens_korean": format_tokens(rec.get("korean", "")),
            "format_tokens_game": format_tokens(rec.get("game_text", "")),
            "format_signature_source": source_sig,
            "format_signature_korean": korean_sig,
            "format_signature_game": game_sig,
            "format_integrity": format_integrity,
            "translation_sentinels": sentinels,
        })
        enriched.append(item)
        status_counts[target_status] += 1
        target_counts[target] += 1
        role_counts[role] += 1
        if target == "no":
            non_targets.append(compact_record(item))
        elif target == "review" or "format_token_mismatch" in flags:
            manual_review.append(compact_record(item))

    out_obj = dict(base_obj) if isinstance(base_obj, dict) else {
        "format": 1,
        "strings": enriched,
    }
    out_obj["strings"] = enriched
    out_obj["classification"] = {
        "format": 1,
        "source_analysis": str(analysis_path),
        "dictionary_blocks": len(dictionary_blocks),
        "fixed_slot_runs": len(fixed_runs),
        "semantic_dialogue_flag_in_nso_header": False,
        "localization_decision_values": ["translate", "preserve_original", "manual_review"],
        "target_status_values": sorted(status_counts),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out_obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    report = {
        "format": 1,
        "source_json": str(base_path),
        "enriched_json": str(out_path),
        "counts": {
            "total": len(records),
            "translated": sum(rec.get("translation_source") != "untranslated" for rec in records),
            "target_status": dict(status_counts),
            "localization_target": dict(target_counts),
            "semantic_role": dict(role_counts),
            "non_localization_candidates": len(non_targets),
            "manual_review_entries": len(manual_review),
            "format_token_issues": len(format_issues),
            "control_byte_entries": sum(bool(control_bytes(rec["text"])) for rec in records),
            "input_filter_alphabet_entries": sum(b["alphabet_entries"] for b in dictionary_blocks),
            "input_filter_entries": sum(b["filter_entries"] for b in dictionary_blocks),
        },
        "method": {
            "dictionary_structure": "20+ adjacent 4/8-byte single-glyph slots followed by a dense short-token list",
            "fixed_slot_structure": "10+ repeated fixed-capacity short strings",
            "pointer_evidence": "64-bit exact pointers in rodata/data and direct ARM64 ADRP+ADD references",
            "format_evidence": "printf conversion-letter signature and leaked translation-sentinel check",
        },
        "dictionary_blocks": dictionary_blocks,
        "fixed_slot_runs": fixed_runs,
        "non_localization_candidates": non_targets,
        "format_token_issues": format_issues,
        "manual_review_sample": manual_review[:500],
        "limitations": [
            "A name table is not dialogue, but it may still require Korean name transliteration; it is not automatically preserved.",
            "A pointer proves reference provenance, not semantic visibility.",
            "Input/profanity dictionaries are marked preserve because changing their Japanese keys can break runtime matching.",
            "Control-prefixed visible text remains a translation target, but its control bytes must be copied unchanged.",
        ],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--analysis", type=Path, default=DEFAULT_ANALYSIS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    report = refine(args.base, args.analysis, args.out, args.report)
    print(json.dumps({"out": str(args.out), "report": str(args.report), **report["counts"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
