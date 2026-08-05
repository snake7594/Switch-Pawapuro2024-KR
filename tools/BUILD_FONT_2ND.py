# -*- coding: utf-8 -*-
"""COMMON_2D_2ND.CHK(1.15.0 신규 폰트) 한글판 생성.

1.15.0 에서 COMMON_2D_ADD.CHK 가 사라지고 COMMON_2D_2ND.CHK 가 생겼다.
2ND 는 COMMON_2D 와 같은 UNCDFONT 구조(FNTL 56x56 / FNTS 44x44)에 한자 몇 자가 추가된 것.
→ 한글 COMMON_2D 의 tsv 대상 셀 글리프를 2ND 의 같은 코드포인트 셀에 복사한다(메트릭 동반).

사용: python BUILD_FONT_2ND.py <원본RDB폴더> <한글COMMON_2D본문> <tsv> <출력본문>
"""
import sys, os, struct, zlib, hashlib
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r"C:\Users\Jay\Desktop\z\파워풀2024-2025\Switch-Pawapuro2024-KR\tools")
from rdblib import RDB

DELTA = {0: -6, 1: 0}   # 청크 idx → 글리프 데이터 위치 델타 (FNTL / FNTS)

def parse(data):
    out = []; i = 0
    while True:
        i = data.find(b'UNCDFONT', i)
        if i < 0: break
        base = i - 0x10
        cnt = struct.unpack_from('<I', data, base+0x20)[0]
        w = struct.unpack_from('<I', data, base+0x24)[0]
        h = struct.unpack_from('<I', data, base+0x28)[0]
        recs = {}
        for k in range(cnt):
            u, off, met = struct.unpack_from('<III', data, base+0x3C+12*k)
            recs[u] = (off, met, base+0x3C+12*k)
        out.append(dict(base=base, cnt=cnt, w=w, h=h, recs=recs, slot=w*h//2))
        i += 8
    return out

def main(rdbdir, kor2d_path, tsv_path, out_path):
    TSV = {}
    for ln in open(tsv_path, encoding='utf-8-sig').read().splitlines():
        x = ln.split('\t')
        if len(x) >= 2 and x[0] and x[1]: TSV[x[0]] = x[1][0]
    R = RDB(rdbdir)
    o2n = R.read_body('COMMON_2D_2ND.CHK')
    R.close()
    kor = open(kor2d_path, 'rb').read()
    if len(kor) % 16 == 0 and kor[:4] != b'CHK ' and len(kor) > 32:
        pass
    pk = parse(kor); pn = parse(o2n)
    assert len(pk) == 2 and len(pn) == 2, f"UNCDFONT 청크 수 {len(pk)}/{len(pn)}"
    new = bytearray(o2n)
    total = miss = 0
    missing = []
    for ci in range(2):
        ck, cn = pk[ci], pn[ci]
        assert ck['slot'] == cn['slot'], "글리프 슬롯 크기 불일치"
        d = DELTA[ci]
        for K in TSV:
            u = ord(TSV[K])
            if u not in ck['recs'] or u not in cn['recs']:
                if ci == 0: missing.append((K, hex(u))); miss += 1
                continue
            koff, kmet, _ = ck['recs'][u]
            g = kor[ck['base']+koff+d : ck['base']+koff+d+ck['slot']]
            noff, nmet, nrec = cn['recs'][u]
            st = cn['base']+noff+d
            new[st:st+cn['slot']] = g
            struct.pack_into('<I', new, nrec+8, kmet)
            total += 1
    print(f"글리프 복사 {total:,}개 (FNTL+FNTS)  · 대응 셀 없음 {miss}")
    if missing: print("  없는 음절:", missing[:20])
    assert len(new) == len(o2n), "본문 크기 변동"
    open(out_path, 'wb').write(bytes(new))
    print(f"→ {out_path}  {len(new):,}B  md5 {hashlib.md5(bytes(new)).hexdigest()}")
    diff = sum(1 for i in range(0, len(new), 4096) if new[i:i+4096] != o2n[i:i+4096])
    print(f"   원본 대비 변경 블록 {diff:,}/{len(new)//4096+1:,}")

if __name__ == '__main__':
    main(*sys.argv[1:5])
