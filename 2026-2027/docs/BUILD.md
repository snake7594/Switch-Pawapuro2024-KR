# 2026–2027 v1.1.0 빌드 메모

## 입력 자료

릴리즈의 `source.zip`에는 다음을 제외한 번역 작업 자료가 들어 있습니다.

- 원본 게임의 `main`, RDB/RDI, 동영상·음원 등 저작권 데이터
- 수십 GB에 달하는 임시 덤프와 반복 생성물

원본 4개는 작업 디렉터리에서만 사용합니다.

```text
workspace/
  exefs/main
  romfs/cdvdroot/RES00.RDB
  romfs/cdvdroot/RES00.RDI
  romfs/cdvdroot/RES10.RDB
  data/main_strings_ja.json
  data/main_strings_ko_menu_compact_patch.json
  data/sjis_hangul_map.json
```

Python 3.10 이상과 표준 라이브러리를 기준으로 하며, 일부 분석 도구는 `numpy`를 선택적으로 사용합니다.

## main 안전 빌드

핵심 스크립트는 `tools/main_patch/patch_main_hardware_safe_pool.py`입니다. 스크립트는 다음을 검사한 뒤 출력합니다.

1. NSO 헤더·텍스트 영역과 파일 크기를 원본과 비교
2. 읽기 전용 영역에서 연속 0-fill 풀을 찾아 문자열을 배치
3. `.data`의 정적 64비트 포인터만 새 문자열 주소로 교체
4. 동적 RELA/JMPREL 재배치 대상과 겹치는 포인터는 건너뜀
5. 모든 재작성 포인터가 실제 UTF-8 문자열을 가리키는지 재검증

기본 사용 예:

```powershell
python tools/main_patch/patch_main_hardware_safe_pool.py `
  --main exefs/main `
  --json data/main_strings_ko_menu_compact_patch.json `
  --out build/main
```

실제 릴리즈 빌드에 사용한 옵션과 통계는 `reports/main_hw_safe_pool_data.report.json`에 기록되어 있습니다. 릴리즈 결과는 원본과 동일한 `97,643,010`바이트입니다.

## RDB 안전 빌드

`tools/rdb/`의 RDB 도구는 `RES00.RDI`의 슬롯과 압축 본문을 확인한 뒤 기존 슬롯 안에 들어가는 CHK만 제자리 교체합니다. 재배치가 필요한 슬롯은 RDI/포인터를 깨뜨리지 않도록 원본을 유지합니다. 폰트는 `data/font/COMMON_FONT.CHK`와 `data/font/hangul_to_hanja_2350.tsv`를 기준으로 만들었습니다.

RDB 결과는 다음 조건을 지킵니다.

- `RES00.RDB`: `7,573,791,232`바이트
- `RES00.RDI`: `469,504`바이트
- `RES10.RDB`: `178,927,104`바이트
- RDI 파일과 슬롯 수 변경 없음
- 재배치가 필요한 슬롯 `5,188`개는 원본 유지

## 재현 및 검증

생성 후 결과 파일의 크기·SHA-256을 `docs/PATCH.md` 표와 비교합니다. `main`은 NSO 헤더와 `.text`가 동일해야 하며, RDB는 슬롯 헤더·압축 해제 크기·RDI 인덱스가 원본 규칙을 따라야 합니다.

릴리즈의 `source.zip`에는 번역 원문/번역문 JSON, 메뉴 분류 정보, SJIS 한글 매핑, 폰트 소스와 생성 도구가 들어 있으므로 중간 검토와 재빌드에 사용할 수 있습니다.
