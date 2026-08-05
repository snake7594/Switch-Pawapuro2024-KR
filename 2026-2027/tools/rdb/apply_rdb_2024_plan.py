# -*- coding: utf-8 -*-
"""Apply the offset-aware 2024 translation plan to a 2026 RDB set.

The output directory must already contain the 2026 RDB/RDI files.  It is
normally seeded from the existing font-patched RES00.RDB, so this script keeps
the user's current font while replacing only verified UTF-8 string slots.
"""
from __future__ import annotations

import argparse
import bisect
import collections
import importlib.util
import json
import os
import struct
import time
import zlib


def load_rdblib(path: str):
    spec = importlib.util.spec_from_file_location("rdblib_2024_apply", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"rdblib import failed: {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--rdb-dir", required=True, help="output RDB directory to modify")
    ap.add_argument("--rdblib", required=True)
    ap.add_argument("--summary", required=True)
    ap.add_argument(
        "--no-relocate",
        action="store_true",
        help="skip a whole CHK when its recompressed slot exceeds the original gap",
    )
    args = ap.parse_args()

    t0 = time.time()
    with open(args.plan, encoding="utf-8") as fh:
        plan = json.load(fh)
    by_file = collections.defaultdict(list)
    for item in plan:
        # Older extra-plan files omit the explicit mode because every emitted
        # row was already capacity-checked; treat those rows as in-place.
        if item.get("mode", "inplace") == "inplace":
            by_file[item["file"]].append(item)
    for rows in by_file.values():
        rows.sort(key=lambda x: (x["off"], x["end"]))
    print(f"계획 {len(plan):,}건 / 적용 대상 {sum(map(len, by_file.values())):,}건 / 파일 {len(by_file):,}개", flush=True)

    rdblib = load_rdblib(args.rdblib)
    dep = rdblib.RDB(args.rdb_dir, writable=True)

    # Original slot starts are the only valid in-place gap boundaries.  A
    # relocated slot is appended after the pre-existing RDB end.
    laid = {"RES00.RDB": [], "RES10.RDB": []}
    for ent in dep.table:
        loc = rdblib.locate(ent["stored"], ent["flag"])
        if loc:
            laid[loc[0]].append(loc[1])
    for name in laid:
        laid[name].sort()
    base_end = {
        name: os.path.getsize(os.path.join(args.rdb_dir, name))
        for name in dep.f
    }
    cursor = {name: rdblib.align_up(size, rdblib.SECTOR) for name, size in base_end.items()}

    def gap(rdb_name: str, local: int) -> int:
        arr = laid[rdb_name]
        j = bisect.bisect_right(arr, local)
        return (arr[j] if j < len(arr) else base_end[rdb_name]) - local

    stats = collections.Counter(
        files_seen=0,
        files_changed=0,
        slots_planned=len(plan),
        slots_applied=0,
        slots_mismatch=0,
        slots_bad_capacity=0,
        files_skipped=0,
        inplace=0,
        relocated=0,
        read_errors=0,
        relocation_skipped=0,
    )
    mismatches = []
    changed = []
    try:
        for name in sorted(by_file):
            stats["files_seen"] += 1
            ent = dep.idx.get(name)
            if not ent or ent["flag"] not in (0, 0x20):
                stats["files_skipped"] += 1
                continue
            try:
                body = bytearray(dep.read_body(name))
            except Exception as exc:
                stats["read_errors"] += 1
                mismatches.append({"file": name, "reason": "read_error", "error": repr(exc)})
                continue
            before = bytes(body)
            applied_here = []
            for item in by_file[name]:
                off = int(item["off"])
                end = int(item["end"])
                region = int(item["region"])
                old = bytes.fromhex(item["source_hex"])
                mapped = str(item["mapped"]).encode("utf-8")
                capacity = int(item["capacity"])
                actual = bytes(body[off:end]) if 0 <= off <= end <= len(body) else b""
                if actual != old:
                    stats["slots_mismatch"] += 1
                    mismatches.append({
                        "file": name,
                        "off": off,
                        "jp": item.get("jp", ""),
                        "reason": "source_mismatch",
                        "expected_hex": old.hex(),
                        "actual_hex": actual.hex(),
                    })
                    continue
                if len(mapped) > capacity or off + region > len(body):
                    stats["slots_bad_capacity"] += 1
                    mismatches.append({
                        "file": name,
                        "off": off,
                        "jp": item.get("jp", ""),
                        "reason": "capacity_or_bounds",
                        "mapped_bytes": len(mapped),
                        "capacity": capacity,
                        "region": region,
                        "body_len": len(body),
                    })
                    continue
                body[off:off + region] = mapped + b"\0" * (region - len(mapped))
                stats["slots_applied"] += 1
                applied_here.append(item)

            if bytes(body) == before:
                continue
            loc = rdblib.locate(ent["stored"], ent["flag"])
            if not loc:
                stats["files_skipped"] += 1
                continue
            rdb_name, local, is10 = loc
            key = rdblib.file_key(name)
            f = dep.f[rdb_name]
            f.seek(local)
            header = bytearray(rdblib.crypt_fast(f.read(32), key))
            if ent["flag"] == 0x20:
                comp = zlib.compress(bytes(body), 9)
                dec_size = rdblib.align_up(len(body), 4)
                struct.pack_into("<I", header, 0x18, len(comp))
            else:
                comp = bytes(body)
                dec_size = rdblib.align_up(32 + len(body), 4)
                struct.pack_into("<I", header, 0x18, dec_size)
            need = rdblib.align_up(32 + len(comp), 4)
            if need <= gap(rdb_name, local):
                new_local = local
                new_stored = ent["stored"]
                struct.pack_into("<I", header, 0x1C, local // rdblib.SECTOR)
                blob = bytearray(need)
                stats["inplace"] += 1
            else:
                if args.no_relocate:
                    stats["relocation_skipped"] += 1
                    mismatches.append({
                        "file": name,
                        "reason": "relocation_disabled",
                        "need": need,
                        "gap": gap(rdb_name, local),
                        "slots": len(applied_here),
                    })
                    continue
                new_local = cursor[rdb_name]
                sector = new_local // rdblib.SECTOR
                new_stored = sector + (0x1000000 if is10 else 0)
                struct.pack_into("<I", header, 0x1C, sector)
                phys = rdblib.align_up(max(dec_size, 32 + len(comp)), rdblib.SECTOR)
                blob = bytearray(phys)
                cursor[rdb_name] = new_local + phys
                stats["relocated"] += 1
            blob[:32] = header
            blob[32:32 + len(comp)] = comp
            f.seek(new_local)
            f.write(rdblib.crypt_fast(bytes(blob), key))
            rec_off = ent["rec_off"]
            struct.pack_into("<I", dep.dec, rec_off, new_stored)
            struct.pack_into("<I", dep.dec, rec_off + 4, dec_size)
            ent["stored"] = new_stored
            ent["DEC_SIZE"] = dec_size
            stats["files_changed"] += 1
            changed.append({
                "file": name,
                "rdb": rdb_name,
                "old_stored": int(item.get("stored", 0)) if applied_here else None,
                "new_stored": new_stored,
                "old_local": local,
                "new_local": new_local,
                "old_dec_size": int(item.get("DEC_SIZE", 0)) if applied_here else None,
                "new_dec_size": dec_size,
                "compressed_size": len(comp),
                "slots": len(applied_here),
                "where": "inplace" if new_local == local else "relocated",
                "body_length": len(body),
            })
            if stats["files_changed"] % 25 == 0:
                print(
                    f"  {stats['files_changed']:,}파일 / {stats['slots_applied']:,}슬롯 "
                    f"({time.time()-t0:.0f}s)",
                    flush=True,
                )
    finally:
        # The RDI is written while the decrypted table is still available.
        out_rdi = os.path.join(args.rdb_dir, "RES00.RDI")
        with open(out_rdi, "wb") as fh:
            fh.write(rdblib.crypt_fast(bytes(dep.dec), rdblib.RDI_KEY))
        dep.close()

    result = {
        "stats": dict(stats),
        "changed": changed,
        "mismatches": mismatches,
        "output_dir": os.path.abspath(args.rdb_dir),
        "plan": os.path.abspath(args.plan),
        "elapsed_seconds": round(time.time() - t0, 2),
    }
    with open(args.summary, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    print(json.dumps(result["stats"], ensure_ascii=False, indent=2), flush=True)
    print(f"요약: {args.summary}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
