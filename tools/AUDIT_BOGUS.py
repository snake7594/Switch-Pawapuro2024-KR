# -*- coding: utf-8 -*-
"""바이너리 오염 주입 전수 감사·복원.
문제: 바이너리 데이터가 우연히 유효 UTF-8 CJK로 디코드 → 추출·번역·주입 → 구조 오염(栄冠 멈춤 등).
감사 규칙(원본 세그먼트 기준):
  A) '그럴듯한 일본어' 엄격 판정 실패 → 해당 주입 전체를 원본 복원
     - 제어문자 포함 / 허용문자 밖 / 가나 0 & 한자<2 / 가나 0 & 희귀한자(실코퍼스 밖) 포함
  B) 栄冠 파일(HSIM/HATK/G2D_HATK/D2D_HATK): 원본이 유효해도 **슬랙 사용분 롤백**
     (원본 문자열 길이 초과분은 구조필드 침범 위험 → ko를 orig길이-1 이내 클린 재절단, 초과영역 원본복원)
출력: 수정된 슬롯 재기록(재압축/제자리/재배치+RDI), 파일별 통계."""
import sys, os, json, zlib, struct, time
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본 게임파일+데이터). 미지정 시 현재 디렉터리 사용
import rdblib
from rdblib import align_up, file_key, crypt_fast, SECTOR, locate

# ---- 실사용 한자 집합(가나 포함 실텍스트 코퍼스에서) ----
doc = json.load(open('번역_일본어.json', encoding='utf-8'))
def has_kana(s): return any('぀' <= c <= 'ヿ' for c in s)
REAL_KANJI = set()
for s in doc['strings']:
    jp = s['jp']
    if has_kana(jp) and not any(ord(c) < 0x20 for c in jp):
        for c in jp:
            if '一' <= c <= '鿿': REAL_KANJI.add(c)
print(f"실사용 한자 집합: {len(REAL_KANJI)}")

OKCH = None
import re
OK_RE = re.compile(r'^[぀-ヿ一-鿿々〇ヶー・～　-〿＀-￯0-9A-Za-z %%.,:;()\[\]/+\-*=!?&#@\'\"<>_%…※→←↑↓○×△□◎☆★♪]+$')
def plausible_jp(s):
    if not s or len(s) < 2: return False
    if any(ord(c) < 0x20 for c in s): return False
    if not OK_RE.match(s): return False
    nk = sum(1 for c in s if '぀' <= c <= 'ヿ')
    nj = sum(1 for c in s if '一' <= c <= '鿿')
    if nk == 0:
        if nj < 2: return False
        # 가나 없는 순한자: 전부 실사용 한자여야
        for c in s:
            if '一' <= c <= '鿿' and c not in REAL_KANJI: return False
    return True

DEP = rdblib.RDB('repack_out', writable=True)
ORG = rdblib.RDB('.')
laid = {"RES00.RDB": [], "RES10.RDB": []}
for t in DEP.table:
    loc = locate(t["stored"], t["flag"])
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

EIKAN = lambda n: n.startswith(('HSIM', 'HATK', 'G2D_HATK', 'D2D_HATK'))
SKIP = {'COMMON_2D.CHK', 'COMMON_2D_ADD.CHK'}
stats = dict(slots=0, restA=0, restB=0, wrote=0, inplace=0, reloc=0)
byfile = {}
t0 = time.time(); n = 0
for name, ent in DEP.idx.items():
    if ent['flag'] not in (0, 0x20) or name in SKIP: continue
    n += 1
    try:
        db = DEP.read_body(name)
        ob = ORG.read_body(name) if name in ORG.idx else None
    except Exception:
        continue
    if db is None or ob is None or db == ob or len(db) != len(ob): continue
    buf = bytearray(db)
    changed = 0
    # diff 런 → 원본 NUL경계 세그먼트 그룹
    import numpy as np
    a = np.frombuffer(bytes(db), dtype=np.uint8); b = np.frombuffer(ob, dtype=np.uint8)
    diff = np.nonzero(a != b)[0]
    if len(diff) == 0: continue
    # 세그먼트 단위 처리: 각 diff 위치의 orig 문자열 시작
    runs = []
    s0 = p = int(diff[0])
    for x in diff[1:]:
        x = int(x)
        if x <= p + 1: p = x; continue
        runs.append((s0, p)); s0 = p = x
    runs.append((s0, p))
    handled = set()
    for (rs, re_) in runs:
        # 원본 기준 세그 시작
        st = rs
        while st > 0 and ob[st-1] != 0: st -= 1
        if st in handled: continue
        handled.add(st)
        oe = ob.find(b'\x00', st)
        if oe < 0: oe = len(ob)
        try: ojp = ob[st:oe].decode('utf-8')
        except UnicodeDecodeError: ojp = None
        # 주입영역 끝: 세그 + 원본 후행 NUL런
        T = 0; k = oe
        while k < len(ob) and ob[k] == 0: T += 1; k += 1
        region_end = oe + T
        if ojp is None or not plausible_jp(ojp):
            # A) 원본 복원
            buf[st:region_end] = ob[st:region_end]
            stats['restA'] += 1; changed += 1
            byfile.setdefault(name, [0, 0])[0] += 1
        elif EIKAN(name):
            # B) 슬랙 롤백: 주입이 oe(원본 문자열 끝) 넘겼으면 orig길이 내 재절단
            cur_e = buf.find(b'\x00', st)
            if cur_e > oe or any(buf[oe:region_end][i] != ob[oe:region_end][i] for i in range(region_end - oe)):
                nb = bytes(buf[st:min(cur_e if cur_e > 0 else region_end, region_end)])
                nb = nb[:oe - st]
                while nb:
                    try: nb.decode('utf-8'); break
                    except UnicodeDecodeError: nb = nb[:-1]
                buf[st:st+len(nb)] = nb
                buf[st+len(nb):oe] = b'\x00' * (oe - st - len(nb))
                buf[oe:region_end] = ob[oe:region_end]
                stats['restB'] += 1; changed += 1
                byfile.setdefault(name, [0, 0])[1] += 1
    if not changed: continue
    stats['slots'] += 1
    ent2 = DEP.idx[name]
    loc = locate(ent2["stored"], ent2["flag"])
    rdbn, local, is10 = loc
    key = file_key(name); f = DEP.f[rdbn]
    f.seek(local); hdr = bytearray(crypt_fast(f.read(32), key))
    if ent2["flag"] == 0x20:
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
        ns = ent2["stored"]; stats['inplace'] += 1
    else:
        nl = cursor[rdbn]
        ns, sect = (nl // SECTOR + (0x1000000 if is10 else 0), nl // SECTOR)
        struct.pack_into("<I", hdr, 0x1C, sect)
        phys = align_up(max(nd, 32 + len(comp)), SECTOR)
        blob = bytearray(phys); blob[:32] = hdr; blob[32:32+len(comp)] = comp
        f.seek(nl); f.write(crypt_fast(bytes(blob), key))
        cursor[rdbn] = nl + phys; fsize[rdbn] = max(fsize[rdbn], cursor[rdbn])
        stats['reloc'] += 1
    struct.pack_into("<I", DEP.dec, ent2["rec_off"], ns)
    struct.pack_into("<I", DEP.dec, ent2["rec_off"]+4, nd)
    ent2["stored"] = ns; ent2["DEC_SIZE"] = nd
    stats['wrote'] += 1
    if n % 3000 == 0: print(f"  {n}... ({time.time()-t0:.0f}s)", flush=True)
enc = crypt_fast(bytes(DEP.dec), rdblib.RDI_KEY)
open(os.path.join('repack_out', 'RES00.RDI'), 'wb').write(enc)
DEP.close(); ORG.close()
print('=' * 60)
print(f"완료 {time.time()-t0:.0f}s: {stats}")
print("파일별(복원A/슬랙롤백B) 상위:")
for fn, (a1, b1) in sorted(byfile.items(), key=lambda x: -(x[1][0]+x[1][1]))[:25]:
    print(f"  {fn}: A={a1} B={b1}")
json.dump(byfile, open('_bogus_report.json', 'w', encoding='utf-8'), ensure_ascii=False)
