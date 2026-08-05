# 패치 적용 가이드 (일반 사용자용)

원본 게임 파일 4개에 xdelta 패치를 적용해 한국어판 파일을 만들고, 에뮬레이터 또는 실기의
MOD 폴더에 넣는 과정입니다. **원본 게임 파일은 본인이 소유한 정품에서 직접 덤프해야 합니다.**

- [준비물](#준비물)
- [1단계 · 자산 내려받기](#1단계--자산-내려받기)
- [2단계 · 패치 실행](#2단계--패치-실행)
- [3단계 · 게임에 적용](#3단계--게임에-적용)
- [수동 패치 (bat 없이 / Linux · macOS)](#수동-패치-bat-없이--linux--macos)
- [문제 해결](#문제-해결)

## 준비물

### 원본 파일 4개

| 파일 | 덤프 위치 | 원본 MD5 |
|---|---|---|
| `main` | ExeFS | `916d81a491408bce1a1871efc24a6fa2` |
| `RES00.RDB` | RomFS의 `cdvdroot/` | `46ccf287fd62e9e2d51b193e788555a0` |
| `RES00.RDI` | RomFS의 `cdvdroot/` | `ad864a8bfb6b8bcf3b10481012a3f013` |
| `RES10.RDB` | RomFS의 `cdvdroot/` | `25d0b86b64fa3fcc389b00359fde96cb` |

> **반드시 2024-2025 최신 업데이트(v1.8.0)를 적용한 상태로 덤프**해야 합니다.
> 업데이트 미적용 덤프는 파일 내용이 달라 패치가 적용되지 않습니다.
> ExeFS의 `main`은 업데이트 NCA 쪽에 들어 있습니다.

MD5 확인 방법 (PowerShell):

```powershell
Get-FileHash main -Algorithm MD5
```

### 디스크 공간

`RES00.RDB`가 약 6.6GB이고 패치 후 약 7.3GB가 됩니다. 원본과 결과물을 동시에 두어야 하므로
**여유 공간 20GB 이상**을 권장합니다.

## 1단계 · 자산 내려받기

[릴리즈 페이지](../../releases/latest)에서 **7개 파일을 모두** 받습니다.

```
Pawa2024KR_v1.4_main.xdelta
Pawa2024KR_v1.4_RES00.RDI.xdelta
Pawa2024KR_v1.4_RES10.RDB.xdelta
Pawa2024KR_v1.4_RES00.RDB.xdelta.001   ← 분할 1/2
Pawa2024KR_v1.4_RES00.RDB.xdelta.002   ← 분할 2/2
Pawa2024KR_tools.zip                   ← xdelta3.exe 등
패치적용.bat
```

`RES00.RDB` 패치는 GitHub의 파일 크기 제한 때문에 `.001` / `.002`로 나뉘어 있습니다.
`패치적용.bat`이 자동으로 합쳐 주므로 따로 손댈 필요 없습니다.

## 2단계 · 패치 실행

1. `Pawa2024KR_tools.zip`을 풀어 `xdelta3.exe`를 꺼냅니다.
2. **한 폴더에** 다음을 모두 모읍니다.
   - 원본 4파일 (`main`, `RES00.RDB`, `RES00.RDI`, `RES10.RDB`)
   - 내려받은 `.xdelta` 5개
   - `xdelta3.exe`, `패치적용.bat`
3. `패치적용.bat`을 실행합니다. (경로에 한글이 있어도 됩니다)

완료되면 같은 폴더에 이런 구조가 생깁니다.

```
mods\0100d1c01c194000\
    ExeFS\main
    RomFS\cdvdroot\RES00.RDB
    RomFS\cdvdroot\RES00.RDI
    RomFS\cdvdroot\RES10.RDB
```

결과 MD5가 아래와 같으면 정상입니다.

| 파일 | 한글판 v1.4 MD5 |
|---|---|
| `main` | `3ef0843dabf03ee4c5d893f6dc52c8de` |
| `RES00.RDB` | `151db69a6c2909e7fd1e943c52759680` |
| `RES00.RDI` | `b5f9ea7fb29cbcd9a9ea933dba659c61` |
| `RES10.RDB` | `dd0169693c858e99b05e3a6c924628e2` |

## 3단계 · 게임에 적용

### Ryujinx

`mods\0100d1c01c194000` 폴더를 통째로 아래 경로에 복사합니다.

```
%AppData%\Ryujinx\mods\contents\0100d1c01c194000\
    ExeFS\main
    RomFS\cdvdroot\...
```

게임 목록에서 우클릭 → *Open Mods Directory* 로 정확한 위치를 열 수 있습니다.
적용 후 게임을 실행해 메뉴가 한국어로 나오면 성공입니다.

### Switch 실기 (Atmosphère)

SD 카드의 아래 경로에 넣습니다. **폴더 이름은 소문자**여야 합니다.

```
/atmosphere/contents/0100d1c01c194000/
    exefs/main
    romfs/cdvdroot/RES00.RDB
    romfs/cdvdroot/RES00.RDI
    romfs/cdvdroot/RES10.RDB
```

> SD 카드가 FAT32면 4GB 이상 파일을 담을 수 없어 `RES00.RDB`(7.3GB)를 넣지 못합니다.
> exFAT로 포맷하거나, exFAT 사용이 불안정한 환경이라면 에뮬레이터 사용을 권장합니다.

### 제거

넣었던 `0100d1c01c194000` 폴더만 지우면 원상복구됩니다. 게임 본체는 건드리지 않습니다.

## 수동 패치 (bat 없이 / Linux · macOS)

`xdelta3`를 설치한 뒤 아래를 순서대로 실행합니다.

```bash
# RES00.RDB 분할 패치 합치기
cat Pawa2024KR_v1.4_RES00.RDB.xdelta.001 Pawa2024KR_v1.4_RES00.RDB.xdelta.002 \
    > Pawa2024KR_v1.4_RES00.RDB.xdelta
```

```bash
mkdir -p out/ExeFS out/RomFS/cdvdroot
xdelta3 -d -f -s main      Pawa2024KR_v1.4_main.xdelta      out/ExeFS/main
xdelta3 -d -f -s RES00.RDI Pawa2024KR_v1.4_RES00.RDI.xdelta out/RomFS/cdvdroot/RES00.RDI
xdelta3 -d -f -s RES10.RDB Pawa2024KR_v1.4_RES10.RDB.xdelta out/RomFS/cdvdroot/RES10.RDB
xdelta3 -B 268435456 -d -f -s RES00.RDB Pawa2024KR_v1.4_RES00.RDB.xdelta out/RomFS/cdvdroot/RES00.RDB
```

`RES00.RDB`에 붙는 `-B 268435456`은 소스 창 크기를 256MB로 키우는 옵션으로, 대용량 파일 패치에
필요합니다. 빼면 실패합니다.

## 문제 해결

**`원본 파일이 없습니다` 또는 패치가 실패한다**
원본 4파일이 bat과 같은 폴더에 있는지, 파일 이름이 정확한지 확인하세요. 그래도 실패하면
원본 MD5가 위 표와 일치하는지 확인합니다 — 다르면 업데이트 미적용 덤프이거나 다른 리전입니다.

**게임이 여전히 일본어로 나온다**
MOD 경로가 맞는지 확인하세요. Ryujinx는 `mods/contents/0100d1c01c194000/`,
실기는 `atmosphere/contents/0100d1c01c194000/`(소문자 exefs/romfs)입니다.
Ryujinx에서 게임별 *Open Mods Directory*로 열어 그 안에 넣는 것이 가장 확실합니다.

**글자가 네모/깨져 보인다**
`RES00.RDB`가 제대로 적용되지 않은 경우입니다. 한글은 폰트 글리프를 교체해 표시하므로
실행파일만 적용하면 글자가 깨집니다. 4개 파일을 **모두** 적용해야 합니다.

**선수 이름이 일본어로 나온다**
기존 세이브 데이터에 저장된 이름이 표시되는 경우가 있습니다. 새로 시작하면 해결됩니다.

**용량이 부족하다**
패치 과정에서 원본과 결과물이 동시에 존재합니다. 임시로 외장 디스크를 쓰거나, `RES00.RDB`
패치가 끝난 뒤 원본을 옮겨 공간을 확보하세요.

**마이라이프 진행 중 게임이 멈춘다**
v1.2 / v1.3의 알려진 문제(28일차 크래시)입니다. **v1.4로 갱신**하면 해결됩니다.
