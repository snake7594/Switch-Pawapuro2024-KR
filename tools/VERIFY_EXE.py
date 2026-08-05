# -*- coding: utf-8 -*-
"""빌드된 exe 무결성·품질 검증.

  1) 구조: 크기·헤더·.text·동적영역이 원본과 동일한가
  2) RELA: 전 엔트리의 addend 가 유효 범위인가, 엔트리 정렬이 유지되는가
  3) 풀 리다이렉트: exe_pool 문장이 실제로 전체 텍스트로 읽히는가
  4) 잔존: 화면에 나올 문자열영역에 가나가 남아 있는가(절대 스캔)
사용: python VERIFY_EXE.py <원본main> <빌드main> <마스터json> <tsv>
"""
import sys, os, json, struct, hashlib
from collections import Counter
import numpy as np
sys.stdout.reconfigure(encoding='utf-8')

def hdr(d):
    u = lambda o: struct.unpack_from('<I', d, o)[0]
    h = dict(TEXT_FO=u(0x10), TEXT_MO=u(0x14), TEXT_SZ=u(0x18),
             ROD_FO=u(0x20), ROD_MO=u(0x24), ROD_SZ=u(0x28),
             DATA_FO=u(0x30), DATA_MO=u(0x34), DATA_SZ=u(0x38))
    def va2fo(va):
        if h['TEXT_MO'] <= va < h['TEXT_MO']+h['TEXT_SZ']: return va-h['TEXT_MO']+h['TEXT_FO']
        if h['ROD_MO'] <= va < h['ROD_MO']+h['ROD_SZ']: return va-h['ROD_MO']+h['ROD_FO']
        if h['DATA_MO'] <= va < h['DATA_MO']+h['DATA_SZ']: return va-h['DATA_MO']+h['DATA_FO']
        return None
    M = h['TEXT_FO'] + u(h['TEXT_FO']+4)
    dfo = va2fo((M-h['TEXT_FO']+h['TEXT_MO']) + struct.unpack_from('<i', d, M+4)[0])
    DYN = {}; o = dfo
    while True:
        t, v = struct.unpack_from('<QQ', d, o)
        if t == 0: break
        DYN.setdefault(t, v); o += 16
    h.update(DYN=DYN, va2fo=va2fo, RELA_FO=va2fo(DYN[7]), RELA_CNT=DYN[8]//24,
             DYN_HI=va2fo(DYN[5])+DYN[10]-1, STR_END=h['ROD_FO']+h['ROD_SZ'],
             RO_DELTA=h['ROD_MO']-h['ROD_FO'])
    return h

def main(orig_p, built_p, master_p, tsv_p):
    orig = open(orig_p, 'rb').read(); b = open(built_p, 'rb').read()
    h = hdr(orig)
    TSV = {}
    for ln in open(tsv_p, encoding='utf-8-sig').read().splitlines():
        x = ln.split('\t')
        if len(x) >= 2 and x[0] and x[1]: TSV[x[0]] = x[1][0]
    TSVR = {v: k for k, v in TSV.items()}
    def dec(s):
        return ''.join(TSVR.get(c, c) for c in s)
    ok = True

    # 1) 구조
    print(f"[1] 크기 {len(b):,} (원본 {len(orig):,})  md5 {hashlib.md5(b).hexdigest()}")
    a1 = np.frombuffer(orig, dtype=np.uint8); a2 = np.frombuffer(b, dtype=np.uint8)
    for nm, lo, hi in (('헤더', 0, 0x100),
                       ('.text', h['TEXT_FO'], h['TEXT_FO']+h['TEXT_SZ']),
                       ('.data이후', h['DATA_FO'], len(orig))):
        same = bool((a1[lo:hi] == a2[lo:hi]).all())
        print(f"    {nm:10s} 불변 {'OK' if same else '✗ 변경됨'}")
        ok &= same
    # 동적영역 중 RELA addend 외 불변
    RF, RC = h['RELA_FO'], h['RELA_CNT']
    d1 = np.frombuffer(orig[RF:RF+RC*24], dtype='<u8').reshape(-1, 3)
    d2 = np.frombuffer(b[RF:RF+RC*24], dtype='<u8').reshape(-1, 3)
    off_ch = int((d1[:, 0] != d2[:, 0]).sum()); inf_ch = int((d1[:, 1] != d2[:, 1]).sum())
    ad_ch = int((d1[:, 2] != d2[:, 2]).sum())
    print(f"    RELA: r_offset 변경 {off_ch} · r_info 변경 {inf_ch} · addend 변경 {ad_ch:,}")
    ok &= (off_ch == 0 and inf_ch == 0)
    dyn = np.arange(0, h['DYN_HI']+1)
    diff_dyn = np.nonzero(a1[:h['DYN_HI']+1] != a2[:h['DYN_HI']+1])[0]
    inrela = ((diff_dyn >= RF) & (diff_dyn < RF+RC*24))
    pos = (diff_dyn[inrela] - RF) % 24
    bad = int(((pos < 16) | (pos >= 24)).sum()) + int((~inrela).sum())
    print(f"    동적영역 변경 {len(diff_dyn):,}B · addend(+16..24) 밖 변경 {bad}")
    ok &= (bad == 0)

    # 2) addend 유효성
    ad = d2[:, 2].astype(np.int64)
    valid = np.zeros(len(ad), dtype=bool)
    for mo, sz in ((h['TEXT_MO'], h['TEXT_SZ']), (h['ROD_MO'], h['ROD_SZ']),
                   (h['DATA_MO'], h['DATA_SZ'])):
        valid |= (ad >= mo) & (ad < mo+sz)
    valid |= (ad >= h['DATA_MO']+h['DATA_SZ'])          # bss
    valid |= (ad == 0)
    n_bad = int((~valid).sum())
    print(f"[2] addend 범위 밖 {n_bad}")
    ok &= (n_bad == 0)

    # 3) 풀 리다이렉트 확인
    master = json.load(open(master_p, encoding='utf-8'))
    ro_mo, ro_fo = h['ROD_MO'], h['ROD_FO']
    pidx = {}
    for seg_fo, seg_sz in ((ro_fo, h['ROD_SZ']), (h['DATA_FO'], h['DATA_SZ'])):
        n = seg_sz // 8
        w = np.frombuffer(orig[seg_fo:seg_fo+n*8], dtype='<u8')
        for i in np.nonzero((w >= ro_mo) & (w < ro_mo+h['ROD_SZ']))[0].tolist():
            pidx.setdefault(int(w[i]), []).append(seg_fo + i*8)
    # exe_ext(마이라이프 완성문장)가 나중에 덮어쓰는 엔트리는 제외 — 그쪽이 우선이다
    ent_addend = set()
    for x in master.get('exe_ext', []):
        for e in x['ents']: ent_addend.add(e + 16)
    good = bad2 = skipped = 0
    for r in master.get('exe_pool', []):
        va = ro_mo + (r['off'] - ro_fo)
        locs = [l for l in pidx.get(va, []) if ro_fo <= l < ro_fo + h['ROD_SZ']]
        if not locs: bad2 += 1; continue
        if any(l in ent_addend for l in locs): skipped += 1; continue
        nv = struct.unpack_from('<Q', b, locs[0])[0]
        fo = nv - h['RO_DELTA']
        s = b[fo:b.find(b'\x00', fo)]
        try: t = dec(s.decode('utf-8'))
        except UnicodeDecodeError: t = None
        if t == r['ko']: good += 1
        else: bad2 += 1
    print(f"[3] exe_pool 리다이렉트 정상 {good:,} / 불일치 {bad2:,} "
          f"(exe_ext 우선 적용으로 제외 {skipped:,})")
    ok &= (bad2 == 0)

    # 4) 잔존 가나 절대 스캔(마스터가 손댄 슬롯 한정)
    KANA = lambda c: ('぀' <= c <= 'ゟ') or ('ァ' <= c <= 'ヺ')
    left = 0; samples = []
    for r in master['exe']:
        o = r['off']
        s = b[o:b.find(b'\x00', o)]
        try: t = s.decode('utf-8')
        except UnicodeDecodeError: continue
        if any(KANA(c) for c in t):
            left += 1
            if len(samples) < 8: samples.append(t[:30])
    print(f"[4] 마스터 슬롯 중 가나 잔존 {left:,}  {samples}")

    # 5) 매달린 UTF-8 / 서식 지정자
    import re
    SPEC = re.compile(r'%[-+ #0]*[0-9]*(?:\.[0-9]+)?(?:hh|h|ll|l|L|z|j|t)?[diouxXeEfgGaAcspn%]')
    spec_bad = 0
    for r in master['exe']:
        o = r['off']
        s = b[o:b.find(b'\x00', o)]
        try: t = s.decode('utf-8')
        except UnicodeDecodeError: spec_bad += 1; continue
        if len(SPEC.findall(t)) > len(SPEC.findall(r['jp'])): spec_bad += 1
    print(f"[5] 디코드 실패 또는 서식지정자 초과 {spec_bad:,}")
    ok &= (spec_bad == 0)

    print("\n" + ("✅ 전체 통과" if ok else "❌ 실패 항목 있음"))
    return 0 if ok else 1

if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:5]))
