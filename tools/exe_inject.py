# -*- coding: utf-8 -*-
"""exe(main NSO) 한국어 주입 — 길이 무제약(거의):
 1) 제자리+슬랙(원본+뒤 NUL런에 들어가면)
 2) 포인터 redirect (.rodata zero-run 풀에 새 문자열 쓰고 8B 포인터를 새 VA로 교체)
 3) 둘 다 안 되면 UTF-8 경계로 잘라내기(pcrel 직접참조 등, 소수)
출력: inject_out/main
"""
import json, struct, os
import numpy as np
import inject_all as IA   # ENC_EXE
import inject_lib as L

SRC = os.path.join("!exefs-작업", "main-원본")
OUT = os.path.join("inject_out", "main")

def main():
    data = bytearray(open(SRC, "rb").read())
    tx_fo, tx_mo, tx_sz = struct.unpack_from("<III", data, 0x10)
    ro_fo, ro_mo, ro_sz = struct.unpack_from("<III", data, 0x20)
    da_fo, da_mo, da_sz = struct.unpack_from("<III", data, 0x30)

    # 1) 포인터 위치 인덱스: VA(→.rodata) -> [data내 바이트오프셋들]
    from collections import defaultdict
    pidx = defaultdict(list)
    lo, hi = ro_mo, ro_mo + ro_sz
    for seg_fo, seg_sz in [(ro_fo, ro_sz), (da_fo, da_sz)]:
        for shift in (0, 4):  # 8B/4B 정렬 포인터
            base = seg_fo + shift
            n = (seg_sz - shift) // 8
            arr = np.frombuffer(bytes(data[base:base + n*8]), dtype="<u8")
            mask = (arr >= lo) & (arr < hi)
            for i in np.nonzero(mask)[0]:
                pidx[int(arr[i])].append(base + int(i)*8)

    # 2) zero-run 풀 (.rodata, >=16). (ro 내 상대오프셋, 길이)
    runs = []
    i = 0; ro_end = ro_fo + ro_sz
    while i < ro_end - ro_fo:
        if data[ro_fo + i] == 0:
            j = i
            while j < ro_sz and data[ro_fo + j] == 0: j += 1
            if j - i >= 16: runs.append([i, j - i])
            i = j
        else:
            i += 1
    runs.sort(key=lambda r: -r[1])
    pool_total = sum(r[1] for r in runs)
    cursor = 0
    def alloc(need):
        nonlocal cursor
        for r in runs:
            if r[1] >= need:
                pos = r[0]; r[0] += need; r[1] -= need
                return pos
        return None

    doc = json.load(open("번역_일본어.json", encoding="utf-8"))
    # exe 점유: (offset, old_len, ko_bytes)  — 같은 ko 중복 va는 각자 처리
    jobs = []
    for s in doc["strings"]:
        ko = s.get("ko", "").strip()
        if not ko: continue
        kob = IA.ENC_EXE.encode(ko)
        for o in s["occurrences"]:
            if o["method"] == "exe":
                jobs.append((o["offset"], o["len"], kob))

    inplace = redirect = trunc = nopool = 0
    for off, old_len, kob in jobs:
        # slack
        T = 0; k = off + old_len
        while k < len(data) and data[k] == 0: T += 1; k += 1
        cap = old_len + T - 1 if T > 0 else old_len
        region_end = off + old_len + T
        if len(kob) <= cap:
            data[off:off+len(kob)] = kob
            data[off+len(kob):region_end] = b"\x00" * (region_end - off - len(kob))
            inplace += 1
            continue
        # redirect
        va = ro_mo + (off - ro_fo)
        ptr_locs = pidx.get(va)
        if ptr_locs:
            need = len(kob) + 1
            pos = alloc(need)
            if pos is not None:
                nfo = ro_fo + pos; nva = ro_mo + pos
                data[nfo:nfo+len(kob)] = kob; data[nfo+len(kob)] = 0
                for loc in ptr_locs:
                    data[loc:loc+8] = struct.pack("<Q", nva)
                redirect += 1
                continue
            else:
                nopool += 1
        # truncate (UTF-8 경계)
        nb = kob[:cap]
        while nb and (nb[-1] & 0xC0) == 0x80: nb = nb[:-1]
        data[off:off+len(nb)] = nb
        data[off+len(nb):region_end] = b"\x00" * (region_end - off - len(nb))
        trunc += 1

    os.makedirs("inject_out", exist_ok=True)
    open(OUT, "wb").write(data)
    print("=" * 60)
    print("exe 주입: 총 %d occ" % len(jobs))
    print("  제자리+슬랙 %d, 포인터redirect %d, 잘림 %d (풀부족 %d)" % (inplace, redirect, trunc, nopool))
    print("  풀 사용: 초기 %d → 잔여 %d 바이트" % (pool_total, sum(r[1] for r in runs)))
    print("  출력: %s" % OUT)
    print("=" * 60)

if __name__ == "__main__":
    main()
