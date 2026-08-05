"""Annotate the review JSON with stable, human-reviewable content groups.

The detailed ``semantic_role`` values are useful for patch generation, but are
too granular for a reviewer who wants to switch between menus, sentences, and
the other broad kinds of text.  This tool adds one stable ``review_group``
value to every string and records the grouping rules/counts in the JSON
metadata.  Existing fields and record order are preserved.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "main_patch" / "main_strings_ko_menu_compact_review.json"
DEFAULT_OUTPUT = DEFAULT_INPUT


GROUPS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "menu",
        "메뉴·레이블",
        ("ui_label", "fixed_menu_table", "input_filter_ui_label"),
    ),
    (
        "sentence",
        "문장·대사",
        ("message_or_dialogue", "control_prefixed_or_suffixed_text"),
    ),
    (
        "name_table",
        "이름·테이블",
        ("short_name_or_table_entry", "name_generation_table", "fixed_name_table"),
    ),
    ("template", "서식·템플릿", ("format_template",)),
    ("description", "설명·긴 텍스트", ("long_label_or_description",)),
    (
        "internal",
        "내부 데이터·보존",
        ("input_character_alphabet", "profanity_filter_entry", "debug_or_binary_metadata"),
    ),
    ("unknown", "미분류·검토 필요", ("unknown",)),
)

ROLE_TO_GROUP = {
    role: group
    for group, _label, roles in GROUPS
    for role in roles
}
GROUP_LABELS = {group: label for group, label, _roles in GROUPS}
GROUP_ORDER = [group for group, _label, _roles in GROUPS]


def classify_record(record: dict) -> tuple[str, str]:
    """Return ``(review_group, reason)`` without changing patch semantics."""

    role = record.get("semantic_role")
    if role in ROLE_TO_GROUP:
        return ROLE_TO_GROUP[role], f"semantic_role:{role}"

    # Older review JSONs can lack semantic_role.  Keep the fallback explicit so
    # the HTML can still load them and reviewers can see why they were grouped.
    category = record.get("string_category")
    category_fallback = {
        "ui_label": "menu",
        "message_or_dialogue": "sentence",
        "name_or_table": "name_table",
        "format_template": "template",
        "long_label_or_description": "description",
        "internal_or_binary": "internal",
    }
    if category in category_fallback:
        return category_fallback[category], f"string_category:{category}"
    return "unknown", "missing_semantic_role_and_category"


def annotate(obj: dict) -> Counter[str]:
    records = obj.get("strings")
    if not isinstance(records, list):
        raise ValueError("JSON에 strings 배열이 없습니다.")

    counts: Counter[str] = Counter()
    for record in records:
        group, reason = classify_record(record)
        record["review_group"] = group
        record["review_group_reason"] = reason
        counts[group] += 1

    obj["review_grouping"] = {
        "format": 1,
        "field": "review_group",
        "label_source": "review_grouping.groups[].label",
        "default_filter": "all",
        "groups": [
            {
                "value": group,
                "label": GROUP_LABELS[group],
                "semantic_roles": list(roles),
                "count": counts.get(group, 0),
            }
            for group, _label, roles in GROUPS
        ],
        "counts": {group: counts.get(group, 0) for group in GROUP_ORDER},
    }
    return counts


def write_json_atomic(obj: dict, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=str(output.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            # The source is intentionally compact; preserving this avoids an
            # unnecessary multi-gigabyte pretty-print intermediate file.
            json.dump(obj, handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        Path(temp_name).replace(output)
    except Exception:
        try:
            Path(temp_name).unlink(missing_ok=True)
        finally:
            raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--backup", type=Path, default=None)
    args = parser.parse_args()

    source = args.input.resolve()
    output = args.output.resolve()
    if args.backup:
        backup = args.backup.resolve()
    elif source == output:
        backup = source.with_name(source.name + ".before_review_groups")
    else:
        backup = None

    with source.open("r", encoding="utf-8") as handle:
        obj = json.load(handle)
    counts = annotate(obj)
    if backup and not backup.exists():
        shutil.copy2(source, backup)
    write_json_atomic(obj, output)

    print(json.dumps({"output": str(output), "counts": dict(counts)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
