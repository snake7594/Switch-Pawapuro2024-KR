# -*- coding: utf-8 -*-
"""고교 CHK: 배포본에서 '종료자 유실(런어웨이)' 및 구조바이트 침범 탐지.
방법: 원본 대비 diff 구간마다, 배포본에서 그 문자열 영역이 원본과 같은 위치에 NUL을 갖는지 확인.
      원본엔 NUL이 있었는데 배포본에서 그 NUL이 비-NUL로 덮여 다음 문자열/구조까지 이어지면 런어웨이."""
import sys, os, struct
sys.stdout.reconfigure(encoding='utf-8')
_R = os.environ.get("PAWA_ROOT")
if _R: os.chdir(_R)   # 작업공간(원본 게임파일+데이터). 미지정 시 현재 디렉터리 사용
import rdblib

ORG = rdblib.RDB('.')
DEP = rdblib.RDB('repack_out')
names = sorted(n for n in DEP.idx if n.startswith(('HSIM', 'HATK', 'D2D_HATK', 'G2D_HATK')) or n in
               ('TEXT_HSIMSCH.CHK', 'CHALLENGE.CHK', 'TEXT_CHAL_STR.CHK', 'LIVE_STG.CHK'))
print(f"검사 {len(names)}개")

issues = []
for name in names:
    try:
        db = DEP.read_body(name); ob = ORG.read_body(name)
    except Exception as e:
        issues.append((name, f'read실패 {e}')); continue
    if db is None or ob is None: continue
    # 크기 다르면(재배치·STRING재구성) 위치 비교 무의미 → STRING 청크는 이미 검증됨. 여기선 동일크기만 정밀.
    if len(db) != len(ob):
        continue
    L = len(ob)
    i = 0
    # 원본의 NUL 위치 집합 대비, 배포본에서 사라진 NUL 탐지(비-NUL로 덮임)
    n_lost = 0; first = None
    for i in range(L):
        if ob[i] == 0 and db[i] != 0:
            n_lost += 1
            if first is None: first = i
    if n_lost:
        # 런어웨이 심각도: 사라진 NUL 뒤로 다음 NUL까지 거리
        e = db.find(b'\x00', first)
        runlen = (e - first) if e >= 0 else (L - first)
        issues.append((name, f'NUL유실 {n_lost}개, 첫 @0x{first:x}, 런길이 {runlen}'))
        print(f'  ★ {name}: NUL유실 {n_lost}, 첫0x{first:x}, 런{runlen}B  주변={db[first-4:first+16].hex()}')
    # 추가: 배포본에 dangling UTF-8(불완전+NUL) — 렌더 bleed
    # (STRING 검증서 UTF-8 확인했으므로 생략)
print('=' * 50)
print(f"런어웨이/NUL유실 파일 {len(issues)}개")
ORG.close(); DEP.close()
