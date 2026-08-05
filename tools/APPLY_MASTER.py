# -*- coding: utf-8 -*-
"""통합 마스터 → exe + RDB 재빌드/재주입 (완전 단일 소스).
- exe: BUILD_FROM_MASTER.py 로 재빌드(원본영역 주입 + rodata 확장 + exe_ext 마이라이프 새영역).
       → inject_out/main-built (master['exe'] + master['exe_ext']가 유일 소스, 결정적 재현)
- rdb: repack_out 슬롯 제자리 주입(슬랙) → 크기증가 시 재배치 + RDI 갱신
사용법:  python3 APPLY_MASTER.py            # 빌드만(inject_out/main-built, repack_out 갱신)
         python3 APPLY_MASTER.py --deploy  # mods로 배포까지
주의: '번역_마스터.json'(exe / exe_ext / rdb)의 ko를 유일 소스로 재빌드한다."""
import sys, os, json, zlib, struct, time, subprocess, hashlib
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본 게임파일+데이터). 미지정 시 현재 디렉터리 사용
import numpy as np
import rdblib
from rdblib import align_up, file_key, crypt_fast, SECTOR, locate

def load_tsv():
    m = {}
    for ln in open('!exefs-작업/hangul_to_hanja.tsv', encoding='utf-8-sig').read().splitlines():
        x = ln.split('\t')
        if len(x) >= 2 and x[0] and x[1]: m[x[0]] = x[1][0]
    return m
TSV = load_tsv()
def enc(ko): return ''.join(TSV.get(c, c) for c in ko).encode('utf-8')
def fit(nb, region):
    if len(nb) > region - 1:
        nb = nb[:region-1]
        while nb:
            try: nb.decode('utf-8'); break
            except UnicodeDecodeError: nb = nb[:-1]
    return nb

master = json.load(open('번역_마스터.json', encoding='utf-8'))
DEPLOY = '--deploy' in sys.argv
DYN_END = 0x3d2551d

# ---------- exe: 마스터로 재빌드(무확장: 원본영역 + 꼬리풀 exe_ext) ----------
fwd = [a for a in sys.argv[1:] if a != '--deploy']   # --no-mylife 등 전달
subprocess.run([sys.executable, 'BUILD_FROM_MASTER.py'] + fwd, check=True)
EXE_OUT = 'inject_out/main-built'
print(f"exe 재빌드 → {EXE_OUT} md5 {hashlib.md5(open(EXE_OUT,'rb').read()).hexdigest()}")

# ---------- rdb ----------
byfile = {}
for r in master['rdb']:
    byfile.setdefault(r['file'], []).append(r)
DEP = rdblib.RDB('repack_out', writable=True)
laid = {"RES00.RDB": [], "RES10.RDB": []}
for t in DEP.table:
    loc = locate(t["stored"], t["flag"])
    if loc: laid[loc[0]].append(loc[1])
for k in laid: laid[k].sort()
fsize = {n: os.path.getsize(os.path.join('repack_out', n)) for n in DEP.f}
import bisect
base_end = dict(fsize)   # ⚠제자리 쓰기 상한은 원본 끝 고정(재배치 영역 침범 방지)
def gap(rdb, local):
    arr = laid[rdb]; j = bisect.bisect_right(arr, local)
    return (arr[j] if j < len(arr) else base_end[rdb]) - local
cursor = {n: align_up(fsize[n], SECTOR) for n in DEP.f}
rs = dict(files=0, inj=0, inplace=0, reloc=0, skip=0)
t0 = time.time()
for fn, patches in byfile.items():
    ent = DEP.idx.get(fn)
    if not ent or ent['flag'] not in (0, 0x20): continue
    try: body = bytearray(DEP.read_body(fn))
    except Exception: continue
    ok = 0
    for r in patches:
        off = r['off']
        oe = body.find(b'\x00', off)
        if oe < 0: continue
        # region = 세그 + 후행 NUL
        T = 0; k = oe
        while k < len(body) and body[k] == 0: T += 1; k += 1
        region = (oe - off) + T
        nb = fit(enc(r['ko']), region)
        body[off:off+len(nb)] = nb
        body[off+len(nb):off+region] = b'\x00' * (region - len(nb))
        ok += 1
    if not ok: continue
    rs['inj'] += ok
    loc = locate(ent["stored"], ent["flag"]); rdbn, local, is10 = loc
    key = file_key(fn); f = DEP.f[rdbn]
    f.seek(local); hdr = bytearray(crypt_fast(f.read(32), key))
    if ent["flag"] == 0x20:
        comp = zlib.compress(bytes(body), 9); struct.pack_into("<I", hdr, 0x18, len(comp)); nd = align_up(len(body), 4)
    else:
        comp = bytes(body); nd = align_up(32+len(body), 4); struct.pack_into("<I", hdr, 0x18, nd)
    need = align_up(32+len(comp), 4)
    if need <= gap(rdbn, local):
        struct.pack_into("<I", hdr, 0x1C, local // SECTOR)
        blob = bytearray(need); blob[:32] = hdr; blob[32:32+len(comp)] = comp
        f.seek(local); f.write(crypt_fast(bytes(blob), key)); ns = ent["stored"]; rs['inplace'] += 1
    else:
        nl = cursor[rdbn]; ns, sect = (nl//SECTOR + (0x1000000 if is10 else 0), nl//SECTOR)
        struct.pack_into("<I", hdr, 0x1C, sect)
        phys = align_up(max(nd, 32+len(comp)), SECTOR)
        blob = bytearray(phys); blob[:32] = hdr; blob[32:32+len(comp)] = comp
        f.seek(nl); f.write(crypt_fast(bytes(blob), key)); cursor[rdbn] = nl+phys; fsize[rdbn] = max(fsize[rdbn], cursor[rdbn]); rs['reloc'] += 1
    struct.pack_into("<I", DEP.dec, ent["rec_off"], ns)
    struct.pack_into("<I", DEP.dec, ent["rec_off"]+4, nd)
    ent["stored"] = ns; ent["DEC_SIZE"] = nd; rs['files'] += 1
open(os.path.join('repack_out', 'RES00.RDI'), 'wb').write(crypt_fast(bytes(DEP.dec), rdblib.RDI_KEY))
DEP.close()
print(f"rdb 주입 {rs} ({time.time()-t0:.0f}s)")

if DEPLOY:
    import shutil
    base = r"C:\Users\Jae Ho Lee\AppData\Roaming\Ryujinx\mods\contents\0100d1c01c194000"
    shutil.copy(EXE_OUT, os.path.join(base, 'ExeFS', 'main'))
    for f in ('RES00.RDB', 'RES00.RDI', 'RES10.RDB'):
        shutil.copy(os.path.join('repack_out', f), os.path.join(base, 'RomFS', 'cdvdroot', f))
    print("배포 완료(main + RDB 3종)")
