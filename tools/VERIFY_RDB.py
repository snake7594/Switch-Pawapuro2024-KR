# -*- coding: utf-8 -*-
"""빌드된 RDB 전수 무결성 검사 + 폰트/텍스트 확인.
사용: python VERIFY_RDB.py <repack_out> <마스터json> <tsv> [한글2ND본문]
"""
import sys, os, json, hashlib, time
sys.path.insert(0, r"C:\Users\Jay\Desktop\z\파워풀2024-2025\Switch-Pawapuro2024-KR\tools")
sys.stdout.reconfigure(encoding='utf-8')
from rdblib import RDB

def main(rdbdir, master_p, tsv_p, kor2nd=None):
    TSV = {}
    for ln in open(tsv_p, encoding='utf-8-sig').read().splitlines():
        x = ln.split('\t')
        if len(x) >= 2 and x[0] and x[1]: TSV[x[0]] = x[1][0]
    TSVR = {v: k for k, v in TSV.items()}
    dec = lambda s: ''.join(TSVR.get(c, c) for c in s)

    R = RDB(rdbdir)
    t0 = time.time(); okc = fail = skip = 0
    fails = []
    for i, t in enumerate(R.table):
        if t['flag'] not in (0, 0x20): skip += 1; continue
        try:
            body = R.read_body(t['name'])
            if body is None: raise ValueError('None')
            okc += 1
        except Exception as e:
            fail += 1; fails.append((t['name'], str(e)[:60]))
        if (i+1) % 3000 == 0: print(f"  …{i+1}/{len(R.table)} ({time.time()-t0:.0f}s)", flush=True)
    print(f"[1] 슬롯 무결성: 정상 {okc:,} · 실패 {fail:,} · 비파일 {skip:,}")
    for n, e in fails[:20]: print(f"    ✗ {n}: {e}")

    # 폰트
    print("[2] 폰트")
    for nm in ('COMMON_2D.CHK', 'COMMON_2D_2ND.CHK', 'COMMON_2D_ADD.CHK'):
        if nm not in R.idx: print(f"    {nm}: 없음"); continue
        b = R.read_body(nm)
        print(f"    {nm}: {len(b):,}B md5 {hashlib.md5(b).hexdigest()}")
        if kor2nd and nm == 'COMMON_2D_2ND.CHK':
            exp = open(kor2nd, 'rb').read()
            print(f"      기대 한글판과 일치: {'OK' if b == exp else '✗ 불일치'}")

    # 텍스트 주입 확인
    master = json.load(open(master_p, encoding='utf-8'))
    byfile = {}
    for r in master['rdb']: byfile.setdefault(r['file'], []).append(r)
    good = bad = 0; samples = []
    for fn, rows in list(byfile.items()):
        try: body = R.read_body(fn)
        except Exception: bad += len(rows); continue
        for r in rows[:40]:
            o = r['off']; e = body.find(b'\x00', o)
            try: got = dec(body[o:e].decode('utf-8'))
            except Exception: got = None
            exp = r['ko']
            if got == exp or (got and exp.startswith(got)): good += 1
            else:
                bad += 1
                if len(samples) < 8: samples.append((fn, hex(o), r['jp'][:16], exp[:24], (got or '')[:24]))
    print(f"[3] 텍스트 표본 확인: 일치 {good:,} · 불일치 {bad:,}")
    for s in samples: print(f"    ✗ {s}")

    # 잔존 가나(주입 대상 슬롯 한정)
    KANA = lambda c: ('぀' <= c <= 'ゟ') or ('ァ' <= c <= 'ヺ')
    left = 0; ls = []
    for fn, rows in byfile.items():
        try: body = R.read_body(fn)
        except Exception: continue
        for r in rows:
            o = r['off']; e = body.find(b'\x00', o)
            try: t = body[o:e].decode('utf-8')
            except Exception: continue
            if any(KANA(c) for c in dec(t)):
                left += 1
                if len(ls) < 8: ls.append((fn, dec(t)[:24]))
    print(f"[4] 주입 슬롯 가나 잔존 {left:,} {ls}")
    R.close()
    print(f"\n{'✅ 통과' if fail == 0 and bad == 0 else '❌ 문제 있음'} ({time.time()-t0:.0f}s)")
    return 0 if (fail == 0 and bad == 0) else 1

if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:5]))
