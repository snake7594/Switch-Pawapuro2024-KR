# -*- coding: utf-8 -*-
"""두 RDB 세트의 '내용'을 비교 — 파일 안 압축·배치가 달라도 본문이 같은지 확인.

사용:  python tools/VERIFY_RDB_BODIES.py <A폴더> <B폴더>
예  :  python tools/VERIFY_RDB_BODIES.py repack_out /어딘가/배포본

RDB 컨테이너는 파일을 어디에 배치했는지에 따라 바이트가 달라집니다(빈 섹터 재배치 이력).
그래서 다시 빌드하면 MD5가 달라지는 것이 정상이며, 실제로 같은지는 **본문(CHK) 단위**로
비교해야 합니다. 이 도구가 그 비교를 합니다.
"""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rdblib

if len(sys.argv) < 3:
    print(__doc__); sys.exit(1)
A, B = sys.argv[1], sys.argv[2]
ra, rb = rdblib.RDB(A), rdblib.RDB(B)
same = diff = onlyA = onlyB = err = 0
bad = []
for name, ent in ra.idx.items():
    if ent['flag'] not in (0, 0x20): continue
    if name not in rb.idx: onlyA += 1; continue
    try:
        x = bytes(ra.read_body(name)); y = bytes(rb.read_body(name))
    except Exception:
        err += 1; continue
    if x == y: same += 1
    else:
        diff += 1
        if len(bad) < 30:
            n = sum(1 for p, q in zip(x, y) if p != q) if len(x) == len(y) else -1
            bad.append((name, len(x), len(y), n))
onlyB = sum(1 for n, e in rb.idx.items() if e['flag'] in (0, 0x20) and n not in ra.idx)
ra.close(); rb.close()
print(f"A={A}\nB={B}\n")
print(f"  본문 동일 : {same:,}")
print(f"  본문 다름 : {diff:,}")
print(f"  A에만/B에만: {onlyA} / {onlyB}    읽기실패: {err}")
if bad:
    print("\n  다른 파일(최대 30):")
    for n, la, lb, c in bad:
        print(f"    {n:34s} A={la:9,}B B={lb:9,}B  차이={'길이다름' if c < 0 else f'{c:,}B'}")
print("\n" + ("✅ 내용이 완전히 같습니다(컨테이너 배치만 다를 수 있음)" if diff == 0
              else "⚠ 내용이 다른 파일이 있습니다"))
