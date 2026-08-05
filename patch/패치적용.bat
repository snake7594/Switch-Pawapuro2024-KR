@echo off
setlocal
title Pawa2024 KR patch v2.0

echo ============================================================
echo  실황 파워풀 프로야구 2024-2025 (Switch) 한글패치 v2.0
echo ============================================================
echo.
echo  [준비] 아래 원본 파일 4개를 이 폴더에 두세요:
echo    main        (ExeFS에서 덤프)
echo    RES00.RDB   (RomFS의 cdvdroot 폴더)
echo    RES00.RDI   (RomFS의 cdvdroot 폴더)
echo    RES10.RDB   (RomFS의 cdvdroot 폴더)
echo  * 게임 업데이트 v1.15.0 을 적용한 상태로 덤프해야 합니다.
echo    (구 v1.8.0 덤프는 이 패치와 호환되지 않습니다)
echo.

set TID=0100d1c01c194000
set OUT=mods\%TID%

if not exist "main"      goto :missing
if not exist "RES00.RDB" goto :missing
if not exist "RES00.RDI" goto :missing
if not exist "RES10.RDB" goto :missing

if not exist "%OUT%\ExeFS" mkdir "%OUT%\ExeFS"
if not exist "%OUT%\RomFS\cdvdroot" mkdir "%OUT%\RomFS\cdvdroot"

echo [1/4] main 패치 중...
.\xdelta3.exe -d -f -s "main" "Pawa2024KR_v2.0_main.xdelta" "%OUT%\ExeFS\main"
if errorlevel 1 goto :err

echo [2/4] RES00.RDI 패치 중...
.\xdelta3.exe -d -f -s "RES00.RDI" "Pawa2024KR_v2.0_RES00.RDI.xdelta" "%OUT%\RomFS\cdvdroot\RES00.RDI"
if errorlevel 1 goto :err

echo [3/4] RES10.RDB 패치 중...
.\xdelta3.exe -d -f -s "RES10.RDB" "Pawa2024KR_v2.0_RES10.RDB.xdelta" "%OUT%\RomFS\cdvdroot\RES10.RDB"
if errorlevel 1 goto :err

echo [4/4] RES00.RDB 패치 중... (6.6GB, 수 분 소요)
.\xdelta3.exe -B 268435456 -d -f -s "RES00.RDB" "Pawa2024KR_v2.0_RES00.RDB.xdelta" "%OUT%\RomFS\cdvdroot\RES00.RDB"
if errorlevel 1 goto :err

echo.
echo ============================================================
echo  완료! 생성된 mods 폴더를 적용하세요.
echo.
echo  [Ryujinx]  mods\%TID% 폴더를
echo     Ryujinx의 mods\contents\ 아래로 복사
echo     (게임 우클릭 - Open Mods Directory 로 정확한 위치)
echo.
echo  [Switch 실기(Atmosphere)]  폴더명 소문자로 바꿔 SD카드에 복사:
echo     atmosphere\contents\%TID%\exefs\main
echo     atmosphere\contents\%TID%\romfs\cdvdroot\RES00.RDB (RDI, RES10 포함)
echo     (ExeFS는 exefs, RomFS는 romfs 소문자 폴더명 주의)
echo ============================================================
pause
exit /b 0

:missing
echo [오류] 원본 파일(main / RES00.RDB / RES00.RDI / RES10.RDB)이 부족합니다.
echo        위 안내를 확인해 4개 파일을 이 폴더에 두고 다시 실행하세요.
pause
exit /b 1

:err
echo.
echo [오류] 패치 적용 실패 - 원본 파일이 올바른 버전인지 확인하세요.
echo        (게임 업데이트 v1.15.0 적용 덤프여야 합니다)
pause
exit /b 1
