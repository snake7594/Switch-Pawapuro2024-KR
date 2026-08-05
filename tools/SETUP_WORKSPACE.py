# -*- coding: utf-8 -*-
"""작업공간(workspace) 구성 — 저장소 데이터 + 사용자 원본 게임파일 → 빌드 가능한 상태로.

사용법:
    python tools/SETUP_WORKSPACE.py <작업공간경로> [--orig <원본4파일이_있는_폴더>]

하는 일:
 1) 원본 4파일(main, RES00.RDB, RES00.RDI, RES10.RDB) 존재·MD5 확인
 2) 저장소 data/ 를 작업공간에 배치(도구들이 기대하는 이름·위치로)
 3) bootstrap/main-safe28.xdelta 를 원본 main 에 적용 → inject_out/main-safe28
 4) inject_out/ repack_out/ 생성
이후:  set PAWA_ROOT=<작업공간>  →  python tools/BUILD_FROM_MASTER.py
"""
import sys, os, shutil, hashlib, subprocess, json
sys.stdout.reconfigure(encoding='utf-8')

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIG_MD5 = {'main': '916d81a491408bce1a1871efc24a6fa2',
            'RES00.RDB': '46ccf287fd62e9e2d51b193e788555a0',
            'RES00.RDI': 'ad864a8bfb6b8bcf3b10481012a3f013',
            'RES10.RDB': '25d0b86b64fa3fcc389b00359fde96cb'}
SAFE28_MD5 = 'e07eea88b8f0687ecd7c8666452b1d3b'
# 저장소 data → 작업공간 배치 경로(도구들이 참조하는 이름 그대로)
LAYOUT = [('data/번역_마스터.json', '번역_마스터.json'),
          ('data/hangul_to_hanja.tsv', '!exefs-작업/hangul_to_hanja.tsv'),
          ('data/rdb_residual.pack', 'rdb_residual.pack'),
          ('data/마이라이프_대사.json', '마이라이프_대사.json'),
          ('data/전체대사_재구성.json', '전체대사_재구성.json')]

def md5(p, chunk=1 << 24):
    h = hashlib.md5()
    with open(p, 'rb') as f:
        while True:
            b = f.read(chunk)
            if not b: break
            h.update(b)
    return h.hexdigest()

def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    ws = os.path.abspath(sys.argv[1])
    orig = os.path.abspath(sys.argv[sys.argv.index('--orig')+1]) if '--orig' in sys.argv else ws
    os.makedirs(ws, exist_ok=True)
    print(f"작업공간 : {ws}\n원본폴더 : {orig}\n저장소   : {REPO}\n")

    # 1) 원본 확인(+필요 시 작업공간으로 복사)
    print("[1/4] 원본 게임파일 확인")
    for fn, want in ORIG_MD5.items():
        src = os.path.join(orig, fn); dst = os.path.join(ws, fn)
        if not os.path.exists(src) and os.path.exists(dst): src = dst
        if not os.path.exists(src):
            print(f"  ✗ {fn} 없음 — 본인 게임 덤프에서 준비하세요"
                  f"\n     main=ExeFS,  RES00.RDB/RES00.RDI/RES10.RDB=RomFS의 cdvdroot/")
            sys.exit(1)
        got = md5(src)
        ok = (got == want)
        print(f"  {'✓' if ok else '✗'} {fn:12s} {got}{'' if ok else '  ← 기대 '+want}")
        if not ok:
            print("     MD5 불일치: 2024-2025 최신 업데이트(v1.8.0) 적용 상태로 덤프했는지 확인하세요.")
            sys.exit(1)
        if os.path.abspath(src) != os.path.abspath(dst):
            print(f"     복사 중… ({os.path.getsize(src)/1048576:.0f}MB)")
            shutil.copy2(src, dst)

    # 2) 데이터 배치
    print("\n[2/4] 번역 데이터·폰트 배치")
    for s, d in LAYOUT:
        sp = os.path.join(REPO, s.replace('/', os.sep))
        dp = os.path.join(ws, d.replace('/', os.sep))
        if not os.path.exists(sp): print(f"  ⚠ 저장소에 없음: {s}"); continue
        os.makedirs(os.path.dirname(dp), exist_ok=True)
        shutil.copy2(sp, dp)
        print(f"  ✓ {d}  ({os.path.getsize(dp)/1048576:.1f}MB)")

    # 3) 부트스트랩 exe
    print("\n[3/4] 베이스 실행파일 복원 (bootstrap xdelta)")
    io = os.path.join(ws, 'inject_out'); os.makedirs(io, exist_ok=True)
    safe28 = os.path.join(io, 'main-safe28')
    if os.path.exists(safe28) and md5(safe28) == SAFE28_MD5:
        print("  ✓ main-safe28 이미 존재(MD5 일치)")
    else:
        xd = os.path.join(REPO, 'patch', 'xdelta3.exe')
        if not os.path.exists(xd): xd = shutil.which('xdelta3') or 'xdelta3'
        r = subprocess.run([xd, '-d', '-f', '-s', os.path.join(ws, 'main'),
                            os.path.join(REPO, 'bootstrap', 'main-safe28.xdelta'), safe28])
        if r.returncode != 0: print("  ✗ xdelta 적용 실패"); sys.exit(1)
        got = md5(safe28)
        print(f"  {'✓' if got == SAFE28_MD5 else '✗'} inject_out/main-safe28  {got}")
        if got != SAFE28_MD5: sys.exit(1)

    # 4) 출력 폴더
    print("\n[4/4] 출력 폴더")
    for d in ('inject_out', 'repack_out'):
        os.makedirs(os.path.join(ws, d), exist_ok=True); print(f"  ✓ {d}/")

    print(f"""
완료. 다음 단계:

  Windows(cmd) :  set PAWA_ROOT={ws}
  PowerShell   :  $env:PAWA_ROOT="{ws}"
  Linux/macOS  :  export PAWA_ROOT={ws}

  실행파일 빌드 :  python tools/BUILD_FROM_MASTER.py      → inject_out/main-built
  RDB 빌드      :  python tools/BUILD_RDB_FROM_MASTER.py  → repack_out/RES00.RDB 등
""")

if __name__ == '__main__':
    main()
