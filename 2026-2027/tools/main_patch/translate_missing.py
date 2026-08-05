"""Fill untranslated main-string entries with Japanese -> Korean MT.

The 2024 patch supplies a large, high-quality local translation dictionary.
This helper only sends the remaining unique strings to Google's public
translation endpoint, in short marker-delimited batches, and keeps a local
cache so an interrupted run is resumable.  Placeholders are protected before
translation and restored afterwards.
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_JSON = ROOT / "main_patch" / "main_strings_ko.json"
DEFAULT_CACHE = ROOT / "main_patch" / "main_translation_google.json"

MARKER_RE = re.compile(r"QX(\d{6})XQ")
TOKEN_RE = re.compile(
    r"%\d*\$?[+#0\- ]*\d*(?:\.\d+)?[sdifuxX]|<[^>\r\n]{1,80}>|\{[^}\r\n]{1,80}\}"
)


def protect(text: str) -> tuple[str, dict[str, str]]:
    saved: dict[str, str] = {}

    def repl(m: re.Match[str]) -> str:
        token = f"QZ{len(saved):04d}ZQ"
        saved[token] = m.group(0)
        return token

    return TOKEN_RE.sub(repl, text), saved


def restore(text: str, saved: dict[str, str]) -> str:
    for token, original in saved.items():
        text = text.replace(token, original)
    return text


def request_batch(batch: list[tuple[int, str]], retries: int = 4) -> dict[int, str]:
    # Put a marker before and after every source.  The endpoint preserves this
    # ASCII marker, even while translating the surrounding Japanese.
    protected: dict[int, dict[str, str]] = {}
    pieces: list[str] = []
    for idx, text in batch:
        p, saved = protect(text)
        protected[idx] = saved
        pieces.append(f"QX{idx:06d}XQ\n{p}\n")
    query = "".join(pieces)
    url = (
        "https://translate.googleapis.com/translate_a/single?client=gtx"
        "&sl=ja&tl=ko&dt=t&q=" + urllib.parse.quote(query, safe="")
    )
    last: Exception | None = None
    for attempt in range(retries):
        try:
            raw = urllib.request.urlopen(url, timeout=45).read()
            obj = json.loads(raw.decode("utf-8"))
            translated = "".join(part[0] for part in obj[0] if part and part[0])
            marks = list(MARKER_RE.finditer(translated))
            result: dict[int, str] = {}
            for i, mark in enumerate(marks):
                idx = int(mark.group(1))
                end = marks[i + 1].start() if i + 1 < len(marks) else len(translated)
                value = translated[mark.end():end].strip(" \r\n")
                # The next source starts with a marker.  A translator may add
                # one trailing newline; it is not part of the game string.
                result[idx] = restore(value, protected.get(idx, {}))
            # If a marker was dropped, retain the original for that item and
            # let the caller count it as a failed translation.
            for idx, text in batch:
                result.setdefault(idx, text)
            return result
        except Exception as exc:  # pragma: no cover - network dependent
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"translation request failed: {last}")


def batches(items: list[tuple[int, str]], max_chars: int = 1800) -> list[list[tuple[int, str]]]:
    out: list[list[tuple[int, str]]] = []
    current: list[tuple[int, str]] = []
    size = 0
    for item in items:
        n = len(item[1]) + 24
        if current and size + n > max_chars:
            out.append(current)
            current, size = [], 0
        current.append(item)
        size += n
    if current:
        out.append(current)
    return out


def map_game_text(korean: str, mapping: dict[str, str]) -> tuple[str, list[str]]:
    out: list[str] = []
    missing: list[str] = []
    for ch in korean:
        if "\uAC00" <= ch <= "\uD7A3":
            mapped = mapping.get(ch)
            if mapped is None:
                missing.append(ch)
                out.append(ch)
            else:
                out.append(mapped)
        else:
            out.append(ch)
    return "".join(out), missing


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=Path, default=DEFAULT_JSON)
    ap.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--all", action="store_true", help="translate every unknown entry; default is dialogue/long text")
    args = ap.parse_args()

    obj = json.loads(args.json.read_text(encoding="utf-8"))
    records = obj["strings"]
    cache: dict[str, str] = {}
    if args.cache.exists():
        cache = json.loads(args.cache.read_text(encoding="utf-8"))

    # Duplicate occurrences share a translation request.  By default focus on
    # dialogue/help blocks and longer strings; the 2024 dictionary already
    # covers the vast majority of short labels.  --all can fill the rest.
    candidates: dict[str, int] = {}
    for rec in records:
        if rec["translation_source"] != "untranslated":
            continue
        text = rec["text"]
        if not args.all and not ("\n" in text or len(text) >= 30):
            continue
        if text not in cache:
            candidates.setdefault(text, len(candidates))
    items = list(candidates.items())
    # Use stable six-digit IDs independent of the dictionary's hash order.
    indexed = [(i, text) for i, (text, _) in enumerate(items)]
    bs = batches(indexed)
    print(f"candidates={len(indexed)} batches={len(bs)} cached={len(cache)}")

    translated: dict[int, str] = {}
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(request_batch, batch): batch for batch in bs}
        done = 0
        for future in as_completed(futures):
            result = future.result()
            translated.update(result)
            done += 1
            if done % 20 == 0 or done == len(bs):
                print(f"translated_batches={done}/{len(bs)}")

    for i, text in indexed:
        value = translated.get(i, text)
        # A failed marker parse returns the Japanese input; do not cache it as
        # a successful MT result.
        if value != text:
            cache[text] = value
    args.cache.parent.mkdir(parents=True, exist_ok=True)
    args.cache.write_text(json.dumps(cache, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # Import the exact SJIS map from the extraction helper, avoiding a second
    # copy of the font-order logic.
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from main_strings import DEFAULT_FONT, korean_to_cjk

    game_map = korean_to_cjk(DEFAULT_FONT)
    applied = 0
    missing_chars: set[str] = set()
    for rec in records:
        if rec["translation_source"] != "untranslated":
            continue
        ko = cache.get(rec["text"])
        if not ko:
            continue
        encoded, missing = map_game_text(ko, game_map)
        rec["korean"] = ko
        rec["game_text"] = encoded
        rec["translation_source"] = "google"
        rec["game_byte_length"] = len(encoded.encode("utf-8"))
        rec["needs_expansion"] = rec["game_byte_length"] + 1 > rec["capacity"]
        missing_chars.update(missing)
        applied += 1
    obj["translated_count"] = sum(r["translation_source"] != "untranslated" for r in records)
    obj["untranslated_count"] = len(records) - obj["translated_count"]
    obj["unsupported_hangul"] = {c: sum(1 for r in records if c in r.get("korean", "")) for c in sorted(missing_chars)}
    args.json.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"applied_occurrences={applied} cache={len(cache)} unsupported={sorted(missing_chars)}")


if __name__ == "__main__":
    main()
