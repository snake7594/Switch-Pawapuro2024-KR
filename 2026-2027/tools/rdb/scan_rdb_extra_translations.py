# -*- coding: utf-8 -*-
"""Find additional RDB strings covered by the existing main/exe translation.

Only exact Japanese-source matches are emitted.  This avoids inventing a
translation for a binary token while allowing common UI text shared by the
executable and RDB to be reused.
"""
from __future__ import annotations

import argparse
import collections
import importlib.util
import json
import os
import time


KANA_RANGES = ((0x3040, 0x30FF), (0x31F0, 0x31FF))
CJK_RANGES = ((0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF))
FULLWIDTH_RANGES = ((0xFF01, 0xFFEF),)


def load_rdblib(path):
    spec = importlib.util.spec_from_file_location("rdblib_extra", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def in_ranges(n, ranges):
    return any(a <= n <= b for a, b in ranges)


def has_kana(s):
    return any(in_ranges(ord(ch), KANA_RANGES) for ch in s)


def has_japanese(s):
    return any(
        in_ranges(ord(ch), KANA_RANGES + CJK_RANGES + FULLWIDTH_RANGES)
        for ch in s
    )


def iter_strings(body):
    p = 0
    while p < len(body):
        if body[p] == 0:
            p += 1
            continue
        q = body.find(b"\0", p)
        if q < 0:
            q = len(body)
        e = q
        while e < len(body) and body[e] == 0:
            e += 1
        yield p, q, body[p:q], e - p
        p = e


def choose_main_map(records):
    # Prefer reviewed 2024 rows over Google rows, then the most frequent row.
    counts = collections.defaultdict(collections.Counter)
    metadata = {}
    for r in records:
        src = r.get("text")
        game = r.get("game_text")
        if not isinstance(src, str) or not isinstance(game, str) or not game:
            continue
        if r.get("patch_excluded") or r.get("localization_decision") != "translate":
            continue
        source = r.get("translation_source", "")
        priority = 2 if source == "2024" else 1
        counts[src][(priority, game, r.get("korean", ""), source)] += 1
    out = {}
    for src, c in counts.items():
        # Sort by source priority, then occurrence count.
        best = sorted(c.items(), key=lambda x: (x[0][0], x[1]), reverse=True)[0][0]
        out[src] = {"game_text": best[1], "korean": best[2], "source": best[3]}
    return out


def choose_global_map(records):
    counts = collections.defaultdict(collections.Counter)
    for r in records:
        src, ko = r.get("jp"), r.get("ko")
        if isinstance(src, str) and isinstance(ko, str) and ko:
            counts[src][ko] += 1
    out = {}
    for src, c in counts.items():
        # Only use global rows when translations agree or one clearly dominates.
        best, n = c.most_common(1)[0]
        total = sum(c.values())
        if len(c) == 1 or n / total >= 0.8:
            out[src] = best
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rdb-dir", required=True)
    ap.add_argument("--rdblib", required=True)
    ap.add_argument("--existing-plan", required=True)
    ap.add_argument("--main-json", required=True)
    ap.add_argument("--master", required=True)
    ap.add_argument("--out-plan", required=True)
    ap.add_argument("--out-report", required=True)
    args = ap.parse_args()
    t0 = time.time()

    existing = json.load(open(args.existing_plan, encoding="utf-8"))
    applied_offsets = {(x["file"], int(x["off"])) for x in existing}
    main_data = json.load(open(args.main_json, encoding="utf-8"))
    main_map = choose_main_map(main_data.get("strings", []))
    master = json.load(open(args.master, encoding="utf-8"))
    global_map = choose_global_map(master.get("rdb", []))
    target_files = {r.get("file") for r in master.get("rdb", []) if r.get("file")}
    print(f"메인 공통 번역 {len(main_map):,}개 / 2024 공통 번역 {len(global_map):,}개", flush=True)

    rdblib = load_rdblib(args.rdblib)
    dep = rdblib.RDB(args.rdb_dir, writable=False)
    extra = []
    overflow = []
    unknown = {}
    seen = decoded = japanese = 0
    main_matches = global_matches = 0
    try:
        for ent in dep.table:
            seen += 1
            if ent["name"] not in target_files:
                continue
            if ent["flag"] not in (0, 0x20):
                continue
            name = ent["name"]
            try:
                body = dep.read_body(name)
            except Exception:
                continue
            if body is None:
                continue
            loc = rdblib.locate(ent["stored"], ent["flag"])
            rdb_name = loc[0] if loc else None
            for off, end, raw, region in iter_strings(body):
                if len(raw) < 2 or len(raw) > 4096:
                    continue
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    continue
                decoded += 1
                if (name, off) in applied_offsets:
                    continue
                main = main_map.get(text)
                source_kind = "main"
                if main is None:
                    ko = global_map.get(text) if has_kana(text) else None
                    if ko:
                        main = {"game_text": ko, "korean": ko, "source": "2024-global"}
                        source_kind = "2024-global"
                if main is None:
                    if has_japanese(text) and has_kana(text):
                        key = text
                        row = unknown.setdefault(key, {"text": text, "occurrences": 0, "samples": []})
                        row["occurrences"] += 1
                        if len(row["samples"]) < 3:
                            row["samples"].append({"file": name, "off": off, "region": region})
                    continue
                japanese += 1
                mapped = main["game_text"]
                mapped_bytes = mapped.encode("utf-8")
                capacity = region - 1
                item = {
                    "file": name,
                    "rdb": rdb_name,
                    "stored": ent["stored"],
                    "DEC_SIZE": ent["DEC_SIZE"],
                    "flag": ent["flag"],
                    "off": off,
                    "end": end,
                    "region": region,
                    "capacity": capacity,
                    "jp": text,
                    "ko": main.get("korean", ""),
                    "mapped": mapped,
                    "mapped_bytes": len(mapped_bytes),
                    "source_bytes": len(raw),
                    "source_hex": raw.hex(),
                    "translation_source": main.get("source", source_kind),
                }
                if len(mapped_bytes) <= capacity:
                    extra.append(item)
                    if source_kind == "main":
                        main_matches += 1
                    else:
                        global_matches += 1
                else:
                    item["mode"] = "overflow"
                    overflow.append(item)
            if seen % 500 == 0:
                print(f"  {seen:,}/{len(dep.table):,} 파일 · 추가 {len(extra):,} · 신규 후보 {len(unknown):,} · {time.time()-t0:.0f}s", flush=True)
    finally:
        dep.close()

    # Never emit duplicate slot plans.
    uniq = {}
    for x in extra:
        uniq[(x["file"], x["off"])] = x
    extra = sorted(uniq.values(), key=lambda x: (x["file"], x["off"]))
    unknown_rows = sorted(unknown.values(), key=lambda x: (-x["occurrences"], x["text"]))
    os.makedirs(os.path.dirname(os.path.abspath(args.out_plan)), exist_ok=True)
    with open(args.out_plan, "w", encoding="utf-8") as fh:
        json.dump(extra, fh, ensure_ascii=False, indent=2)
    report = {
        "counts": {
            "rdb_entries": len(dep.table),
            "decoded_strings": decoded,
            "extra_plan": len(extra),
            "main_matches": main_matches,
            "global_matches": global_matches,
            "overflow": len(overflow),
            "unknown_kana_unique": len(unknown_rows),
            "unknown_kana_occurrences": sum(x["occurrences"] for x in unknown_rows),
        },
        "overflow": overflow,
        "unknown": unknown_rows,
        "elapsed_seconds": round(time.time() - t0, 2),
    }
    with open(args.out_report, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print(json.dumps(report["counts"], ensure_ascii=False, indent=2), flush=True)
    print(f"추가 계획: {args.out_plan}", flush=True)
    print(f"보고서: {args.out_report}", flush=True)


if __name__ == "__main__":
    main()
