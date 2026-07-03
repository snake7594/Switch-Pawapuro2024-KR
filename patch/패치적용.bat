@echo off
chcp 65001 >nul
setlocal
title 실황 파워풀 프로야구 2024-2025 한글패치 적용

echo ============================================================
echo  실황 파워풀 프로야구 2024-2025 (Switch) 한글패치 적용
echo ============================================================
echo.
echo  [준비물] 본인이 덤프한 원본 파일 4개를 이 폴더에 두세요:
echo    main        (ExeFS에서 추출)
echo    RES00.RDB   (RomFS의 cdvdroot 폴더)
echo    RES00.RDI   (RomFS의 cdvdroot 폴더)
echo    RES10.RDB   (RomFS의 cdvdroot 폴더)
echo  * 게임 업데이트(2024-2025 최신)를 적용한 상태로 덤프해야 합니다.
echo.

set TID=0100d1c01c194000
set OUT=mods\%TID%

for %%F in (main RES00.RDB RES00.RDI RES10.RDB) do (
    if not exist "%%F" (
        echo [오류] 원본 파일 %%F 가 없습니다. 위 안내를 확인하세요.
        pause
        exit /b 1
    )
)

mkdir "%OUT%\ExeFS" 2>nul
mkdir "%OUT%\RomFS\cdvdroot" 2>nul

echo [1/4] main 패치 중...
xdelta3.exe -d -f -s "main" "Pawa2024KR_v1.0_main.xdelta" "%OUT%\ExeFS\main" || goto :err
echo [2/4] RES00.RDI 패치 중...
xdelta3.exe -d -f -s "RES00.RDI" "Pawa2024KR_v1.0_RES00.RDI.xdelta" "%OUT%\RomFS\cdvdroot\RES00.RDI" || goto :err
echo [3/4] RES10.RDB 패치 중...
xdelta3.exe -d -f -s "RES10.RDB" "Pawa2024KR_v1.0_RES10.RDB.xdelta" "%OUT%\RomFS\cdvdroot\RES10.RDB" || goto :err
echo [4/4] RES00.RDB 패치 중... (6.6GB, 수 분 소요)
xdelta3.exe -B 268435456 -d -f -s "RES00.RDB" "Pawa2024KR_v1.0_RES00.RDB.xdelta" "%OUT%\RomFS\cdvdroot\RES00.RDB" || goto :err

echo.
echo ============================================================
echo  완료! 생성된 mods 폴더를 사용하세요.
echo.
echo  [Ryujinx]  mods\%TID% 폴더를
echo     Ryujinx의 mods\contents\ 아래에 복사
echo     (우클릭 게임 - Open Mods Directory 로 열리는 위치)
echo.
echo  [Switch 실기(Atmosphere)]  구조를 다음으로 바꿔 SD카드에 복사:
echo     atmosphere\contents\%TID%\exefs\main
echo     atmosphere\contents\%TID%\romfs\cdvdroot\RES00.RDB (RDI, RES10 동일)
echo     (ExeFS→exefs, RomFS→romfs 소문자 폴더명 주의)
echo ============================================================
pause
exit /b 0

:err
echo.
echo [오류] 패치 적용 실패 — 원본 파일이 올바른 버전인지 확인하세요.
pause
exit /b 1
