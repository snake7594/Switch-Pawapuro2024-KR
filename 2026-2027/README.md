# 실황 파워풀 프로야구 2026–2027 한국어 패치

이 디렉터리는 Nintendo Switch판 **실황 파워풀 프로야구 2026–2027, 게임 업데이트 1.1.0**용 작업물입니다.

| 항목 | 값 |
|---|---|
| 게임 | 실황 파워풀 프로야구 2026–2027 (Switch) |
| 게임 업데이트 | **v1.1.0** |
| 타이틀 ID | `01007e8023f36000` |
| 최신 릴리즈 태그 | `2026-v1.1.0` |
| 적용 대상 | ExeFS `main`, RomFS `cdvdroot/RES00.RDB`, `RES00.RDI`, `RES10.RDB` |
| 폰트 | 빙그레체 일반체, 완성형 한글 2350자 / SJIS 한자 슬롯 순서 |

## 배포물

GitHub 릴리즈의 `*.xdelta`는 본인이 덤프한 게임 파일에만 적용합니다. 원본 게임 데이터는 저장소와 릴리즈에 포함하지 않습니다.

- `Pawapuro2026-1.1.0-main.xdelta`: 실기 호환을 위해 파일 크기를 늘리지 않는 `main` 패치
- `Pawapuro2026-1.1.0-RES00.RDB.xdelta`: 대사·메뉴·폰트 RDB 패치
- `Pawapuro2026-1.1.0-RES00.RDI.xdelta`: RDI 패치(이번 빌드에서는 원본과 동일할 수 있음)
- `Pawapuro2026-1.1.0-RES10.RDB.xdelta`: 보조 RDB 패치
- `Pawapuro2026-1.1.0-source.zip`: 번역 JSON, 매핑 테이블, 폰트 입력, 빌드 도구와 검증 보고서 전체

## 적용 전 확인

반드시 게임 업데이트 **1.1.0**을 설치한 뒤 다음 원본 4개를 덤프해야 합니다.

```text
main
RES00.RDB
RES00.RDI
RES10.RDB
```

다른 게임 버전의 파일에 적용하면 xdelta가 실패하거나 게임이 실행되지 않습니다. 원본 백업을 먼저 보관하세요.

## 적용 방법

`xdelta3`와 릴리즈의 네 파일을 원본 파일이 있는 작업 폴더에 둡니다.

```powershell
xdelta3 -d -f -s .\main .\Pawapuro2026-1.1.0-main.xdelta .\out\main
xdelta3 -d -f -s .\RES00.RDB .\Pawapuro2026-1.1.0-RES00.RDB.xdelta .\out\RES00.RDB
xdelta3 -d -f -s .\RES00.RDI .\Pawapuro2026-1.1.0-RES00.RDI.xdelta .\out\RES00.RDI
xdelta3 -d -f -s .\RES10.RDB .\Pawapuro2026-1.1.0-RES10.RDB.xdelta .\out\RES10.RDB
```

완성된 파일을 모드 경로에 다음처럼 배치합니다.

```text
/atmosphere/contents/01007e8023f36000/
  exefs/main
  romfs/cdvdroot/RES00.RDB
  romfs/cdvdroot/RES00.RDI
  romfs/cdvdroot/RES10.RDB
```

에뮬레이터에서는 같은 구조를 해당 에뮬레이터의 타이틀 모드 폴더에 사용합니다. 파일을 교체한 뒤 에뮬레이터·게임을 완전히 종료하고 다시 실행하세요.

## 빌드 방식

자세한 절차는 [`docs/BUILD.md`](docs/BUILD.md), xdelta 적용과 해시는 [`docs/PATCH.md`](docs/PATCH.md)를 참고하세요.

이번 `main` 빌드는 NSO 파일 끝에 데이터를 덧붙이거나 텍스트/데이터 오프셋을 이동하지 않습니다. 원본의 검증된 0-fill 영역에 긴 문자열을 배치하고 `.data`의 정적 포인터만 해당 영역으로 바꿉니다. 이 방식은 에뮬레이터에서만 동작하고 실기에서 종료되는 문제를 피하기 위한 것입니다.

빌드 결과 요약:

- 파일 크기: `97,643,010`바이트(원본과 동일)
- 제자리 문자열: `219,016`
- 0-fill 풀에 배치한 완전한 긴 문자열: `16,621`
- 직접 코드 참조 등으로 안전하게 건너뛴 항목: `820`
- 정적 포인터 재작성: `23,313`곳
- RDB: 원본 파일 크기 유지, 안전한 제자리 교체만 적용

## 주의사항

- 글자가 이미지에 구워진 일부 텍스트와 동적 조합 대사는 번역 대상에서 제외될 수 있습니다.
- 원본 폰트의 슬롯·폭을 유지하므로 일부 긴 문장은 일본어 원문과 같은 폭 제약을 받습니다.
- 실기에서 아직 확인되지 않은 메뉴가 있을 수 있습니다. 문제가 생기면 모드 폴더를 제거하고 원본 백업으로 복구하세요.
- Konami의 저작권이 있는 게임 데이터는 배포하지 않습니다. 정품에서 직접 덤프한 파일을 사용하세요.
