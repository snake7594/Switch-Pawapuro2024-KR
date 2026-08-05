# -*- coding: utf-8 -*-
"""베이스 실행파일 생성 = 원본 main + '죽은 zero-run 풀' 리다이렉트 계층.

SAFE_REDIRECT.py(v2) 의 공법을 마스터 단일소스 기준으로 재구현한 것.
  - 제자리 예산(maxb)에 안 들어가는 번역은 잘려서 표시된다.
  - 그중 '데이터 포인터(=RELA addend 등 8정렬 워드)'가 가리키는 문자열은,
    죽은 zero-run 풀에 전체 문장을 기록하고 그 포인터들을 풀 VA 로 바꿔 온전히 표시한다.
  - 풀 조건(전부 만족): run>=64B · run 내부를 가리키는 데이터포인터 없음 ·
    run 이 걸친 페이지를 ADRP/ADR 로 참조하는 코드 없음 · 양끝 32B 예약.
  - .text / 헤더 / 파일크기 불변.

사용: python BUILD_BASE.py <원본main> <마스터json> <tsv> <출력>
"""
import sys, os, struct, json
from collections import defaultdict
import numpy as np
sys.stdout.reconfigure(encoding='utf-8')

RES, MINRUN = 32, 64

def main(orig_path, master_path, tsv_path, out_path):
    orig = open(orig_path, 'rb').read()
    data = bytearray(orig)
    tx_fo, tx_mo, tx_sz = struct.unpack_from('<III', orig, 0x10)
    ro_fo, ro_mo, ro_sz = struct.unpack_from('<III', orig, 0x20)
    da_fo, da_mo, da_sz = struct.unpack_from('<III', orig, 0x30)
    ro_lo, ro_hi = ro_mo, ro_mo + ro_sz

    TSV = {}
    for ln in open(tsv_path, encoding='utf-8-sig').read().splitlines():
        x = ln.split('\t')
        if len(x) >= 2 and x[0] and x[1]: TSV[x[0]] = x[1][0]
    enc = lambda ko: ''.join(TSV.get(c, c) for c in ko).encode('utf-8')

    # ---- 데이터 포인터 색인: 8정렬 워드값이 .rodata VA ----
    # 색인은 .rodata + .data 양쪽에서 만든다(풀 후보에서 배제할 참조를 과수집하기 위해).
    # ⚠ 그러나 '재작성'은 .rodata 안(=DT_RELA addend 등)만 한다.
    #   .data 슬롯은 로더가 재배치로 덮어쓰므로 쓸 필요가 없고,
    #   재배치 대상이 아닌 .data 워드는 포인터가 아닐 수 있다(v1.4 도 .data 를 건드리지 않았다).
    pidx = defaultdict(list)
    for seg_fo, seg_sz in ((ro_fo, ro_sz), (da_fo, da_sz)):
        n = seg_sz // 8
        arr = np.frombuffer(orig[seg_fo:seg_fo + n*8], dtype='<u8')
        for i in np.nonzero((arr >= ro_lo) & (arr < ro_hi))[0].tolist():
            pidx[int(arr[i])].append(seg_fo + i*8)
    def writable(locs):
        return [l for l in locs if ro_fo <= l < ro_fo + ro_sz]
    tgt_sorted = np.array(sorted(pidx), dtype='<u8')
    print(f"데이터포인터 타깃 {len(tgt_sorted):,} (참조 {sum(len(v) for v in pidx.values()):,}곳)")

    # ---- 코드가 참조하는 .rodata 페이지 ----
    txt = np.frombuffer(orig[tx_fo:tx_fo + (tx_sz//4)*4], dtype='<u4')
    pc = tx_mo + np.arange(len(txt), dtype=np.int64) * 4
    w = txt.astype(np.int64)
    imm = (((w >> 5) & 0x7FFFF) << 2) | ((w >> 29) & 3)
    imm = np.where(imm & (1 << 20), imm - (1 << 21), imm)
    pages = set()
    m = (txt & 0x9F000000) == 0x90000000                      # ADRP
    tp = ((pc[m] >> 12) << 12) + (imm[m] << 12)
    pages |= set((tp[(tp >= ro_lo - 0x1000) & (tp < ro_hi)] >> 12).tolist())
    m = (txt & 0x9F000000) == 0x10000000                      # ADR
    ta = pc[m] + imm[m]
    pages |= set((ta[(ta >= ro_lo) & (ta < ro_hi)] >> 12).tolist())
    print(f"코드참조 .rodata 페이지 {len(pages):,}")

    # ---- 안전 풀 ----
    a = np.frombuffer(orig, dtype=np.uint8)[ro_fo:ro_fo+ro_sz]
    nz = np.nonzero(a != 0)[0]
    starts = np.concatenate(([0], nz + 1)); ends = np.concatenate((nz, [ro_sz]))
    keep = (ends - starts) >= MINRUN
    runs = []
    for s, e in zip(starts[keep].tolist(), ends[keep].tolist()):
        s_va, e_va = ro_mo + s, ro_mo + e
        lo = int(np.searchsorted(tgt_sorted, s_va)); hi = int(np.searchsorted(tgt_sorted, e_va))
        if hi > lo: continue
        if any(p in pages for p in range(s_va >> 12, ((e_va - 1) >> 12) + 1)): continue
        runs.append([s + RES, (e - RES) - (s + RES)])
    runs = [r for r in runs if r[1] >= 8]
    runs.sort(key=lambda r: -r[1])
    print(f"안전 풀 {len(runs):,} runs, {sum(r[1] for r in runs):,}B")

    def alloc(need):
        for r in runs:
            if r[1] >= need:
                pos = r[0]; r[0] += need; r[1] -= need; return pos
        return None

    master = json.load(open(master_path, encoding='utf-8'))
    # exe_pool = 제자리 예산을 넘겨 잘리는 문장의 '전체 텍스트'. 결정적 순서로 처리.
    entries = sorted(master.get('exe_pool', []), key=lambda r: r['off'])
    st = defaultdict(int); written = []
    for r in entries:
        off, ko = r['off'], r['ko']
        kob = enc(ko)
        va = ro_mo + (off - ro_fo)
        locs = writable(pidx.get(va, []))
        if not locs: st['noptr'] += 1; continue
        pos = alloc(len(kob) + 1)
        if pos is None: st['poolfull'] += 1; continue
        nfo = ro_fo + pos
        data[nfo:nfo+len(kob)] = kob; data[nfo+len(kob)] = 0
        for loc in locs: struct.pack_into('<Q', data, loc, ro_mo + pos)
        written.append((nfo, nfo + len(kob) + 1))
        st['redirect'] += 1; st['ptrs'] += len(locs)
    print(f"리다이렉트 {st['redirect']:,}건(포인터 {st['ptrs']:,}곳) / exe_pool {len(entries):,} · "
          f"포인터無 {st['noptr']:,} · 풀부족 {st['poolfull']:,}")

    # ---- 검증 ----
    an = np.frombuffer(bytes(data), dtype=np.uint8); ao = np.frombuffer(orig, dtype=np.uint8)
    diff = np.nonzero(ao != an)[0]
    assert len(data) == len(orig), "크기 변동"
    assert int((diff < 0x100).sum()) == 0, "헤더 변경"
    assert int(((diff >= tx_fo) & (diff < tx_fo + tx_sz)).sum()) == 0, ".text 변경"
    assert int((diff >= da_fo).sum()) == 0, ".data 변경"
    ok = np.zeros(len(orig), dtype=bool)
    for l, h in written: ok[l:h] = True
    for va, locs in pidx.items():
        pass
    for r in master['exe']:
        pass
    # 풀 기록 자리는 원본에서 전부 NUL 이어야 한다
    for l, h in written:
        assert ao[l:h].max() == 0, f"풀 기록 자리가 비어있지 않음 0x{l:x}"
    print(f"검증: 크기·헤더·.text 불변, 풀 기록 {sum(h-l for l,h in written):,}B 전부 원본 NUL 자리")
    open(out_path, 'wb').write(bytes(data))
    import hashlib
    print(f"→ {out_path}  md5 {hashlib.md5(bytes(data)).hexdigest()}  변경 {len(diff):,}B")

if __name__ == '__main__':
    main(*sys.argv[1:5])
