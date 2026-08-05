"""Materialize the patch exclusion decision in a patch-ready JSON.

The review JSON keeps a provisional Korean/game mapping for every extracted
record so it can be inspected.  This tool changes only records marked as
preserve_original: their game_text is restored from the original NSO bytes and
patch_excluded=true is written explicitly.  Thus both the current patcher and
older JSON-only tooling will leave those records untouched.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MAIN = ROOT / "exefs" / "main"
DEFAULT_REVIEW = ROOT / "main_patch" / "main_strings_ko_review.json"
DEFAULT_OUT = ROOT / "main_patch" / "main_strings_ko_patch.json"


def prepare(main_path: Path, review_path: Path, out_path: Path) -> dict:
    main = main_path.read_bytes()
    obj = json.loads(review_path.read_text(encoding="utf-8"))
    records = obj["strings"]
    counts: Counter[str] = Counter()
    excluded = 0
    for rec in records:
        should_exclude = bool(
            rec.get("preserve_original") or rec.get("localization_target") == "no"
        )
        if should_exclude:
            raw = main[rec["offset"]:rec["offset"] + rec["byte_length"]]
            try:
                original_game_text = raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError(f"excluded record is not UTF-8 at {rec['offset']:#x}") from exc
            rec["game_text"] = original_game_text
            rec["game_byte_length"] = len(raw)
            rec["needs_expansion"] = False
            rec["patch_excluded"] = True
            rec["patch_exclusion_reason"] = rec.get("target_status", "preserve_original")
            counts[rec["patch_exclusion_reason"]] += 1
            excluded += 1
        else:
            rec["patch_excluded"] = False

    out = dict(obj)
    out["strings"] = records
    out["patch_policy"] = {
        "format": 1,
        "source_main": str(main_path),
        "excluded_count": excluded,
        "excluded_status_counts": dict(counts),
        "rule": "patch_excluded=true records retain exact original game bytes",
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # Verify every excluded slot against the original before reporting success.
    check = json.loads(out_path.read_text(encoding="utf-8"))
    for rec in check["strings"]:
        if not rec.get("patch_excluded"):
            continue
        raw = main[rec["offset"]:rec["offset"] + rec["byte_length"]]
        if rec["game_text"].encode("utf-8") != raw:
            raise AssertionError(f"excluded bytes changed at {rec['offset']:#x}")
    return {"output": str(out_path), "records": len(records), "excluded": excluded, "status_counts": dict(counts)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--main", type=Path, default=DEFAULT_MAIN)
    ap.add_argument("--review", type=Path, default=DEFAULT_REVIEW)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()
    print(json.dumps(prepare(args.main, args.review, args.out), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
