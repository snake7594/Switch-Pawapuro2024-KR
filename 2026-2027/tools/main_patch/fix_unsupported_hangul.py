"""Replace the five rare syllables outside the game's 2350 EUC-KR atlas.

The atlas is intentionally limited to the standard 2350 syllables.  Google
occasionally emits a rare syllable in a transliterated name; these nearest
phonetic substitutes keep the name visible instead of leaving a missing-glyph
box.  The original Korean text remains in the JSON for later atlas expansion.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from main_strings import DEFAULT_FONT, korean_to_cjk


FALLBACK = {
    "슌": "쉰",
    "짿": "쨀",
    "캸": "캘",
    "콽": "콸",
    "펬": "펫",
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", type=Path, nargs="?", default=Path("main_patch/main_strings_ko.json"))
    args = ap.parse_args()
    obj = json.loads(args.path.read_text(encoding="utf-8"))
    cmap = korean_to_cjk(DEFAULT_FONT)
    changed = 0
    for rec in obj["strings"]:
        ko = rec.get("korean", rec["text"])
        replaced = "".join(FALLBACK.get(ch, ch) for ch in ko)
        if replaced != ko:
            changed += 1
        rec["korean"] = replaced
        game = "".join(cmap.get(ch, ch) if "\uAC00" <= ch <= "\uD7A3" else ch for ch in replaced)
        rec["game_text"] = game
        rec["game_byte_length"] = len(game.encode("utf-8"))
        rec["needs_expansion"] = rec["game_byte_length"] + 1 > rec["capacity"]
    obj["unsupported_hangul"] = {}
    args.path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({"records_changed": changed, "fallback": FALLBACK}, ensure_ascii=False))


if __name__ == "__main__":
    main()
