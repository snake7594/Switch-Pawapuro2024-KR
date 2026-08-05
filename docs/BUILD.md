# 소스에서 다시 빌드하기

이 저장소의 데이터와 도구만으로 배포본과 **동일한 파일을 재현**할 수 있습니다.
번역을 고쳐서 나만의 패치를 만들 때도 같은 절차를 씁니다.

- [준비](#준비)
- [1 · 작업공간 만들기](#1--작업공간-만들기)
- [2 · 실행파일 빌드](#2--실행파일-빌드)
- [3 · RDB 빌드](#3--rdb-빌드)
- [4 · 검증](#4--검증)
- [5 · 게임에 넣기 / 배포용 xdelta 만들기](#5--게임에-넣기--배포용-xdelta-만들기)
- [도구 지도](#도구-지도)
- [건드리면 안 되는 것](#건드리면-안-되는-것)

## 준비

- **Python 3.10 이상**, `pip install numpy`
- 원본 게임 파일 4개 (`main`, `RES00.RDB`, `RES00.RDI`, `RES10.RDB`) — **게임 업데이트 v1.15.0**
  기준. [PATCH.md](PATCH.md#준비물) 참고
- 디스크 여유 **25GB 이상** (원본 + 작업본 + 결과물)
- Windows 기준으로 설명하지만 Linux/macOS에서도 동일하게 동작합니다
  (`xdelta3`는 패키지 매니저로 설치).

## 1 · 작업공간 만들기

도구들은 **작업공간(workspace)** 한 폴더 안에서 동작합니다.

```bash
python tools/SETUP_WORKSPACE.py D:\pawa_ws --orig D:\내덤프폴더 --link
```

이 스크립트가 하는 일:

1. 원본 4파일의 MD5를 검증하고 작업공간에 배치 (다르면 즉시 중단 — 잘못된 덤프 조기 발견).
   `--link` 를 주면 복사 대신 **하드링크**를 걸어 7GB 복사를 아낍니다(같은 볼륨일 때).
2. `data/`의 번역 데이터를 도구들이 기대하는 이름·위치로 배치
3. `tools/BUILD_BASE.py` 를 돌려 **베이스 실행파일**을 생성 (`inject_out/main-base`)
4. `inject_out/`, `repack_out/` 생성

만들어진 작업공간 구조:

```
D:\pawa_ws\
  main  RES00.RDB  RES00.RDI  RES10.RDB     ← 원본
  번역_마스터.json                            ← 번역 단일 소스
  rdb_residual.pack                          ← 폰트 글리프 등 잔차
  !exefs-작업\hangul_to_hanja.tsv             ← 인코딩 테이블
  inject_out\main-base                       ← 빌드 베이스(생성물)
  repack_out\                                ← RDB 결과가 쌓일 곳
```

이후 모든 명령 전에 작업공간을 알려 줍니다.

```bash
# Windows cmd
set PAWA_ROOT=D:\pawa_ws
# PowerShell
$env:PAWA_ROOT="D:\pawa_ws"
# Linux/macOS
export PAWA_ROOT=/path/to/pawa_ws
```

> **v1.4 까지 있던 `bootstrap/main-safe28.xdelta` 는 없어졌습니다.**
> 베이스에 들어 있던 "잘린 문장의 전체 텍스트"가 마스터의 `exe_pool` 섹션으로 올라와,
> 베이스까지 마스터에서 결정적으로 재생성되기 때문입니다. 자세한 경위는 [PORTING.md](PORTING.md).

## 2 · 실행파일 빌드

```bash
python tools/BUILD_EXE.py
```

출력 예:

```
0) DYN_HI=0x3d7831d 문자열영역 0x3d7831e~0x5aca139 크기 106,455,713
1) 원본영역 주입 {'inj': 182818, 'skip': 0}
2) 보호셋: … → 문자열영역 참조 360,224곳
   멀티필드(비연속 ents) 제외: 0 → 완성문장 대상 5,243
   풀(꼬리, NUL런 제외): 58,446청크 758,445B
3) 수납: 통짜 128 + 분할 4,625(15322파트) + 스킵 4 / 리다이렉트 {'redir': 16683, 'empt': 5711}
4) 검증: 문장체인 5,239/5,239 일치(스킵 4), diff 353,507B 규율 내, 보호셋 침범 0, …
→ inject_out/main-built  md5 feff0c268e9835d14c15a25e5409678f  (무확장, 크기 106,455,713)
```

**MD5가 `feff0c26…`면 v2.0 배포본과 바이트 단위로 동일**합니다. 번역을 고치지 않았는데 값이
다르면 데이터나 베이스가 어긋난 것이니 멈추고 원인을 찾으세요.

이 스크립트는 매 실행마다 스스로를 검증합니다 — 문장 체인 디코드 일치, 변경 바이트가 허용
구역 안에만 있는지, 보호된 참조를 침범하지 않았는지, `.text`/`.data`가 그대로인지. 하나라도
어긋나면 `assert`로 중단합니다. 원리는 [ARCHITECTURE.md](ARCHITECTURE.md) 참고.

옵션:

```bash
python tools/BUILD_EXE.py --no-mylife   # 마이라이프 완성문장 없이(조각 표시) 빌드
```

## 3 · RDB 빌드

```bash
python tools/BUILD_RDB_FROM_MASTER.py --fresh
```

원본 RDB를 `repack_out/`으로 복사한 뒤, 폰트 CHK를 한글판으로 바꾸고 `번역_마스터.json`의
텍스트 55,186건을 제자리에 주입합니다. **7GB를 다루므로 복사 몇 분 + 주입 3분쯤** 걸립니다.

폰트를 다시 만들어야 할 때(게임 업데이트로 폰트 CHK가 바뀐 경우):

```bash
python tools/BUILD_FONT_2ND.py <원본RDB폴더> <한글COMMON_2D본문> <tsv> <출력>
python tools/BUILD_RESIDUAL.py <기존팩> <원본RDB폴더> <한글2ND본문> <새팩>
```

## 4 · 검증

```bash
python tools/VERIFY_EXE.py main inject_out/main-built 번역_마스터.json !exefs-작업/hangul_to_hanja.tsv
python tools/VERIFY_RDB.py repack_out 번역_마스터.json !exefs-작업/hangul_to_hanja.tsv
```

`VERIFY_EXE` 가 보는 것: 크기·헤더·`.text`·`.data` 불변, 동적영역 변경이 RELA `addend`
필드에만 있는지, addend 가 전부 유효 범위인지, `exe_pool` 리다이렉트가 실제로 전체 문장을
가리키는지, 잘린 UTF-8·서식지정자 초과가 없는지, 가나가 남았는지.

`VERIFY_RDB` 가 보는 것: 전 슬롯 복호+zlib 해제 성공 여부, 폰트 교체 여부,
주입 텍스트 표본 일치, 가나 잔존.

v2.0 기준 통과 결과:

| 검사 | 결과 |
|---|---|
| exe 구조/참조/풀/서식 | ✅ 전 항목 통과 |
| RDB 슬롯 무결성 | ✅ 13,453개 정상 · 실패 0 |
| RDB 텍스트 표본 | ✅ 4,950 일치 · 불일치 0 |
| 가나 잔존 | ✅ exe 0 · RDB 0 |
| 빌드 결정성 | ✅ 두 번 빌드 md5 동일 |
| xdelta 왕복 | ✅ 4파일 전부 MD5 일치 |

## 5 · 게임에 넣기 / 배포용 xdelta 만들기

빌드 결과를 MOD 폴더 구조로 배치합니다.

```
mods/0100d1c01c194000/ExeFS/main                    ← inject_out/main-built
mods/0100d1c01c194000/RomFS/cdvdroot/RES00.RDB      ← repack_out/RES00.RDB
mods/0100d1c01c194000/RomFS/cdvdroot/RES00.RDI      ← repack_out/RES00.RDI
mods/0100d1c01c194000/RomFS/cdvdroot/RES10.RDB      ← repack_out/RES10.RDB
```

남에게 배포할 때는 원본 대비 xdelta 패치를 만듭니다(게임 데이터를 직접 배포하지 않기 위해서).

```bash
xdelta3 -B 268435456 -e -S none -fs main       inject_out/main-built  Pawa2024KR_v2.0_main.xdelta
xdelta3 -B 268435456 -e -S none -fs RES00.RDI  repack_out/RES00.RDI   Pawa2024KR_v2.0_RES00.RDI.xdelta
xdelta3 -B 268435456 -e -S none -fs RES10.RDB  repack_out/RES10.RDB   Pawa2024KR_v2.0_RES10.RDB.xdelta
xdelta3 -B 268435456 -e -S none -fs RES00.RDB  repack_out/RES00.RDB   Pawa2024KR_v2.0_RES00.RDB.xdelta
```

`-9` / `-S djw` 는 이미 압축된 데이터에 무익하고 느리기만 합니다(실측: 옵션을 바꿔도
412,317,578 vs 412,284,672 로 차이 없음).

### ⚠ 델타 크기는 '얼마나 많은 슬롯을 다시 썼는가'로 결정된다

`RES00.RDB` 패치가 v1.4 에서 **3.72GB**, v2.0 에서 **412MB** 로 9배 차이가 났습니다.
인코더 옵션 때문이 아니라 **산출물 내용이 원본과 얼마나 다른가**의 차이입니다.

| | 원본 구간에서 덮어쓴 비율 | 뒤에 붙은 재배치 분량 | 원본에 없는 바이트 | 델타 |
|---|---|---|---|---|
| v1.4 | **40.1%** (521개 재배치) | 934MB | 약 3,483MB | 3,720MB |
| v2.0 | **6.1%** (4개 재배치) | 3MB | 약 388MB | 412MB |

CHK 하나에 글자 한 자만 고쳐도 **zlib 스트림이 그 지점부터 전부 달라지고**, 슬롯 전체가
새 바이트가 됩니다. 게다가 원래 자리에 안 들어가면 아카이브 끝에 통째로 새로 붙습니다.
그 바이트들은 이미 압축·암호화된 상태라 xdelta 가 압축하지도 못합니다.

- v1.4 는 기존 `repack_out` 위에 여러 세대에 걸쳐 덮어쓰며 만들어졌고, 과거 전 슬롯 재인코딩
  (`RECODE_ALL2.py` 등) 이력이 쌓여 아카이브의 40%가 원본과 달라졌습니다.
- v2.0 은 원본에서 **`--fresh` 로 한 번에** 빌드해 실제로 바뀌는 493개 파일만 건드렸습니다.

> **배포용 빌드는 반드시 `--fresh` 로 하세요.** 재사용 빌드(`--reuse`)는 개발 중 반복이 빠른
> 대신, 그대로 배포하면 델타가 몇 배로 부풀고 사용자 다운로드가 그만큼 늘어납니다.

## 재현 검증 결과

이 저장소만으로 원본에서 처음부터 빌드해 배포본과 대조한 결과입니다.

| 대상 | 결과 |
|---|---|
| `main` (실행파일) | ✅ MD5 `feff0c26…` — 릴리즈 v2.0과 **바이트 단위 동일** |
| RDB 본문 (CHK 13,453개) | ✅ 전부 정상 복호·해제 |
| RDB 파일 MD5 | ⚠ 빌드 이력에 따라 달라질 수 있음 — **본문 단위로** 비교하세요 |

```bash
python tools/VERIFY_RDB_BODIES.py <내가_빌드한>/repack_out <비교대상>/repack_out
```

## 도구 지도

`tools/`에는 개발 과정에서 쓰인 스크립트가 모두 들어 있습니다. **현재 빌드에 필요한 것**은 다음뿐입니다.

| 파일 | 역할 |
|---|---|
| `SETUP_WORKSPACE.py` | 작업공간 구성(원본 검증·데이터 배치·베이스 생성) |
| `BUILD_BASE.py` | ★ 베이스 실행파일 = 원본 + 죽은 zero-run 풀 리다이렉트(`exe_pool`) |
| `BUILD_EXE.py` | ★ 실행파일 빌드 (원본영역 주입 + 꼬리풀 완성문장 리다이렉트 + 자체검증) |
| `BUILD_RDB_FROM_MASTER.py` | ★ 원본 RDB → 한국어 RDB (폰트 교체 + 텍스트 주입) |
| `rdblib.py` | RDB/RDI 포맷 라이브러리(암복호화·압축·재배치) |
| `BUILD_FONT_2ND.py` / `BUILD_RESIDUAL.py` | 새 폰트 CHK 한글화 · 잔차 팩 재생성 |
| `VERIFY_EXE.py` / `VERIFY_RDB.py` | 산출물 검증 |
| `port/` | 게임 업데이트 간 좌표 이식 도구 — [PORTING.md](PORTING.md) |

그 밖의 스크립트는 **과거 작업 기록**입니다. 추출·분석·일회성 수리·폐기된 실험이 섞여 있으며,
그중에는 **쓰면 안 되는 것**도 있습니다(아래 참고). 참고할 만한 것들:

| 파일 | 역할 |
|---|---|
| `BUILD_FROM_MASTER.py` | ⛔ 구 빌더(게임 v1.8.0 상수 하드코딩). `BUILD_EXE.py` 로 대체됨 |
| `SAFE_REDIRECT.py` | 죽은 zero-run 풀 리다이렉트 원형(현재는 `BUILD_BASE.py`) |
| `SCAN_RDB_LINE.py` | RDB 텍스트의 줄 규칙(24자/3줄) 위반 수집 |
| `POOL_MEASURE.py` | 꼬리풀 용량 측정 |
| `FIX_JOSA.py` | 조사 병기(`이(가)`)를 앞 글자 받침에 맞춰 확정 |
| `EXPAND_NSO.py` | ⛔ 폐기된 세그먼트 확장 (아래 참고) |

> 과거 스크립트 중 일부는 예전 폴더 구조나 게임 v1.8.0 을 전제합니다. 읽고 참고하는 용도로 보세요.

## 건드리면 안 되는 것

**`EXPAND_NSO.py`(세그먼트 재배치 확장)를 쓰지 마세요.** 실행파일을 늘려 새 문자열 공간을
만드는 방식으로, 부팅과 초반 플레이는 정상이지만 **마이라이프 28일차에서 게임이 죽습니다.**
게임이 일부 주소를 저장된 포인터가 아니라 코드 즉치값/직렬화 데이터의 모듈 상대 오프셋으로
계산하기 때문에, 정적으로 모든 참조를 갱신하는 것이 원리적으로 불가능합니다.
현재 방식은 **파일 크기를 1바이트도 바꾸지 않으므로** 이 문제가 없습니다.
자세한 경위는 [HISTORY.md](HISTORY.md).

**`.rodata`의 0으로 채워진 영역을 마음대로 빈 공간으로 쓰지 마세요.** 셰이더/리소스 디스크립터
테이블의 0 필드일 수 있고(`base+index`로 접근하므로 포인터 검사에 걸리지 않음), 덮어쓰면 게임
시작 직후 GPU 크래시가 납니다. `BUILD_BASE.py` 의 풀은 데이터포인터·코드참조 페이지를 배제하고
양끝 32B를 예약하는 **검증된 조건**을 지킵니다 — 그 조건을 완화하지 마세요.

**빌드 스크립트의 `assert`를 우회하지 마세요.** 그 검증들은 전부 실제 사고를 겪고 추가된 것입니다.
