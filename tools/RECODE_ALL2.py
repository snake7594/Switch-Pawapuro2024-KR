# -*- coding: utf-8 -*-
"""배포 RDB 전 슬롯 wReplace 잔존 완결 재인코딩(+사전주입).
- 대상: 배포 repack_out의 모든 슬롯(flag 0/0x20). 원본과 raw 동일시 스킵(고속).
- aligned 슬롯: 원본과 다른 NUL문자열 →
    tsv_r 완전한글 → 이미 정상, 스킵
    wrep_r 완전한글 → tsv 재인코딩(+·→・)
    겹침 모호 → 파일 다수결(명확 표본의 인코딩 상태)로 판정
  원본과 같은 JP 문자열 → 사전(jp→ko) 있으면 tsv 주입(슬랙)
- 쓰기: zlib9, gap 제자리/끝 재배치, RDI 갱신. 폰트 2종 제외.
"""
import sys, os, json, zlib, struct, time
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본 게임파일+데이터). 미지정 시 현재 디렉터리 사용
import rdblib
from rdblib import align_up, file_key, crypt_fast, SECTOR

def load_tsv():
    m = {}
    for ln in open('!exefs-작업/hangul_to_hanja.tsv', encoding='utf-8-sig').read().splitlines():
        x = ln.split('\t')
        if len(x) >= 2 and x[0] and x[1]: m[x[0]] = x[1][0]
    return m
def load_w():
    m = {}
    txt = open('!폰트작업/실황2024.wReplace', 'rb').read().decode('utf-16')
    for ln in txt.splitlines():
        ln = ln.lstrip('﻿')
        if ln.startswith('#'): continue
        x = ln.split('\t')
        if len(x) >= 2 and x[0] and x[1]: m[x[0]] = x[1][0]
    return m
TSV = load_tsv(); WREP = load_w()
TSV_R = {v: k for k, v in TSV.items()}; WREP_R = {v: k for k, v in WREP.items()}
DICT = json.load(open('_dict_jpko.json', encoding='utf-8'))
def enc_tsv(ko): return ''.join(TSV.get(c, c) for c in ko).encode('utf-8')
def charfix(s): return s.replace('·', '・').replace('—', 'ー')
def is_h(c): return '가' <= c <= '힣'
def cjk(c): return '一' <= c <= '鿿'
def full_hangul(dec, txt):
    nc = sum(1 for c in txt if cjk(c))
    if nc == 0: return False
    nh = sum(1 for c in dec if is_h(c))
    return nh == nc and all(is_h(c) or not cjk(c) for c in dec)
def dec_via(txt, R): return ''.join(R.get(c, c) for c in txt)

DEP = rdblib.RDB('repack_out', writable=True)
ORG = rdblib.RDB('.')
dec_rdi = DEP.dec
laid = {"RES00.RDB": [], "RES10.RDB": []}
for t in DEP.table:
    loc = rdblib.locate(t["stored"], t["flag"])
    if loc: laid[loc[0]].append(loc[1])
for k in laid: laid[k].sort()
fsize = {n: os.path.getsize(os.path.join('repack_out', n)) for n in DEP.f}
import bisect
def gap_to_next(rdb, local):
    arr = laid[rdb]
    j = bisect.bisect_right(arr, local)
    nxt = arr[j] if j < len(arr) else fsize[rdb]
    return nxt - local
cursor = {n: align_up(fsize[n], SECTOR) for n in DEP.f}

t0 = time.time()
stats = dict(slots=0, reenc=0, dictinj=0, wrote=0, inplace=0, reloc=0, amb=0)
SKIP = {'COMMON_2D.CHK', 'COMMON_2D_ADD.CHK'}
names = [t['name'] for t in DEP.table if t['flag'] in (0, 0x20) and t['name'] not in SKIP]
for idx, name in enumerate(names):
    try:
        db = DEP.read_body(name)
        ob = ORG.read_body(name) if name in ORG.idx else None
    except Exception:
        continue
    if db is None or ob is None: continue
    if db == ob: continue
    if len(db) != len(ob): continue     # 재구축 슬롯은 기존 패스에서 처리됨
    stats['slots'] += 1
    buf = bytearray(db)
    # 1) 파일 인코딩 상태 표본(명확한 것만)
    votes_t = votes_w = 0
    segs = []
    pos = 0
    while pos < len(buf):
        e = buf.find(b'\x00', pos)
        if e < 0: break
        if 4 <= e - pos <= 120:
            seg = bytes(buf[pos:e])
            try: s = seg.decode('utf-8')
            except UnicodeDecodeError: s = None
            if s: segs.append((pos, e, s))
        pos = e + 1
    diffsegs = [(p, e, s) for (p, e, s) in segs if buf[p:e] != ob[p:e]]
    for (p, e, s) in diffsegs:
        dt = dec_via(s, TSV_R); dw = dec_via(s, WREP_R)
        ft = full_hangul(dt, s); fw = full_hangul(dw, s)
        if ft and not fw: votes_t += 1
        elif fw and not ft: votes_w += 1
    file_is_wrep = votes_w > votes_t
    changed = False
    for (p, e, s) in diffsegs:
        dt = dec_via(s, TSV_R); dw = dec_via(s, WREP_R)
        ft = full_hangul(dt, s); fw = full_hangul(dw, s)
        ko = None
        if fw and not ft: ko = dw
        elif fw and ft:
            stats['amb'] += 1
            if file_is_wrep: ko = dw
        if ko is None: continue
        nb = enc_tsv(charfix(ko))
        T = 0; k = e
        while k < len(buf) and buf[k] == 0: T += 1; k += 1
        region = (e - p) + T
        if len(nb) > region - 1:
            nb = nb[:region-1]
            while nb:
                try: nb.decode('utf-8'); break
                except UnicodeDecodeError: nb = nb[:-1]
        buf[p:p+len(nb)] = nb
        buf[p+len(nb):p+region] = b'\x00' * (region - len(nb))
        stats['reenc'] += 1; changed = True
    # 2) 미번역 JP(원본과 동일) → 사전 주입
    for (p, e, s) in segs:
        if buf[p:e] != ob[p:e]: continue
        if not any(('぀' <= c <= 'ヿ') or cjk(c) for c in s): continue
        ko = DICT.get(s)
        if not ko: continue
        nb = enc_tsv(charfix(ko))
        T = 0; k = e
        while k < len(buf) and buf[k] == 0: T += 1; k += 1
        region = (e - p) + T
        if len(nb) > region - 1:
            nb2 = enc_tsv(charfix(ko).replace(' ', ''))
            nb = nb2 if len(nb2) <= region - 1 else nb[:region-1]
            while nb:
                try: nb.decode('utf-8'); break
                except UnicodeDecodeError: nb = nb[:-1]
        buf[p:p+len(nb)] = nb
        buf[p+len(nb):p+region] = b'\x00' * (region - len(nb))
        stats['dictinj'] += 1; changed = True
    if not changed: continue
    # 3) 기록
    ent = DEP.idx[name]
    loc = rdblib.locate(ent["stored"], ent["flag"])
    rdbn, local, is10 = loc
    key = file_key(name)
    f = DEP.f[rdbn]
    f.seek(local); hdr = bytearray(crypt_fast(f.read(32), key))
    if ent["flag"] == 0x20:
        comp = zlib.compress(bytes(buf), 9)
        struct.pack_into("<I", hdr, 0x18, len(comp))
        nd = align_up(len(buf), 4)
    else:
        comp = bytes(buf)
        nd = align_up(32 + len(buf), 4)
        struct.pack_into("<I", hdr, 0x18, nd)
    need = align_up(32 + len(comp), 4)
    if need <= gap_to_next(rdbn, local):
        struct.pack_into("<I", hdr, 0x1C, local // SECTOR)
        blob = bytearray(need); blob[:32] = hdr; blob[32:32+len(comp)] = comp
        f.seek(local); f.write(crypt_fast(bytes(blob), key))
        ns = ent["stored"]; stats['inplace'] += 1
    else:
        nl = cursor[rdbn]
        ns, sect = (nl // SECTOR + (0x1000000 if is10 else 0), nl // SECTOR)
        struct.pack_into("<I", hdr, 0x1C, sect)
        phys = align_up(max(nd, 32 + len(comp)), SECTOR)
        blob = bytearray(phys); blob[:32] = hdr; blob[32:32+len(comp)] = comp
        f.seek(nl); f.write(crypt_fast(bytes(blob), key))
        cursor[rdbn] = nl + phys; fsize[rdbn] = max(fsize[rdbn], cursor[rdbn])
        stats['reloc'] += 1
    struct.pack_into("<I", dec_rdi, ent["rec_off"], ns)
    struct.pack_into("<I", dec_rdi, ent["rec_off"]+4, nd)
    ent["stored"] = ns; ent["DEC_SIZE"] = nd
    stats['wrote'] += 1
    if stats['wrote'] % 20 == 0:
        print(f"  {idx}/{len(names)} wrote {stats['wrote']} ({time.time()-t0:.0f}s)", flush=True)

enc = crypt_fast(bytes(dec_rdi), rdblib.RDI_KEY)
open(os.path.join('repack_out', 'RES00.RDI'), 'wb').write(enc)
print('=' * 60)
print(f"완료 {time.time()-t0:.0f}s: {stats}")
DEP.close(); ORG.close()
