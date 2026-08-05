# -*- coding: utf-8 -*-
"""Build a capacity-checked RDB plan from the translated unknown cache."""
from __future__ import annotations

import argparse
import collections
import importlib.util
import json
import os
import re
import time


def load_rdblib(path):
    spec = importlib.util.spec_from_file_location("rdblib_unknown_plan", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_mapping(path):
    out = {}
    for line in open(path, encoding="utf-8-sig"):
        cols = line.rstrip("\r\n").split("\t")
        if len(cols) >= 2 and cols[0] and cols[1]:
            out[cols[0]] = cols[1][0]
    return out


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


def should_skip(src, ko):
    if not ko or ko == src or len(src.strip()) <= 1:
        return True
    if any(ord(c) < 0x20 and c not in "\r\n\t" for c in src):
        return True
    # These are resource placeholders/control labels rather than visible text.
    if "start(" in src or "@" in src or src in {"ます", "あ", "ぁ", "ー", "AーZ", "UUUDbオUU"}:
        return True
    if not any("가" <= c <= "힣" for c in ko):
        return True
    return False


# Short labels and a few baseball-specific terms need context that a generic
# translator commonly misses.  These overrides are intentionally limited to
# high-confidence UI/name cases; long player biographies remain in the cached
# translation so they can be reviewed in-game.
OVERRIDES = {
    "操作ヘルプ": "조작 도움말",
    "起用(能力・調子)": "기용(능력·컨디션)",
    "試合助っ人マネ": "경기 도우미 매니저",
    "当たり": "당첨",
    "ハズレ": "꽝",
    "伝説のとんかち＆のみ": "전설의 망치&끌",
    "覆水武明の特訓イベント回数": "후쿠미즈 타케아키의 특훈 이벤트 횟수",
    "パワマップで最も行った場所": "파워맵에서 가장 많이 간 장소",
    "DLC応援曲を含む動画のアップロード規約文": "DLC 응원곡이 포함된 동영상 업로드 약관",
    "９９年振り ９９回目優勝": "99년 만의 99번째 우승",
    "あ　り": "있음",
    "調子変化まで": "컨디션 변화까지",
    "両打ち野手": "양타 야수",
    "年殿堂入り": "년 명예의 전당",
    "他球団からのトレード依頼はありません": "다른 구단에서 트레이드 제안이 없습니다",
    "ドラフト合格選手": "드래프트 합격 선수",
    "スカウト済み選手": "스카우트 완료 선수",
    "プロ入り合計人数": "프로 입단 총인원",
    "→1軍まであと〇〇歩": "→1군까지 앞으로 〇〇걸음",
    "持っていない": "가지고 있지 않음",
    "マイオーダー": "내 오더",
    "おまかせオーダー": "자동 편성",
    "戻る": "돌아가기",
    "パワーツルハシ": "파워 곡괭이",
}


def encode(text, mapping):
    return "".join(mapping.get(c, c) for c in text).encode("utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rdb-dir", required=True)
    ap.add_argument("--rdblib", required=True)
    ap.add_argument("--master", required=True)
    ap.add_argument("--mapping", required=True)
    ap.add_argument("--existing-plan", action="append", required=True)
    ap.add_argument("--translations", required=True)
    ap.add_argument("--out-plan", required=True)
    ap.add_argument("--out-report", required=True)
    args = ap.parse_args()
    t0 = time.time()

    applied = set()
    for path in args.existing_plan:
        for item in json.load(open(path, encoding="utf-8")):
            applied.add((item["file"], int(item["off"])))
    cache = json.load(open(args.translations, encoding="utf-8"))
    trans = {x["text"]: x["korean"] for x in cache.get("translations", [])}
    mapping = load_mapping(args.mapping)
    master = json.load(open(args.master, encoding="utf-8"))
    target_files = {x.get("file") for x in master.get("rdb", []) if x.get("file")}
    print(f"번역 캐시 {len(trans):,}개 / 대상 CHK {len(target_files):,}개", flush=True)

    rdblib = load_rdblib(args.rdblib)
    dep = rdblib.RDB(args.rdb_dir, writable=False)
    plan = []
    overflow = []
    matched = 0
    skipped = 0
    try:
        for ent in dep.table:
            name = ent["name"]
            if name not in target_files or ent["flag"] not in (0, 0x20):
                continue
            try:
                body = dep.read_body(name)
            except Exception:
                continue
            if body is None:
                continue
            loc = rdblib.locate(ent["stored"], ent["flag"])
            for off, end, raw, region in iter_strings(body):
                if (name, off) in applied or len(raw) < 2 or len(raw) > 4096:
                    continue
                try:
                    src = raw.decode("utf-8")
                except UnicodeDecodeError:
                    continue
                ko = OVERRIDES.get(src, trans.get(src))
                if should_skip(src, ko):
                    skipped += 1
                    continue
                # Compact short menu-like labels first; preserve spacing for
                # prose and multiline text.
                candidates = [ko]
                if "\n" not in ko and "\r" not in ko and (len(src) <= 30 or region <= 80):
                    compact = re.sub(r"\s+", "", ko)
                    if compact and compact != ko:
                        candidates.insert(0, compact)
                chosen = None
                for cand in candidates:
                    mb = encode(cand, mapping)
                    if len(mb) <= region - 1:
                        chosen = (cand, mb)
                        break
                matched += 1
                item = {
                    "file": name,
                    "rdb": loc[0] if loc else None,
                    "stored": ent["stored"],
                    "DEC_SIZE": ent["DEC_SIZE"],
                    "flag": ent["flag"],
                    "off": off,
                    "end": end,
                    "region": region,
                    "capacity": region - 1,
                    "jp": src,
                    "ko": ko,
                    "mapped": chosen[0] if chosen else ko,
                    "mapped_bytes": len(chosen[1]) if chosen else len(encode(ko, mapping)),
                    "source_bytes": len(raw),
                    "source_hex": raw.hex(),
                    "translation_source": "google_unknown",
                }
                if chosen:
                    item["mode"] = "inplace"
                    plan.append(item)
                else:
                    item["mode"] = "overflow"
                    overflow.append(item)
            if len(plan) and len(plan) % 500 == 0:
                print(f"  추가 계획 {len(plan):,}건 / overflow {len(overflow):,} · {time.time()-t0:.0f}s", flush=True)
    finally:
        dep.close()

    plan.sort(key=lambda x: (x["file"], x["off"]))
    overflow.sort(key=lambda x: (x["file"], x["off"]))
    os.makedirs(os.path.dirname(os.path.abspath(args.out_plan)), exist_ok=True)
    json.dump(plan, open(args.out_plan, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    report = {
        "counts": {
            "matched_cache_strings": matched,
            "inplace": len(plan),
            "overflow": len(overflow),
            "skipped": skipped,
            "files": len(set(x["file"] for x in plan)),
        },
        "overflow": overflow,
        "elapsed_seconds": round(time.time() - t0, 2),
    }
    json.dump(report, open(args.out_report, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(json.dumps(report["counts"], ensure_ascii=False, indent=2), flush=True)
    print(f"계획: {args.out_plan}\n보고서: {args.out_report}")


if __name__ == "__main__":
    main()
