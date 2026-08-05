# -*- coding: utf-8 -*-
"""빌드 결과 검증: 작업공간의 산출물 MD5를 배포본(v1.4) 기준값과 대조.
사용:  set PAWA_ROOT=<작업공간>  &&  python tools/VERIFY_BUILD.py
"""
import sys, os, hashlib
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)

EXPECT = [
    ('inject_out/main-safe28', 'e07eea88b8f0687ecd7c8666452b1d3b', '빌드 베이스(부트스트랩)'),
    ('inject_out/main-built',  '3ef0843dabf03ee4c5d893f6dc52c8de', '실행파일 결과(v1.4)'),
    ('repack_out/RES00.RDB',   '151db69a6c2909e7fd1e943c52759680', 'RDB 결과(v1.4)'),
    ('repack_out/RES00.RDI',   'b5f9ea7fb29cbcd9a9ea933dba659c61', 'RDI 결과(v1.4)'),
    ('repack_out/RES10.RDB',   'dd0169693c858e99b05e3a6c924628e2', 'RDB10 결과(v1.4)'),
    ('main',      '916d81a491408bce1a1871efc24a6fa2', '원본 main'),
    ('RES00.RDB', '46ccf287fd62e9e2d51b193e788555a0', '원본 RES00.RDB'),
    ('RES00.RDI', 'ad864a8bfb6b8bcf3b10481012a3f013', '원본 RES00.RDI'),
    ('RES10.RDB', '25d0b86b64fa3fcc389b00359fde96cb', '원본 RES10.RDB'),
]

def md5(p, chunk=1 << 24):
    h = hashlib.md5()
    with open(p, 'rb') as f:
        while True:
            b = f.read(chunk)
            if not b: break
            h.update(b)
    return h.hexdigest()

print(f"작업공간: {os.getcwd()}\n")
bad = 0
for path, want, desc in EXPECT:
    if not os.path.exists(path):
        print(f"  ·  {path:26s} 없음        ({desc})"); continue
    got = md5(path)
    ok = got == want
    if not ok: bad += 1
    print(f"  {'✓' if ok else '✗'}  {path:26s} {got}  ({desc})")
    if not ok: print(f"     기대: {want}")
print()
if bad:
    print(f"⚠ {bad}건 불일치. 번역을 수정했다면 결과물 MD5가 달라지는 것이 정상입니다.")
    print("  수정하지 않았는데 다르면 데이터/베이스가 어긋난 것이니 원인을 찾으세요.")
else:
    print("모두 일치 — 배포본(v1.4)과 동일하게 재현되었습니다.")
