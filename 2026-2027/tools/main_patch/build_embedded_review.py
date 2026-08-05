"""Build a file://-safe compressed snapshot for the translation editor.

Browsers block fetch/XMLHttpRequest from a page opened directly with
``file://``.  A script element is still allowed to load a sibling local file,
so the editor can use this gzip/base64 snapshot only as a fallback.  HTTP
serving continues to load the live JSON file first.
"""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "main_patch" / "main_strings_ko_menu_compact_review.json"
DEFAULT_OUTPUT = ROOT / "main_patch" / "main_strings_ko_menu_compact_review.embedded.js"
CHUNK_SIZE = 65536


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="ascii", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        Path(temp_name).replace(path)
    except Exception:
        Path(temp_name).unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    raw = args.input.read_bytes()
    compressed = gzip.compress(raw, compresslevel=9, mtime=0)
    encoded = base64.b64encode(compressed).decode("ascii")
    digest = hashlib.sha256(raw).hexdigest()

    chunks = [encoded[i:i + CHUNK_SIZE] for i in range(0, len(encoded), CHUNK_SIZE)]
    lines = [
        "// Generated from main_strings_ko_menu_compact_review.json. Do not edit manually.",
        f"window.__PP2026_DEFAULT_REVIEW_JSON_SHA256__ = {json.dumps(digest)};",
        "window.__PP2026_DEFAULT_REVIEW_GZIP_B64__ =",
    ]
    lines.extend(f"  {json.dumps(chunk)}" + (" +" if i < len(chunks) - 1 else ";") for i, chunk in enumerate(chunks))
    lines.append("")
    write_atomic(args.output, "\n".join(lines))
    print(json.dumps({
        "output": str(args.output.resolve()),
        "source_bytes": len(raw),
        "gzip_bytes": len(compressed),
        "base64_bytes": len(encoded),
        "sha256": digest,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
