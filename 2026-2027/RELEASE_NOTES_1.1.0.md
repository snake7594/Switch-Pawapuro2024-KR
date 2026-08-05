# 실황 파워풀 프로야구 2026–2027 한국어 패치 — 게임 업데이트 1.1.0

이 릴리즈는 타이틀 ID `01007e8023f36000`의 게임 업데이트 **v1.1.0**을 대상으로 합니다. 2024–2025 작업에서 사용한 RDB 슬롯·폰트·xdelta 배포 방식을 기준으로 2026–2027의 파일 구조를 새로 분석해 적용했습니다.

## 릴리즈 자산

| 자산 | 설명 |
|---|---|
| `Pawapuro2026-1.1.0-main.xdelta` | 파일 크기를 늘리지 않는 실기 안전형 ExeFS `main` 패치 |
| `Pawapuro2026-1.1.0-RES00.RDB.xdelta` | 메뉴·대사·폰트가 포함된 주 RDB 패치 |
| `Pawapuro2026-1.1.0-RES00.RDI.xdelta` | RDI 패치(출력은 원본과 동일하며 호환성을 위해 함께 제공) |
| `Pawapuro2026-1.1.0-RES10.RDB.xdelta` | 보조 RDB 패치 |
| `Pawapuro2026-1.1.0-source.zip` | 번역 JSON, 메뉴 분류·검토 자료, SJIS 한글 매핑, 폰트 입력, 빌드·검증 도구 전체 |
| `Pawapuro2026-1.1.0-tools.zip` | Windows용 `xdelta3.exe`와 자동 적용 스크립트 |
| `SHA256SUMS.txt` | 릴리즈 자산 및 패치 결과 SHA-256 |

원본 게임의 `main`, RDB/RDI, 동영상·음원 등은 저작권 보호를 위해 저장소와 릴리즈에 포함하지 않습니다.

## 패치 전 원본 확인

아래 SHA-256은 업데이트 1.1.0 원본 덤프의 값입니다.

```text
main       133ca68c41910024b1984808d48eb4e3c63393d93fe868c3dc0322a3b0d44f66
RES00.RDB  59b4872c755c27ffec5e10528bd65c21dcca28b8fa40dd4d676bc5d2c005ddec
RES00.RDI  ef7dba93d9bccb166a4152cd952a0e72a8fc7af6787300eef1d3bcb14ccee16b
RES10.RDB  b5e18b3984346065f73945644edac08fc9312fed7312b700ad7f79f23766eff3
```

다른 업데이트의 파일에는 적용하지 마세요. 적용 전 원본 백업을 권장합니다.

## 적용

`Pawapuro2026-1.1.0-tools.zip`을 풀고 원본 네 파일을 `original/`에 둔 뒤, 네 개의 `*.xdelta`를 같은 폴더에 놓고 `apply_patch.bat`를 실행합니다. 수동 적용은 다음과 같습니다.

```powershell
xdelta3 -B 268435456 -d -f -s .\main .\Pawapuro2026-1.1.0-main.xdelta .\out\main
xdelta3 -B 268435456 -d -f -s .\RES00.RDB .\Pawapuro2026-1.1.0-RES00.RDB.xdelta .\out\RES00.RDB
xdelta3 -B 268435456 -d -f -s .\RES00.RDI .\Pawapuro2026-1.1.0-RES00.RDI.xdelta .\out\RES00.RDI
xdelta3 -B 268435456 -d -f -s .\RES10.RDB .\Pawapuro2026-1.1.0-RES10.RDB.xdelta .\out\RES10.RDB
```

Atmosphère 모드 경로는 다음과 같습니다.

```text
/atmosphere/contents/01007e8023f36000/exefs/main
/atmosphere/contents/01007e8023f36000/romfs/cdvdroot/RES00.RDB
/atmosphere/contents/01007e8023f36000/romfs/cdvdroot/RES00.RDI
/atmosphere/contents/01007e8023f36000/romfs/cdvdroot/RES10.RDB
```

## 기술 요약

- `main`은 원본 파일 크기(`97,643,010`바이트), NSO 헤더와 `.text`를 유지합니다.
- 긴 문자열은 검증된 0-fill 풀에 배치하고 `.data`의 정적 포인터만 바꿉니다. 동적 재배치가 필요한 항목은 원본을 유지해 실기에서의 즉시 종료 가능성을 줄였습니다.
- 제자리 문자열 `219,016`개, 안전한 풀에 완전 배치한 문자열 `16,621`개, 정적 포인터 재작성 `23,313`곳입니다.
- RDB는 파일 크기와 RDI 슬롯을 유지하고, 재배치가 필요한 `5,188` 슬롯은 원본으로 남겼습니다.
- 폰트는 빙그레체 일반체를 사용하고, 완성형 한글 2350자를 게임의 SJIS 한자 슬롯 순서에 맞춰 넣었습니다.
- 메뉴형 텍스트는 원문 폭 제약을 고려해 불필요한 띄어쓰기를 줄였고, 문장형 대사는 의미를 우선했습니다.

## 검증된 패치 결과

```text
main       4cb0ef73932d003cd8d1f2d4596a8645840e8c252c1b4436f102bf7f56b909bb
RES00.RDB  111f439e8fc16f3a3458fbf6ee635155a75e944ee8db0c24edb601d9182fbf55
RES00.RDI  ef7dba93d9bccb166a4152cd952a0e72a8fc7af6787300eef1d3bcb14ccee16b
RES10.RDB  9ec8c38e8ce5c7c128df1c1ed853d171c8233e83b0174aa890091225b3a163d6
```

작업 환경과 에뮬레이터에서 xdelta 복원 및 해시 검증을 완료했습니다. 실기에서는 기존 모드를 완전히 종료한 뒤 새 모드를 적용해 확인하세요. 문제가 생기면 타이틀 ID 모드 폴더의 파일을 제거하면 원본으로 돌아갑니다.

자세한 재빌드 절차는 소스 ZIP의 `2026-2027/docs/BUILD.md`, 적용 절차는 `2026-2027/docs/PATCH.md`에 있습니다.
