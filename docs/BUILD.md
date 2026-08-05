# 소스에서 다시 빌드하기

이 저장소의 데이터와 도구만으로 배포본과 **동일한 파일을 재현**할 수 있습니다.
번역을 고쳐서 나만의 패치를 만들 때도 같은 절차를 씁니다.

- [준비](#준비)
- [1 · 작업공간 만들기](#1--작업공간-만들기)
- [2 · 실행파일 빌드](#2--실행파일-빌드)
- [3 · RDB 빌드](#3--rdb-빌드)
- [4 · 게임에 넣기 / 배포용 xdelta 만들기](#4--게임에-넣기--배포용-xdelta-만들기)
- [도구 지도](#도구-지도)
- [건드리면 안 되는 것](#건드리면-안-되는-것)

## 준비

- **Python 3.10 이상**, `pip install numpy`
- 원본 게임 파일 4개 (`main`, `RES00.RDB`, `RES00.RDI`, `RES10.RDB`) — [PATCH.md](PATCH.md#준비물) 참고
- 디스크 여유 **25GB 이상** (원본 + 작업본 + 결과물)
- Windows 기준으로 설명하지만 Linux/macOS에서도 동일하게 동작합니다
  (`xdelta3`는 패키지 매니저로 설치).

## 1 · 작업공간 만들기

도구들은 **작업공간(workspace)** 한 폴더 안에서 동작합니다. 원본 게임 파일과 번역 데이터가
그 안에 모여 있어야 합니다. 아래 한 줄이 전부 준비해 줍니다.

```bash
python tools/SETUP_WORKSPACE.py D:\pawa_ws --orig D:\내덤프폴더
```

이 스크립트가 하는 일:

1. 원본 4파일의 MD5를 검증하고 작업공간으로 복사 (다르면 즉시 중단 — 잘못된 덤프 조기 발견)
2. `data/`의 번역 데이터·폰트를 도구들이 기대하는 이름·위치로 배치
3. `bootstrap/main-safe28.xdelta`를 원본 `main`에 적용해 **빌드 베이스 실행파일**을 복원
   (`inject_out/main-safe28`, MD5 `e07eea88b8f0687ecd7c8666452b1d3b`)
4. `inject_out/`, `repack_out/` 생성

만들어진 작업공간 구조:

```
D:\pawa_ws\
  main  RES00.RDB  RES00.RDI  RES10.RDB     ← 원본
  번역_마스터.json                            ← 번역 단일 소스
  !exefs-작업\hangul_to_hanja.tsv             ← 인코딩 테이블
  COMMON_2D-한글폰트삽입.CHK  (외 1개)        ← 한글 폰트
  inject_out\main-safe28                     ← 빌드 베이스
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

> `PAWA_ROOT`를 지정하지 않으면 도구는 **현재 디렉터리**를 작업공간으로 씁니다.
> 작업공간 안에서 직접 실행해도 됩니다.

## 2 · 실행파일 빌드

```bash
python tools/BUILD_FROM_MASTER.py
```

출력 예:

```
1) 원본영역 주입 {'inj': 182787, 'skip': 0}
2) 보호셋: RELA(원본+safe28)+JMPREL+SYMTAB+코드즉치 85,238 → 문자열영역 참조 359,741곳
   멀티필드(비연속 ents) 제외: 25 → 완성문장 대상 5,244
3) 수납: 통짜 127 + 분할 4,631(15350파트) + 스킵 0 / 리다이렉트 {'redir': 16712, 'empt': 5697}
4) 검증: 문장체인 5,244/5,244 일치(스킵 0), diff 353,826B 규율 내, 보호셋 침범 0, ...
→ inject_out/main-built  md5 3ef0843dabf03ee4c5d893f6dc52c8de  (무확장, 크기 106,034,273)
```

**MD5가 `3ef0843d…`면 v1.4 배포본과 바이트 단위로 동일**합니다. 번역을 고치지 않았는데 값이
다르면 데이터나 베이스가 어긋난 것이니 멈추고 원인을 찾으세요.

이 스크립트는 매 실행마다 스스로를 검증합니다 — 문장 체인 디코드 일치, 변경 바이트가 허용
구역 안에만 있는지, 보호된 참조를 침범하지 않았는지, `.text`/`.data`가 그대로인지. 하나라도
어긋나면 `assert`로 중단합니다. 원리는 [ARCHITECTURE.md](ARCHITECTURE.md) 참고.

옵션:

```bash
python tools/BUILD_FROM_MASTER.py --no-mylife   # 마이라이프 완성문장 없이(조각 표시) 빌드
```

## 3 · RDB 빌드

```bash
python tools/BUILD_RDB_FROM_MASTER.py
```

원본 RDB를 `repack_out/`으로 복사한 뒤, 폰트 CHK를 한글판으로 바꾸고 `번역_마스터.json`의
텍스트 54,510건을 제자리에 주입합니다. **7GB를 다루므로 복사 몇 분 + 주입 수 분**이 걸립니다.

```bash
python tools/BUILD_RDB_FROM_MASTER.py --fresh   # repack_out을 원본으로 되돌리고 처음부터
```

> 이미 배포본 `repack_out/`을 갖고 있다면 `tools/APPLY_MASTER.py`가 더 빠릅니다
> (있는 것 위에 마스터를 다시 덮어씀). `--deploy`를 붙이면 Ryujinx MOD 폴더까지 복사합니다.
> 단 이 경로는 경로가 하드코딩되어 있으니 코드를 확인하고 쓰세요.

## 4 · 게임에 넣기 / 배포용 xdelta 만들기

빌드 결과를 MOD 폴더 구조로 배치합니다.

```
mods/0100d1c01c194000/ExeFS/main                    ← inject_out/main-built
mods/0100d1c01c194000/RomFS/cdvdroot/RES00.RDB      ← repack_out/RES00.RDB
mods/0100d1c01c194000/RomFS/cdvdroot/RES00.RDI      ← repack_out/RES00.RDI
mods/0100d1c01c194000/RomFS/cdvdroot/RES10.RDB      ← repack_out/RES10.RDB
```

남에게 배포할 때는 원본 대비 xdelta 패치를 만듭니다(게임 데이터를 직접 배포하지 않기 위해서).

```bash
patch/xdelta3.exe -e -9 -f -s main       inject_out/main-built   main.xdelta
patch/xdelta3.exe -e -9 -f -s RES00.RDI  repack_out/RES00.RDI    RES00.RDI.xdelta
patch/xdelta3.exe -e -9 -f -s RES10.RDB  repack_out/RES10.RDB    RES10.RDB.xdelta
patch/xdelta3.exe -e -9 -f -s RES00.RDB  repack_out/RES00.RDB    RES00.RDB.xdelta
```

`RES00.RDB.xdelta`는 3GB를 넘으므로 GitHub 릴리즈에 올리려면 2GB 미만으로 분할합니다
(`split -b 1900m -d ... .xdelta.` 후 `.001`/`.002`로 이름 변경 — `패치적용.bat`이 그 이름을 기대합니다).

## 도구 지도

`tools/`에는 개발 과정에서 쓰인 스크립트가 모두 들어 있습니다. **현재 빌드에 필요한 것**은 다음뿐입니다.

| 파일 | 역할 |
|---|---|
| `SETUP_WORKSPACE.py` | 작업공간 구성(원본 검증·데이터 배치·부트스트랩) |
| `BUILD_FROM_MASTER.py` | ★ 실행파일 빌드 (원본영역 주입 + 꼬리풀 완성문장 리다이렉트 + 자체검증) |
| `BUILD_RDB_FROM_MASTER.py` | ★ 원본 RDB → 한국어 RDB (폰트 교체 + 텍스트 주입) |
| `rdblib.py` | RDB/RDI 포맷 라이브러리(암복호화·압축·재배치) |
| `APPLY_MASTER.py` | 기존 결과물 위에 마스터를 다시 덮어쓰는 빠른 경로 |

그 밖의 스크립트는 **과거 작업 기록**입니다. 추출·분석·일회성 수리·폐기된 실험이 섞여 있으며,
그중에는 **쓰면 안 되는 것**도 있습니다(아래 참고). 참고할 만한 것들:

| 파일 | 역할 |
|---|---|
| `EXTRACT_EXE_EXT.py` | 배포본 실행파일에서 완성문장을 역추출해 마스터에 넣기 |
| `SCAN_RDB_LINE.py` | RDB 텍스트의 줄 규칙(24자/3줄) 위반 수집 |
| `POOL_MEASURE.py` | 꼬리풀 용량 측정 |
| `FIX_JOSA.py` | 조사 병기(`이(가)`)를 앞 글자 받침에 맞춰 확정 |
| `EXPAND_NSO.py` | ⛔ 폐기된 세그먼트 확장 (아래 참고) |

> 과거 스크립트 중 일부는 예전 폴더 구조를 전제합니다. 저장소에 담으면서 하드코딩 경로는
> `PAWA_ROOT` 기준으로 자동 치환했지만, 오래된 중간 산출물(`main-safe20` 등)을 요구하는
> 스크립트는 그대로는 실행되지 않습니다. 읽고 참고하는 용도로 보세요.

## 건드리면 안 되는 것

**`EXPAND_NSO.py`(세그먼트 재배치 확장)를 쓰지 마세요.** 실행파일을 늘려 새 문자열 공간을
만드는 방식으로, 부팅과 초반 플레이는 정상이지만 **마이라이프 28일차에서 게임이 죽습니다.**
게임이 일부 주소를 저장된 포인터가 아니라 코드 즉치값/직렬화 데이터의 모듈 상대 오프셋으로
계산하기 때문에, 정적으로 모든 참조를 갱신하는 것이 원리적으로 불가능합니다.
현재의 꼬리풀 방식은 **파일 크기를 1바이트도 바꾸지 않으므로** 이 문제가 없습니다.
자세한 경위는 [HISTORY.md](HISTORY.md).

**`.rodata`의 0으로 채워진 영역을 빈 공간으로 쓰지 마세요.** 셰이더/리소스 디스크립터 테이블의
0 필드일 수 있고(`base+index`로 접근하므로 포인터 검사에 걸리지 않음), 덮어쓰면 게임 시작
직후 GPU 크래시가 납니다. 실제로 겪었던 일입니다.

**빌드 스크립트의 `assert`를 우회하지 마세요.** 그 검증들은 전부 실제 사고를 겪고 추가된 것입니다.
