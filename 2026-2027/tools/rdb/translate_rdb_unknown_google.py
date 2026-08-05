# -*- coding: utf-8 -*-
"""Translate reviewable RDB-only Japanese candidates using Google Translate.

This is a translation cache builder only; it never writes an RDB.  Structural
tokens and control-byte strings are excluded, and the resulting cache is later
capacity-checked before any patch is emitted.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import time

import httpx


def usable(text: str) -> bool:
    if len(text.strip()) <= 1:
        return False
    if any(ord(c) < 0x20 and c not in "\r\n\t" for c in text):
        return False
    if "start(" in text or "@" in text:
        return False
    if re.fullmatch(r"[あいうえお]{6,}", text):
        return False
    # A single prolonged-sound mark or punctuation placeholder is not a label.
    if all(c in "ー・…—-_　 " for c in text):
        return False
    return True


def translate_one(text: str):
    url = "https://translate.googleapis.com/translate_a/single"
    last = None
    for attempt in range(4):
        try:
            r = httpx.get(
                url,
                params={"client": "gtx", "sl": "ja", "tl": "ko", "dt": "t", "q": text},
                timeout=30,
            )
            if r.status_code != 200:
                last = f"http_{r.status_code}"
                time.sleep(0.7 * (attempt + 1))
                continue
            data = json.loads(r.content.decode("utf-8"))
            parts = data[0] or []
            out = "".join(p[0] for p in parts if p and p[0])
            if out:
                return text, out, None
            last = "empty"
        except Exception as exc:
            last = repr(exc)
        time.sleep(0.7 * (attempt + 1))
    return text, None, last


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    report = json.load(open(args.report, encoding="utf-8"))
    candidates = [x for x in report.get("unknown", []) if usable(x["text"])]
    print(f"후보 {len(candidates):,}개 / 제외 {len(report.get('unknown', []))-len(candidates):,}개", flush=True)
    results = {}
    failures = []
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [pool.submit(translate_one, x["text"]) for x in candidates]
        for fut in concurrent.futures.as_completed(futures):
            text, ko, err = fut.result()
            done += 1
            if ko:
                # Keep occurrence/sample metadata for later slot planning.
                row = next(x for x in candidates if x["text"] == text)
                results[text] = {
                    "text": text,
                    "korean": ko,
                    "occurrences": row["occurrences"],
                    "samples": row["samples"],
                }
            else:
                failures.append({"text": text, "error": err})
            if done % 100 == 0:
                print(f"  {done:,}/{len(candidates):,} 완료", flush=True)
    out = {
        "count": len(results),
        "failed": len(failures),
        "translations": sorted(results.values(), key=lambda x: (-x["occurrences"], x["text"])),
        "failures": failures,
        "source_report": os.path.abspath(args.report),
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(json.dumps({"translated": out["count"], "failed": out["failed"]}, ensure_ascii=False, indent=2), flush=True)
    print(f"번역 캐시: {args.out}")


if __name__ == "__main__":
    main()
