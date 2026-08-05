# -*- coding: utf-8 -*-
"""줄규칙 축약분(마스터 rdb)만 repack_out에 재주입. exe는 건드리지 않음.
축약된 파일에 대해 그 파일의 마스터 패치 전체를 재적용(idempotent, 소스=마스터)."""
import sys, os, json, zlib, struct, time, bisect
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본 게임파일+데이터). 미지정 시 현재 디렉터리 사용
import numpy as np, rdblib
from rdblib import align_up, file_key, crypt_fast, SECTOR, locate

def load_tsv():
    m={}
    for ln in open('!exefs-작업/hangul_to_hanja.tsv', encoding='utf-8-sig').read().splitlines():
        x=ln.split('\t')
        if len(x)>=2 and x[0] and x[1]: m[x[0]]=x[1][0]
    return m
TSV=load_tsv()
def enc(ko): return ''.join(TSV.get(c,c) for c in ko).encode('utf-8')
def fit(nb, region):
    if len(nb) > region-1:
        nb=nb[:region-1]
        while nb:
            try: nb.decode('utf-8'); break
            except UnicodeDecodeError: nb=nb[:-1]
    return nb

master=json.load(open('번역_마스터.json', encoding='utf-8'))
ok=json.load(open('_rdb_fit_ok.json', encoding='utf-8'))
TARGET=set(x['file'] for x in ok)   # 축약된 파일만
print("대상 파일:", sorted(TARGET))
byfile={}
for r in master['rdb']:
    if r['file'] in TARGET: byfile.setdefault(r['file'], []).append(r)

DEP=rdblib.RDB('repack_out', writable=True)
laid={"RES00.RDB": [], "RES10.RDB": []}
for t in DEP.table:
    loc=locate(t["stored"], t["flag"])
    if loc: laid[loc[0]].append(loc[1])
for k in laid: laid[k].sort()
fsize={n: os.path.getsize(os.path.join('repack_out', n)) for n in DEP.f}
def gap(rdb, local):
    arr=laid[rdb]; j=bisect.bisect_right(arr, local)
    return (arr[j] if j<len(arr) else fsize[rdb]) - local
cursor={n: align_up(fsize[n], SECTOR) for n in DEP.f}
rs=dict(files=0, inj=0, inplace=0, reloc=0); t0=time.time()
for fn, patches in byfile.items():
    ent=DEP.idx.get(fn)
    if not ent or ent['flag'] not in (0, 0x20): continue
    try: body=bytearray(DEP.read_body(fn))
    except Exception: continue
    ok_n=0
    for r in patches:
        off=r['off']; oe=body.find(b'\x00', off)
        if oe<0: continue
        T=0; k=oe
        while k<len(body) and body[k]==0: T+=1; k+=1
        region=(oe-off)+T
        nb=fit(enc(r['ko']), region)
        body[off:off+len(nb)]=nb
        body[off+len(nb):off+region]=b'\x00'*(region-len(nb))
        ok_n+=1
    if not ok_n: continue
    rs['inj']+=ok_n
    loc=locate(ent["stored"], ent["flag"]); rdbn, local, is10=loc
    key=file_key(fn); f=DEP.f[rdbn]
    f.seek(local); hdr=bytearray(crypt_fast(f.read(32), key))
    if ent["flag"]==0x20:
        comp=zlib.compress(bytes(body), 9); struct.pack_into("<I", hdr, 0x18, len(comp)); nd=align_up(len(body), 4)
    else:
        comp=bytes(body); nd=align_up(32+len(body), 4); struct.pack_into("<I", hdr, 0x18, nd)
    need=align_up(32+len(comp), 4)
    if need<=gap(rdbn, local):
        struct.pack_into("<I", hdr, 0x1C, local//SECTOR)
        blob=bytearray(need); blob[:32]=hdr; blob[32:32+len(comp)]=comp
        f.seek(local); f.write(crypt_fast(bytes(blob), key)); ns=ent["stored"]; rs['inplace']+=1
    else:
        nl=cursor[rdbn]; ns, sect=(nl//SECTOR+(0x1000000 if is10 else 0), nl//SECTOR)
        struct.pack_into("<I", hdr, 0x1C, sect)
        phys=align_up(max(nd, 32+len(comp)), SECTOR)
        blob=bytearray(phys); blob[:32]=hdr; blob[32:32+len(comp)]=comp
        f.seek(nl); f.write(crypt_fast(bytes(blob), key)); cursor[rdbn]=nl+phys; fsize[rdbn]=max(fsize[rdbn], cursor[rdbn]); rs['reloc']+=1
    struct.pack_into("<I", DEP.dec, ent["rec_off"], ns)
    struct.pack_into("<I", DEP.dec, ent["rec_off"]+4, nd)
    ent["stored"]=ns; ent["DEC_SIZE"]=nd; rs['files']+=1
open(os.path.join('repack_out', 'RES00.RDI'), 'wb').write(crypt_fast(bytes(DEP.dec), rdblib.RDI_KEY))
DEP.close()
print(f"rdb 재주입 {rs} ({time.time()-t0:.0f}s)")
