"""Compact safe spaces in Korean menu-like labels.

The executable's menu strings are short, fixed-width labels.  Korean
translations often contain spaces between nouns where the Japanese source has
one uninterrupted label.  This helper removes only spaces that are safe for a
menu label; dialogue, format templates, control-prefixed text, names and
grammar-bearing phrases are left untouched.  No text is truncated.

The input is the review JSON.  A separate output is written so the reviewed
translation file remains available for comparison.  ``prepare_patch_json.py``
should be run on the output before invoking ``patch_main.py``.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "main_patch" / "main_strings_ko_review.json"
DEFAULT_OUTPUT = ROOT / "main_patch" / "main_strings_ko_menu_compact_review.json"
DEFAULT_REPORT = ROOT / "main_patch" / "main_menu_compaction.report.json"
DEFAULT_MAP = ROOT / "main_patch" / "sjis_hangul_map.json"

MENU_ROLES = {"ui_label", "short_name_or_table_entry", "fixed_menu_table"}
MAX_SOURCE_LENGTH = {
    "short_name_or_table_entry": 10,
    "ui_label": 24,
    "fixed_menu_table": 9,
}

# These indicate a sentence or quoted dialogue rather than a fixed menu item.
SOURCE_SENTENCE_MARKS = set("\r\n、。！？?!…『』「」")
KOREAN_SENTENCE_MARKS = set("\r\n、。！？?!…，,.")

# A single Japanese particle at the end is a useful signal that an otherwise
# short table entry is actually a fragment of a sentence (親友と, 一文字目の).
JAPANESE_PARTICLES = set("のとにへではがを")

# Multi-syllable particles and unmistakable grammatical endings.  One-
# syllable endings such as 가/이 are treated separately because many Korean
# nouns themselves end in those syllables (평가, 국가, 종이).
PARTICLE_SUFFIXES = (
    "으로", "에서", "에게", "한테", "부터", "까지", "밖에", "대로", "처럼",
    "만큼", "마저", "조차", "이라", "이며", "의", "와", "과", "로",
)
SHORT_PARTICLES = ("은", "는", "이", "가", "을", "를", "에", "도", "만")
GRAMMAR_SUFFIXES = (
    "로운", "적인", "하는", "하게", "하고", "해서", "하여", "하며", "할",
    "한", "된", "되는", "받는", "있는", "없는", "않는", "싶은", "같은",
    "위한", "위해", "때문에", "하기", "하려", "했", "였다", "였다가",
    "합니다", "됩니다", "주세요", "어도", "아도", "여도", "이어도",
    "이라도", "든지", "거나", "지만", "인데", "인데도", "라고", "다고",
)

# Adverbs/pronouns which should stay separate in a sentence.  They are only
# protected for UI labels; explicit short/fixed tables are already strongly
# constrained and may use the same words as a compact title.
PHRASE_WORDS = {
    "가장", "매우", "정말", "아주", "더", "또", "모든", "각", "이번", "지난",
    "오늘", "내일", "다음", "어떤", "이런", "그", "저", "우선", "처음", "이미",
    "아직", "여러", "시간",
}

# These are never fused, including in short tables: doing so would turn a
# sentence fragment such as "어떤 일이 있어도" into an unreadable token.
ALWAYS_PHRASE_WORDS = {"가장", "매우", "정말", "아주", "더", "또", "모든", "각", "어떤", "이런", "그", "저", "여러"}

# Threshold words are clearer with a separating space (7초 이상, 140 미만).
RIGHT_TERM_WORDS = {
    "이상", "이하", "미만", "초과", "이내", "이후", "이전", "동안", "것", "수",
    "때", "경우",
}

HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")
LATIN_RE = re.compile(r"[A-Za-z]")
CORE_RE = re.compile(r"[^\uac00-\ud7a3\u0030-\u0039]")


def load_game_map(path: Path) -> dict[str, str]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    return {row["hangul"]: row["japanese"] for row in obj["rows"]}


def map_game_text(korean: str, game_map: dict[str, str]) -> tuple[str, list[str]]:
    out: list[str] = []
    missing: list[str] = []
    for ch in korean:
        if "\uac00" <= ch <= "\ud7a3":
            mapped = game_map.get(ch)
            if mapped is None:
                missing.append(ch)
                out.append(ch)
            else:
                out.append(mapped)
        else:
            out.append(ch)
    return "".join(out), missing


def game_byte_length(korean: str, game_map: dict[str, str]) -> int:
    game, _ = map_game_text(korean, game_map)
    return len(game.encode("utf-8"))


def core(token: str) -> str:
    return CORE_RE.sub("", token)


def has_latin(text: str) -> bool:
    return bool(LATIN_RE.search(text))


def is_particle_or_verb(token_core: str, *, force_table: bool) -> bool:
    if not token_core:
        return False
    if not force_table and token_core in PHRASE_WORDS:
        return True
    if any(token_core.endswith(suffix) for suffix in PARTICLE_SUFFIXES):
        return True
    if any(token_core.endswith(suffix) for suffix in GRAMMAR_SUFFIXES):
        return True
    # Only classify a one-syllable particle as grammatical when a reasonable
    # stem remains.  This keeps 평가는/국가/종이-like nouns eligible.
    return len(token_core) >= 3 and any(token_core.endswith(suffix) for suffix in SHORT_PARTICLES)


def is_right_grammar(token_core: str) -> bool:
    if not token_core:
        return False
    if token_core in RIGHT_TERM_WORDS:
        return True
    if token_core.endswith(("의", "와", "과", "으로", "에서", "에게", "한테", "부터", "까지")):
        return True
    if any(token_core.endswith(suffix) for suffix in GRAMMAR_SUFFIXES):
        return True
    return False


def name_like_source(source: str, korean: str) -> bool:
    """Avoid fusing likely two-part transliterated personal names."""

    if not source:
        return False
    # Decorative markers and a trailing index are common in generated name
    # tables (◆山咲花子３, 諏訪野君子２).  Remove those before testing the
    # kanji body, while retaining the original Korean text for the token test.
    body = source.lstrip("◆◇★☆○●")
    body = body.rstrip("0123456789０１２３４５６７８９")
    if not body or any(not ("\u4e00" <= ch <= "\u9fff") for ch in body):
        return False
    if not 3 <= len(body) <= 5:
        return False
    parts = korean.split(" ")
    while parts and not core(parts[-1]):
        parts.pop()
    if parts and parts[-1].isdigit():
        parts.pop()
    if len(parts) != 2 or any(not core(part) for part in parts):
        return False
    left, right = (core(part) for part in parts)
    return len(left) >= 3 and len(right) >= 2


def safe_boundary(left: str, right: str, *, soft: bool, force_table: bool) -> bool:
    if has_latin(left + right):
        return False
    left_core, right_core = core(left), core(right)
    if not left_core or not right_core:
        return False
    if left_core in ALWAYS_PHRASE_WORDS:
        return False
    if is_particle_or_verb(left_core, force_table=force_table):
        return False
    if is_right_grammar(right_core):
        return False

    limit = 10 if soft else 5
    if any(ch.isdigit() for ch in left + right):
        limit = max(limit, 10)
    return len(left_core) <= limit and len(right_core) <= limit


def compact_label(
    korean: str,
    target_bytes: int,
    game_map: dict[str, str],
    *,
    force_table: bool,
) -> tuple[str, list[dict[str, object]]]:
    current = korean
    changes: list[dict[str, object]] = []
    # Short/fixed tables use all safe compounds.  UI labels use hard compounds
    # unconditionally, then soft compounds only while they exceed the source
    # byte budget, preserving readability when there is room.
    for soft in (False, True):
        parts = current.split(" ")
        if len(parts) < 2:
            break
        output = [parts[0]]
        for right in parts[1:]:
            left = output[-1]
            candidate = " ".join(output + [right])
            if safe_boundary(left, right, soft=soft, force_table=force_table) and (
                force_table
                or not soft
                or game_byte_length(candidate, game_map) > target_bytes
            ):
                output[-1] = left + right
                changes.append({"left": left, "right": right, "soft": soft})
            else:
                output.append(right)
        current = " ".join(output)
    return current, changes


def eligible_record(rec: dict) -> tuple[bool, str]:
    role = rec.get("semantic_role")
    if role not in MENU_ROLES:
        return False, "not_menu_role"
    if rec.get("preserve_original") or rec.get("localization_target") == "no":
        return False, "preserved_or_excluded"
    if rec.get("control_bytes") or rec.get("format_signature_source"):
        return False, "control_or_format"

    source = rec.get("text", "")
    korean = rec.get("korean", "")
    if not korean or " " not in korean:
        return False, "no_ascii_space"
    if any(ch.isspace() for ch in source):
        return False, "source_has_whitespace"
    if any(ord(ch) < 32 for ch in source):
        return False, "source_control_byte"
    if any(ch in source for ch in SOURCE_SENTENCE_MARKS):
        return False, "source_sentence_mark"
    if any(ch in korean for ch in KOREAN_SENTENCE_MARKS):
        return False, "korean_sentence_mark"
    if has_latin(korean):
        return False, "latin_in_translation"
    if len(source) > MAX_SOURCE_LENGTH[role]:
        return False, "source_too_long"

    hiragana_count = sum("\u3040" <= ch <= "\u309f" for ch in source)
    if hiragana_count > 1:
        return False, "too_much_hiragana"
    if hiragana_count == 1 and source[-1] in JAPANESE_PARTICLES and not any(ch.isdigit() for ch in source):
        return False, "source_grammar_fragment"
    if name_like_source(source, korean):
        return False, "likely_person_name"
    return True, "eligible"


def compact(input_path: Path, output_path: Path, report_path: Path, map_path: Path) -> dict:
    obj = json.loads(input_path.read_text(encoding="utf-8"))
    records = obj["strings"]
    game_map = load_game_map(map_path)
    report_counts: Counter[str] = Counter()
    changed_examples: list[dict[str, object]] = []
    unresolved: list[dict[str, object]] = []
    missing_chars: Counter[str] = Counter()

    for rec in records:
        eligible, reason = eligible_record(rec)
        report_counts[reason] += 1
        if not eligible:
            continue
        report_counts["eligible"] += 1
        source = rec["text"]
        korean = rec["korean"]
        force_table = rec["semantic_role"] in {"short_name_or_table_entry", "fixed_menu_table"}
        compacted, changes = compact_label(
            korean,
            int(rec["byte_length"]),
            game_map,
            force_table=force_table,
        )
        if compacted == korean:
            if game_byte_length(korean, game_map) > int(rec["byte_length"]):
                report_counts["overflow_unresolved"] += 1
                unresolved.append({
                    "offset": rec["offset"],
                    "source": source,
                    "korean": korean,
                    "byte_length": rec["byte_length"],
                    "game_byte_length": game_byte_length(korean, game_map),
                    "reason": "no_safe_space_to_remove",
                })
            continue

        game_text, missing = map_game_text(compacted, game_map)
        missing_chars.update(missing)
        old_game_length = int(rec.get("game_byte_length", 0))
        rec["korean"] = compacted
        rec["game_text"] = game_text
        rec["game_byte_length"] = len(game_text.encode("utf-8"))
        rec["needs_expansion"] = rec["game_byte_length"] + 1 > int(rec["capacity"])
        rec["menu_compaction"] = {
            "version": 1,
            "removed_spaces": len(changes),
            "source_byte_length": rec["byte_length"],
            "old_game_byte_length": old_game_length,
            "new_game_byte_length": rec["game_byte_length"],
            "force_table": force_table,
        }
        report_counts["changed"] += 1
        report_counts["removed_spaces"] += len(changes)
        report_counts["hard_space_removals"] += sum(not bool(change["soft"]) for change in changes)
        report_counts["soft_space_removals"] += sum(bool(change["soft"]) for change in changes)
        if rec["game_byte_length"] > int(rec["byte_length"]):
            report_counts["overflow_after_compaction"] += 1
            unresolved.append({
                "offset": rec["offset"],
                "source": source,
                "korean": compacted,
                "byte_length": rec["byte_length"],
                "game_byte_length": rec["game_byte_length"],
                "reason": "still_longer_after_safe_compaction",
            })
        if len(changed_examples) < 200:
            changed_examples.append({
                "offset": rec["offset"],
                "source": source,
                "before": korean,
                "after": compacted,
                "removed_spaces": len(changes),
                "byte_before": old_game_length,
                "byte_after": rec["game_byte_length"],
                "role": rec["semantic_role"],
            })

    out = dict(obj)
    out["strings"] = records
    out["menu_compaction"] = {
        "format": 1,
        "input": str(input_path),
        "rule": (
            "compact only short ui_label/short_name/fixed_menu records with "
            "no sentence marks, no format/control tokens, at most one internal "
            "hiragana and no likely two-part personal name"
        ),
        "counts": dict(report_counts),
        "missing_hangul": dict(missing_chars),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    report = {
        "format": 1,
        "input": str(input_path),
        "output": str(output_path),
        "counts": dict(report_counts),
        "changed_examples": changed_examples,
        "unresolved": unresolved,
        "missing_hangul": dict(missing_chars),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP)
    args = parser.parse_args()
    report = compact(args.input, args.output, args.report, args.map)
    print(json.dumps({"output": report["output"], "counts": report["counts"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
