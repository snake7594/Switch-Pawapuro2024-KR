# -*- coding: utf-8 -*-
"""단일 마스터 → exe 재주입. exe_마스터.json 의 ko를 off 위치에 주입해 새 main 빌드.
- 베이스: main-safe23 (부팅검증된 동적영역/redirect 포함, 문자열 주입 전 상태)
- 각 row: off에 tsv(ko) 인코딩 주입, region=원본세그+후행NUL, maxb 초과시 클린절단
- 동적영역[<0x3d2551d] 불변 assert
사용법: exe_마스터.json의 ko만 수정 → 이 스크립트 실행 → inject_out/main-new 생성.
        (--deploy 인자 주면 mods로 배포까지)"""
import sys, os, json
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본 게임파일+데이터). 미지정 시 현재 디렉터리 사용
import numpy as np

def load_tsv():
    m = {}
    for ln in open('!exefs-작업/hangul_to_hanja.tsv', encoding='utf-8-sig').read().splitlines():
        x = ln.split('\t')
        if len(x) >= 2 and x[0] and x[1]: m[x[0]] = x[1][0]
    return m
TSV = load_tsv()
def enc(ko): return ''.join(TSV.get(c, c) for c in ko).encode('utf-8')

BASE = 'inject_out/main-safe28'   # 현재 배포본. 마스터에 없는 죽은풀/redirect도 그대로 보존
OUT = 'inject_out/main-new'
DYN_END = 0x3d2551d
master = json.load(open('exe_마스터.json', encoding='utf-8'))
rows = master['rows']
ob = open('main', 'rb').read()
buf = bytearray(open(BASE, 'rb').read())
assert len(ob) == len(buf)

stats = dict(inj=0, trunc=0, skip=0)
for r in rows:
    off = r['off']; ko = r['ko']; maxb = r['maxb']
    assert off > DYN_END, f"동적영역 침범 {off}"
    jp_b = r['jp'].encode('utf-8')
    if ob[off:off+len(jp_b)] != jp_b:   # 원본 세그 불일치 = 잘못된 off
        stats['skip'] += 1; continue
    e = off + len(jp_b)
    T = 0
    while e + T < len(ob) and ob[e + T] == 0: T += 1
    region = len(jp_b) + T
    nb = enc(ko)
    if len(nb) > region - 1:
        nb = nb[:region-1]
        while nb:
            try: nb.decode('utf-8'); break
            except UnicodeDecodeError: nb = nb[:-1]
        stats['trunc'] += 1
    buf[off:off+len(nb)] = nb
    buf[off+len(nb):off+region] = b'\x00' * (region - len(nb))
    stats['inj'] += 1
# 동적영역 불변
c = np.frombuffer(bytes(buf), dtype=np.uint8)
base = np.frombuffer(open(BASE, 'rb').read(), dtype=np.uint8)
assert (c[:DYN_END] == base[:DYN_END]).all(), "동적영역 변경!"
open(OUT, 'wb').write(bytes(buf))
import hashlib
print(f"주입 {stats} → {OUT}  md5 {hashlib.md5(bytes(buf)).hexdigest()}")

if '--deploy' in sys.argv:
    import shutil
    dst = r"C:\Users\Jae Ho Lee\AppData\Roaming\Ryujinx\mods\contents\0100d1c01c194000\ExeFS\main"
    shutil.copy(OUT, dst)
    print("배포 완료:", dst)
