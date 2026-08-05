# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import collections
import importlib.util
import json
import os


def load_rdblib(path):
    spec = importlib.util.spec_from_file_location("rdblib_2024_verify", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--rdb-dir", required=True)
    ap.add_argument("--rdblib", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    plan = json.load(open(args.plan, encoding="utf-8"))
    by_file = collections.defaultdict(list)
    for item in plan:
        if item.get("mode", "inplace") == "inplace":
            by_file[item["file"]].append(item)
    rdblib = load_rdblib(args.rdblib)
    dep = rdblib.RDB(args.rdb_dir, writable=False)
    result = {
        "files": len(by_file),
        "slots": len(plan),
        "files_ok": 0,
        "slots_ok": 0,
        "slot_failures": [],
        "read_failures": [],
    }
    try:
        for name in sorted(by_file):
            try:
                body = dep.read_body(name)
            except Exception as exc:
                result["read_failures"].append({"file": name, "error": repr(exc)})
                continue
            if body is None:
                result["read_failures"].append({"file": name, "error": "missing"})
                continue
            file_ok = True
            for item in by_file[name]:
                off = int(item["off"])
                mapped = str(item["mapped"]).encode("utf-8")
                got = body[off:off + len(mapped)]
                if got != mapped:
                    file_ok = False
                    result["slot_failures"].append({
                        "file": name,
                        "off": off,
                        "jp": item.get("jp", ""),
                        "want_hex": mapped.hex(),
                        "got_hex": got.hex(),
                    })
                else:
                    result["slots_ok"] += 1
            if file_ok:
                result["files_ok"] += 1
    finally:
        dep.close()
    result["ok"] = not result["slot_failures"] and not result["read_failures"] and result["slots_ok"] == result["slots"]
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    print(json.dumps({k: result[k] for k in ("files", "slots", "files_ok", "slots_ok", "ok")}, ensure_ascii=False, indent=2))
    print(f"검증 결과: {args.out}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
