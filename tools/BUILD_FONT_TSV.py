# -*- coding: utf-8 -*-
"""COMMON_2D(메인 폰트)를 tsv 매핑으로 재구축 v2.
근거(실증):
 - ADD 폰트(COMMON_2D_ADD)는 FNTL/FNTS 모두 정확한 tsv 매핑(글리프 상관 0.88, 시각검증 완벽).
 - 글리프 데이터는 레코드 오프셋 대비 FNTL=-6바이트/FNTS=0 위치에 실재(스윕 피크).
 - 폰트B(기존 한글판 COMMON_2D)는 wReplace도 아닌 어긋난 매핑 → 소스로 사용 불가.
빌드: 새 메인폰트 = 원본 메인폰트(전 셀 원본 한자) + tsv[K]셀(delta 적용)에 ADD폰트 한글 글리프 복사(메트릭 동반).
출력: _build/COMMON_2D_TSV.CHK"""
import sys, os, struct
sys.stdout.reconfigure(encoding='utf-8')
os.chdir(r"C:\Users\Jae Ho Lee\Desktop\z\실황2024")
import rdblib

DELTA = {0: -6, 1: 0}   # chunk idx → 글리프 데이터 델타 (FNTL 56, FNTS 44)

def load_tsv():
    m = {}
    for ln in open('!exefs-작업/hangul_to_hanja.tsv', encoding='utf-8-sig').read().splitlines():
        x = ln.split('\t')
        if len(x) >= 2 and x[0] and x[1]: m[x[0]] = x[1][0]
    return m

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

tsv = load_tsv()
R = rdblib.RDB('.')
orig = R.read_body('COMMON_2D.CHK')     # 원본 메인 폰트(전 셀 한자)
R.close()
addK = open('repack_in/COMMON_2D_ADD.CHK', 'rb').read()[32:]   # 한글 ADD 폰트(tsv 확정)
hdr32 = open('repack_in/COMMON_2D.CHK', 'rb').read()[:32]

po = parse(orig); pa = parse(addK)
new = bytearray(orig)
total = 0
for ci in range(2):
    co, ca = po[ci], pa[ci]
    slot = co['slot']; d = DELTA[ci]
    assert slot == ca['slot']
    for K in tsv:
        u = ord(tsv[K])
        aoff, amet, _ = ca['recs'][u]
        g = addK[ca['base']+aoff+d : ca['base']+aoff+d+slot]
        doff, dmet, drec = co['recs'][u]
        st = co['base']+doff+d
        new[st:st+slot] = g
        struct.pack_into('<I', new, drec+8, amet)   # 메트릭 복사
        total += 1

os.makedirs('_build', exist_ok=True)
out = hdr32 + bytes(new)
open('_build/COMMON_2D_TSV.CHK', 'wb').write(out)
print(f"글리프 {total}개 배치(ADD폰트 소스, delta L{DELTA[0]}/S{DELTA[1]}) → _build/COMMON_2D_TSV.CHK")
