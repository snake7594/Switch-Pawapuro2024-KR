"""Export the exact 2350-slot font/text mapping used by the patch."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from main_strings import DEFAULT_FONT, hangul_2350, sjis_targets


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--font", type=Path, default=DEFAULT_FONT)
    ap.add_argument("--out", type=Path, default=Path("main_patch/sjis_hangul_map.json"))
    args = ap.parse_args()
    hangul = hangul_2350()
    rows = []
    for index, (u, ko) in enumerate(zip(sjis_targets(args.font), hangul)):
        c = chr(u)
        rows.append({
            "index": index,
            "sjis": c.encode("cp932").hex().upper(),
            "japanese_codepoint": f"U+{u:04X}",
            "japanese": c,
            "hangul": ko,
        })
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"count": len(rows), "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"count": len(rows), "out": str(args.out)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
