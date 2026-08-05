# 2026–2027 v1.1.0 패치 가이드

## 원본 요구사항

이 릴리즈는 타이틀 ID `01007e8023f36000`의 게임 업데이트 **v1.1.0**을 기준으로 만들었습니다. 다음 파일은 반드시 같은 업데이트에서 추출해야 합니다.

| 파일 | 위치 | 패치 결과 SHA-256 |
|---|---|---|
| `main` | ExeFS | `4cb0ef73932d003cd8d1f2d4596a8645840e8c252c1b4436f102bf7f56b909bb` |
| `RES00.RDB` | RomFS/cdvdroot | `111f439e8fc16f3a3458fbf6ee635155a75e944ee8db0c24edb601d9182fbf55` |
| `RES00.RDI` | RomFS/cdvdroot | `ef7dba93d9bccb166a4152cd952a0e72a8fc7af6787300eef1d3bcb14ccee16b` |
| `RES10.RDB` | RomFS/cdvdroot | `9ec8c38e8ce5c7c128df1c1ed853d171c8233e83b0174aa890091225b3a163d6` |

패치 후에는 다음 명령으로 결과를 확인할 수 있습니다.

```powershell
Get-FileHash .\out\main -Algorithm SHA256
Get-FileHash .\out\RES00.RDB -Algorithm SHA256
Get-FileHash .\out\RES00.RDI -Algorithm SHA256
Get-FileHash .\out\RES10.RDB -Algorithm SHA256
```

## xdelta 적용

릴리즈의 `xdelta3` 또는 배포판 패키지를 사용합니다. `RES00.RDB`는 7GB가 넘으므로 여유 공간을 충분히 확보하고 `-B 268435456`를 지정하는 것을 권장합니다.

```powershell
New-Item -ItemType Directory -Force .\out | Out-Null
xdelta3 -B 268435456 -d -f -s .\main .\Pawapuro2026-1.1.0-main.xdelta .\out\main
xdelta3 -B 268435456 -d -f -s .\RES00.RDB .\Pawapuro2026-1.1.0-RES00.RDB.xdelta .\out\RES00.RDB
xdelta3 -B 268435456 -d -f -s .\RES00.RDI .\Pawapuro2026-1.1.0-RES00.RDI.xdelta .\out\RES00.RDI
xdelta3 -B 268435456 -d -f -s .\RES10.RDB .\Pawapuro2026-1.1.0-RES10.RDB.xdelta .\out\RES10.RDB
```

입력 파일의 SHA-256이 릴리즈 노트의 원본 해시와 다르면 적용을 중단해야 합니다. 다른 업데이트에 억지로 적용하지 마세요.

## 모드 설치

Atmosphère SD 카드:

```text
/atmosphere/contents/01007e8023f36000/exefs/main
/atmosphere/contents/01007e8023f36000/romfs/cdvdroot/RES00.RDB
/atmosphere/contents/01007e8023f36000/romfs/cdvdroot/RES00.RDI
/atmosphere/contents/01007e8023f36000/romfs/cdvdroot/RES10.RDB
```

Ryujinx/Eden도 타이틀 ID 아래에서 `exefs`와 `romfs/cdvdroot`를 같은 대소문자로 유지하면 됩니다. 기존 모드는 제거하거나 이름을 바꿔 충돌을 피하세요.

## 실패 시 복구

게임이 시작 직후 종료되면 모드 디렉터리의 `main`을 먼저 제거하고 실행 여부를 확인합니다. 이후 네 파일을 모두 원본으로 되돌리면 패치 전 상태로 복구됩니다. 세이브 데이터에는 손대지 않습니다.
