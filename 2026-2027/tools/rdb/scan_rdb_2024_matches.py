# -*- coding: utf-8 -*-
"""Find 2024-2025 RDB translations that can be applied to the 2026 RDB.

The 2024 master stores offsets from the old build, so offsets are deliberately
not reused.  This scanner matches the original UTF-8 string in each current
CHK and emits fresh offsets/capacity information for a safe 2026 repack.
"""
from __future__ import annotations

import argparse
import collections
import importlib.util
import json
import os
import re
import sys
import time
from typing import Dict, Iterable, Iterator, List, Tuple


def load_rdblib(path: str):
    spec = importlib.util.spec_from_file_location("rdblib_2024", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"rdblib import failed: {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# These are the ranges used by the 2024 porting tools.  They avoid treating
# arbitrary binary bytes as translatable text while retaining Japanese labels.
_CJK = (
    (0x3400, 0x4DBF),
    (0x4E00, 0x9FFF),
    (0xF900, 0xFAFF),
    (0x20000, 0x2FA1F),
)
_KANA = ((0x3040, 0x30FF), (0x31F0, 0x31FF))
_FULLWIDTH = ((0xFF01, 0xFFEF),)


def has_japanese(s: str) -> bool:
    for ch in s:
        n = ord(ch)
        if any(a <= n <= b for a, b in _CJK + _KANA + _FULLWIDTH):
            return True
    return False


def iter_nul_strings(body: bytes) -> Iterator[Tuple[int, int, bytes, int]]:
    """Yield (start, end, bytes, slot_region_length) for NUL strings.

    The region includes all consecutive NUL bytes after a string.  The final
    NUL is reserved, matching BUILD_RDB_FROM_MASTER.py's capacity rule.
    """
    p = 0
    n = len(body)
    while p < n:
        if body[p] == 0:
            p += 1
            continue
        q = body.find(b"\0", p)
        if q < 0:
            q = n
        e = q
        while e < n and body[e] == 0:
            e += 1
        yield p, q, body[p:q], e - p
        p = e


def load_mapping(path: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    with open(path, encoding="utf-8-sig") as fh:
        for line in fh:
            cols = line.rstrip("\r\n").split("\t")
            if len(cols) >= 2 and cols[0] and cols[1]:
                out[cols[0]] = cols[1][0]
    return out


def encode_game_text(text: str, mapping: Dict[str, str]) -> bytes:
    # The game has no Hangul glyphs.  Reuse the exact 2024 glyph mapping.
    return "".join(mapping.get(ch, ch) for ch in text).encode("utf-8")


def build_dicts(records: Iterable[dict]):
    by_file: Dict[str, Dict[str, str]] = {}
    global_counts: Dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    file_counts: Dict[str, Dict[str, collections.Counter]] = collections.defaultdict(
        lambda: collections.defaultdict(collections.Counter)
    )
    for rec in records:
        fn = str(rec.get("file", ""))
        jp = rec.get("jp")
        ko = rec.get("ko")
        if not fn or not isinstance(jp, str) or not isinstance(ko, str) or not ko:
            continue
        file_counts[fn][jp][ko] += 1
        global_counts[jp][ko] += 1
    for fn, rows in file_counts.items():
        by_file[fn] = {jp: c.most_common(1)[0][0] for jp, c in rows.items()}
    global_map = {jp: c.most_common(1)[0][0] for jp, c in global_counts.items()}
    return by_file, global_map, file_counts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rdb-dir", required=True)
    ap.add_argument("--master", required=True)
    ap.add_argument("--map", dest="mapping", required=True)
    ap.add_argument("--rdblib", required=True)
    ap.add_argument("--out-plan", required=True)
    ap.add_argument("--out-report", required=True)
    args = ap.parse_args()

    t0 = time.time()
    print(f"마스터 읽기: {args.master}", flush=True)
    with open(args.master, encoding="utf-8") as fh:
        master = json.load(fh)
    records = master.get("rdb", [])
    by_file, global_map, file_counts = build_dicts(records)
    mapping = load_mapping(args.mapping)
    print(
        f"번역 {len(records):,}건 / 파일 {len(by_file):,}개 / 공통문 {len(global_map):,}개 / 맵핑 {len(mapping):,}자",
        flush=True,
    )

    rdblib = load_rdblib(args.rdblib)
    dep = rdblib.RDB(args.rdb_dir, writable=False)
    plans: List[dict] = []
    overflow: List[dict] = []
    seen = 0
    decoded = 0
    matched = 0
    fit_count = 0
    files_with_match = collections.Counter()
    files_with_overflow = collections.Counter()
    skipped_error = 0
    try:
        for ent in dep.table:
            name = ent["name"]
            seen += 1
            # The master is file-scoped.  Do not read large font/image/asset
            # CHKs that have no 2024 translation rows; this also prevents a
            # common Japanese label from being injected into an unrelated
            # 2026 resource merely through the global fallback dictionary.
            if name not in by_file:
                continue
            if ent["flag"] not in (0, 0x20):
                continue
            try:
                body = dep.read_body(name)
            except Exception:
                skipped_error += 1
                continue
            if body is None:
                continue
            for start, end, raw, region in iter_nul_strings(body):
                if not raw or len(raw) < 2 or len(raw) > 4096:
                    continue
                try:
                    jp = raw.decode("utf-8")
                except UnicodeDecodeError:
                    continue
                decoded += 1
                if not has_japanese(jp):
                    continue
                ko = by_file[name].get(jp)
                if not ko or ko == jp:
                    continue
                mapped = "".join(mapping.get(ch, ch) for ch in ko)
                mapped_bytes = mapped.encode("utf-8")
                # At least one terminating NUL must remain in the slot.
                capacity = max(0, region - 1)
                item = {
                    "file": name,
                    "rdb": "RES10.RDB" if rdblib.locate(ent["stored"], ent["flag"])[2] else "RES00.RDB",
                    "stored": ent["stored"],
                    "DEC_SIZE": ent["DEC_SIZE"],
                    "flag": ent["flag"],
                    "off": start,
                    "end": end,
                    "region": region,
                    "capacity": capacity,
                    "jp": jp,
                    "ko": ko,
                    "mapped": mapped,
                    "mapped_bytes": len(mapped_bytes),
                    "source_bytes": len(raw),
                    "source_hex": raw.hex(),
                }
                matched += 1
                files_with_match[name] += 1
                if len(mapped_bytes) <= capacity:
                    item["mode"] = "inplace"
                    plans.append(item)
                    fit_count += 1
                else:
                    item["mode"] = "overflow"
                    overflow.append(item)
                    files_with_overflow[name] += 1
            if seen % 500 == 0:
                print(
                    f"  {seen:,}/{len(dep.table):,} 파일 · 매칭 {matched:,} · 제자리 {fit_count:,} · {time.time()-t0:.0f}s",
                    flush=True,
                )
    finally:
        dep.close()

    # Stable ordering makes the generated plan easy to diff and review.
    plans.sort(key=lambda x: (x["file"], x["off"], x["jp"]))
    overflow.sort(key=lambda x: (x["file"], x["off"], x["jp"]))
    os.makedirs(os.path.dirname(os.path.abspath(args.out_plan)), exist_ok=True)
    with open(args.out_plan, "w", encoding="utf-8") as fh:
        json.dump(plans, fh, ensure_ascii=False, indent=2)
    report = {
        "source": {
            "rdb_dir": os.path.abspath(args.rdb_dir),
            "master": os.path.abspath(args.master),
            "mapping": os.path.abspath(args.mapping),
        },
        "counts": {
            "rdb_entries": len(dep.table),
            "scanned_entries": seen,
            "decoded_strings": decoded,
            "matched": matched,
            "inplace": fit_count,
            "overflow": len(overflow),
            "files_with_match": len(files_with_match),
            "files_with_overflow": len(files_with_overflow),
            "read_errors": skipped_error,
        },
        "files_with_match": files_with_match,
        "files_with_overflow": files_with_overflow,
        "overflow": overflow,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "elapsed_seconds": round(time.time() - t0, 2),
    }
    with open(args.out_report, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print(json.dumps(report["counts"], ensure_ascii=False, indent=2), flush=True)
    print(f"계획: {args.out_plan}", flush=True)
    print(f"보고서: {args.out_report}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
